from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

from transdssat.domain import CropAction, Trajectory, TrajectoryStep
from transdssat.environments import make_environment
from transdssat.scenarios import STAGES, SimulationScenario


IRRIGATION_THRESHOLDS = {
    "balanced": {
        "emergence": 0.52,
        "vegetative": 0.58,
        "reproductive": 0.64,
        "grain_fill": 0.56,
    },
    "reproductive_focus": {
        "emergence": 0.47,
        "vegetative": 0.54,
        "reproductive": 0.69,
        "grain_fill": 0.60,
    },
}

NITROGEN_THRESHOLDS = {
    "balanced": {
        "emergence": 65.0,
        "vegetative": 58.0,
        "reproductive": 50.0,
        "grain_fill": 42.0,
    },
    "reproductive_focus": {
        "emergence": 55.0,
        "vegetative": 52.0,
        "reproductive": 60.0,
        "grain_fill": 44.0,
    },
}

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
class ScenarioPlanner:
    scenario: SimulationScenario
    remaining_irrigation: float = 0.0
    remaining_nitrogen: float = 0.0
    stage_irrigation_used: dict[str, float] | None = None
    stage_nitrogen_applied: dict[str, bool] | None = None
    mode: str = ""

    def __post_init__(self) -> None:
        self.remaining_irrigation = self.scenario.irrigation_budget_mm
        self.remaining_nitrogen = self.scenario.nitrogen_budget_kg_ha
        self.stage_irrigation_used = {stage: 0.0 for stage in STAGES}
        self.stage_nitrogen_applied = {stage: False for stage in STAGES}
        self.mode = self.scenario.management_mode

    def act(self, state) -> CropAction:
        stage = state.stage
        irrigation_fraction, nitrogen_fraction = STAGE_BUDGET_SPLITS[self.mode][stage]
        stage_irrigation_cap = self.scenario.irrigation_budget_mm * irrigation_fraction
        stage_nitrogen_cap = self.scenario.nitrogen_budget_kg_ha * nitrogen_fraction
        irrigation_mm = 0.0
        nitrogen_kg_ha = 0.0

        if (
            state.soil_moisture < IRRIGATION_THRESHOLDS[self.mode][stage]
            and self.remaining_irrigation > 0.0
        ):
            application_size = 18.0 if stage in {"emergence", "grain_fill"} else 28.0
            stage_remaining = max(0.0, stage_irrigation_cap - self.stage_irrigation_used[stage])
            irrigation_mm = min(application_size, self.remaining_irrigation, stage_remaining)
            self.remaining_irrigation -= irrigation_mm
            self.stage_irrigation_used[stage] += irrigation_mm

        if (
            state.soil_nitrogen_kg_ha < NITROGEN_THRESHOLDS[self.mode][stage]
            and self.remaining_nitrogen > 0.0
            and not self.stage_nitrogen_applied[stage]
        ):
            dose = min(stage_nitrogen_cap, self.remaining_nitrogen)
            nitrogen_kg_ha = round(dose, 3)
            self.remaining_nitrogen -= nitrogen_kg_ha
            self.stage_nitrogen_applied[stage] = nitrogen_kg_ha > 0.0

        return CropAction(
            irrigation_mm=round(irrigation_mm, 3),
            nitrogen_kg_ha=round(nitrogen_kg_ha, 3),
        )


def rollout_scenario(scenario: SimulationScenario) -> Trajectory:
    env = make_environment(scenario)
    planner = ScenarioPlanner(scenario=scenario)
    steps: list[TrajectoryStep] = []
    state = env.reset()

    while True:
        action = planner.act(state)
        next_state, reward, done, info = env.step(action)
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
    )


def split_name(scenario_id: str, train_ratio: float = 0.8) -> str:
    digest = hashlib.sha256(scenario_id.encode("utf-8")).hexdigest()
    value = int(digest[:8], 16) / 0xFFFFFFFF
    return "train" if value < train_ratio else "test"


def generate_dataset_bundle(scenarios: list[SimulationScenario]) -> dict[str, list[Trajectory]]:
    bundle = {"train": [], "test": []}
    for scenario in scenarios:
        bundle[split_name(scenario.scenario_id)].append(rollout_scenario(scenario))
    return bundle


def summarize_bundle(bundle: dict[str, list[Trajectory]]) -> dict:
    summary = {}
    for split, trajectories in bundle.items():
        scenario_count = len(trajectories)
        step_count = sum(len(trajectory.steps) for trajectory in trajectories)
        mean_yield = round(
            sum(trajectory.outcome.yield_kg_ha for trajectory in trajectories) / max(1, scenario_count),
            3,
        )
        summary[split] = {
            "scenario_count": scenario_count,
            "step_count": step_count,
            "mean_yield_kg_ha": mean_yield,
        }
    return summary


def save_dataset_bundle(output_dir: str | Path, bundle: dict[str, list[Trajectory]]) -> dict:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    summary = summarize_bundle(bundle)

    for split, trajectories in bundle.items():
        file_path = output_path / f"{split}.jsonl"
        with file_path.open("w", encoding="utf-8") as handle:
            for trajectory in trajectories:
                handle.write(json.dumps(trajectory.to_dict(), ensure_ascii=False) + "\n")

    metadata = {
        "summary": summary,
        "schema": {
            "state_features": [
                "day_index",
                "stage_index",
                "soil_moisture",
                "root_zone_water_mm",
                "soil_nitrogen_kg_ha",
                "canopy_cover",
                "biomass_kg_ha",
                "water_stress",
                "nitrogen_stress",
                "tmean_c",
                "precipitation_mm",
                "et0_mm",
                "radiation_mj_m2",
            ],
            "action_features": ["irrigation_mm", "nitrogen_kg_ha"],
            "reward_definition": "daily biomass gain and final yield minus water, nitrogen, and stress costs",
        },
    }
    with (output_path / "metadata.json").open("w", encoding="utf-8") as handle:
        json.dump(metadata, handle, indent=2, ensure_ascii=False)

    return metadata
