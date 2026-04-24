from __future__ import annotations

from dataclasses import dataclass
import math
import random


STAGES = ("emergence", "vegetative", "reproductive", "grain_fill")


@dataclass(slots=True)
class SoilProfile:
    soil_name: str
    field_capacity_mm: float
    wilting_point_mm: float
    saturation_mm: float
    initial_root_zone_water_mm: float
    initial_nitrogen_kg_ha: float
    drainage_coeff: float


@dataclass(slots=True)
class CropSpec:
    crop_name: str
    season_length_days: int
    base_temperature_c: float
    optimal_temperature_c: float
    radiation_use_efficiency: float
    harvest_index: float
    stage_water_demand: dict[str, float]
    stage_nitrogen_demand: dict[str, float]
    stage_canopy_growth: dict[str, float]


@dataclass(slots=True)
class WeatherDay:
    day_index: int
    tmin_c: float
    tmax_c: float
    precipitation_mm: float
    radiation_mj_m2: float
    et0_mm: float

    @property
    def tmean_c(self) -> float:
        return (self.tmin_c + self.tmax_c) / 2.0


@dataclass(slots=True)
class SimulationScenario:
    scenario_id: str
    engine_name: str
    crop_spec: CropSpec
    soil_profile: SoilProfile
    weather_regime: str
    weather: list[WeatherDay]
    irrigation_budget_mm: float
    nitrogen_budget_kg_ha: float
    management_mode: str
    seed: int
    planting_date: str = ""
    cultivar_code: str = ""
    template_name: str = ""
    site_name: str = "quzhou"


def quzhou_typical_soil() -> SoilProfile:
    return SoilProfile(
        soil_name="quzhou_flvo_aquic",
        field_capacity_mm=235.0,
        wilting_point_mm=95.0,
        saturation_mm=300.0,
        initial_root_zone_water_mm=180.0,
        initial_nitrogen_kg_ha=90.0,
        drainage_coeff=0.12,
    )


def build_crop_specs() -> dict[str, CropSpec]:
    return {
        "wheat": CropSpec(
            crop_name="wheat",
            season_length_days=210,
            base_temperature_c=0.0,
            optimal_temperature_c=20.0,
            radiation_use_efficiency=2.5,
            harvest_index=0.46,
            stage_water_demand={
                "emergence": 0.65,
                "vegetative": 0.95,
                "reproductive": 1.10,
                "grain_fill": 0.85,
            },
            stage_nitrogen_demand={
                "emergence": 0.8,
                "vegetative": 1.4,
                "reproductive": 1.2,
                "grain_fill": 0.6,
            },
            stage_canopy_growth={
                "emergence": 0.010,
                "vegetative": 0.016,
                "reproductive": 0.006,
                "grain_fill": -0.008,
            },
        ),
        "maize": CropSpec(
            crop_name="maize",
            season_length_days=135,
            base_temperature_c=8.0,
            optimal_temperature_c=28.0,
            radiation_use_efficiency=3.0,
            harvest_index=0.50,
            stage_water_demand={
                "emergence": 0.70,
                "vegetative": 1.05,
                "reproductive": 1.20,
                "grain_fill": 0.90,
            },
            stage_nitrogen_demand={
                "emergence": 1.0,
                "vegetative": 1.8,
                "reproductive": 1.4,
                "grain_fill": 0.7,
            },
            stage_canopy_growth={
                "emergence": 0.014,
                "vegetative": 0.020,
                "reproductive": 0.008,
                "grain_fill": -0.010,
            },
        ),
    }


def stage_for_day(day_index: int, season_length_days: int) -> tuple[str, int]:
    progress = day_index / max(1, season_length_days - 1)
    if progress < 0.15:
        return "emergence", 0
    if progress < 0.55:
        return "vegetative", 1
    if progress < 0.82:
        return "reproductive", 2
    return "grain_fill", 3


