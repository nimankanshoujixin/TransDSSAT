from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from transdssat.real_subset_replay import (
    build_real_subset_replacement_plan,
    load_real_subset_replay_case,
    write_real_subset_policy_tsv,
)
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
        description="Prepare a real-subset management-replacement plan and render-compatible policy TSV."
    )
    parser.add_argument("--subset-id", required=True, choices=("mx475_migrated", "wuhu_rice_calibrated"))
    parser.add_argument("--treatment-no", required=True, type=int)
    parser.add_argument("--candidate-policy-json", required=True, help="Path to SeasonPolicy JSON payload.")
    parser.add_argument("--control-mode", choices=("joint", "water_only", "nitrogen_only"), default="joint")
    parser.add_argument("--output-dir", required=True, help="Directory for replacement-plan artifacts.")
    parser.add_argument("--subset-root", help="Override root containing 作物模型_20260616.")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    case = load_real_subset_replay_case(
        args.subset_id,
        args.treatment_no,
        root=Path(args.subset_root) if args.subset_root else None,
    )
    candidate_policy = _load_policy(Path(args.candidate_policy_json).resolve())
    plan = build_real_subset_replacement_plan(
        case,
        candidate_policy,
        control_mode=args.control_mode,
    )

    policy_path = write_real_subset_policy_tsv(plan.composed_policy, output_dir / "transdssat_policy.tsv")
    plan_payload = plan.to_dict()
    plan_payload["policy_tsv_path"] = str(policy_path)
    plan_path = output_dir / "real_subset_replacement_plan.json"
    plan_path.write_text(json.dumps(plan_payload, indent=2, ensure_ascii=False), encoding="utf-8")

    print(json.dumps({"plan_path": str(plan_path), "policy_tsv_path": str(policy_path)}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
