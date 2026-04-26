from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Iterable

from transdssat.domain import Trajectory
from transdssat.environments.adapters import OfficialDSSATEnvironment
from transdssat.policy import IRRIGATION_BINS, NITROGEN_BINS
from transdssat.scenarios import STAGES, SimulationScenario, stage_for_day
from transdssat.season import SeasonPolicy, StageDecision, policy_date, rollout_proxy_policy, stage_start_days


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
    from torch.distributions import Categorical

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
            self.irrigation_head = nn.Linear(hidden_dim, len(IRRIGATION_BINS))
            self.nitrogen_head = nn.Linear(hidden_dim, len(NITROGEN_BINS))

        def forward(
            self,
            x: torch.Tensor,
            stage_indices: torch.Tensor,
            padding_mask: torch.Tensor | None = None,
        ) -> tuple[torch.Tensor, torch.Tensor]:
            hidden = self.input_projection(x)
            encoded = self.encoder(hidden, src_key_padding_mask=padding_mask)
            gather_index = stage_indices.unsqueeze(-1).expand(-1, -1, encoded.size(-1))
            stage_hidden = torch.gather(encoded, 1, gather_index)
            stage_hidden = self.norm(stage_hidden)
            return self.irrigation_head(stage_hidden), self.nitrogen_head(stage_hidden)

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


def build_policy_from_bin_actions(
    scenario: SimulationScenario,
    irrigation_bins: Iterable[int],
    nitrogen_bins: Iterable[int],
) -> SeasonPolicy:
    starts = stage_indices_for_scenario(scenario)
    irrigation_indices = list(irrigation_bins)
    nitrogen_indices = list(nitrogen_bins)
    actions: list[StageDecision] = []
    for index, stage in enumerate(STAGES):
        irrigation_mm = IRRIGATION_BINS[int(irrigation_indices[index])]
        nitrogen_kg_ha = NITROGEN_BINS[int(nitrogen_indices[index])]
        day_index = starts[index]
        actions.append(
            StageDecision(
                stage=stage,
                day_index=day_index,
                date=policy_date(scenario.planting_date, day_index),
                irrigation_mm=irrigation_mm,
                nitrogen_kg_ha=nitrogen_kg_ha,
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


def sample_policies(
    model: "SeasonRLTransformer",
    scenarios: list[SimulationScenario],
    greedy: bool = False,
) -> list[SampledSeasonPolicy]:
    if not TORCH_AVAILABLE:
        raise RuntimeError("PyTorch is required to sample RL policies.")
    import torch

    features, padding_mask, stage_indices = collate_scenarios_for_rl(scenarios)
    irrigation_logits, nitrogen_logits = model(features, stage_indices, padding_mask=padding_mask)
    sampled: list[SampledSeasonPolicy] = []

    for row_index, scenario in enumerate(scenarios):
        irrigation_dist = Categorical(logits=irrigation_logits[row_index])
        nitrogen_dist = Categorical(logits=nitrogen_logits[row_index])

        if greedy:
            irrigation_actions = irrigation_logits[row_index].argmax(dim=1)
            nitrogen_actions = nitrogen_logits[row_index].argmax(dim=1)
            log_prob = irrigation_dist.log_prob(irrigation_actions).sum() + nitrogen_dist.log_prob(nitrogen_actions).sum()
        else:
            irrigation_actions = irrigation_dist.sample()
            nitrogen_actions = nitrogen_dist.sample()
            log_prob = irrigation_dist.log_prob(irrigation_actions).sum() + nitrogen_dist.log_prob(nitrogen_actions).sum()

        entropy = irrigation_dist.entropy().sum() + nitrogen_dist.entropy().sum()
        policy = build_policy_from_bin_actions(
            scenario,
            irrigation_actions.tolist(),
            nitrogen_actions.tolist(),
        )
        sampled.append(SampledSeasonPolicy(policy=policy, log_prob=log_prob, entropy=entropy))

    return sampled
