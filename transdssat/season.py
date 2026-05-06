from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
import hashlib
from typing import Iterable

from transdssat.domain import CropAction, Trajectory, TrajectoryStep
from transdssat.environments import make_environment
from transdssat.rewarding import RewardWeights, reward_from_outcome
from transdssat.scenarios import STAGES, SimulationScenario, stage_for_day


HEURISTIC_STAGE_BUDGET_SPLITS = {
    "balanced": {
        "emergence": (0.18, 0.20),
        "vegetative": (0.30, 0.38),
        "reproductive": (0.34, 0.30),
        "grain_fill": (0.18, 0.12),
    },
    "reproductive_focus": {
        "emergence": (0.12, 0.16),
        "vegetative": (0.23, 0.32),
        "reproductive": (0.43, 0.36),
        "grain_fill": (0.22, 0.16),
    },
    "vegetative_focus": {
        "emergence": (0.15, 0.18),
        "vegetative": (0.40, 0.42),
        "reproductive": (0.27, 0.26),
        "grain_fill": (0.18, 0.14),
    },
}

BASELINE_NAMES = ("heuristic", "literature_ncp")
BASELINE_BUDGET_SOURCES = ("scenario", "paper")
CONTROL_MODES = ("joint", "water_only", "nitrogen_only")
DECISION_GRANULARITIES = ("stage", "daily")

LITERATURE_OPTIMAL_TOTALS = {
    "wheat": (165.0, 186.0),
    "maize": (90.0, 185.0),
}

LITERATURE_STAGE_SPLITS = {
    "wheat": {
        "emergence": (0.00, 0.40),
        "vegetative": (0.50, 0.30),
        "reproductive": (0.50, 0.30),
        "grain_fill": (0.00, 0.00),
    },
    "maize": {
        "emergence": (0.34, 0.60),
        "vegetative": (0.33, 0.20),
        "reproductive": (0.33, 0.20),
        "grain_fill": (0.00, 0.00),
    },
}

LITERATURE_EVENT_PLAN = {
    "wheat": (
        ("emergence", 0.00, 0.00, 0.20),
        ("emergence", 0.08, 0.00, 0.15),
        ("vegetative", 0.18, 0.00, 0.15),
        ("vegetative", 0.28, 0.34, 0.15),
        ("vegetative", 0.56, 0.33, 0.15),
        ("reproductive", 0.70, 0.33, 0.10),
        ("reproductive", 0.80, 0.00, 0.10),
    ),
    "maize": (
        ("emergence", 0.00, 0.00, 0.40),
        ("emergence", 0.10, 1.0 / 3.0, 0.20),
        ("vegetative", 0.42, 1.0 / 3.0, 0.20),
        ("reproductive", 0.72, 1.0 / 3.0, 0.20),
    ),
}


@dataclass(slots=True)
class StageDecision:
    stage: str
    day_index: int
    date: str
    irrigation_mm: float
    nitrogen_kg_ha: float

    def to_dict(self) -> dict:
        return {
            "stage": self.stage,
            "day_index": self.day_index,
            "date": self.date,
            "irrigation_mm": self.irrigation_mm,
            "nitrogen_kg_ha": self.nitrogen_kg_ha,
        }


@dataclass(slots=True)
class SeasonPolicy:
    policy_id: str
    scenario_id: str
    actions: list[StageDecision]

    @property
    def total_irrigation_mm(self) -> float:
        return round(sum(action.irrigation_mm for action in self.actions), 3)

    @property
    def total_nitrogen_kg_ha(self) -> float:
        return round(sum(action.nitrogen_kg_ha for action in self.actions), 3)

    def action_map(self) -> dict[int, CropAction]:
        return {
            action.day_index: CropAction(
                irrigation_mm=action.irrigation_mm,
                nitrogen_kg_ha=action.nitrogen_kg_ha,
            )
            for action in self.actions
        }

    def to_dict(self) -> dict:
        return {
            "policy_id": self.policy_id,
            "scenario_id": self.scenario_id,
            "actions": [action.to_dict() for action in self.actions],
            "total_irrigation_mm": self.total_irrigation_mm,
            "total_nitrogen_kg_ha": self.total_nitrogen_kg_ha,
        }


def stage_start_days(season_length_days: int) -> dict[str, int]:
    starts: dict[str, int] = {}
    seen: set[str] = set()
    for day_index in range(season_length_days):
        stage, _ = stage_for_day(day_index, season_length_days)
        if stage not in seen:
            starts[stage] = day_index
            seen.add(stage)
    return starts


