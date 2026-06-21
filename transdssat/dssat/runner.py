from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess

from transdssat.scenarios import SimulationScenario
from transdssat.season import SeasonPolicy

from .config import DSSATRunConfig, split_command
from .inputs import DSSATInputBuilder, DSSATRunContext


PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(slots=True)
class DSSATRunResult:
    context: DSSATRunContext
    return_code: int
    stdout_path: Path
    stderr_path: Path


class DSSATRunner:
    def __init__(self, config: DSSATRunConfig | None = None) -> None:
        self.config = config or DSSATRunConfig.from_env()
        self.builder = DSSATInputBuilder(self.config)

    def prepare(self, scenario: SimulationScenario, policy: SeasonPolicy) -> DSSATRunContext:
        if not self.config.runtime_root:
            raise RuntimeError("DSSAT_HOME is not set.")
        if str(self.config.runtime_root) == "." or not self.config.runtime_root.exists():
            raise RuntimeError(
                f"DSSAT_HOME does not exist: {self.config.runtime_root}. "
                "Install the official DSSAT runtime on the server first."
            )
        return self.builder.build(scenario, policy)

    def run(self, context: DSSATRunContext) -> DSSATRunResult:
        stdout_path = context.run_dir / "transdssat_stdout.log"
        stderr_path = context.run_dir / "transdssat_stderr.log"

        if self.config.preprocess_command:
            self._run_command(
                self.config.preprocess_command,
                context,
                stdout_path,
                stderr_path,
                cwd=PROJECT_ROOT,
            )

        if not self.config.run_command:
            raise RuntimeError(
                "DSSAT_RUN_COMMAND is not set. Provide a command template that can execute the "
                "prepared run directory, for example a wrapper script or the DSSAT executable."
            )

        return_code = self._run_command(self.config.run_command, context, stdout_path, stderr_path)
        return DSSATRunResult(
            context=context,
            return_code=return_code,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
        )

    def _run_command(
        self,
        command_template: str,
        context: DSSATRunContext,
        stdout_path: Path,
        stderr_path: Path,
        *,
        cwd: Path | None = None,
    ) -> int:
        command = command_template.format(
            run_dir=str(context.run_dir),
            manifest=str(context.manifest_path),
            policy=str(context.policy_path),
            scenario=str(context.scenario_path),
            crop=context.crop_name,
            experiment=context.experiment_file,
        )
        argv = split_command(command)
        if not argv:
            raise RuntimeError("Command template resolved to an empty command.")

        with stdout_path.open("a", encoding="utf-8") as stdout_handle:
            with stderr_path.open("a", encoding="utf-8") as stderr_handle:
                result = subprocess.run(
                    argv,
                    cwd=cwd or context.run_dir,
                    stdout=stdout_handle,
                    stderr=stderr_handle,
                    check=False,
                    timeout=self.config.timeout_seconds,
                )
        if result.returncode != 0:
            raise RuntimeError(
                f"DSSAT command failed with exit code {result.returncode}. "
                f"See {stdout_path} and {stderr_path}."
            )
        return result.returncode
