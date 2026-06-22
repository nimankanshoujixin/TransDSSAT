from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from transdssat.dssat.validation import compare_real_subset_replays, write_runtime_comparison_report
from transdssat.real_subset_runner import run_real_subset_original_management
from transdssat.testset import load_real_data_test_subsets


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compare vanilla vs patched official DSSAT runtimes on identical real-subset replay inputs."
    )
    parser.add_argument("--vanilla-runtime-root", required=True, help="Preserved original DSSAT runtime root")
    parser.add_argument("--patched-runtime-root", required=True, help="Copied patched DSSAT runtime root")
    parser.add_argument("--output-root", required=True, help="Directory for side-by-side runtime replay outputs")
    parser.add_argument("--subset-ids", nargs="+", default=["mx475_migrated", "wuhu_rice_calibrated"])
    parser.add_argument(
        "--case",
        action="append",
        default=[],
        help="Optional subset:treatment selector, for example mx475_migrated:1 . Repeatable.",
    )
    parser.add_argument("--subset-root", help="Override root containing the stable real-data subset assets")
    parser.add_argument("--report-name", default="dssat_runtime_comparison_report.json")
    return parser


def parse_case_selectors(raw_values: list[str]) -> dict[str, set[int]]:
    selectors: dict[str, set[int]] = {}
    for raw in raw_values:
        subset_id, _, treatment_text = str(raw).partition(":")
        if not subset_id or not treatment_text or not treatment_text.isdigit():
            raise ValueError(f"Invalid --case value: {raw}. Expected subset_id:treatment_no")
        selectors.setdefault(subset_id, set()).add(int(treatment_text))
    return selectors


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    vanilla_runtime_root = Path(args.vanilla_runtime_root).resolve()
    patched_runtime_root = Path(args.patched_runtime_root).resolve()
    output_root = Path(args.output_root).resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    report_path = output_root / args.report_name
    selectors = parse_case_selectors(list(args.case))

    bundles = load_real_data_test_subsets(tuple(args.subset_ids))
    comparisons = []
    for bundle in bundles:
        if selectors and bundle.asset.subset_id not in selectors:
            continue
        allowed_treatments = selectors.get(bundle.asset.subset_id)
        for case in bundle.replay_cases:
            if allowed_treatments is not None and case.treatment.treatment_no not in allowed_treatments:
                continue
            case_root = output_root / f"{bundle.asset.subset_id}_tr{case.treatment.treatment_no:02d}"
            vanilla_replay = run_real_subset_original_management(
                bundle.asset.subset_id,
                case.treatment.treatment_no,
                runtime_root=vanilla_runtime_root,
                output_root=case_root / "vanilla",
                subset_root=Path(args.subset_root) if args.subset_root else None,
            )
            patched_replay = run_real_subset_original_management(
                bundle.asset.subset_id,
                case.treatment.treatment_no,
                runtime_root=patched_runtime_root,
                output_root=case_root / "patched",
                subset_root=Path(args.subset_root) if args.subset_root else None,
            )
            comparisons.append(
                compare_real_subset_replays(
                    vanilla_replay,
                    patched_replay,
                    left_runtime_label="vanilla",
                    right_runtime_label="patched",
                )
            )

    report = write_runtime_comparison_report(
        report_path,
        left_runtime_root=str(vanilla_runtime_root),
        right_runtime_root=str(patched_runtime_root),
        left_runtime_label="vanilla",
        right_runtime_label="patched",
        case_comparisons=comparisons,
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
