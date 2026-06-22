from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
import subprocess
import time
from typing import Any, Protocol

from transdssat.dssat.config import DSSATRunConfig, split_command
from transdssat.dssat.inputs import DSSATInputBuilder
from transdssat.domain import CropAction, CropOutcome, CropState
from transdssat.scenarios import SimulationScenario
from transdssat.season import SeasonPolicy

INTERACTIVE_PROTOCOL_VERSION = "patched-dssat-v1"
INTERACTIVE_ACTION_CHANNELS = ("irrigation_mm", "nitrogen_kg_ha")
INTERACTIVE_CONTROLLER_SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "run_interactive_dssat_controller.py"
PROJECT_ROOT = INTERACTIVE_CONTROLLER_SCRIPT_PATH.parents[1]


@dataclass(slots=True)
class InteractiveDSSATResetResult:
    state: CropState
    run_dir: str = ""
    info: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class InteractiveDSSATStepResult:
    next_state: CropState
    reward: float = 0.0
    done: bool = False
    daily_trace: list[dict[str, Any]] = field(default_factory=list)
    final_outcome: CropOutcome | None = None
    run_dir: str = ""
    info: dict[str, Any] = field(default_factory=dict)


class InteractiveDSSATTransport(Protocol):
    def start_session(self, scenario: SimulationScenario) -> InteractiveDSSATResetResult:
        ...

    def step_session(
        self,
        action: CropAction,
        *,
        decision_interval_days: int,
    ) -> InteractiveDSSATStepResult:
        ...

    def close_session(self) -> CropOutcome | None:
        ...


@dataclass(slots=True)
class FileSystemInteractiveProtocol:
    root_dir: Path

    @property
    def session_manifest_path(self) -> Path:
        return self.root_dir / "session_manifest.json"

    @property
    def session_ready_path(self) -> Path:
        return self.root_dir / "session_ready.json"

    @property
    def final_outcome_path(self) -> Path:
        return self.root_dir / "final_outcome.json"

    @property
    def close_request_path(self) -> Path:
        return self.root_dir / "close_request.json"

    def request_path(self, step_index: int) -> Path:
        return self.root_dir / f"step_request_{step_index:04d}.json"

    def response_path(self, step_index: int) -> Path:
        return self.root_dir / f"step_response_{step_index:04d}.json"

    def to_dict(self) -> dict[str, str]:
        return {
            "root_dir": str(self.root_dir),
            "session_manifest_path": str(self.session_manifest_path),
            "session_ready_path": str(self.session_ready_path),
            "final_outcome_path": str(self.final_outcome_path),
            "close_request_path": str(self.close_request_path),
            "request_glob": str(self.root_dir / "step_request_*.json"),
            "response_glob": str(self.root_dir / "step_response_*.json"),
        }


@dataclass(slots=True)
class FileSystemInteractiveControllerConfig:
    launch_command: str
    log_filename: str = "interactive_controller.log"
    poll_interval_seconds: float = 0.2
    ready_timeout_seconds: float = 60.0
    step_timeout_seconds: float = 60.0
    close_timeout_seconds: float = 30.0


def build_interactive_protocol_metadata(
    scenario: SimulationScenario,
    *,
    run_dir: Path,
    runtime_role: str,
    poll_interval_seconds: float,
    backend_mode: str = "interactive_patched",
) -> dict[str, Any]:
    return {
        "protocol_version": INTERACTIVE_PROTOCOL_VERSION,
        "engine_name": scenario.engine_name,
        "backend_mode": backend_mode,
        "runtime_role": runtime_role,
        "run_dir": str(run_dir),
        "crop_name": scenario.crop_spec.crop_name,
        "action_channels": list(INTERACTIVE_ACTION_CHANNELS),
        "decision_interval_days": scenario.decision_context.decision_interval_days,
        "state_interface_contract": scenario.state_interface_contract_dict(),
        "poll_interval_seconds": poll_interval_seconds,
    }


