from __future__ import annotations

import os
from pathlib import Path

from transdssat.domain import CropAction, CropOutcome, CropState
from transdssat.environments.base import CropEnvironment
from transdssat.scenarios import SimulationScenario


class PyDSSATEnvironment(CropEnvironment):
    """
    Server-side adapter entrypoint for a real DSSAT backend driven through pyDSSAT.

    This class is intentionally conservative:
    - it validates that the expected Python package and runtime directory exist,
    - it exposes the same environment interface as the proxy models,
    - it does not guess undocumented pyDSSAT APIs.

    After the server runtime is prepared, replace the TODO blocks with the exact
    pyDSSAT calls that generate one-step state transitions from your DSSAT setup.
    """

    def __init__(self, scenario: SimulationScenario) -> None:
        self.scenario = scenario
        self.runtime_dir = Path(os.environ.get("PYDSSAT_HOME", "")).expanduser()
        self._state: CropState | None = None
        self._final_outcome: CropOutcome | None = None
        self._done = False

        if not self.runtime_dir or str(self.runtime_dir) == ".":
            raise RuntimeError(
                "PYDSSAT_HOME is not set. Set it to the DSSAT runtime directory on the server "
                "before using engine 'pydssat'."
            )
        if not self.runtime_dir.exists():
            raise RuntimeError(
                f"PYDSSAT_HOME does not exist: {self.runtime_dir}"
            )

        try:
            __import__("pydssat")
        except ImportError as exc:
            raise RuntimeError(
                "Engine 'pydssat' requested, but the Python package is not installed in this environment."
            ) from exc

    def reset(self) -> CropState:
        self._done = False
        self._final_outcome = None

        # TODO: Replace this bootstrapped state with the real pyDSSAT model state
        # after loading cultivar, soil profile, weather file, and management events.
        first_day = self.scenario.weather[0]
        self._state = CropState(
            day_index=0,
            stage="emergence",
            stage_index=0,
            soil_moisture=0.60,
            root_zone_water_mm=self.scenario.soil_profile.initial_root_zone_water_mm,
            soil_nitrogen_kg_ha=self.scenario.soil_profile.initial_nitrogen_kg_ha,
            canopy_cover=0.08,
            biomass_kg_ha=25.0,
            water_stress=0.0,
            nitrogen_stress=0.0,
            tmean_c=first_day.tmean_c,
            precipitation_mm=first_day.precipitation_mm,
            et0_mm=first_day.et0_mm,
            radiation_mj_m2=first_day.radiation_mj_m2,
        )
        return self._state

    def step(self, action: CropAction) -> tuple[CropState, float, bool, dict]:
        if self._done or self._state is None:
            raise RuntimeError("Environment is not ready. Call reset() before step().")

        raise NotImplementedError(
            "pyDSSAT adapter scaffold is present, but the concrete step logic still needs "
            "to be wired to your server-side DSSAT runtime and file layout."
        )

    def final_outcome(self) -> CropOutcome:
        if self._final_outcome is None:
            raise RuntimeError("No pyDSSAT final outcome is available before a completed run.")
        return self._final_outcome
