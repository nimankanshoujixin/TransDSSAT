from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from transdssat.dssat import DSSATOutputParser, DSSATRunConfig, DSSATRunner
from transdssat.dssat.validation import (
    compare_output_file,
    load_interactive_session_scenario,
    reconstruct_interactive_session_policy,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Replay the action schedule from an interactive patched-DSSAT session on the vanilla DSSAT runtime "
            "and compare the final outputs."
        )
    )
    parser.add_argument("--interactive-report", required=True, help="Path to smoke_report.json from an interactive patched run.")
    parser.add_argument("--output-root", required=True, help="Directory where the vanilla replay run should be materialized.")
    parser.add_argument("--vanilla-runtime-root", default="", help="Optional override for DSSAT_VANILLA_HOME.")
    parser.add_argument("--report-name", default="interactive_vs_vanilla_report.json")
    return parser


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve_protocol_dir(report: dict) -> Path:
    archived_run_dir = str(report.get("archived_run_dir", "")).strip()
    if archived_run_dir:
        candidate = Path(archived_run_dir) / "interactive_protocol"
        if candidate.exists():
            return candidate
    protocol_dir = str(report.get("protocol_dir", "")).strip()
    if protocol_dir:
        candidate = Path(protocol_dir)
        if candidate.exists():
            return candidate
    raise RuntimeError("Could not resolve interactive protocol directory from smoke report.")


def _compare_environmental_metric(left: dict, right: dict, field: str) -> float:
    left_env = dict(left.get("environmental_metrics", {}))
    right_env = dict(right.get("environmental_metrics", {}))
    return round(abs(float(left_env.get(field, 0.0)) - float(right_env.get(field, 0.0))), 6)


def main() -> int:
    args = build_parser().parse_args()
    report_path = Path(args.interactive_report).resolve()
    output_root = Path(args.output_root).resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    report = _load_json(report_path)
    protocol_dir = _resolve_protocol_dir(report)
    interactive_run_dir = Path(str(report.get("archived_run_dir") or report.get("run_dir", ""))).resolve()
    if not interactive_run_dir.exists():
        raise RuntimeError(f"Interactive run dir does not exist: {interactive_run_dir}")

    scenario = load_interactive_session_scenario(protocol_dir)
    policy = reconstruct_interactive_session_policy(protocol_dir)

    config = DSSATRunConfig.from_env(runtime_role="vanilla")
    if args.vanilla_runtime_root:
        config = replace(config, runtime_root=Path(args.vanilla_runtime_root).resolve())
    config = replace(config, working_root=output_root)

    runner = DSSATRunner(config=config)
    context = runner.prepare(scenario, policy)
    runner.run(context)
    vanilla_run_dir = context.run_dir

    parser = DSSATOutputParser()
    interactive_parsed = parser.parse(interactive_run_dir, scenario)
    vanilla_parsed = parser.parse(vanilla_run_dir, scenario)

    file_comparisons = [
        compare_output_file(interactive_run_dir / file_name, vanilla_run_dir / file_name, file_name=file_name).to_dict()
        for file_name in ("Summary.OUT", "PlantGro.OUT", "SoilWat.OUT", "SoilNi.OUT", "Evaluate.OUT")
    ]

    outcome_errors = {
        "yield_kg_ha": round(abs(interactive_parsed.outcome.yield_kg_ha - vanilla_parsed.outcome.yield_kg_ha), 6),
        "biomass_kg_ha": round(abs(interactive_parsed.outcome.biomass_kg_ha - vanilla_parsed.outcome.biomass_kg_ha), 6),
        "total_irrigation_mm": round(
            abs(interactive_parsed.outcome.total_irrigation_mm - vanilla_parsed.outcome.total_irrigation_mm),
            6,
        ),
        "total_nitrogen_kg_ha": round(
            abs(interactive_parsed.outcome.total_nitrogen_kg_ha - vanilla_parsed.outcome.total_nitrogen_kg_ha),
            6,
        ),
        "terminal_root_zone_water_mm": _compare_environmental_metric(
            interactive_parsed.outcome.to_dict(),
            vanilla_parsed.outcome.to_dict(),
            "terminal_root_zone_water_mm",
        ),
        "terminal_soil_nitrogen_kg_ha": _compare_environmental_metric(
            interactive_parsed.outcome.to_dict(),
            vanilla_parsed.outcome.to_dict(),
            "terminal_soil_nitrogen_kg_ha",
        ),
    }

    payload = {
        "status": "ok",
        "interactive_report": str(report_path),
        "protocol_dir": str(protocol_dir),
        "interactive_run_dir": str(interactive_run_dir),
        "vanilla_run_dir": str(vanilla_run_dir),
        "scenario_id": scenario.scenario_id,
        "reconstructed_policy": policy.to_dict(),
        "interactive_outcome": interactive_parsed.outcome.to_dict(),
        "vanilla_outcome": vanilla_parsed.outcome.to_dict(),
        "outcome_errors": outcome_errors,
        "file_comparisons": file_comparisons,
        "checks": {
            "all_files_match": all(bool(item["match"]) for item in file_comparisons),
            "all_outcome_fields_match": all(value <= 1e-3 for value in outcome_errors.values()),
        },
    }
    payload["status"] = "ok" if all(payload["checks"].values()) else "failed"

    rendered = json.dumps(payload, indent=2, ensure_ascii=False)
    output_path = output_root / args.report_name
    output_path.write_text(rendered, encoding="utf-8")
    print(rendered)
    return 0 if payload["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
