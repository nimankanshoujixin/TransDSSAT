from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class CropState:
    day_index: int
    stage: str
    stage_index: int
    soil_moisture: float
    root_zone_water_mm: float
    soil_nitrogen_kg_ha: float
    canopy_cover: float
    biomass_kg_ha: float
    water_stress: float
    nitrogen_stress: float
    tmean_c: float
    precipitation_mm: float
    et0_mm: float
    radiation_mj_m2: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class CropAction:
    irrigation_mm: float = 0.0
    nitrogen_kg_ha: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class CropOutcome:
    yield_kg_ha: float
    biomass_kg_ha: float
    total_irrigation_mm: float
    total_nitrogen_kg_ha: float
    water_use_efficiency: float
    nitrogen_use_efficiency: float
    cumulative_reward: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class TrajectoryStep:
    state: CropState
    action: CropAction
    reward: float
    next_state: CropState
    done: bool
    info: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["state"] = self.state.to_dict()
        payload["action"] = self.action.to_dict()
        payload["next_state"] = self.next_state.to_dict()
        return payload


@dataclass(slots=True)
class Trajectory:
    scenario_id: str
    engine_name: str
    crop_name: str
    weather_regime: str
    management_mode: str
    steps: list[TrajectoryStep]
    outcome: CropOutcome
    policy: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "scenario_id": self.scenario_id,
            "engine_name": self.engine_name,
            "crop_name": self.crop_name,
            "weather_regime": self.weather_regime,
            "management_mode": self.management_mode,
            "steps": [step.to_dict() for step in self.steps],
            "outcome": self.outcome.to_dict(),
        }
        if self.policy is not None:
            payload["policy"] = self.policy
        return payload
