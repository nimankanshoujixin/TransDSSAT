from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
import hashlib

from transdssat.domain import CropAction, CropOutcome, Trajectory, TrajectoryStep
from transdssat.environments import make_environment
from transdssat.scenarios import STAGES, SimulationScenario, stage_for_day


STAGE_BUDGET_SPLITS = {
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


@dataclass(slots=True)
class RewardWeights:
    yield_weight: float = 0.003
    irrigation_cost: float = 0.010
    nitrogen_cost: float = 0.020
    water_stress_cost: float = 1.250
    nitrogen_stress_cost: float = 1.100
    biomass_gain_weight: float = 0.0025


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


def build_baseline_policy(scenario: SimulationScenario) -> SeasonPolicy:
    mode = STAGE_BUDGET_SPLITS[scenario.management_mode]
    starts = stage_start_days(scenario.crop_spec.season_length_days)
    irrigation_allocations = _allocate_stage_totals(
        scenario.irrigation_budget_mm,
        [mode[stage][0] for stage in STAGES],
    )
    nitrogen_allocations = _allocate_stage_totals(
        scenario.nitrogen_budget_kg_ha,
        [mode[stage][1] for stage in STAGES],
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

    policy_hash = hashlib.sha256(
        "|".join(
            f"{action.stage}:{action.day_index}:{action.irrigation_mm}:{action.nitrogen_kg_ha}"
            for action in actions
        ).encode("utf-8")
    ).hexdigest()[:10]
    return SeasonPolicy(
        policy_id=f"{scenario.scenario_id}-{policy_hash}",
        scenario_id=scenario.scenario_id,
        actions=actions,
    )


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


def reward_from_outcome(
    outcome: CropOutcome,
    avg_water_stress: float,
    avg_nitrogen_stress: float,
    weights: RewardWeights | None = None,
) -> float:
    weights = weights or RewardWeights()
    return round(
        outcome.yield_kg_ha * weights.yield_weight
        - outcome.total_irrigation_mm * weights.irrigation_cost
        - outcome.total_nitrogen_kg_ha * weights.nitrogen_cost
        - avg_water_stress * weights.water_stress_cost
        - avg_nitrogen_stress * weights.nitrogen_stress_cost,
        6,
    )
