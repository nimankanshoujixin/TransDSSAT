from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Iterable

from transdssat.domain import Trajectory
from transdssat.environments.adapters import OfficialDSSATEnvironment
from transdssat.scenarios import STAGES, SimulationScenario, stage_for_day
from transdssat.season import (
    CONTROL_MODES,
    DECISION_GRANULARITIES,
    SeasonPolicy,
    StageDecision,
    apply_control_mode,
    policy_date,
    rollout_proxy_policy,
    stage_start_days,
)

STAGE_ACTION_MASKS = {
    "wheat": {
        "irrigation": (0.0, 1.0, 1.0, 0.0),
        "nitrogen": (1.0, 1.0, 1.0, 0.0),
    },
    "maize": {
        "irrigation": (1.0, 1.0, 1.0, 0.0),
        "nitrogen": (1.0, 1.0, 1.0, 0.0),
    },
}


def evaluate_policy_for_scenario(scenario: SimulationScenario, policy: SeasonPolicy) -> Trajectory:
    if scenario.engine_name == "dssat_official":
        return OfficialDSSATEnvironment().evaluate_policy(scenario, policy).trajectory
    return rollout_proxy_policy(scenario, policy)


def encode_scenario_day(scenario: SimulationScenario, day_index: int) -> list[float]:
    weather = scenario.weather[min(day_index, len(scenario.weather) - 1)]
    stage, stage_index = stage_for_day(day_index, scenario.crop_spec.season_length_days)
    soil = scenario.soil_profile
    crop_indicator = 1.0 if scenario.crop_spec.crop_name == "maize" else 0.0
    return [
        day_index / max(1.0, scenario.crop_spec.season_length_days - 1),
        stage_index / max(1.0, len(STAGES) - 1),
        weather.tmean_c / 40.0,
        weather.precipitation_mm / 60.0,
        weather.et0_mm / 12.0,
        weather.radiation_mj_m2 / 30.0,
        soil.field_capacity_mm / 400.0,
        soil.wilting_point_mm / 200.0,
        soil.initial_root_zone_water_mm / 400.0,
        soil.initial_nitrogen_kg_ha / 300.0,
        scenario.irrigation_budget_mm / 300.0,
        scenario.nitrogen_budget_kg_ha / 300.0,
        crop_indicator,
    ]


def encode_scenario_sequence(scenario: SimulationScenario) -> list[list[float]]:
    return [encode_scenario_day(scenario, day_index) for day_index in range(scenario.crop_spec.season_length_days)]


def stage_indices_for_scenario(scenario: SimulationScenario) -> list[int]:
    starts = stage_start_days(scenario.crop_spec.season_length_days)
    return [starts[stage] for stage in STAGES]


try:
    import torch
    from torch import nn
    from torch.distributions import Dirichlet

    TORCH_AVAILABLE = True

    class SeasonRLTransformer(nn.Module):
        def __init__(
            self,
            input_dim: int = 13,
            hidden_dim: int = 128,
            num_heads: int = 4,
            num_layers: int = 3,
        ) -> None:
            super().__init__()
            self.input_projection = nn.Linear(input_dim, hidden_dim)
            encoder_layer = nn.TransformerEncoderLayer(
                d_model=hidden_dim,
                nhead=num_heads,
                batch_first=True,
                dim_feedforward=hidden_dim * 4,
                dropout=0.1,
                activation="gelu",
            )
            self.encoder = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)
            self.norm = nn.LayerNorm(hidden_dim)
            self.irrigation_head = nn.Linear(hidden_dim, 1)
            self.nitrogen_head = nn.Linear(hidden_dim, 1)

        def forward(
            self,
            x: torch.Tensor,
            stage_indices: torch.Tensor | None = None,
            padding_mask: torch.Tensor | None = None,
            decision_granularity: str = "stage",
        ) -> tuple[torch.Tensor, torch.Tensor]:
            hidden = self.input_projection(x)
            encoded = self.encoder(hidden, src_key_padding_mask=padding_mask)
            if decision_granularity == "stage":
                if stage_indices is None:
                    raise RuntimeError("Stage indices are required for stage-level decision granularity.")
                gather_index = stage_indices.unsqueeze(-1).expand(-1, -1, encoded.size(-1))
                decision_hidden = torch.gather(encoded, 1, gather_index)
            elif decision_granularity == "daily":
                decision_hidden = encoded
            else:
                raise ValueError(f"Unsupported decision granularity: {decision_granularity}")
            decision_hidden = self.norm(decision_hidden)
            irrigation_concentration = torch.nn.functional.softplus(self.irrigation_head(decision_hidden).squeeze(-1)) + 0.2
            nitrogen_concentration = torch.nn.functional.softplus(self.nitrogen_head(decision_hidden).squeeze(-1)) + 0.2
            return irrigation_concentration, nitrogen_concentration

except ImportError:  # pragma: no cover - optional locally
    TORCH_AVAILABLE = False
    SeasonRLTransformer = None


