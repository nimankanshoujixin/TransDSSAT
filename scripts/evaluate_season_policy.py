from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from transdssat.dataset import rollout_scenario
from transdssat.scenarios import build_quzhou_scenarios
from transdssat.season import BASELINE_BUDGET_SOURCES, BASELINE_NAMES, DECISION_GRANULARITIES, build_baseline_policy


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate one season policy on the selected backend.")
    parser.add_argument(
        "--engine",
        choices=("dssat_official",),
        default="dssat_official",
        help="Evaluation backend. Official DSSAT only.",
    )
    parser.add_argument("--crop", default="wheat", help="Crop filter: wheat or maize")
    parser.add_argument("--weather-regime", default="normal", help="dry, normal, wet")
    parser.add_argument("--sampling-mode", choices=("grid", "random"), default="grid")
    parser.add_argument("--baseline-name", choices=BASELINE_NAMES, default="literature_ncp")
    parser.add_argument("--baseline-budget-source", choices=BASELINE_BUDGET_SOURCES, default="scenario")
    parser.add_argument("--decision-granularity", choices=DECISION_GRANULARITIES, default="stage")
    parser.add_argument("--seed", type=int, default=20260426)
    args = parser.parse_args()

    scenarios = build_quzhou_scenarios(
        target_count=400,
        engines=(args.engine,),
        sampling_mode=args.sampling_mode,
        seed=args.seed,
    )
    scenario = next(
        scenario
        for scenario in scenarios
        if scenario.crop_spec.crop_name == args.crop and scenario.weather_regime == args.weather_regime
    )
    policy = build_baseline_policy(
        scenario,
        baseline_name=args.baseline_name,
        decision_granularity=args.decision_granularity,
        budget_source=args.baseline_budget_source,
    )
    trajectory = rollout_scenario(
        scenario,
        baseline_name=args.baseline_name,
        decision_granularity=args.decision_granularity,
        budget_source=args.baseline_budget_source,
    )
    print(
        json.dumps(
            {
                "scenario_id": trajectory.scenario_id,
                "engine_name": trajectory.engine_name,
                "policy": policy.to_dict(),
                "outcome": trajectory.outcome.to_dict(),
                "steps": len(trajectory.steps),
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
