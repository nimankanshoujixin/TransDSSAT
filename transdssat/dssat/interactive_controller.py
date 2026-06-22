from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import subprocess
import time
from typing import Any, Protocol

from transdssat.dssat.config import DSSATRunConfig, split_command
from transdssat.domain import CropAction, CropOutcome, CropState
from transdssat.environments.adapters import OfficialDSSATEnvironment
from transdssat.scenarios import SimulationScenario
from transdssat.season import SeasonPolicy, StageDecision

from .interactive import (
    build_interactive_protocol_metadata,
    FileSystemInteractiveProtocol,
    INTERACTIVE_ACTION_CHANNELS,
    INTERACTIVE_PROTOCOL_VERSION,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(slots=True)
class InteractiveEvaluationSnapshot:
    trajectory_states: list[CropState]
    outcome: CropOutcome
    cumulative_reward: float
    daily_trace: list[dict[str, Any]]
    run_dir: str


class InteractiveReplayEvaluator(Protocol):
    def evaluate_actions(self, actions: list[StageDecision]) -> InteractiveEvaluationSnapshot:
        ...


class InteractiveControllerDriver(Protocol):
    def run(self) -> None:
        ...


INTERACTIVE_DRIVER_MODE_REPLAY_BRIDGE = "replay_bridge"
INTERACTIVE_DRIVER_MODE_PATCHED_SUBPROCESS = "patched_runtime_subprocess"


class OfficialReplayEvaluator:
    def __init__(self, scenario: SimulationScenario) -> None:
        self.scenario = scenario
        self.official_env = OfficialDSSATEnvironment()

    def evaluate_actions(self, actions: list[StageDecision]) -> InteractiveEvaluationSnapshot:
        policy = SeasonPolicy(
            policy_id=f"{self.scenario.scenario_id}-interactive-controller",
            scenario_id=self.scenario.scenario_id,
            actions=list(actions),
        )
        result = self.official_env.evaluate_policy(self.scenario, policy)
        trajectory_states = [result.trajectory.steps[0].state] + [step.next_state for step in result.trajectory.steps]
        daily_trace = [
            {
                "day_index": step.state.day_index,
                "reward": step.reward,
                "done": step.done,
                "engine_info": step.info,
            }
            for step in result.trajectory.steps
        ]
        return InteractiveEvaluationSnapshot(
            trajectory_states=trajectory_states,
            outcome=result.trajectory.outcome,
            cumulative_reward=result.reward,
            daily_trace=daily_trace,
            run_dir=result.run_dir,
        )


class ReplayBridgeInteractiveController:
    """
    Transitional external-process controller for official DSSAT.

    This keeps the transport/controller boundary real while the evaluator still
    uses whole-season official DSSAT replay under the hood. The next runtime
    step can swap only the evaluator with a true patched daily DSSAT loop.
    """

    def __init__(
        self,
        *,
        scenario: SimulationScenario,
        protocol: FileSystemInteractiveProtocol,
        evaluator: InteractiveReplayEvaluator,
        poll_interval_seconds: float = 0.2,
    ) -> None:
        self.scenario = scenario
        self.protocol = protocol
        self.evaluator = evaluator
        self.poll_interval_seconds = poll_interval_seconds
        self.executed_actions: list[StageDecision] = []
        self.current_snapshot = self.evaluator.evaluate_actions([])
        self.current_state = self.current_snapshot.trajectory_states[0]
        self.cumulative_reward = 0.0
        self.current_step_index = 0
        self.interaction_metadata = build_interactive_protocol_metadata(
            scenario,
            run_dir=Path(self.current_snapshot.run_dir or "."),
            runtime_role="patched",
            poll_interval_seconds=poll_interval_seconds,
            backend_mode="season_replay_wrapper_external_controller",
        )

    def run(self) -> None:
        self.protocol.root_dir.mkdir(parents=True, exist_ok=True)
        self._write_json(
            self.protocol.session_ready_path,
            {
                "state": self.current_state.to_dict(),
                "run_dir": self.current_snapshot.run_dir,
                "info": dict(self.interaction_metadata),
            },
        )
        while True:
            if self.protocol.close_request_path.exists():
                self._write_json(self.protocol.final_outcome_path, self.current_snapshot.outcome.to_dict())
                return

            request_path = self.protocol.request_path(self.current_step_index)
            if request_path.exists():
                payload = self._read_json(request_path)
                response = self._handle_step_request(payload)
                self._write_json(self.protocol.response_path(self.current_step_index), response)
                self.current_step_index += 1
                continue

            time.sleep(self.poll_interval_seconds)

    def _handle_step_request(self, payload: dict[str, Any]) -> dict[str, Any]:
        decision_interval_days = int(payload.get("decision_interval_days", self.scenario.decision_context.decision_interval_days))
        action = CropAction(
            irrigation_mm=float(payload.get("action", {}).get("irrigation_mm", 0.0)),
            nitrogen_kg_ha=float(payload.get("action", {}).get("nitrogen_kg_ha", 0.0)),
        )
        decision_day = self.current_state.day_index
        if action.irrigation_mm > 0.0 or action.nitrogen_kg_ha > 0.0:
            self.executed_actions.append(
                StageDecision(
                    stage=self.current_state.stage,
                    day_index=decision_day,
                    date=self._decision_date(decision_day),
                    irrigation_mm=round(action.irrigation_mm, 3),
                    nitrogen_kg_ha=round(action.nitrogen_kg_ha, 3),
                )
            )
        previous_reward = self.cumulative_reward
        self.current_snapshot = self.evaluator.evaluate_actions(self.executed_actions)
        current_index = self._state_index_for_day(decision_day + decision_interval_days)
        self.current_state = self.current_snapshot.trajectory_states[current_index]
        self.cumulative_reward = self.current_snapshot.cumulative_reward
        reward = round(self.cumulative_reward - previous_reward, 6)
        done = current_index >= len(self.current_snapshot.trajectory_states) - 1
        response = {
            "next_state": self.current_state.to_dict(),
            "reward": reward,
            "done": done,
            "daily_trace": self.current_snapshot.daily_trace[decision_day:current_index],
            "run_dir": self.current_snapshot.run_dir,
            "info": {
                "engine_name": "dssat_official",
                "backend_mode": "season_replay_wrapper_external_controller",
                "official_cumulative_reward": round(self.cumulative_reward, 6),
            },
        }
        if done:
            response["final_outcome"] = self.current_snapshot.outcome.to_dict()
        return response

    def _decision_date(self, day_index: int) -> str:
        from datetime import date, timedelta

        planting = date.fromisoformat(self.scenario.planting_date)
        return (planting + timedelta(days=day_index)).isoformat()

    def _state_index_for_day(self, day_index: int) -> int:
        return max(0, min(day_index, len(self.current_snapshot.trajectory_states) - 1))

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        for _ in range(20):
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                time.sleep(0.01)
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def _write_json(path: Path, payload: dict[str, Any]) -> None:
        rendered = json.dumps(payload, indent=2, ensure_ascii=False)
        temp_path = path.with_name(f"{path.name}.tmp")
        temp_path.write_text(rendered, encoding="utf-8")
        temp_path.replace(path)


def load_protocol_from_manifest(manifest: dict[str, Any]) -> FileSystemInteractiveProtocol:
    protocol_payload = dict(manifest["protocol"])
    return FileSystemInteractiveProtocol(root_dir=Path(protocol_payload["root_dir"]))


def load_scenario_from_manifest(manifest: dict[str, Any]) -> SimulationScenario:
    scenario_payload = manifest.get("scenario")
    if not isinstance(scenario_payload, dict):
        raise RuntimeError("Interactive session manifest did not include a full scenario payload.")
    return SimulationScenario.from_dict(scenario_payload)


def load_interaction_metadata_from_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    interaction_payload = manifest.get("interaction")
    if not isinstance(interaction_payload, dict):
        raise RuntimeError("Interactive session manifest did not include interaction metadata.")
    return dict(interaction_payload)


def validate_interaction_metadata(interaction: dict[str, Any]) -> dict[str, Any]:
    protocol_version = str(interaction.get("protocol_version", "")).strip()
    if protocol_version != INTERACTIVE_PROTOCOL_VERSION:
        raise RuntimeError(
            "Interactive session manifest protocol version mismatch: "
            f"expected {INTERACTIVE_PROTOCOL_VERSION}, got {protocol_version or '<missing>'}."
        )
    engine_name = str(interaction.get("engine_name", "")).strip()
    if engine_name != "dssat_official":
        raise RuntimeError(
            f"Interactive session manifest engine_name must be dssat_official, got {engine_name or '<missing>'}."
        )
    action_channels = tuple(str(item).strip() for item in interaction.get("action_channels", []))
    if action_channels != INTERACTIVE_ACTION_CHANNELS:
        raise RuntimeError(
            "Interactive session manifest action_channels mismatch: "
            f"expected {list(INTERACTIVE_ACTION_CHANNELS)}, got {list(action_channels)}."
        )
    backend_mode = str(interaction.get("backend_mode", "")).strip()
    allowed_backend_modes = {"interactive_patched", "season_replay_wrapper_external_controller"}
    if backend_mode not in allowed_backend_modes:
        raise RuntimeError(
            f"Interactive session manifest backend_mode must be one of {sorted(allowed_backend_modes)}, "
            f"got {backend_mode or '<missing>'}."
        )
    runtime_role = str(interaction.get("runtime_role", "")).strip().lower()
    if runtime_role not in {"patched", "vanilla"}:
        raise RuntimeError(
            f"Interactive session manifest runtime_role must be patched or vanilla, got {runtime_role or '<missing>'}."
        )
    return {
        **interaction,
        "protocol_version": protocol_version,
        "engine_name": engine_name,
        "backend_mode": backend_mode,
        "runtime_role": runtime_role,
        "action_channels": list(action_channels),
    }


def resolve_interactive_driver_mode(
    requested_mode: str | None,
    *,
    interaction: dict[str, Any],
) -> str:
    normalized = str(
        requested_mode
        or os.environ.get("TRANSDSSAT_INTERACTIVE_DRIVER_MODE")
        or INTERACTIVE_DRIVER_MODE_REPLAY_BRIDGE
    ).strip().lower()
    if normalized == "auto":
        normalized = INTERACTIVE_DRIVER_MODE_REPLAY_BRIDGE
    allowed_modes = {
        INTERACTIVE_DRIVER_MODE_REPLAY_BRIDGE,
        INTERACTIVE_DRIVER_MODE_PATCHED_SUBPROCESS,
    }
    if normalized not in allowed_modes:
        raise RuntimeError(
            f"Unsupported interactive controller driver mode: {normalized}. "
            f"Expected one of {sorted(allowed_modes)}."
        )
    if normalized == INTERACTIVE_DRIVER_MODE_PATCHED_SUBPROCESS and interaction["backend_mode"] != "interactive_patched":
        raise RuntimeError(
            "Patched runtime subprocess driver requires backend_mode=interactive_patched in the session manifest."
        )
    return normalized


def build_runtime_subprocess_env(
    *,
    protocol: FileSystemInteractiveProtocol,
    manifest_path: Path,
    interaction: dict[str, Any],
) -> dict[str, str]:
    env = dict(os.environ)
    state_interface_contract = interaction.get("state_interface_contract", {})
    env.update(
        {
            "DSSAT_INTERACTIVE_MODE": "1",
            "DSSAT_INTERACTIVE_PROTOCOL_DIR": str(protocol.root_dir),
            "DSSAT_INTERACTIVE_SESSION_MANIFEST": str(manifest_path),
            "DSSAT_INTERACTIVE_PROTOCOL_VERSION": str(interaction["protocol_version"]),
            "DSSAT_INTERACTIVE_ENGINE_NAME": str(interaction["engine_name"]),
            "DSSAT_INTERACTIVE_BACKEND_MODE": str(interaction["backend_mode"]),
            "DSSAT_INTERACTIVE_RUNTIME_ROLE": str(interaction["runtime_role"]),
            "DSSAT_INTERACTIVE_RUN_DIR": str(interaction["run_dir"]),
            "DSSAT_INTERACTIVE_CROP_NAME": str(interaction["crop_name"]),
            "DSSAT_INTERACTIVE_ACTION_CHANNELS": ",".join(interaction["action_channels"]),
            "DSSAT_INTERACTIVE_DECISION_INTERVAL_DAYS": str(interaction["decision_interval_days"]),
            "DSSAT_INTERACTIVE_HELPER_COMMAND": (
                f"python {PROJECT_ROOT / 'scripts' / 'dssat_interactive_protocol_helper.py'}"
            ),
            "DSSAT_INTERACTIVE_STATE_INTERFACE_CONTRACT_JSON": json.dumps(
                state_interface_contract,
                ensure_ascii=False,
                separators=(",", ":"),
            ),
        }
    )
    return env


class PatchedRuntimeSubprocessController:
    def __init__(
        self,
        *,
        manifest_path: Path,
        scenario: SimulationScenario,
        protocol: FileSystemInteractiveProtocol,
        interaction: dict[str, Any],
    ) -> None:
        self.manifest_path = manifest_path
        self.scenario = scenario
        self.protocol = protocol
        self.interaction = interaction

    def run(self) -> None:
        config = DSSATRunConfig.from_env(runtime_role=self.interaction["runtime_role"])
        command_template = config.run_command
        if not command_template:
            raise RuntimeError(
                "Patched runtime subprocess driver requires a DSSAT run command. "
                "Set DSSAT_PATCHED_RUN_COMMAND or DSSAT_RUN_COMMAND."
            )
        run_dir = Path(self.interaction["run_dir"]).resolve()
        command = command_template.format(
            run_dir=str(run_dir),
            manifest=str(self.manifest_path),
            policy=str(run_dir / "transdssat_policy.tsv"),
            scenario=str(run_dir / "transdssat_scenario.json"),
            crop=self.scenario.crop_spec.crop_name,
            experiment=self.scenario.experiment_file,
            project_root=str(PROJECT_ROOT),
            repo_root=str(PROJECT_ROOT),
        )
        argv = split_command(command)
        if not argv:
            raise RuntimeError("Patched runtime subprocess command resolved to an empty command.")
        env = build_runtime_subprocess_env(
            protocol=self.protocol,
            manifest_path=self.manifest_path,
            interaction=self.interaction,
        )
        result = subprocess.run(
            argv,
            cwd=run_dir,
            env=env,
            check=False,
            timeout=config.timeout_seconds,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"Patched DSSAT runtime subprocess exited with code {result.returncode}. "
                f"Run dir: {run_dir}."
            )


def build_interactive_controller_driver(
    *,
    driver_mode: str,
    manifest_path: Path,
    scenario: SimulationScenario,
    protocol: FileSystemInteractiveProtocol,
    interaction: dict[str, Any],
) -> InteractiveControllerDriver:
    if driver_mode == INTERACTIVE_DRIVER_MODE_PATCHED_SUBPROCESS:
        return PatchedRuntimeSubprocessController(
            manifest_path=manifest_path,
            scenario=scenario,
            protocol=protocol,
            interaction=interaction,
        )
    return ReplayBridgeInteractiveController(
        scenario=scenario,
        protocol=protocol,
        evaluator=OfficialReplayEvaluator(scenario),
        poll_interval_seconds=float(interaction.get("poll_interval_seconds", 0.2)),
    )
