from __future__ import annotations

import json
from pathlib import Path

from transdssat.real_subset_stepwise_eval import build_real_subset_simulation_scenario
from transdssat.scenarios import SimulationScenario, build_quzhou_scenarios


def load_scenario_from_json(path: str | Path) -> SimulationScenario:
    scenario_path = Path(path).resolve()
    payload = json.loads(scenario_path.read_text(encoding="utf-8"))
    return SimulationScenario.from_dict(payload)


def resolve_scenario(
    *,
    source: str = "quzhou",
    crop: str = "maize",
    seed: int = 20260622,
    scenario_index: int = 0,
    sampling_mode: str = "random",
    scenario_json: str | Path | None = None,
    subset_id: str = "",
    treatment_no: int = 0,
) -> SimulationScenario:
    if source == "json":
        if not scenario_json:
            raise ValueError("scenario source 'json' requires --scenario-json")
        return load_scenario_from_json(scenario_json)

    if source == "real_subset":
        if not subset_id or treatment_no <= 0:
            raise ValueError("scenario source 'real_subset' requires --subset-id and --treatment-no")
        materialized = build_real_subset_simulation_scenario(subset_id, treatment_no)
        scenario = materialized.scenario
        experiment_path = Path(materialized.case.experiment_file).resolve()
        scenario.template_name = str(experiment_path.parent)
        scenario.experiment_file = experiment_path.name
        return scenario

    if source == "quzhou":
        scenarios = build_quzhou_scenarios(
            target_count=max(1, scenario_index + 1),
            engines=("dssat_official",),
            crops_filter=(crop,),
            sampling_mode=sampling_mode,
            seed=seed,
        )
        return scenarios[scenario_index]

    raise ValueError(f"Unsupported scenario source: {source}")