def policy_date(planting_date: str, day_index: int) -> str:
    planting = date.fromisoformat(planting_date)
    return (planting + timedelta(days=day_index)).isoformat()


def _allocate_stage_totals(total: float, fractions: list[float]) -> list[float]:
    allocations: list[float] = []
    used = 0.0
    for index, fraction in enumerate(fractions):
        if index == len(fractions) - 1:
            value = round(total - used, 3)
        else:
            value = round(total * fraction, 3)
            used += value
        allocations.append(max(0.0, value))
    return allocations


def _build_policy(actions: list[StageDecision], scenario_id: str, suffix: str = "") -> SeasonPolicy:
    policy_hash = hashlib.sha256(
        "|".join(
            f"{action.stage}:{action.day_index}:{action.irrigation_mm}:{action.nitrogen_kg_ha}"
            for action in actions
        ).encode("utf-8")
    ).hexdigest()[:10]
    name_suffix = f"-{suffix}" if suffix else ""
    return SeasonPolicy(
        policy_id=f"{scenario_id}{name_suffix}-{policy_hash}",
        scenario_id=scenario_id,
        actions=actions,
    )


def scenario_budget_targets(
    scenario: SimulationScenario,
    baseline_name: str,
    budget_source: str,
) -> tuple[float, float]:
    if baseline_name == "literature_ncp" and budget_source == "paper":
        return LITERATURE_OPTIMAL_TOTALS[scenario.crop_spec.crop_name]
    return scenario.irrigation_budget_mm, scenario.nitrogen_budget_kg_ha


def build_stage_split_policy(
    scenario: SimulationScenario,
    irrigation_splits: dict[str, float],
    nitrogen_splits: dict[str, float],
    total_irrigation_mm: float,
    total_nitrogen_kg_ha: float,
    suffix: str = "",
) -> SeasonPolicy:
    starts = stage_start_days(scenario.crop_spec.season_length_days)
    irrigation_allocations = _allocate_stage_totals(
        total_irrigation_mm,
        [irrigation_splits[stage] for stage in STAGES],
    )
    nitrogen_allocations = _allocate_stage_totals(
        total_nitrogen_kg_ha,
        [nitrogen_splits[stage] for stage in STAGES],
    )
    actions: list[StageDecision] = []
    for index, stage in enumerate(STAGES):
        day_index = starts[stage]
        actions.append(
            StageDecision(
                stage=stage,
                day_index=day_index,
                date=policy_date(scenario.planting_date, day_index),
                irrigation_mm=irrigation_allocations[index],
                nitrogen_kg_ha=nitrogen_allocations[index],
            )
        )
    return _build_policy(actions, scenario.scenario_id, suffix=suffix)


def _day_from_fraction(season_length_days: int, fraction: float) -> int:
    return max(0, min(season_length_days - 1, round((season_length_days - 1) * fraction)))


def _normalize_event_allocations(total: float, shares: Iterable[float]) -> list[float]:
    amounts = _allocate_stage_totals(total, list(shares))
    return [round(max(0.0, amount), 3) for amount in amounts]


def build_event_policy(
    scenario: SimulationScenario,
    event_plan: tuple[tuple[str, float, float, float], ...],
    total_irrigation_mm: float,
    total_nitrogen_kg_ha: float,
    suffix: str = "",
) -> SeasonPolicy:
    irrigation_allocations = _normalize_event_allocations(total_irrigation_mm, [event[2] for event in event_plan])
    nitrogen_allocations = _normalize_event_allocations(total_nitrogen_kg_ha, [event[3] for event in event_plan])
    actions: list[StageDecision] = []
    for index, (stage_name, fraction, _, _) in enumerate(event_plan):
        day_index = _day_from_fraction(scenario.crop_spec.season_length_days, fraction)
        actions.append(
            StageDecision(
                stage=stage_name,
                day_index=day_index,
                date=policy_date(scenario.planting_date, day_index),
                irrigation_mm=irrigation_allocations[index],
                nitrogen_kg_ha=nitrogen_allocations[index],
            )
        )
    return _build_policy(actions, scenario.scenario_id, suffix=suffix)