class PatchedInteractiveDSSATSession:
    """
    Python-side session wrapper for the future patched official DSSAT backend.

    The transport is intentionally abstract here. The real implementation can be
    backed later by file polling, sockets, ZeroMQ, shared memory, or another
    patched-runtime control channel without changing PPO-facing step-wise code.
    """

    def __init__(
        self,
        scenario: SimulationScenario,
        transport: InteractiveDSSATTransport,
    ) -> None:
        self.scenario = scenario
        self.transport = transport
        self.started = False
        self.last_run_dir = ""
        self._cached_final_outcome: CropOutcome | None = None

    def reset(self) -> InteractiveDSSATResetResult:
        result = self.transport.start_session(self.scenario)
        self.started = True
        self.last_run_dir = result.run_dir
        self._cached_final_outcome = None
        return result

    def step(
        self,
        action: CropAction,
        *,
        decision_interval_days: int,
    ) -> InteractiveDSSATStepResult:
        if not self.started:
            raise RuntimeError("Interactive DSSAT session has not been reset.")
        result = self.transport.step_session(
            action,
            decision_interval_days=decision_interval_days,
        )
        self.last_run_dir = result.run_dir or self.last_run_dir
        if result.final_outcome is not None:
            self._cached_final_outcome = result.final_outcome
        return result

    def final_outcome(self) -> CropOutcome:
        if self._cached_final_outcome is not None:
            return self._cached_final_outcome
        outcome = self.transport.close_session()
        if outcome is None:
            raise RuntimeError("Interactive DSSAT transport did not provide a final outcome.")
        self._cached_final_outcome = outcome
        return outcome


