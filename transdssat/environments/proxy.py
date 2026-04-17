from __future__ import annotations

from dataclasses import dataclass

from transdssat.domain import CropAction, CropOutcome, CropState
from transdssat.environments.base import CropEnvironment
from transdssat.scenarios import SimulationScenario, stage_for_day


@dataclass(slots=True)
class ProxyCoefficients:
    name: str
    rainfall_capture: float
    irrigation_efficiency: float
    nitrogen_efficiency: float
    mineralization_rate: float
    biomass_scale: float
    stress_penalty: float
    yield_scale: float
    leaching_scale: float


PROXY_ENGINES = {
    "wofost_proxy": ProxyCoefficients(
        name="wofost_proxy",
        rainfall_capture=0.87,
        irrigation_efficiency=0.85,
        nitrogen_efficiency=0.72,
        mineralization_rate=0.18,
        biomass_scale=17.0,
        stress_penalty=0.18,
        yield_scale=1.02,
        leaching_scale=0.040,
    ),
    "dssat_proxy": ProxyCoefficients(
        name="dssat_proxy",
        rainfall_capture=0.82,
        irrigation_efficiency=0.88,
        nitrogen_efficiency=0.76,
        mineralization_rate=0.22,
        biomass_scale=18.5,
        stress_penalty=0.21,
        yield_scale=0.98,
        leaching_scale=0.048,
    ),
}


