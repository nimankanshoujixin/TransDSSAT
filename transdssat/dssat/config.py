from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import shlex


def split_command(command: str) -> list[str]:
    if not command.strip():
        return []
    return shlex.split(command, posix=os.name != "nt")


@dataclass(slots=True)
class DSSATRunConfig:
    runtime_role: str
    runtime_root: Path
    working_root: Path
    template_root: Path | None
    preprocess_command: str
    run_command: str
    interactive_launch_command: str = ""
    interactive_protocol_dirname: str = "interactive_protocol"
    interactive_controller_log_filename: str = "interactive_controller.log"
    interactive_poll_interval_seconds: float = 0.2
    interactive_ready_timeout_seconds: float = 60.0
    interactive_step_timeout_seconds: float = 60.0
    interactive_close_timeout_seconds: float = 30.0
    timeout_seconds: int = 600
    preserve_run_dirs: bool = True

    @classmethod
    def from_env(cls, *, runtime_role: str = "patched") -> "DSSATRunConfig":
        role_token = runtime_role.strip().upper()
        if role_token not in {"VANILLA", "PATCHED"}:
            raise ValueError(f"Unsupported DSSAT runtime role: {runtime_role}")

        runtime_home = os.environ.get(f"DSSAT_{role_token}_HOME", "").strip()
        if not runtime_home:
            runtime_home = os.environ.get("DSSAT_HOME", "").strip()
        runtime_root = Path(runtime_home).expanduser()
        working_root = Path(os.environ.get("DSSAT_WORK_ROOT", "data/dssat_runs")).expanduser()
        template_root_value = os.environ.get("DSSAT_TEMPLATE_ROOT", "").strip()
        template_root = Path(template_root_value).expanduser() if template_root_value else None
        preprocess_command = os.environ.get("DSSAT_PREPROCESS_COMMAND", "").strip()
        run_command = os.environ.get(f"DSSAT_{role_token}_RUN_COMMAND", "").strip()
        if not run_command:
            run_command = os.environ.get("DSSAT_RUN_COMMAND", "").strip()
        interactive_launch_command = os.environ.get(f"DSSAT_{role_token}_INTERACTIVE_LAUNCH_COMMAND", "").strip()
        if not interactive_launch_command:
            interactive_launch_command = os.environ.get("DSSAT_INTERACTIVE_LAUNCH_COMMAND", "").strip()
        interactive_protocol_dirname = os.environ.get(
            "DSSAT_INTERACTIVE_PROTOCOL_DIRNAME",
            "interactive_protocol",
        ).strip() or "interactive_protocol"
        interactive_controller_log_filename = os.environ.get(
            "DSSAT_INTERACTIVE_CONTROLLER_LOG_FILENAME",
            "interactive_controller.log",
        ).strip() or "interactive_controller.log"
        interactive_poll_interval_seconds = float(os.environ.get("DSSAT_INTERACTIVE_POLL_INTERVAL_SECONDS", "0.2"))
        interactive_ready_timeout_seconds = float(os.environ.get("DSSAT_INTERACTIVE_READY_TIMEOUT_SECONDS", "60"))
        interactive_step_timeout_seconds = float(os.environ.get("DSSAT_INTERACTIVE_STEP_TIMEOUT_SECONDS", "60"))
        interactive_close_timeout_seconds = float(os.environ.get("DSSAT_INTERACTIVE_CLOSE_TIMEOUT_SECONDS", "30"))
        timeout_seconds = int(os.environ.get("DSSAT_TIMEOUT_SECONDS", "600"))
        preserve_run_dirs = os.environ.get("DSSAT_PRESERVE_RUN_DIRS", "1").strip() != "0"
        return cls(
            runtime_role=runtime_role.strip().lower(),
            runtime_root=runtime_root,
            working_root=working_root,
            template_root=template_root,
            preprocess_command=preprocess_command,
            run_command=run_command,
            interactive_launch_command=interactive_launch_command,
            interactive_protocol_dirname=interactive_protocol_dirname,
            interactive_controller_log_filename=interactive_controller_log_filename,
            interactive_poll_interval_seconds=interactive_poll_interval_seconds,
            interactive_ready_timeout_seconds=interactive_ready_timeout_seconds,
            interactive_step_timeout_seconds=interactive_step_timeout_seconds,
            interactive_close_timeout_seconds=interactive_close_timeout_seconds,
            timeout_seconds=timeout_seconds,
            preserve_run_dirs=preserve_run_dirs,
        )