def build_baseline_policy(
    scenario: SimulationScenario,
    baseline_name: str = "heuristic",
    decision_granularity: str = "stage",
    budget_source: str = "scenario",
) -> SeasonPolicy:
    if baseline_name not in BASELINE_NAMES:
        raise ValueError(f"Unsupported baseline: {baseline_name}")
    if decision_granularity not in DECISION_GRANULARITIES:
        raise ValueError(f"Unsupported decision granularity: {decision_granularity}")
    if budget_source not in BASELINE_BUDGET_SOURCES:
        raise ValueError(f"Unsupported baseline budget source: {budget_source}")

    total_irrigation_mm, total_nitrogen_kg_ha = scenario_budget_targets(
        scenario,
        baseline_name=baseline_name,
        budget_source=budget_source,
    )
    if baseline_name == "heuristic":
        mode = HEURISTIC_STAGE_BUDGET_SPLITS[scenario.management_mode]
        return build_stage_split_policy(
            scenario,
            irrigation_splits={stage: mode[stage][0] for stage in STAGES},
            nitrogen_splits={stage: mode[stage][1] for stage in STAGES},
            total_irrigation_mm=total_irrigation_mm,
            total_nitrogen_kg_ha=total_nitrogen_kg_ha,
            suffix="heuristic",
        )

    crop_name = scenario.crop_spec.crop_name
    if decision_granularity == "daily":
        return build_event_policy(
            scenario,
            event_plan=LITERATURE_EVENT_PLAN[crop_name],
            total_irrigation_mm=total_irrigation_mm,
            total_nitrogen_kg_ha=total_nitrogen_kg_ha,
            suffix="literature",
        )
    mode = LITERATURE_STAGE_SPLITS[crop_name]
    return build_stage_split_policy(
        scenario,
        irrigation_splits={stage: mode[stage][0] for stage in STAGES},
        nitrogen_splits={stage: mode[stage][1] for stage in STAGES},
        total_irrigation_mm=total_irrigation_mm,
        total_nitrogen_kg_ha=total_nitrogen_kg_ha,
        suffix="literature",
    )


def apply_control_mode(
    candidate_policy: SeasonPolicy,
    reference_policy: SeasonPolicy,
    control_mode: str = "joint",
) -> SeasonPolicy:
    if control_mode not in CONTROL_MODES:
        raise ValueError(f"Unsupported control mode: {control_mode}")
    if control_mode == "joint":
        return candidate_policy

    candidate_map = {action.day_index: action for action in candidate_policy.actions}
    reference_map = {action.day_index: action for action in reference_policy.actions}
    union_days = sorted(set(candidate_map) | set(reference_map))
    actions: list[StageDecision] = []
    for day_index in union_days:
        candidate = candidate_map.get(day_index)
        reference = reference_map.get(day_index)
        anchor = candidate or reference
        if anchor is None:
            continue
        irrigation_mm = candidate.irrigation_mm if control_mode == "water_only" and candidate else 0.0
        nitrogen_kg_ha = candidate.nitrogen_kg_ha if control_mode == "nitrogen_only" and candidate else 0.0
        if reference is not None:
            if control_mode == "nitrogen_only":
                irrigation_mm = reference.irrigation_mm
            else:
                nitrogen_kg_ha = reference.nitrogen_kg_ha
        actions.append(
            StageDecision(
                stage=anchor.stage,
                day_index=anchor.day_index,
                date=anchor.date,
                irrigation_mm=round(irrigation_mm, 3),
                nitrogen_kg_ha=round(nitrogen_kg_ha, 3),
            )
        )
    return _build_policy(actions, candidate_policy.scenario_id, suffix=control_mode)


def rollout_proxy_policy(scenario: SimulationScenario, policy: SeasonPolicy) -> Trajectory:
    env = make_environment(scenario)
    steps: list[TrajectoryStep] = []
    action_map = policy.action_map()
    state = env.reset()

    while True:
        action = action_map.get(state.day_index, CropAction())
        next_state, reward, done, info = env.step(action)
        info["policy_id"] = policy.policy_id
        info["policy_stage_action"] = action.to_dict()
        steps.append(
            TrajectoryStep(
                state=state,
                action=action,
                reward=reward,
                next_state=next_state,
                done=done,
                info=info,
            )
        )
        state = next_state
        if done:
            break

    outcome = env.final_outcome()
    return Trajectory(
        scenario_id=scenario.scenario_id,
        engine_name=scenario.engine_name,
        crop_name=scenario.crop_spec.crop_name,
        weather_regime=scenario.weather_regime,
        management_mode=scenario.management_mode,
        steps=steps,
        outcome=outcome,
        policy=policy.to_dict(),
    )
