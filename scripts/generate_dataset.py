from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from transdssat.dataset import generate_dataset_bundle, save_dataset_bundle
from transdssat.scenarios import build_quzhou_scenarios
from transdssat.season import BASELINE_BUDGET_SOURCES, BASELINE_NAMES, DECISION_GRANULARITIES


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Quzhou-style simulation trajectories.")
    parser.add_argument("--output-dir", default="data/generated", help="Directory for JSONL outputs.")
    parser.add_argument(
        "--scenario-count",
        type=int,
        default=216,
        help="Number of scenarios to generate.",
    )
    parser.add_argument(
        "--sampling-mode",
        choices=("grid", "random", "realistic"),
        default="grid",
        help="Use the legacy fixed grid, synthetic random sampling, or real-data-driven realistic sampling.",
    )
    parser.add_argument(
        "--engines",
        nargs="+",
        default=["dssat_official"],
        help="Backends to include, for example: dssat_official",
    )
    parser.add_argument(
        "--crops",
        nargs="+",
        default=None,
        help="Optional crop filter, for example: maize wheat",
    )
    parser.add_argument("--baseline-name", choices=BASELINE_NAMES, default="heuristic")
    parser.add_argument("--baseline-budget-source", choices=BASELINE_BUDGET_SOURCES, default="scenario")
    parser.add_argument("--decision-granularity", choices=DECISION_GRANULARITIES, default="stage")
    parser.add_argument("--seed", type=int, default=20260426, help="Scenario sampling seed.")
    args = parser.parse_args()

    scenarios = build_quzhou_scenarios(
        target_count=args.scenario_count,
        engines=tuple(args.engines),
        crops_filter=tuple(args.crops) if args.crops else None,
        sampling_mode=args.sampling_mode,
        seed=args.seed,
    )
    bundle = generate_dataset_bundle(
        scenarios,
        baseline_name=args.baseline_name,
        decision_granularity=args.decision_granularity,
        budget_source=args.baseline_budget_source,
    )
    metadata = save_dataset_bundle(args.output_dir, bundle)
    print(json.dumps(metadata, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
