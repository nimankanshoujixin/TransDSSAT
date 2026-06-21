from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from statistics import mean
from typing import Any

from transdssat.real_subset_assets import load_real_subset_asset
from transdssat.real_subset_runner import run_real_subset_original_management


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run all treatments in a real subset under original management and aggregate replay accuracy."
    )
    parser.add_argument("--subset-id", required=True, choices=("mx475_migrated", "wuhu_rice_calibrated"))
    parser.add_argument("--runtime-root", required=True, help="Path to the DSSAT runtime root containing dscsm048.")
    parser.add_argument("--output-root", required=True, help="Directory where replay runs and aggregate outputs will be written.")
    parser.add_argument("--subset-root", help="Override root containing 作物模型_20260616.")
    return parser


def _bridge_active(subset_id: str, cultivar_code: str) -> bool:
    return subset_id == "wuhu_rice_calibrated" and cultivar_code == "WHR006"


def _row_payload(result: Any) -> dict[str, Any]:
    relative_abs_gap = abs(float(result.yield_gap_kg_ha))
    relative_ratio = abs(float(result.yield_gap_ratio))
    return {
        "subset_id": result.subset_id,
        "treatment_no": result.treatment_no,
        "treatment_name": result.treatment_name,
        "cultivar_code": result.cultivar_code,
        "observed_yield_kg_ha": result.observed_yield_kg_ha,
        "simulated_yield_kg_ha": result.simulated_yield_kg_ha,
        "yield_gap_kg_ha": result.yield_gap_kg_ha,
        "yield_gap_ratio": result.yield_gap_ratio,
        "abs_yield_gap_kg_ha": round(relative_abs_gap, 3),
        "abs_yield_gap_ratio": round(relative_ratio, 6),
        "bridge_active": _bridge_active(result.subset_id, result.cultivar_code),
        "run_dir": result.run_dir,
    }


def _summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    abs_gaps = [float(row["abs_yield_gap_kg_ha"]) for row in rows]
    abs_ratios = [float(row["abs_yield_gap_ratio"]) for row in rows]
    signed_gaps = [float(row["yield_gap_kg_ha"]) for row in rows]
    signed_ratios = [float(row["yield_gap_ratio"]) for row in rows]
    bridged = [row for row in rows if row["bridge_active"]]
    top_errors = sorted(rows, key=lambda item: item["abs_yield_gap_ratio"], reverse=True)[:5]
    return {
        "treatment_count": len(rows),
        "bridge_treatment_count": len(bridged),
        "mean_abs_yield_gap_kg_ha": round(mean(abs_gaps), 3),
        "mean_abs_yield_gap_ratio": round(mean(abs_ratios), 6),
        "mean_signed_yield_gap_kg_ha": round(mean(signed_gaps), 3),
        "mean_signed_yield_gap_ratio": round(mean(signed_ratios), 6),
        "max_abs_yield_gap_kg_ha": round(max(abs_gaps), 3),
        "max_abs_yield_gap_ratio": round(max(abs_ratios), 6),
        "top_error_treatments": [
            {
                "treatment_no": row["treatment_no"],
                "cultivar_code": row["cultivar_code"],
                "yield_gap_kg_ha": row["yield_gap_kg_ha"],
                "yield_gap_ratio": row["yield_gap_ratio"],
                "bridge_active": row["bridge_active"],
            }
            for row in top_errors
        ],
    }


def _write_csv(rows: list[dict[str, Any]], output_path: Path) -> None:
    fieldnames = [
        "subset_id",
        "treatment_no",
        "treatment_name",
        "cultivar_code",
        "observed_yield_kg_ha",
        "simulated_yield_kg_ha",
        "yield_gap_kg_ha",
        "yield_gap_ratio",
        "abs_yield_gap_kg_ha",
        "abs_yield_gap_ratio",
        "bridge_active",
        "run_dir",
    ]
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _write_markdown(subset_name: str, rows: list[dict[str, Any]], summary: dict[str, Any], output_path: Path) -> None:
    lines = [
        f"# {subset_name} Replay Audit",
        "",
        "## Summary",
        "",
        f"- treatment count: `{summary['treatment_count']}`",
        f"- bridge treatment count: `{summary['bridge_treatment_count']}`",
        f"- mean abs yield gap: `{summary['mean_abs_yield_gap_kg_ha']} kg/ha`",
        f"- mean abs yield gap ratio: `{summary['mean_abs_yield_gap_ratio']}`",
        f"- mean signed yield gap: `{summary['mean_signed_yield_gap_kg_ha']} kg/ha`",
        f"- mean signed yield gap ratio: `{summary['mean_signed_yield_gap_ratio']}`",
        f"- max abs yield gap: `{summary['max_abs_yield_gap_kg_ha']} kg/ha`",
        f"- max abs yield gap ratio: `{summary['max_abs_yield_gap_ratio']}`",
        "",
        "## Treatments",
        "",
        "| TR | Cultivar | Observed | Simulated | Gap | Ratio | Bridge |",
        "| --- | --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in rows:
        lines.append(
            f"| {row['treatment_no']} | {row['cultivar_code']} | {row['observed_yield_kg_ha']} | "
            f"{row['simulated_yield_kg_ha']} | {row['yield_gap_kg_ha']} | {row['yield_gap_ratio']} | "
            f"{'yes' if row['bridge_active'] else 'no'} |"
        )
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    output_root = Path(args.output_root).resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    asset = load_real_subset_asset(args.subset_id, root=Path(args.subset_root) if args.subset_root else None)
    rows: list[dict[str, Any]] = []
    for treatment in asset.treatments:
        result = run_real_subset_original_management(
            args.subset_id,
            treatment.treatment_no,
            runtime_root=Path(args.runtime_root),
            output_root=output_root,
            subset_root=Path(args.subset_root) if args.subset_root else None,
        )
        rows.append(_row_payload(result))

    rows.sort(key=lambda item: int(item["treatment_no"]))
    summary = _summarize(rows)
    payload = {
        "subset_id": args.subset_id,
        "subset_name": asset.subset_name,
        "runtime_root": str(Path(args.runtime_root).resolve()),
        "output_root": str(output_root),
        "summary": summary,
        "treatments": rows,
    }

    (output_root / "real_subset_replay_audit.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    _write_csv(rows, output_root / "real_subset_replay_audit.csv")
    _write_markdown(asset.subset_name, rows, summary, output_root / "real_subset_replay_audit.md")
    print(json.dumps(payload, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
