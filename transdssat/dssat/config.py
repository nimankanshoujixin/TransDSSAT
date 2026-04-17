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
    runtime_root: Path
    working_root: Path
    template_root: Path | None
    preprocess_command: str
    run_command: str
    timeout_seconds: int = 600
    preserve_run_dirs: bool = True

    @classmethod
    def from_env(cls) -> "DSSATRunConfig":
        runtime_root = Path(os.environ.get("DSSAT_HOME", "")).expanduser()
        working_root = Path(os.environ.get("DSSAT_WORK_ROOT", "data/dssat_runs")).expanduser()
        template_root_value = os.environ.get("DSSAT_TEMPLATE_ROOT", "").strip()
        template_root = Path(template_root_value).expanduser() if template_root_value else None
        preprocess_command = os.environ.get("DSSAT_PREPROCESS_COMMAND", "").strip()
        run_command = os.environ.get("DSSAT_RUN_COMMAND", "").strip()
        timeout_seconds = int(os.environ.get("DSSAT_TIMEOUT_SECONDS", "600"))
        preserve_run_dirs = os.environ.get("DSSAT_PRESERVE_RUN_DIRS", "1").strip() != "0"
        return cls(
            runtime_root=runtime_root,
            working_root=working_root,
            template_root=template_root,
            preprocess_command=preprocess_command,
            run_command=run_command,
            timeout_seconds=timeout_seconds,
            preserve_run_dirs=preserve_run_dirs,
        )