@dataclass(slots=True)
class SampledSeasonPolicy:
    policy: SeasonPolicy
    log_prob: "torch.Tensor"
    entropy: "torch.Tensor"


def collate_scenarios_for_rl(
    scenarios: list[SimulationScenario],
) -> tuple["torch.Tensor", "torch.Tensor", "torch.Tensor"]:
    if not TORCH_AVAILABLE:
        raise RuntimeError("PyTorch is required for RL policy batching.")
    import torch

    max_len = max(scenario.crop_spec.season_length_days for scenario in scenarios)
    feature_dim = len(encode_scenario_sequence(scenarios[0])[0])
    features = torch.zeros((len(scenarios), max_len, feature_dim), dtype=torch.float32)
    padding_mask = torch.ones((len(scenarios), max_len), dtype=torch.bool)
    stage_indices = torch.zeros((len(scenarios), len(STAGES)), dtype=torch.long)

    for row_index, scenario in enumerate(scenarios):
        sequence = torch.tensor(encode_scenario_sequence(scenario), dtype=torch.float32)
        length = sequence.size(0)
        features[row_index, :length, :] = sequence
        padding_mask[row_index, :length] = False
        stage_indices[row_index, :] = torch.tensor(stage_indices_for_scenario(scenario), dtype=torch.long)

    return features, padding_mask, stage_indices


def build_policy_from_allocations(
    scenario: SimulationScenario,
    irrigation_shares: Iterable[float],
    nitrogen_shares: Iterable[float],
) -> SeasonPolicy:
    starts = stage_indices_for_scenario(scenario)
    crop_masks = STAGE_ACTION_MASKS[scenario.crop_spec.crop_name]
    irrigation_weights = [
        share * mask
        for share, mask in zip(irrigation_shares, crop_masks["irrigation"])
    ]
    nitrogen_weights = [
        share * mask
        for share, mask in zip(nitrogen_shares, crop_masks["nitrogen"])
    ]
    irrigation_sum = sum(irrigation_weights)
    nitrogen_sum = sum(nitrogen_weights)
    if irrigation_sum <= 1e-9:
        irrigation_weights = list(crop_masks["irrigation"])
        irrigation_sum = sum(irrigation_weights)
    if nitrogen_sum <= 1e-9:
        nitrogen_weights = list(crop_masks["nitrogen"])
        nitrogen_sum = sum(nitrogen_weights)
    irrigation_weights = [weight / irrigation_sum for weight in irrigation_weights]
    nitrogen_weights = [weight / nitrogen_sum for weight in nitrogen_weights]
    irrigation_total = max(0.0, scenario.irrigation_budget_mm)
    nitrogen_total = max(0.0, scenario.nitrogen_budget_kg_ha)
    actions: list[StageDecision] = []
    for index, stage in enumerate(STAGES):
        if index == len(STAGES) - 1:
            irrigation_mm = round(
                irrigation_total - sum(action.irrigation_mm for action in actions),
                3,
            )
            nitrogen_kg_ha = round(
                nitrogen_total - sum(action.nitrogen_kg_ha for action in actions),
                3,
            )
        else:
            irrigation_mm = round(irrigation_total * max(0.0, irrigation_weights[index]), 3)
            nitrogen_kg_ha = round(nitrogen_total * max(0.0, nitrogen_weights[index]), 3)
        day_index = starts[index]
        actions.append(
            StageDecision(
                stage=stage,
                day_index=day_index,
                date=policy_date(scenario.planting_date, day_index),
                irrigation_mm=max(0.0, irrigation_mm),
                nitrogen_kg_ha=max(0.0, nitrogen_kg_ha),
            )
        )

    policy_hash = hashlib.sha256(
        "|".join(
            f"{action.stage}:{action.day_index}:{action.irrigation_mm}:{action.nitrogen_kg_ha}"
            for action in actions
        ).encode("utf-8")
    ).hexdigest()[:10]
    return SeasonPolicy(
        policy_id=f"{scenario.scenario_id}-rl-{policy_hash}",
        scenario_id=scenario.scenario_id,
        actions=actions,
    )


def _sparsify_daily_allocations(total: float, shares: list[float], min_event_amount: float) -> list[float]:
    if total <= 0.0:
        return [0.0 for _ in shares]
    raw_amounts = [max(0.0, total * share) for share in shares]
    keep = [index for index, amount in enumerate(raw_amounts) if amount >= min_event_amount]
    if not keep:
        keep = [max(range(len(raw_amounts)), key=lambda idx: raw_amounts[idx])]
    kept_total = sum(raw_amounts[index] for index in keep)
    scale = total / max(1e-6, kept_total)
    allocations = [0.0 for _ in shares]
    running = 0.0
    for keep_index, day_index in enumerate(keep):
        if keep_index == len(keep) - 1:
            value = round(total - running, 3)
        else:
            value = round(raw_amounts[day_index] * scale, 3)
            running += value
        allocations[day_index] = max(0.0, value)
    return allocations


