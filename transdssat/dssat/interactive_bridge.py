from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any

from transdssat.domain import CropAction, CropOutcome, CropState
from transdssat.dssat.parser import DSSATOutputParser
from transdssat.rewarding import (
    anti_collapse_preferences,
    objective_reward_weights,
    resource_settlement_preferences,
    reward_from_outcome,
    step_reward,
)
from transdssat.scenarios import SimulationScenario, scenario_yield_floor_reference

from .interactive import INTERACTIVE_ACTION_CHANNELS, INTERACTIVE_PROTOCOL_VERSION

STATE_FIELD_TYPES: dict[str, type] = {
    "day_index": int,
    "stage": str,
    "stage_index": int,
    "soil_moisture": float,
    "root_zone_water_mm": float,
    "soil_nitrogen_kg_ha": float,
    "canopy_cover": float,
    "biomass_kg_ha": float,
    "water_stress": float,
    "nitrogen_stress": float,
    "tmean_c": float,
    "precipitation_mm": float,
    "et0_mm": float,
    "radiation_mj_m2": float,
}

OUTCOME_FIELD_TYPES: dict[str, type] = {
    "yield_kg_ha": float,
    "biomass_kg_ha": float,
    "total_irrigation_mm": float,
    "total_nitrogen_kg_ha": float,
    "water_use_efficiency": float,
    "nitrogen_use_efficiency": float,
    "cumulative_reward": float,
}

PROGRESS_FILENAME = "interactive_progress.json"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Bridge helper between a minimal patched DSSAT Fortran runtime and the "
            "existing TransDSSAT JSON interactive protocol."
        )
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    ready = subparsers.add_parser("write-ready", help="Write session_ready.json from a simple state payload.")
    _add_protocol_args(ready)
    ready.add_argument("--state-file", required=True)
    ready.add_argument("--run-dir", default="")
    ready.add_argument(
        "--info-tag",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Extra info fields to append to the ready payload.",
    )

    wait = subparsers.add_parser("await-action", help="Wait for one step request and write a Fortran-friendly action file.")
    _add_protocol_args(wait)
    wait.add_argument("--step-index", type=int, required=True)
    wait.add_argument("--output-action-file", required=True)
    wait.add_argument("--poll-interval-seconds", type=float, default=0.2)
    wait.add_argument("--timeout-seconds", type=float, default=60.0)

    response = subparsers.add_parser(
        "write-step-response",
        help="Write step_response_XXXX.json from simple state/outcome payloads.",
    )
    _add_protocol_args(response)
    response.add_argument("--step-index", type=int, required=True)
    response.add_argument("--state-file", required=True)
    response.add_argument("--run-dir", default="")
    response.add_argument("--reward", type=float, default=None)
    response.add_argument("--done", action="store_true")
    response.add_argument("--days-executed", type=int, default=0)
    response.add_argument("--daily-trace-file", default="")
    response.add_argument("--final-outcome-file", default="")
    response.add_argument(
        "--info-tag",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Extra info fields to append to the step response info block.",
    )

    final = subparsers.add_parser("write-final-outcome", help="Write final_outcome.json from a simple outcome payload.")
    _add_protocol_args(final)
    final.add_argument("--outcome-file", required=True)

    return parser


def _add_protocol_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--protocol-dir", default=os.environ.get("DSSAT_INTERACTIVE_PROTOCOL_DIR", ""))
    parser.add_argument(
        "--session-manifest",
        default=os.environ.get("DSSAT_INTERACTIVE_SESSION_MANIFEST", ""),
    )


def _require_protocol_args(args: argparse.Namespace) -> tuple[Path, Path, dict[str, Any]]:
    protocol_dir = Path(str(args.protocol_dir).strip()).resolve()
    session_manifest = Path(str(args.session_manifest).strip()).resolve()
    if not str(protocol_dir):
        raise RuntimeError("Missing --protocol-dir and DSSAT_INTERACTIVE_PROTOCOL_DIR is not set.")
    if not str(session_manifest):
        raise RuntimeError("Missing --session-manifest and DSSAT_INTERACTIVE_SESSION_MANIFEST is not set.")
    manifest = json.loads(session_manifest.read_text(encoding="utf-8"))
    interaction = dict(manifest.get("interaction", {}))
    _validate_interaction(interaction)
    return protocol_dir, session_manifest, interaction


