from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from transdssat.dssat.parser import DSSATOutputParser
from transdssat.scenarios import SimulationScenario


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate interactive patched-runtime action effects by comparing a baseline "
            "smoke run against an action-applied smoke run using real DSSAT artifacts."
        )
    )
    parser.add_argument("--baseline-report", required=True)
    parser.add_argument("--action-report", required=True)
    parser.add_argument("--output-json", default="")
    parser.add_argument("--min-irrigation-delta-mm", type=float, default=0.0)
    parser.add_argument("--min-nitrogen-delta-kg-ha", type=float, default=0.0)
    parser.add_argument("--action-delta-tolerance-mm", type=float, default=1e-3)
    parser.add_argument("--action-delta-tolerance-kg-ha", type=float, default=1e-3)
    return parser


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_scenario(report: dict) -> SimulationScenario:
    manifest_path = Path(report["session_manifest"])
    payload = _load_json(manifest_path)
    scenario_payload = payload.get("scenario")
    if not isinstance(scenario_payload, dict):
        raise RuntimeError(f"Scenario payload missing from session manifest: {manifest_path}")
    return SimulationScenario.from_dict(scenario_payload)


def _parse_outcome(report: dict, scenario: SimulationScenario) -> dict:
    run_dir = Path(str(report.get("archived_run_dir") or report["run_dir"]))
    parsed = DSSATOutputParser().parse(run_dir, scenario)
    outcome = parsed.outcome.to_dict()
    outcome["run_dir"] = str(run_dir)
    return outcome


def _extract_protocol_final_outcome(report: dict) -> dict | None:
    outcome = report.get("final_outcome")
    if not isinstance(outcome, dict):
        return None
    payload = dict(outcome)
    payload["run_dir"] = str(report.get("archived_run_dir") or report.get("run_dir", ""))
    return payload


def _absolute_error(left: dict, right: dict, field: str) -> float:
    return round(abs(float(left.get(field, 0.0)) - float(right.get(field, 0.0))), 6)


def _environmental_absolute_error(left: dict, right: dict, field: str) -> float:
    left_env = dict(left.get("environmental_metrics", {}))
    right_env = dict(right.get("environmental_metrics", {}))
    return round(abs(float(left_env.get(field, 0.0)) - float(right_env.get(field, 0.0))), 6)


def _build_protocol_alignment(protocol_outcome: dict | None, archived_outcome: dict) -> dict:
    if protocol_outcome is None:
        return {
            "present": False,
            "matches_archived": False,
            "reward_source": "",
        }
    field_errors = {
        "yield_kg_ha": _absolute_error(protocol_outcome, archived_outcome, "yield_kg_ha"),
        "biomass_kg_ha": _absolute_error(protocol_outcome, archived_outcome, "biomass_kg_ha"),
        "total_irrigation_mm": _absolute_error(protocol_outcome, archived_outcome, "total_irrigation_mm"),
        "total_nitrogen_kg_ha": _absolute_error(protocol_outcome, archived_outcome, "total_nitrogen_kg_ha"),
        "terminal_root_zone_water_mm": _environmental_absolute_error(
            protocol_outcome,
            archived_outcome,
            "terminal_root_zone_water_mm",
        ),
        "terminal_soil_nitrogen_kg_ha": _environmental_absolute_error(
            protocol_outcome,
            archived_outcome,
            "terminal_soil_nitrogen_kg_ha",
        ),
    }
    return {
        "present": True,
        "matches_archived": all(value <= 1e-3 for value in field_errors.values()),
        "field_errors": field_errors,
        "cumulative_reward": round(float(protocol_outcome.get("cumulative_reward", 0.0)), 6),
        "reward_source": str(dict(protocol_outcome.get("environmental_metrics", {})).get("interactive_reward_source", "")),
    }


def _extract_requested_action(report: dict) -> dict[str, float]:
    action = dict(report.get("requested_action", {}))
    return {
        "irrigation_mm": float(action.get("irrigation_mm", 0.0)),
        "nitrogen_kg_ha": float(action.get("nitrogen_kg_ha", 0.0)),
    }