def clip(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def temp_factor(tmean_c: float, base_c: float, optimal_c: float) -> float:
    if tmean_c <= base_c:
        return 0.0
    if tmean_c <= optimal_c:
        return clip((tmean_c - base_c) / max(1e-6, (optimal_c - base_c)), 0.0, 1.0)
    decline = 1.0 - 0.04 * (tmean_c - optimal_c)
    return clip(decline, 0.0, 1.0)


class ProxyCropEnvironment(CropEnvironment):
    def __init__(self, scenario: SimulationScenario, coefficients: ProxyCoefficients) -> None:
        self.scenario = scenario
        self.coefficients = coefficients
        self.day_index = 0
        self.root_zone_water_mm = scenario.soil_profile.initial_root_zone_water_mm
        self.soil_nitrogen_kg_ha = scenario.soil_profile.initial_nitrogen_kg_ha
        self.canopy_cover = 0.08
        self.biomass_kg_ha = 25.0
        self.last_water_stress = 0.0
        self.last_nitrogen_stress = 0.0
        self.total_irrigation_mm = 0.0
        self.total_nitrogen_kg_ha = 0.0
        self.cumulative_reward = 0.0
        self._done = False

    def reset(self) -> CropState:
        self.day_index = 0
        self.root_zone_water_mm = self.scenario.soil_profile.initial_root_zone_water_mm
        self.soil_nitrogen_kg_ha = self.scenario.soil_profile.initial_nitrogen_kg_ha
        self.canopy_cover = 0.08
        self.biomass_kg_ha = 25.0
        self.last_water_stress = 0.0
        self.last_nitrogen_stress = 0.0
        self.total_irrigation_mm = 0.0
        self.total_nitrogen_kg_ha = 0.0
        self.cumulative_reward = 0.0
        self._done = False
        return self._current_state()

    def step(self, action: CropAction) -> tuple[CropState, float, bool, dict]:
        if self._done:
            raise RuntimeError("Environment already finished. Call reset() before stepping again.")

        weather = self.scenario.weather[self.day_index]
        stage, _ = stage_for_day(self.day_index, self.scenario.crop_spec.season_length_days)
        crop = self.scenario.crop_spec
        soil = self.scenario.soil_profile

        effective_rain = weather.precipitation_mm * self.coefficients.rainfall_capture
        effective_irrigation = action.irrigation_mm * self.coefficients.irrigation_efficiency
        available_water = self.root_zone_water_mm + effective_rain + effective_irrigation
        potential_et = weather.et0_mm * (0.55 + self.canopy_cover)
        stage_water_multiplier = crop.stage_water_demand[stage]
        actual_transpiration = min(available_water, potential_et * stage_water_multiplier)
        water_stress = clip(
            1.0 - (actual_transpiration / max(1e-6, potential_et * stage_water_multiplier)),
            0.0,
            1.0,
        )

        mineralized_n = self.coefficients.mineralization_rate * max(weather.tmean_c, 0.0)
        applied_n = action.nitrogen_kg_ha * self.coefficients.nitrogen_efficiency
        available_n = self.soil_nitrogen_kg_ha + mineralized_n + applied_n
        n_demand = crop.stage_nitrogen_demand[stage] * (1.0 + self.canopy_cover * 0.9)
        n_uptake = min(available_n, n_demand)
        nitrogen_stress = clip(1.0 - n_uptake / max(1e-6, n_demand), 0.0, 1.0)

        thermal_factor = temp_factor(
            tmean_c=weather.tmean_c,
            base_c=crop.base_temperature_c,
            optimal_c=crop.optimal_temperature_c,
        )
        combined_stress = (1.0 - 0.58 * water_stress) * (1.0 - 0.42 * nitrogen_stress)
        biomass_gain = (
            weather.radiation_mj_m2
            * crop.radiation_use_efficiency
            * thermal_factor
            * combined_stress
            * self.coefficients.biomass_scale
            / 10.0
        )

        excess_water = max(0.0, available_water - soil.field_capacity_mm)
        drainage = excess_water * soil.drainage_coeff
        leaching = (action.nitrogen_kg_ha + mineralized_n) * self.coefficients.leaching_scale * (
            1.0 + excess_water / max(1.0, soil.field_capacity_mm)
        )
        next_root_zone_water = clip(
            available_water - actual_transpiration - drainage,
            0.0,
            soil.saturation_mm,
        )
        next_soil_n = max(0.0, available_n - n_uptake - leaching)

        canopy_change = crop.stage_canopy_growth[stage] * (1.0 - 0.5 * water_stress)
        next_canopy_cover = clip(self.canopy_cover + canopy_change, 0.05, 0.98)
        next_biomass = max(self.biomass_kg_ha, self.biomass_kg_ha + biomass_gain)

        self.root_zone_water_mm = next_root_zone_water
        self.soil_nitrogen_kg_ha = next_soil_n
        self.canopy_cover = next_canopy_cover
        self.biomass_kg_ha = next_biomass
        self.last_water_stress = water_stress
        self.last_nitrogen_stress = nitrogen_stress
        self.total_irrigation_mm += action.irrigation_mm
        self.total_nitrogen_kg_ha += action.nitrogen_kg_ha

        reward = (
            biomass_gain * 0.018
            - action.irrigation_mm * 0.06
            - action.nitrogen_kg_ha * 0.09
            - self.coefficients.stress_penalty * (water_stress + nitrogen_stress) * 3.5
        )

        self.day_index += 1
        self._done = self.day_index >= self.scenario.crop_spec.season_length_days
        if self._done:
            reward += self.final_outcome().yield_kg_ha / 1000.0
        self.cumulative_reward += reward
        next_state = self._current_state()
        info = {
            "engine_name": self.coefficients.name,
            "water_stress": round(water_stress, 4),
            "nitrogen_stress": round(nitrogen_stress, 4),
            "biomass_gain_kg_ha": round(biomass_gain, 4),
        }
        return next_state, round(reward, 6), self._done, info

    def final_outcome(self) -> CropOutcome:
        yield_kg_ha = (
            self.biomass_kg_ha
            * self.scenario.crop_spec.harvest_index
            * self.coefficients.yield_scale
            * (1.0 - 0.18 * self.last_water_stress)
            * (1.0 - 0.12 * self.last_nitrogen_stress)
        )
        return CropOutcome(
            yield_kg_ha=round(yield_kg_ha, 3),
            biomass_kg_ha=round(self.biomass_kg_ha, 3),
            total_irrigation_mm=round(self.total_irrigation_mm, 3),
            total_nitrogen_kg_ha=round(self.total_nitrogen_kg_ha, 3),
            water_use_efficiency=round(yield_kg_ha / max(1.0, self.total_irrigation_mm + 1.0), 5),
            nitrogen_use_efficiency=round(yield_kg_ha / max(1.0, self.total_nitrogen_kg_ha + 1.0), 5),
            cumulative_reward=round(self.cumulative_reward, 5),
        )

    def _current_state(self) -> CropState:
        effective_day_index = min(self.day_index, self.scenario.crop_spec.season_length_days - 1)
        weather = self.scenario.weather[effective_day_index]
        stage, stage_index = stage_for_day(
            effective_day_index,
            self.scenario.crop_spec.season_length_days,
        )
        soil = self.scenario.soil_profile
        soil_moisture = clip(
            (self.root_zone_water_mm - soil.wilting_point_mm)
            / max(1e-6, soil.field_capacity_mm - soil.wilting_point_mm),
            0.0,
            1.2,
        )
        return CropState(
            day_index=effective_day_index,
            stage=stage,
            stage_index=stage_index,
            soil_moisture=round(soil_moisture, 4),
            root_zone_water_mm=round(self.root_zone_water_mm, 3),
            soil_nitrogen_kg_ha=round(self.soil_nitrogen_kg_ha, 3),
            canopy_cover=round(self.canopy_cover, 4),
            biomass_kg_ha=round(self.biomass_kg_ha, 3),
            water_stress=round(self.last_water_stress, 4),
            nitrogen_stress=round(self.last_nitrogen_stress, 4),
            tmean_c=round(weather.tmean_c, 3),
            precipitation_mm=weather.precipitation_mm,
            et0_mm=weather.et0_mm,
            radiation_mj_m2=weather.radiation_mj_m2,
        )


def make_environment(scenario: SimulationScenario) -> CropEnvironment:
    coefficients = PROXY_ENGINES.get(scenario.engine_name)
    if coefficients is None:
        raise ValueError(f"Unknown engine: {scenario.engine_name}")
    return ProxyCropEnvironment(scenario=scenario, coefficients=coefficients)
