from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import time
from typing import Any


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Boundary-only stand-in runtime for the patched DSSAT interactive protocol. "
            "It validates the launch contract and serves a minimal ready/step/close loop."
        )
    )
    parser.add_argument(
        "--idle-timeout-seconds",
        type=float,
        default=30.0,
        help="Maximum idle wait while polling for step/close requests.",
    )
    parser.add_argument(
        "--poll-interval-seconds",
        type=float,
        default=0.2,
        help="Polling interval for protocol files.",
    )
    parser.add_argument(
        "--mark-done-after-step",
        action="store_true",
        help="Return done=true immediately after the first step response.",
    )
    return parser


def require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required interactive runtime env var: {name}")
    return value


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def load_contract() -> tuple[dict[str, Any], dict[str, Any], Path, dict[str, str]]:
    protocol_dir = Path(require_env("DSSAT_INTERACTIVE_PROTOCOL_DIR")).resolve()
    manifest_path = Path(require_env("DSSAT_INTERACTIVE_SESSION_MANIFEST")).resolve()
    manifest = read_json(manifest_path)
    interaction = dict(manifest.get("interaction", {}))
    required = {
        "protocol_version": require_env("DSSAT_INTERACTIVE_PROTOCOL_VERSION"),
        "engine_name": require_env("DSSAT_INTERACTIVE_ENGINE_NAME"),
        "backend_mode": require_env("DSSAT_INTERACTIVE_BACKEND_MODE"),
        "runtime_role": require_env("DSSAT_INTERACTIVE_RUNTIME_ROLE"),
        "run_dir": require_env("DSSAT_INTERACTIVE_RUN_DIR"),
        "crop_name": require_env("DSSAT_INTERACTIVE_CROP_NAME"),
        "action_channels": require_env("DSSAT_INTERACTIVE_ACTION_CHANNELS"),
        "decision_interval_days": require_env("DSSAT_INTERACTIVE_DECISION_INTERVAL_DAYS"),
        "state_interface_contract_json": require_env("DSSAT_INTERACTIVE_STATE_INTERFACE_CONTRACT_JSON"),
    }
    return manifest, interaction, protocol_dir, required


def validate_contract(manifest: dict[str, Any], interaction: dict[str, Any], required: dict[str, str]) -> dict[str, Any]:
    if not interaction:
        raise RuntimeError("Interactive session manifest missing interaction block.")
    expected_contract = json.loads(required["state_interface_contract_json"])
    observed_contract = interaction.get("state_interface_contract", {})
    observed_channels = ",".join(interaction.get("action_channels", []))
    observed = {
        "protocol_version": str(interaction.get("protocol_version", "")),
        "engine_name": str(interaction.get("engine_name", "")),
        "backend_mode": str(interaction.get("backend_mode", "")),
        "runtime_role": str(interaction.get("runtime_role", "")),
        "run_dir": str(interaction.get("run_dir", "")),
        "crop_name": str(interaction.get("crop_name", "")),
        "action_channels": observed_channels,
        "decision_interval_days": str(interaction.get("decision_interval_days", "")),
        "state_interface_contract_json": json.dumps(observed_contract, ensure_ascii=False, separators=(",", ":")),
    }
    for key, expected in required.items():
        if observed[key] != expected:
            raise RuntimeError(
                f"Interactive contract mismatch for {key}: expected {expected!r}, got {observed[key]!r}."
            )
    scenario = dict(manifest.get("scenario", {}))
    if not scenario:
        raise RuntimeError("Interactive session manifest missing scenario payload.")
    return expected_contract


def build_state(day_index: int, crop_name: str) -> dict[str, Any]:
    base_nitrogen = 120.0 if crop_name == "maize" else 90.0
    return {
        "day_index": day_index,
        "stage": "vegetative",
        "stage_index": 1,
        "soil_moisture": 0.50,
        "root_zone_water_mm": 180.0,
        "soil_nitrogen_kg_ha": base_nitrogen,
        "canopy_cover": min(0.95, 0.18 + 0.02 * day_index),
        "biomass_kg_ha": 100.0 + 12.0 * day_index,
        "water_stress": 0.10,
        "nitrogen_stress": 0.10,
        "tmean_c": 22.0,
        "precipitation_mm": 0.0,
        "et0_mm": 4.0,
        "radiation_mj_m2": 18.0,
    }


def build_final_outcome() -> dict[str, Any]:
    return {
        "yield_kg_ha": 7000.0,
        "biomass_kg_ha": 15000.0,
        "total_irrigation_mm": 0.0,
        "total_nitrogen_kg_ha": 0.0,
        "water_use_efficiency": 0.0,
        "nitrogen_use_efficiency": 0.0,
        "cumulative_reward": 0.0,
        "environmental_metrics": {},
    }


def main() -> int:
    args = build_parser().parse_args()
    manifest, interaction, protocol_dir, required = load_contract()
    validate_contract(manifest, interaction, required)
    protocol_dir.mkdir(parents=True, exist_ok=True)

    ready_payload = {
        "state": build_state(day_index=0, crop_name=required["crop_name"]),
        "run_dir": required["run_dir"],
        "info": {
            "protocol_version": required["protocol_version"],
            "engine_name": required["engine_name"],
            "backend_mode": required["backend_mode"],
            "runtime_role": required["runtime_role"],
            "run_dir_env": required["run_dir"],
            "crop_name": required["crop_name"],
            "action_channels": required["action_channels"],
            "decision_interval_days": required["decision_interval_days"],
            "state_interface_contract_json": required["state_interface_contract_json"],
            "probe_mode": "boundary_probe",
        },
    }
    write_json(protocol_dir / "runtime_boundary_capture.json", ready_payload["info"])
    write_json(protocol_dir / "session_ready.json", ready_payload)

    idle_deadline = time.monotonic() + args.idle_timeout_seconds
    step_index = 0
    while time.monotonic() < idle_deadline:
        close_request_path = protocol_dir / "close_request.json"
        if close_request_path.exists():
            write_json(protocol_dir / "final_outcome.json", build_final_outcome())
            return 0

        request_path = protocol_dir / f"step_request_{step_index:04d}.json"
        if request_path.exists():
            request_payload = read_json(request_path)
            requested_interval = int(request_payload.get("decision_interval_days", required["decision_interval_days"]))
            next_day = max(0, requested_interval * (step_index + 1))
            response_payload = {
                "next_state": build_state(day_index=next_day, crop_name=required["crop_name"]),
                "reward": 0.0,
                "done": bool(args.mark_done_after_step),
                "daily_trace": [
                    {
                        "day_index": day,
                        "reward": 0.0,
                        "done": False,
                    }
                    for day in range(max(0, next_day - requested_interval), next_day)
                ],
                "run_dir": required["run_dir"],
                "info": {
                    "protocol_version": required["protocol_version"],
                    "engine_name": required["engine_name"],
                    "backend_mode": required["backend_mode"],
                    "runtime_role": required["runtime_role"],
                    "days_executed": requested_interval,
                    "probe_mode": "boundary_probe",
                },
            }
            if args.mark_done_after_step:
                response_payload["final_outcome"] = build_final_outcome()
            write_json(protocol_dir / f"step_response_{step_index:04d}.json", response_payload)
            step_index += 1
            idle_deadline = time.monotonic() + args.idle_timeout_seconds
            continue

        time.sleep(args.poll_interval_seconds)

    raise TimeoutError(
        f"Boundary probe timed out waiting for step/close requests in {protocol_dir} "
        f"after {args.idle_timeout_seconds} seconds."
    )


if __name__ == "__main__":
    raise SystemExit(main())