def _build_validation_payload(
    baseline_report: dict,
    action_report: dict,
    baseline_archived_outcome: dict,
    action_archived_outcome: dict,
    baseline_protocol_outcome: dict | None,
    action_protocol_outcome: dict | None,
) -> dict:
    requested_action = _extract_requested_action(action_report)
    irrigation_delta = round(
        float(action_archived_outcome.get("total_irrigation_mm", 0.0))
        - float(baseline_archived_outcome.get("total_irrigation_mm", 0.0)),
        6,
    )
    nitrogen_delta = round(
        float(action_archived_outcome.get("total_nitrogen_kg_ha", 0.0))
        - float(baseline_archived_outcome.get("total_nitrogen_kg_ha", 0.0)),
        6,
    )
    yield_delta = round(
        float(action_archived_outcome.get("yield_kg_ha", 0.0))
        - float(baseline_archived_outcome.get("yield_kg_ha", 0.0)),
        6,
    )
    terminal_water_delta = round(
        float(action_archived_outcome.get("environmental_metrics", {}).get("terminal_root_zone_water_mm", 0.0))
        - float(baseline_archived_outcome.get("environmental_metrics", {}).get("terminal_root_zone_water_mm", 0.0)),
        6,
    )
    terminal_nitrogen_delta = round(
        float(action_archived_outcome.get("environmental_metrics", {}).get("terminal_soil_nitrogen_kg_ha", 0.0))
        - float(baseline_archived_outcome.get("environmental_metrics", {}).get("terminal_soil_nitrogen_kg_ha", 0.0)),
        6,
    )
    baseline_outcome = baseline_protocol_outcome or baseline_archived_outcome
    action_outcome = action_protocol_outcome or action_archived_outcome
    return {
        "status": "ok",
        "scenario_id": str(action_report.get("scenario_id", "")),
        "baseline_report": str(baseline_report.get("__path__", "")),
        "action_report": str(action_report.get("__path__", "")),
        "requested_action": requested_action,
        "requested_action_match_error": {
            "total_irrigation_mm": round(abs(irrigation_delta - requested_action["irrigation_mm"]), 6),
            "total_nitrogen_kg_ha": round(abs(nitrogen_delta - requested_action["nitrogen_kg_ha"]), 6),
        },
        "deltas": {
            "total_irrigation_mm": irrigation_delta,
            "total_nitrogen_kg_ha": nitrogen_delta,
            "yield_kg_ha": yield_delta,
            "terminal_root_zone_water_mm": terminal_water_delta,
            "terminal_soil_nitrogen_kg_ha": terminal_nitrogen_delta,
        },
        "baseline_archived_outcome": baseline_archived_outcome,
        "action_archived_outcome": action_archived_outcome,
        "baseline_protocol_alignment": _build_protocol_alignment(baseline_protocol_outcome, baseline_archived_outcome),
        "action_protocol_alignment": _build_protocol_alignment(action_protocol_outcome, action_archived_outcome),
        "baseline_outcome": baseline_outcome,
        "action_outcome": action_outcome,
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    baseline_report_path = Path(args.baseline_report).resolve()
    action_report_path = Path(args.action_report).resolve()
    baseline_report = _load_json(baseline_report_path)
    baseline_report["__path__"] = str(baseline_report_path)
    action_report = _load_json(action_report_path)
    action_report["__path__"] = str(action_report_path)
    baseline_scenario = _load_scenario(baseline_report)
    action_scenario = _load_scenario(action_report)
    if baseline_scenario.scenario_id != action_scenario.scenario_id:
        raise RuntimeError(
            "Baseline and action smoke reports do not point to the same scenario: "
            f"{baseline_scenario.scenario_id!r} vs {action_scenario.scenario_id!r}"
        )
    baseline_archived_outcome = _parse_outcome(baseline_report, baseline_scenario)
    action_archived_outcome = _parse_outcome(action_report, action_scenario)
    baseline_protocol_outcome = _extract_protocol_final_outcome(baseline_report)
    action_protocol_outcome = _extract_protocol_final_outcome(action_report)
    payload = _build_validation_payload(
        baseline_report=baseline_report,
        action_report=action_report,
        baseline_archived_outcome=baseline_archived_outcome,
        action_archived_outcome=action_archived_outcome,
        baseline_protocol_outcome=baseline_protocol_outcome,
        action_protocol_outcome=action_protocol_outcome,
    )
    requested_action = payload["requested_action"]
    checks = {
        "irrigation_effect_observed": payload["deltas"]["total_irrigation_mm"] >= max(
            float(args.min_irrigation_delta_mm), requested_action["irrigation_mm"]
        ),
        "nitrogen_effect_observed": payload["deltas"]["total_nitrogen_kg_ha"] >= max(
            float(args.min_nitrogen_delta_kg_ha), requested_action["nitrogen_kg_ha"]
        ),
        "irrigation_scale_matches_request": payload["requested_action_match_error"]["total_irrigation_mm"]
        <= float(args.action_delta_tolerance_mm),
        "nitrogen_scale_matches_request": payload["requested_action_match_error"]["total_nitrogen_kg_ha"]
        <= float(args.action_delta_tolerance_kg_ha),
        "terminal_water_shift_observed": payload["deltas"]["terminal_root_zone_water_mm"] > 0.0
        if requested_action["irrigation_mm"] > 0.0
        else True,
        "terminal_nitrogen_shift_observed": payload["deltas"]["terminal_soil_nitrogen_kg_ha"] > 0.0
        if requested_action["nitrogen_kg_ha"] > 0.0
        else True,
        "baseline_protocol_matches_archived": payload["baseline_protocol_alignment"]["matches_archived"],
        "action_protocol_matches_archived": payload["action_protocol_alignment"]["matches_archived"],
        "baseline_protocol_is_parser_backed": payload["baseline_protocol_alignment"]["reward_source"] == "dssat_output_parser",
        "action_protocol_is_parser_backed": payload["action_protocol_alignment"]["reward_source"] == "dssat_output_parser",
    }
    payload["checks"] = checks
    payload["status"] = "ok" if all(checks.values()) else "failed"
    rendered = json.dumps(payload, indent=2, ensure_ascii=False)
    if args.output_json:
        output_path = Path(args.output_json).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered, encoding="utf-8")
    print(rendered)
    return 0 if payload["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