def build_daily_policy_from_allocations(
    scenario: SimulationScenario,
    irrigation_shares: Iterable[float],
    nitrogen_shares: Iterable[float],
    irrigation_min_event_mm: float = 1.0,
    nitrogen_min_event_kg_ha: float = 1.0,
) -> SeasonPolicy:
    irrigation_allocations = _sparsify_daily_allocations(
        scenario.irrigation_budget_mm,
        list(irrigation_shares),
        min_event_amount=irrigation_min_event_mm,
    )
    nitrogen_allocations = _sparsify_daily_allocations(
        scenario.nitrogen_budget_kg_ha,
        list(nitrogen_shares),
        min_event_amount=nitrogen_min_event_kg_ha,
    )
    actions: list[StageDecision] = []
    for day_index, (irrigation_mm, nitrogen_kg_ha) in enumerate(zip(irrigation_allocations, nitrogen_allocations)):
        if irrigation_mm <= 0.0 and nitrogen_kg_ha <= 0.0:
            continue
        stage, _ = stage_for_day(day_index, scenario.crop_spec.season_length_days)
        actions.append(
            StageDecision(
                stage=stage,
                day_index=day_index,
                date=policy_date(scenario.planting_date, day_index),
                irrigation_mm=round(irrigation_mm, 3),
                nitrogen_kg_ha=round(nitrogen_kg_ha, 3),
            )
        )

    policy_hash = hashlib.sha256(
        "|".join(
            f"{action.stage}:{action.day_index}:{action.irrigation_mm}:{action.nitrogen_kg_ha}"
            for action in actions
        ).encode("utf-8")
    ).hexdigest()[:10]
    return SeasonPolicy(
        policy_id=f"{scenario.scenario_id}-rl-daily-{policy_hash}",
        scenario_id=scenario.scenario_id,
        actions=actions,
    )


def sample_policies(
    model: "SeasonRLTransformer",
    scenarios: list[SimulationScenario],
    greedy: bool = False,
    decision_granularity: str = "stage",
    control_mode: str = "joint",
    reference_policies: list[SeasonPolicy] | None = None,
) -> list[SampledSeasonPolicy]:
    if not TORCH_AVAILABLE:
        raise RuntimeError("PyTorch is required to sample RL policies.")
    if decision_granularity not in DECISION_GRANULARITIES:
        raise ValueError(f"Unsupported decision granularity: {decision_granularity}")
    if control_mode not in CONTROL_MODES:
        raise ValueError(f"Unsupported control mode: {control_mode}")
    if control_mode != "joint" and reference_policies is None:
        raise RuntimeError("Reference policies are required for water_only or nitrogen_only control modes.")
    import torch

    features, padding_mask, stage_indices = collate_scenarios_for_rl(scenarios)
    model_stage_indices = stage_indices if decision_granularity == "stage" else None
    irrigation_concentration, nitrogen_concentration = model(
        features,
        model_stage_indices,
        padding_mask=padding_mask,
        decision_granularity=decision_granularity,
    )
    sampled: list[SampledSeasonPolicy] = []

    for row_index, scenario in enumerate(scenarios):
        if decision_granularity == "stage":
            irrigation_alpha = irrigation_concentration[row_index]
            nitrogen_alpha = nitrogen_concentration[row_index]
        else:
            valid_length = scenario.crop_spec.season_length_days
            irrigation_alpha = irrigation_concentration[row_index, :valid_length]
            nitrogen_alpha = nitrogen_concentration[row_index, :valid_length]

        irrigation_dist = Dirichlet(irrigation_alpha)
        nitrogen_dist = Dirichlet(nitrogen_alpha)

        if greedy:
            irrigation_actions = irrigation_alpha / irrigation_alpha.sum()
            nitrogen_actions = nitrogen_alpha / nitrogen_alpha.sum()
            log_prob = irrigation_dist.log_prob(irrigation_actions) + nitrogen_dist.log_prob(nitrogen_actions)
        else:
            irrigation_actions = irrigation_dist.sample()
            nitrogen_actions = nitrogen_dist.sample()
            log_prob = irrigation_dist.log_prob(irrigation_actions) + nitrogen_dist.log_prob(nitrogen_actions)

        entropy = irrigation_dist.entropy() + nitrogen_dist.entropy()
        if decision_granularity == "daily":
            policy = build_daily_policy_from_allocations(
                scenario,
                irrigation_actions.tolist(),
                nitrogen_actions.tolist(),
            )
        else:
            policy = build_policy_from_allocations(
                scenario,
                irrigation_actions.tolist(),
                nitrogen_actions.tolist(),
            )
        if control_mode != "joint":
            policy = apply_control_mode(policy, reference_policies[row_index], control_mode=control_mode)
        sampled.append(SampledSeasonPolicy(policy=policy, log_prob=log_prob, entropy=entropy))

    return sampled