class FileSystemInteractiveDSSATTransport:
    """
    File-based control channel for the future patched DSSAT runtime.

    The patched runtime side is expected to:
    1. read `session_manifest.json`
    2. write `session_ready.json` containing the initial state
    3. for each `step_request_XXXX.json`, write the matching `step_response_XXXX.json`
    4. on shutdown, write `final_outcome.json`
    """

    def __init__(
        self,
        *,
        protocol: FileSystemInteractiveProtocol,
        controller: FileSystemInteractiveControllerConfig,
        run_dir: Path,
    ) -> None:
        self.protocol = protocol
        self.controller = controller
        self.run_dir = run_dir
        self.process: subprocess.Popen[str] | None = None
        self.current_step_index = 0
        self._last_cumulative_reward = 0.0
        self.controller_log_path = self.run_dir / self.controller.log_filename
        self._controller_log_handle: Any | None = None

    def start_session(self, scenario: SimulationScenario) -> InteractiveDSSATResetResult:
        self.protocol.root_dir.mkdir(parents=True, exist_ok=True)
        self._cleanup_protocol_dir()
        protocol_metadata = build_interactive_protocol_metadata(
            scenario,
            run_dir=self.run_dir,
            runtime_role="patched",
            poll_interval_seconds=self.controller.poll_interval_seconds,
        )
        manifest = {
            "scenario_id": scenario.scenario_id,
            "protocol": self.protocol.to_dict(),
            "scenario": scenario.to_dict(),
            "decision_context": scenario.decision_context.to_dict(),
            "interaction": protocol_metadata,
        }
        _write_json_atomic(
            self.protocol.session_manifest_path,
            manifest,
        )
        self.process = self._launch_controller()
        self.current_step_index = 0
        self._last_cumulative_reward = 0.0
        payload = self._wait_for_json(
            self.protocol.session_ready_path,
            timeout_seconds=self.controller.ready_timeout_seconds,
            timeout_label="interactive session ready state",
        )
        return InteractiveDSSATResetResult(
            state=_state_from_payload(payload["state"]),
            run_dir=str(payload.get("run_dir", self.run_dir)),
            info=dict(payload.get("info", {})),
        )

    def step_session(
        self,
        action: CropAction,
        *,
        decision_interval_days: int,
    ) -> InteractiveDSSATStepResult:
        request_path = self.protocol.request_path(self.current_step_index)
        response_path = self.protocol.response_path(self.current_step_index)
        _write_json_atomic(
            request_path,
            {
                "step_index": self.current_step_index,
                "decision_interval_days": decision_interval_days,
                "action": action.to_dict(),
            },
        )
        payload = self._wait_for_json(
            response_path,
            timeout_seconds=self.controller.step_timeout_seconds,
            timeout_label=f"interactive step response {self.current_step_index}",
        )
        final_outcome_payload = payload.get("final_outcome")
        done = bool(payload.get("done", False))
        if done:
            self._finalize_terminal_session(expect_final_outcome_file=final_outcome_payload is None)
        self.current_step_index += 1
        if final_outcome_payload is not None:
            self._last_cumulative_reward = float(final_outcome_payload.get("cumulative_reward", self._last_cumulative_reward))
        else:
            self._last_cumulative_reward = round(self._last_cumulative_reward + float(payload.get("reward", 0.0)), 6)
        return InteractiveDSSATStepResult(
            next_state=_state_from_payload(payload["next_state"]),
            reward=float(payload.get("reward", 0.0)),
            done=done,
            daily_trace=list(payload.get("daily_trace", [])),
            final_outcome=None if final_outcome_payload is None else _outcome_from_payload(final_outcome_payload),
            run_dir=str(payload.get("run_dir", self.run_dir)),
            info=dict(payload.get("info", {})),
        )

    def close_session(self) -> CropOutcome | None:
        _write_json_atomic(
            self.protocol.close_request_path,
            {"close": True},
        )
        payload = self._wait_for_json(
            self.protocol.final_outcome_path,
            timeout_seconds=self.controller.close_timeout_seconds,
            timeout_label="interactive final outcome",
        )
        self._cleanup_process()
        self._last_cumulative_reward = float(payload.get("cumulative_reward", self._last_cumulative_reward))
        return _outcome_from_payload(payload) if payload else None

    def _launch_controller(self) -> subprocess.Popen[str]:
        argv = self.controller.launch_command.format(
            protocol_dir=str(self.protocol.root_dir),
            run_dir=str(self.run_dir),
            session_manifest=str(self.protocol.session_manifest_path),
            controller_script=str(INTERACTIVE_CONTROLLER_SCRIPT_PATH),
            project_root=str(INTERACTIVE_CONTROLLER_SCRIPT_PATH.parents[1]),
            repo_root=str(INTERACTIVE_CONTROLLER_SCRIPT_PATH.parents[1]),
        )
        self.controller_log_path.parent.mkdir(parents=True, exist_ok=True)
        self._controller_log_handle = self.controller_log_path.open("a", encoding="utf-8")
        return subprocess.Popen(  # noqa: S603
            argv,
            cwd=self.run_dir,
            shell=True,
            stdout=self._controller_log_handle,
            stderr=subprocess.STDOUT,
            text=True,
        )

    def _cleanup_protocol_dir(self) -> None:
        for path in self.protocol.root_dir.glob("*.json"):
            path.unlink(missing_ok=True)

    def _cleanup_process(self) -> None:
        if self.process is None:
            return
        try:
            self.process.wait(timeout=1.0)
        except subprocess.TimeoutExpired:
            self.process.terminate()
            try:
                self.process.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=1.0)
        finally:
            if self._controller_log_handle is not None:
                self._controller_log_handle.close()
                self._controller_log_handle = None
            self.process = None

    def _wait_for_json(self, path: Path, *, timeout_seconds: float, timeout_label: str) -> dict[str, Any]:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            if path.exists():
                try:
                    return json.loads(path.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    pass
            if self.process is not None and self.process.poll() is not None:
                recovered = self._recover_terminal_payload(path)
                if recovered is not None:
                    return recovered
                detail = self._controller_log_summary()
                raise RuntimeError(
                    f"Interactive DSSAT controller exited before producing {timeout_label}. "
                    f"Protocol dir: {self.protocol.root_dir}. {detail}"
                )
            time.sleep(self.controller.poll_interval_seconds)
        raise TimeoutError(
            f"Timed out waiting for {timeout_label} at {path} after {timeout_seconds} seconds. "
            f"{self._controller_log_summary()}"
        )

    def _controller_log_summary(self) -> str:
        if not self.controller_log_path.exists():
            return f"Controller log path: {self.controller_log_path} (not created)."
        lines = self.controller_log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        if not lines:
            return f"Controller log path: {self.controller_log_path} (empty)."
        tail = " | ".join(lines[-10:])
        return f"Controller log path: {self.controller_log_path}. Tail: {tail}"

    def _finalize_terminal_session(self, *, expect_final_outcome_file: bool) -> None:
        if expect_final_outcome_file and not self.protocol.final_outcome_path.exists():
            try:
                self._wait_for_json(
                    self.protocol.final_outcome_path,
                    timeout_seconds=self.controller.close_timeout_seconds,
                    timeout_label="interactive final outcome",
                )
            except TimeoutError:
                pass
        if self.process is not None:
            terminal_wait_seconds = max(self.controller.close_timeout_seconds, 300.0)
            try:
                self.process.wait(timeout=terminal_wait_seconds)
            except subprocess.TimeoutExpired:
                pass
            if self.process.poll() is not None:
                self._cleanup_process()

    def _recover_terminal_payload(self, expected_path: Path) -> dict[str, Any] | None:
        if expected_path.name == self.protocol.final_outcome_path.name and expected_path.exists():
            try:
                return json.loads(expected_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                return None
        if not expected_path.name.startswith("step_response_"):
            return None
        if not self.protocol.final_outcome_path.exists():
            return None
        try:
            final_outcome_payload = json.loads(self.protocol.final_outcome_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
        progress_payload = self._load_progress_payload()
        next_state_payload = dict(progress_payload.get("last_state", {}))
        if not next_state_payload:
            next_state_payload = self._load_state_payload_from_run_dir()
        if not next_state_payload:
            return None
        run_dir = str(progress_payload.get("run_dir", self.run_dir))
        reward = round(
            float(final_outcome_payload.get("cumulative_reward", self._last_cumulative_reward))
            - self._last_cumulative_reward,
            6,
        )
        recovered_payload = {
            "next_state": next_state_payload,
            "reward": reward,
            "done": True,
            "daily_trace": [],
            "final_outcome": final_outcome_payload,
            "run_dir": run_dir,
            "info": {
                "backend_mode": "interactive_patched",
                "terminal_response_recovered": True,
                "recovery_source": "final_outcome_fallback",
            },
        }
        _write_json_atomic(expected_path, recovered_payload)
        return recovered_payload

    def _load_progress_payload(self) -> dict[str, Any]:
        progress_path = self.protocol.root_dir / "interactive_progress.json"
        if not progress_path.exists():
            return {}
        try:
            return json.loads(progress_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}

    def _load_state_payload_from_run_dir(self) -> dict[str, Any]:
        state_path = self.run_dir / "transdssat_interactive_state.kv"
        if not state_path.exists():
            return {}
        payload: dict[str, Any] = {}
        for raw_line in state_path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = raw_line.strip()
            if not line or "=" not in line:
                continue
            key, value = line.split("=", 1)
            payload[key.strip()] = value.strip()
        required_fields = {
            "day_index",
            "stage",
            "stage_index",
            "soil_moisture",
            "root_zone_water_mm",
            "soil_nitrogen_kg_ha",
            "canopy_cover",
            "biomass_kg_ha",
            "water_stress",
            "nitrogen_stress",
            "tmean_c",
            "precipitation_mm",
            "et0_mm",
            "radiation_mj_m2",
        }
        return payload if required_fields.issubset(payload) else {}


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    rendered = json.dumps(payload, indent=2, ensure_ascii=False)
    temp_path = path.with_name(f"{path.name}.tmp")
    temp_path.write_text(rendered, encoding="utf-8")
    temp_path.replace(path)


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


def _outcome_from_payload(payload: dict[str, Any]) -> CropOutcome:
    return CropOutcome(
        yield_kg_ha=float(payload["yield_kg_ha"]),
        biomass_kg_ha=float(payload["biomass_kg_ha"]),
        total_irrigation_mm=float(payload["total_irrigation_mm"]),
        total_nitrogen_kg_ha=float(payload["total_nitrogen_kg_ha"]),
        water_use_efficiency=float(payload["water_use_efficiency"]),
        nitrogen_use_efficiency=float(payload["nitrogen_use_efficiency"]),
        cumulative_reward=float(payload["cumulative_reward"]),
        environmental_metrics=dict(payload.get("environmental_metrics", {})),
    )


def build_filesystem_interactive_transport_from_env(
    scenario: SimulationScenario,
    *,
    runtime_role: str = "patched",
) -> FileSystemInteractiveDSSATTransport:
    config = DSSATRunConfig.from_env(runtime_role=runtime_role)
    if not config.interactive_launch_command:
        raise RuntimeError(
            "Interactive DSSAT launch command is not configured. "
            "Set DSSAT_PATCHED_INTERACTIVE_LAUNCH_COMMAND or DSSAT_INTERACTIVE_LAUNCH_COMMAND."
        )
    builder = DSSATInputBuilder(config)
    context = builder.build(
        scenario,
        SeasonPolicy(
            policy_id=f"{scenario.scenario_id}-interactive-session",
            scenario_id=scenario.scenario_id,
            actions=[],
        ),
    )
    _run_interactive_preprocess_if_configured(config, context)
    protocol = FileSystemInteractiveProtocol(
        root_dir=context.run_dir / config.interactive_protocol_dirname,
    )
    controller = FileSystemInteractiveControllerConfig(
        launch_command=config.interactive_launch_command,
        log_filename=config.interactive_controller_log_filename,
        poll_interval_seconds=config.interactive_poll_interval_seconds,
        ready_timeout_seconds=config.interactive_ready_timeout_seconds,
        step_timeout_seconds=config.interactive_step_timeout_seconds,
        close_timeout_seconds=config.interactive_close_timeout_seconds,
    )
    return FileSystemInteractiveDSSATTransport(
        protocol=protocol,
        controller=controller,
        run_dir=context.run_dir,
    )


def _run_interactive_preprocess_if_configured(config: DSSATRunConfig, context) -> None:
    if not config.preprocess_command:
        return
    stdout_path = context.run_dir / "transdssat_stdout.log"
    stderr_path = context.run_dir / "transdssat_stderr.log"
    command = config.preprocess_command.format(
        run_dir=str(context.run_dir),
        manifest=str(context.manifest_path),
        policy=str(context.policy_path),
        scenario=str(context.scenario_path),
        crop=context.crop_name,
        experiment=context.experiment_file,
    )
    argv = split_command(command)
    if not argv:
        raise RuntimeError("Interactive DSSAT preprocess command resolved to an empty command.")
    with stdout_path.open("a", encoding="utf-8") as stdout_handle:
        with stderr_path.open("a", encoding="utf-8") as stderr_handle:
            result = subprocess.run(
                argv,
                cwd=PROJECT_ROOT,
                stdout=stdout_handle,
                stderr=stderr_handle,
                check=False,
                timeout=config.timeout_seconds,
            )
    if result.returncode != 0:
        raise RuntimeError(
            f"Interactive DSSAT preprocess command failed with exit code {result.returncode}. "
            f"See {stdout_path} and {stderr_path}."
        )
