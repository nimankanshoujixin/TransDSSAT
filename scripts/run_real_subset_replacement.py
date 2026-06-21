from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from transdssat.real_subset_runner import run_real_subset_management_replacement
from transdssat.season import SeasonPolicy, StageDecision


def _load_policy(path: Path) -> SeasonPolicy:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return SeasonPolicy(
        policy_id=str(payload["policy_id"]),
        scenario_id=str(payload["scenario_id"]),
        actions=[
            StageDecision(
                stage=str(item["stage"]),
                day_index=int(item["day_index"]),
                date=str(item["date"]),
                irrigation_mm=float(item["irrigation_mm"]),
                nitrogen_kg_ha=float(item["nitrogen_kg_ha"]),
            )
            for item in payload["actions"]
        ],
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a real-subset DSSAT replay after injecting a management-replacement policy."
    )
    parser.add_argument("--subset-id", required=True, choices=("mx475_migrated", "wuhu_rice_calibrated"))
    parser.add_argument("--treatment-no", required=True, type=int)
    parser.add_argument("--candidate-policy-json", required=True, help="Path to SeasonPolicy JSON payload.")
    parser.add_argument("--control-mode", choices=("joint", "water_only", "nitrogen_only"), default="joint")
    parser.add_argument("--runtime-root", required=True, help="Path to the DSSAT runtime root containing dscsm048.")
    parser.add_argument("--output-root", required=True, help="Directory where isolated replay runs will be written.")
    parser.add_argument("--subset-root", help="Override root containing 作物模型_20260616.")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    result = run_real_subset_management_replacement(
        args.subset_id,
        args.treatment_no,
        _load_policy(Path(args.candidate_policy_json).resolve()),
        control_mode=args.control_mode,
        runtime_root=Path(args.runtime_root),
        output_root=Path(args.output_root),
        subset_root=Path(args.subset_root) if args.subset_root else None,
    )
    print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