def _validate_interaction(interaction: dict[str, Any]) -> None:
    if str(interaction.get("protocol_version", "")).strip() != INTERACTIVE_PROTOCOL_VERSION:
        raise RuntimeError("Interactive manifest protocol_version mismatch.")
    channels = tuple(str(item).strip() for item in interaction.get("action_channels", []))
    if channels != INTERACTIVE_ACTION_CHANNELS:
        raise RuntimeError("Interactive manifest action_channels mismatch.")


def _parse_simple_payload(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return {}
    if path.suffix.lower() == ".json" or text.startswith("{") or text.startswith("["):
        return json.loads(text)
    payload: dict[str, Any] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise RuntimeError(f"Malformed payload line in {path}: {raw_line!r}")
        key, value = line.split("=", 1)
        payload[key.strip()] = value.strip()
    return payload


def _coerce_fields(payload: dict[str, Any], field_types: dict[str, type], *, label: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    missing = [field for field in field_types if field not in payload]
    if missing:
        raise RuntimeError(f"{label} payload missing required fields: {', '.join(missing)}")
    for field, field_type in field_types.items():
        raw_value = payload[field]
        if field_type is str:
            result[field] = str(raw_value)
        else:
            result[field] = field_type(raw_value)
    return result


def _parse_info_tags(items: list[str]) -> dict[str, Any]:
    tags: dict[str, Any] = {}
    for item in items:
        if "=" not in item:
            raise RuntimeError(f"Malformed --info-tag value: {item!r}")
        key, value = item.split("=", 1)
        tags[key.strip()] = value.strip()
    return tags


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _progress_path(protocol_dir: Path) -> Path:
    return protocol_dir / PROGRESS_FILENAME


def _load_progress(protocol_dir: Path) -> dict[str, Any]:
    path = _progress_path(protocol_dir)
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _save_progress(protocol_dir: Path, payload: dict[str, Any]) -> None:
    _write_json(_progress_path(protocol_dir), payload)


def _write_close_action_file(output_path: Path, step_index: int) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        "\n".join(
            [
                f"step_index={step_index}",
                "decision_interval_days=0",
                "irrigation_mm=0.0",
                "nitrogen_kg_ha=0.0",
                "close_requested=1",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def _protocol_has_terminal_outcome(protocol_dir: Path) -> bool:
    final_outcome_path = protocol_dir / "final_outcome.json"
    if final_outcome_path.exists():
        return True
    try:
        progress = _load_progress(protocol_dir)
    except json.JSONDecodeError:
        return False
    return isinstance(progress.get("final_outcome"), dict)


def _build_info_block(interaction: dict[str, Any], *, days_executed: int | None = None, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    info = {
        "protocol_version": interaction["protocol_version"],
        "engine_name": interaction["engine_name"],
        "backend_mode": interaction["backend_mode"],
        "runtime_role": interaction["runtime_role"],
    }
    if days_executed is not None:
        info["days_executed"] = int(days_executed)
    if extra:
        info.update(extra)
    return info


def _load_scenario_from_manifest(session_manifest: Path) -> SimulationScenario:
    manifest = json.loads(session_manifest.read_text(encoding="utf-8"))
    scenario_payload = manifest.get("scenario")
    if not isinstance(scenario_payload, dict):
        raise RuntimeError("Interactive session manifest did not include a full scenario payload.")
    return SimulationScenario.from_dict(scenario_payload)


def _state_from_payload(payload: dict[str, Any]) -> CropState:
    return CropState(
        day_index=int(payload["day_index"]),
        stage=str(payload["stage"]),
        stage_index=int(payload["stage_index"]),
        soil_moisture=float(payload["soil_moisture"]),
        root_zone_water_mm=float(payload["root_zone_water_mm"]),
        soil_nitrogen_kg_ha=float(payload["soil_nitrogen_kg_ha"]),
        canopy_cover=float(payload["canopy_cover"]),
        biomass_kg_ha=float(payload["biomass_kg_ha"]),
        water_stress=float(payload["water_stress"]),
        nitrogen_stress=float(payload["nitrogen_stress"]),
        tmean_c=float(payload["tmean_c"]),
        precipitation_mm=float(payload["precipitation_mm"]),
        et0_mm=float(payload["et0_mm"]),
        radiation_mj_m2=float(payload["radiation_mj_m2"]),
    )


def _outcome_to_payload(outcome: CropOutcome) -> dict[str, Any]:
    return outcome.to_dict()


def _request_action(protocol_dir: Path, step_index: int) -> CropAction:
    request_path = protocol_dir / f"step_request_{step_index:04d}.json"
    if not request_path.exists():
        return CropAction()
    payload = json.loads(request_path.read_text(encoding="utf-8"))
    action = dict(payload.get("action", {}))
    return CropAction(
        irrigation_mm=float(action.get("irrigation_mm", 0.0)),
        nitrogen_kg_ha=float(action.get("nitrogen_kg_ha", 0.0)),
    )


def _compute_parser_outcome(
    *,
    run_dir: Path,
    scenario: SimulationScenario,
    total_irrigation_mm: float,
    total_nitrogen_kg_ha: float,
    cumulative_reward: float,
    operation_count: int,
) -> CropOutcome:
    parsed = DSSATOutputParser().parse(run_dir, scenario)
    outcome = parsed.outcome
    if outcome.total_irrigation_mm <= 0.0:
        outcome.total_irrigation_mm = round(total_irrigation_mm, 3)
    else:
        outcome.total_irrigation_mm = round(max(outcome.total_irrigation_mm, total_irrigation_mm), 3)
    if outcome.total_nitrogen_kg_ha <= 0.0:
        outcome.total_nitrogen_kg_ha = round(total_nitrogen_kg_ha, 3)
    else:
        outcome.total_nitrogen_kg_ha = round(max(outcome.total_nitrogen_kg_ha, total_nitrogen_kg_ha), 3)
    terminal_reward = reward_from_outcome(
        yield_kg_ha=outcome.yield_kg_ha,
        total_irrigation_mm=outcome.total_irrigation_mm,
        total_nitrogen_kg_ha=outcome.total_nitrogen_kg_ha,
        irrigation_budget_mm=scenario.irrigation_budget_mm,
        nitrogen_budget_kg_ha=scenario.nitrogen_budget_kg_ha,
        avg_water_stress=parsed.avg_water_stress,
        avg_nitrogen_stress=parsed.avg_nitrogen_stress,
        operation_count=operation_count,
        environmental_metrics=dict(outcome.environmental_metrics),
        weights=objective_reward_weights(scenario.objective_context.to_dict()),
        yield_floor_reference=scenario_yield_floor_reference(scenario),
        anti_collapse_guardrail=anti_collapse_preferences(scenario.objective_context.to_dict()),
        resource_settlement=resource_settlement_preferences(scenario.objective_context.to_dict()),
    )
    outcome.cumulative_reward = round(cumulative_reward + terminal_reward, 6)
    outcome.environmental_metrics = {
        **dict(outcome.environmental_metrics),
        "reward_contract": scenario.objective_context.reward_contract,
        "interactive_reward_source": "dssat_output_parser",
    }
    return outcome


def command_write_ready(args: argparse.Namespace) -> int:
    protocol_dir, session_manifest, interaction = _require_protocol_args(args)
    state_payload = _coerce_fields(_parse_simple_payload(Path(args.state_file)), STATE_FIELD_TYPES, label="State")
    run_dir = str(args.run_dir or interaction.get("run_dir", "")).strip()
    ready_payload = {
        "state": state_payload,
        "run_dir": run_dir,
        "info": _build_info_block(interaction, extra=_parse_info_tags(args.info_tag)),
    }
    _write_json(protocol_dir / "session_ready.json", ready_payload)
    scenario = _load_scenario_from_manifest(session_manifest)
    _save_progress(
        protocol_dir,
        {
            "scenario_id": scenario.scenario_id,
            "run_dir": run_dir,
            "last_state": state_payload,
            "cumulative_reward": 0.0,
            "total_irrigation_mm": 0.0,
            "total_nitrogen_kg_ha": 0.0,
            "operation_count": 0,
        },
    )
    return 0


def command_await_action(args: argparse.Namespace) -> int:
    protocol_dir, _, _ = _require_protocol_args(args)
    step_index = int(args.step_index)
    request_path = protocol_dir / f"step_request_{step_index:04d}.json"
    output_path = Path(args.output_action_file)
    deadline = time.monotonic() + float(args.timeout_seconds)
    while time.monotonic() < deadline:
        if (protocol_dir / "close_request.json").exists():
            _write_close_action_file(output_path, step_index)
            return 0
        if _protocol_has_terminal_outcome(protocol_dir):
            _write_close_action_file(output_path, step_index)
            return 0
        if request_path.exists():
            payload = json.loads(request_path.read_text(encoding="utf-8"))
            action = dict(payload.get("action", {}))
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(
                "\n".join(
                    [
                        f"step_index={int(payload.get('step_index', step_index))}",
                        f"decision_interval_days={int(payload.get('decision_interval_days', 0))}",
                        f"irrigation_mm={float(action.get('irrigation_mm', 0.0))}",
                        f"nitrogen_kg_ha={float(action.get('nitrogen_kg_ha', 0.0))}",
                        "close_requested=0",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            return 0
        time.sleep(float(args.poll_interval_seconds))
    raise TimeoutError(f"Timed out waiting for {request_path} in {protocol_dir}.")


def command_write_step_response(args: argparse.Namespace) -> int:
    protocol_dir, session_manifest, interaction = _require_protocol_args(args)
    state_payload = _coerce_fields(_parse_simple_payload(Path(args.state_file)), STATE_FIELD_TYPES, label="State")
    scenario = _load_scenario_from_manifest(session_manifest)
    progress = _load_progress(protocol_dir)
    previous_state_payload = dict(progress.get("last_state", {}))
    previous_state = _state_from_payload(previous_state_payload) if previous_state_payload else _state_from_payload(state_payload)
    next_state = _state_from_payload(state_payload)
    current_action = _request_action(protocol_dir, int(args.step_index))
    operation_count = int(progress.get("operation_count", 0))
    step_operation_count = 1 if current_action.irrigation_mm > 0.0 or current_action.nitrogen_kg_ha > 0.0 else 0
    cumulative_reward = float(progress.get("cumulative_reward", 0.0))
    computed_step_reward = step_reward(
        biomass_gain=max(0.0, next_state.biomass_kg_ha - previous_state.biomass_kg_ha),
        irrigation_mm=current_action.irrigation_mm,
        nitrogen_kg_ha=current_action.nitrogen_kg_ha,
        water_stress=previous_state.water_stress,
        nitrogen_stress=previous_state.nitrogen_stress,
        operation_count=step_operation_count,
        weights=objective_reward_weights(scenario.objective_context.to_dict()),
    )
    step_reward_value = float(args.reward) if args.reward is not None else computed_step_reward
    cumulative_reward = round(cumulative_reward + step_reward_value, 6)
    total_irrigation_mm = round(float(progress.get("total_irrigation_mm", 0.0)) + current_action.irrigation_mm, 6)
    total_nitrogen_kg_ha = round(float(progress.get("total_nitrogen_kg_ha", 0.0)) + current_action.nitrogen_kg_ha, 6)
    operation_count += step_operation_count
    response_payload: dict[str, Any] = {
        "next_state": state_payload,
        "reward": round(step_reward_value, 6),
        "done": bool(args.done),
        "daily_trace": [],
        "run_dir": str(args.run_dir or interaction.get("run_dir", "")).strip(),
        "info": _build_info_block(
            interaction,
            days_executed=int(args.days_executed),
            extra=_parse_info_tags(args.info_tag),
        ),
    }
    if args.daily_trace_file:
        trace_payload = _parse_simple_payload(Path(args.daily_trace_file))
        if not isinstance(trace_payload, list):
            raise RuntimeError("Daily trace payload must be a JSON list.")
        response_payload["daily_trace"] = trace_payload
    elif bool(args.done):
        response_payload["daily_trace"] = [{"day_index": next_state.day_index, "reward": round(step_reward_value, 6), "done": True}]
    if args.final_outcome_file:
        outcome_payload = _coerce_fields(
            _parse_simple_payload(Path(args.final_outcome_file)),
            OUTCOME_FIELD_TYPES,
            label="Outcome",
        )
        environmental_metrics = _parse_simple_payload(Path(args.final_outcome_file)).get("environmental_metrics", {})
        outcome_payload["environmental_metrics"] = environmental_metrics
        response_payload["final_outcome"] = outcome_payload
    elif bool(args.done):
        run_dir = Path(str(args.run_dir or interaction.get("run_dir", "")).strip() or ".").resolve()
        outcome = _compute_parser_outcome(
            run_dir=run_dir,
            scenario=scenario,
            total_irrigation_mm=total_irrigation_mm,
            total_nitrogen_kg_ha=total_nitrogen_kg_ha,
            cumulative_reward=cumulative_reward,
            operation_count=operation_count,
        )
        response_payload["final_outcome"] = _outcome_to_payload(outcome)
        response_payload["reward"] = round(outcome.cumulative_reward - float(progress.get("cumulative_reward", 0.0)), 6)
        cumulative_reward = outcome.cumulative_reward
    progress_payload = {
        "scenario_id": scenario.scenario_id,
        "run_dir": response_payload["run_dir"],
        "last_state": state_payload,
        "cumulative_reward": cumulative_reward,
        "total_irrigation_mm": total_irrigation_mm,
        "total_nitrogen_kg_ha": total_nitrogen_kg_ha,
        "operation_count": operation_count,
    }
    if "final_outcome" in response_payload:
        progress_payload["final_outcome"] = response_payload["final_outcome"]
    _write_json(protocol_dir / f"step_response_{int(args.step_index):04d}.json", response_payload)
    _save_progress(protocol_dir, progress_payload)
    return 0


def command_write_final_outcome(args: argparse.Namespace) -> int:
    protocol_dir, session_manifest, interaction = _require_protocol_args(args)
    progress = _load_progress(protocol_dir)
    if isinstance(progress.get("final_outcome"), dict):
        _write_json(protocol_dir / "final_outcome.json", dict(progress["final_outcome"]))
        return 0
    scenario = _load_scenario_from_manifest(session_manifest)
    run_dir = Path(str(interaction.get("run_dir", "")).strip() or progress.get("run_dir") or ".").resolve()
    try:
        outcome = _compute_parser_outcome(
            run_dir=run_dir,
            scenario=scenario,
            total_irrigation_mm=float(progress.get("total_irrigation_mm", 0.0)),
            total_nitrogen_kg_ha=float(progress.get("total_nitrogen_kg_ha", 0.0)),
            cumulative_reward=float(progress.get("cumulative_reward", 0.0)),
            operation_count=int(progress.get("operation_count", 0)),
        )
        payload = _outcome_to_payload(outcome)
    except Exception:
        raw_payload = _parse_simple_payload(Path(args.outcome_file))
        outcome_payload = _coerce_fields(raw_payload, OUTCOME_FIELD_TYPES, label="Outcome")
        outcome_payload["environmental_metrics"] = raw_payload.get("environmental_metrics", {})
        payload = outcome_payload
    else:
        progress["final_outcome"] = payload
        progress["cumulative_reward"] = payload["cumulative_reward"]
        _save_progress(protocol_dir, progress)
    _write_json(protocol_dir / "final_outcome.json", payload)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    command = str(args.command)
    if command == "write-ready":
        return command_write_ready(args)
    if command == "await-action":
        return command_await_action(args)
    if command == "write-step-response":
        return command_write_step_response(args)
    if command == "write-final-outcome":
        return command_write_final_outcome(args)
    raise RuntimeError(f"Unsupported command: {command}")
