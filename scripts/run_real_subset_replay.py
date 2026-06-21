from __future__ import annotations

import argparse
import json
from pathlib import Path

from transdssat.real_subset_runner import run_real_subset_original_management


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Replay a real-data DSSAT subset under its original management and compare against observed yield."
    )
    parser.add_argument("--subset-id", required=True, choices=("mx475_migrated", "wuhu_rice_calibrated"))
    parser.add_argument("--treatment-no", required=True, type=int)
    parser.add_argument("--runtime-root", required=True, help="Path to the DSSAT runtime root containing dscsm048.")
    parser.add_argument("--output-root", required=True, help="Directory where isolated replay runs will be written.")
    parser.add_argument("--subset-root", help="Override root containing 作物模型_20260616.")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    result = run_real_subset_original_management(
        args.subset_id,
        args.treatment_no,
        runtime_root=Path(args.runtime_root),
        output_root=Path(args.output_root),
        subset_root=Path(args.subset_root) if args.subset_root else None,
    )
    print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
