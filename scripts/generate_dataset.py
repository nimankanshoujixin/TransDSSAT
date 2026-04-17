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


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Quzhou-style simulation trajectories.")
    parser.add_argument("--output-dir", default="data/generated", help="Directory for JSONL outputs.")
    parser.add_argument(
        "--scenario-count",
        type=int,
        default=216,
        help="Number of scenarios to generate from the scenario grid.",
    )
    parser.add_argument(
        "--engines",
        nargs="+",
        default=["wofost_proxy", "dssat_proxy"],
        help="Backends to include, for example: wofost_proxy dssat_proxy dssat_official",
    )
    args = parser.parse_args()

    scenarios = build_quzhou_scenarios(
        target_count=args.scenario_count,
        engines=tuple(args.engines),
    )
    bundle = generate_dataset_bundle(scenarios)
    metadata = save_dataset_bundle(args.output_dir, bundle)
    print(json.dumps(metadata, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
