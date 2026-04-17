from __future__ import annotations

import hashlib
import json
from pathlib import Path

from transdssat.domain import Trajectory
from transdssat.environments.adapters import OfficialDSSATEnvironment
from transdssat.scenarios import SimulationScenario
from transdssat.season import build_baseline_policy, rollout_proxy_policy


def rollout_scenario(scenario: SimulationScenario) -> Trajectory:
    policy = build_baseline_policy(scenario)
    if scenario.engine_name == "dssat_official":
        return OfficialDSSATEnvironment().evaluate_policy(scenario, policy).trajectory
    return rollout_proxy_policy(scenario, policy)


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
            "season_action_schema": [
                "stage",
                "date",
                "day_index",
                "irrigation_mm",
                "nitrogen_kg_ha",
            ],
            "reward_definition": (
                "season reward from final yield minus irrigation, nitrogen, and stress costs, "
                "with per-step biomass-growth shaping"
            ),
        },
    }
    with (output_path / "metadata.json").open("w", encoding="utf-8") as handle:
        json.dump(metadata, handle, indent=2, ensure_ascii=False)

    return metadata