def build_representative_weather(
    crop_name: str,
    regime: str,
    season_length_days: int,
    seed: int,
) -> list[WeatherDay]:
    rng = random.Random(seed)
    regime_precip_factor = {"dry": 0.55, "normal": 1.0, "wet": 1.45}[regime]
    regime_cloud_factor = {"dry": 1.05, "normal": 1.0, "wet": 0.92}[regime]
    regime_et_factor = {"dry": 1.08, "normal": 1.0, "wet": 0.95}[regime]
    base_temp = 11.0 if crop_name == "wheat" else 24.0
    amplitude = 8.0 if crop_name == "wheat" else 5.5
    weather: list[WeatherDay] = []

    for day_index in range(season_length_days):
        angle = 2.0 * math.pi * day_index / max(1, season_length_days)
        tmean = base_temp + amplitude * math.sin(angle - 0.8) + rng.uniform(-1.6, 1.6)
        tmin = tmean - rng.uniform(4.0, 8.0)
        tmax = tmean + rng.uniform(5.0, 9.0)
        storm_pulse = max(0.0, math.sin(angle * 3.0 + 0.9))
        precipitation = (1.4 + 7.0 * storm_pulse + rng.uniform(0.0, 3.5)) * regime_precip_factor
        radiation = (16.5 + 5.0 * math.cos(angle - 0.4) + rng.uniform(-1.0, 1.0)) * regime_cloud_factor
        et0 = max(0.8, (2.2 + 0.16 * max(0.0, tmean) + rng.uniform(-0.4, 0.5)) * regime_et_factor)
        weather.append(
            WeatherDay(
                day_index=day_index,
                tmin_c=round(tmin, 2),
                tmax_c=round(tmax, 2),
                precipitation_mm=round(max(0.0, precipitation), 2),
                radiation_mj_m2=round(max(6.0, radiation), 2),
                et0_mm=round(et0, 2),
            )
        )

    return weather


def build_quzhou_scenarios(
    target_count: int = 216,
    engines: tuple[str, ...] = ("wofost_proxy", "dssat_proxy"),
    crops_filter: tuple[str, ...] | None = None,
) -> list[SimulationScenario]:
    soil = quzhou_typical_soil()
    crops = build_crop_specs()
    if crops_filter:
        allowed = set(crops_filter)
        crops = {name: spec for name, spec in crops.items() if name in allowed}
    scenarios: list[SimulationScenario] = []
    weather_regimes = ("dry", "normal", "wet")
    irrigation_budgets = (90.0, 150.0, 210.0)
    nitrogen_budgets = (100.0, 170.0, 240.0)
    management_modes = ("balanced", "reproductive_focus")
    seed = 20260417

    for engine_name in engines:
        for crop_name, crop_spec in crops.items():
            for regime in weather_regimes:
                for irrigation_budget_mm in irrigation_budgets:
                    for nitrogen_budget_kg_ha in nitrogen_budgets:
                        for management_mode in management_modes:
                            scenario_seed = seed + len(scenarios) * 17
                            weather = build_representative_weather(
                                crop_name=crop_name,
                                regime=regime,
                                season_length_days=crop_spec.season_length_days,
                                seed=scenario_seed,
                            )
                            scenario_id = (
                                f"{engine_name}-{crop_name}-{regime}-"
                                f"irr{int(irrigation_budget_mm)}-n{int(nitrogen_budget_kg_ha)}-"
                                f"{management_mode}"
                            )
                            scenarios.append(
                                SimulationScenario(
                                    scenario_id=scenario_id,
                                    engine_name=engine_name,
                                    crop_spec=crop_spec,
                                    soil_profile=soil,
                                    weather_regime=regime,
                                    weather=weather,
                                    irrigation_budget_mm=irrigation_budget_mm,
                                    nitrogen_budget_kg_ha=nitrogen_budget_kg_ha,
                                    management_mode=management_mode,
                                    seed=scenario_seed,
                                    planting_date="2025-10-08" if crop_name == "wheat" else "2025-06-18",
                                    cultivar_code="QM6-WH" if crop_name == "wheat" else "ZD958-MZ",
                                    template_name=f"{crop_name}_quzhou_base",
                                )
                            )

    return scenarios[:target_count]
