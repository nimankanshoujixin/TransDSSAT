from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
import math
import random
import copy
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
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

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "SoilProfile":
        return cls(
            soil_name=str(payload["soil_name"]),
            field_capacity_mm=float(payload["field_capacity_mm"]),
            wilting_point_mm=float(payload["wilting_point_mm"]),
            saturation_mm=float(payload["saturation_mm"]),
            initial_root_zone_water_mm=float(payload["initial_root_zone_water_mm"]),
            initial_nitrogen_kg_ha=float(payload["initial_nitrogen_kg_ha"]),
            drainage_coeff=float(payload["drainage_coeff"]),
        )


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

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "CropSpec":
        return cls(
            crop_name=str(payload["crop_name"]),
            season_length_days=int(payload["season_length_days"]),
            base_temperature_c=float(payload["base_temperature_c"]),
            optimal_temperature_c=float(payload["optimal_temperature_c"]),
            radiation_use_efficiency=float(payload["radiation_use_efficiency"]),
            harvest_index=float(payload["harvest_index"]),
            stage_water_demand={str(key): float(value) for key, value in dict(payload["stage_water_demand"]).items()},
            stage_nitrogen_demand={str(key): float(value) for key, value in dict(payload["stage_nitrogen_demand"]).items()},
            stage_canopy_growth={str(key): float(value) for key, value in dict(payload["stage_canopy_growth"]).items()},
        )


@dataclass(slots=True)
class CultivarParameterRecord:
    cultivar_id: str
    cultivar_name: str
    crop_name: str
    cultivar_reference: str = ""
    parameter_vector: list[float] = field(default_factory=list)
    parameter_names: list[str] = field(default_factory=list)
    parameter_units: list[str] = field(default_factory=list)
    parameter_description: str = ""
    dssat_cultivar_code: str = ""
    dssat_genotype_file: str = ""
    dssat_ecotype_code: str = ""
    data_source: str = ""
    missing_details: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "CultivarParameterRecord":
        return cls(
            cultivar_id=str(payload.get("cultivar_id", "")),
            cultivar_name=str(payload.get("cultivar_name", "")),
            crop_name=str(payload.get("crop_name", "")),
            cultivar_reference=str(payload.get("cultivar_reference", "")),
            parameter_vector=[float(value) for value in payload.get("parameter_vector", [])],
            parameter_names=[str(value) for value in payload.get("parameter_names", [])],
            parameter_units=[str(value) for value in payload.get("parameter_units", [])],
            parameter_description=str(payload.get("parameter_description", "")),
            dssat_cultivar_code=str(payload.get("dssat_cultivar_code", "")),
            dssat_genotype_file=str(payload.get("dssat_genotype_file", "")),
            dssat_ecotype_code=str(payload.get("dssat_ecotype_code", "")),
            data_source=str(payload.get("data_source", "")),
            missing_details=[str(value) for value in payload.get("missing_details", [])],
        )


@dataclass(slots=True)
class CropContext:
    crop_name: str
    crop_type: str
    cultivar: CultivarParameterRecord
    site_name: str = "quzhou"
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "crop_name": self.crop_name,
            "crop_type": self.crop_type,
            "cultivar": self.cultivar.to_dict(),
            "site_name": self.site_name,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "CropContext":
        return cls(
            crop_name=str(payload.get("crop_name", "")),
            crop_type=str(payload.get("crop_type", "")),
            cultivar=CultivarParameterRecord.from_dict(dict(payload.get("cultivar", {}))),
            site_name=str(payload.get("site_name", "quzhou")),
            notes=str(payload.get("notes", "")),
        )


@dataclass(slots=True)
class ObjectiveContext:
    objective_id: str
    objective_name: str
    primary_metric: str
    reward_contract: str = "reward_v2"
    reward_weights: dict[str, float] = field(default_factory=dict)
    budget_constraints: dict[str, Any] = field(default_factory=dict)
    soft_preferences: dict[str, Any] = field(default_factory=dict)
    report_metrics: list[str] = field(default_factory=list)
    environmental_metric_specs: list[dict[str, Any]] = field(default_factory=list)
    missing_details: list[str] = field(default_factory=list)
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ObjectiveContext":
        return cls(
            objective_id=str(payload.get("objective_id", "")),
            objective_name=str(payload.get("objective_name", "")),
            primary_metric=str(payload.get("primary_metric", "")),
            reward_contract=str(payload.get("reward_contract", "reward_v2")),
            reward_weights=dict(payload.get("reward_weights", {})),
            budget_constraints=dict(payload.get("budget_constraints", {})),
            soft_preferences=dict(payload.get("soft_preferences", {})),
            report_metrics=[str(value) for value in payload.get("report_metrics", [])],
            environmental_metric_specs=[dict(value) for value in payload.get("environmental_metric_specs", [])],
            missing_details=[str(value) for value in payload.get("missing_details", [])],
            notes=str(payload.get("notes", "")),
        )


@dataclass(slots=True)
class StateInterfaceContract:
    version: str
    stable_core_fields: list[str] = field(default_factory=list)
    pending_agronomy_fields: list[str] = field(default_factory=list)
    simulator_internal_fields: list[str] = field(default_factory=list)
    derived_fields: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "StateInterfaceContract":
        return cls(
            version=str(payload.get("version", "")),
            stable_core_fields=[str(value) for value in payload.get("stable_core_fields", [])],
            pending_agronomy_fields=[str(value) for value in payload.get("pending_agronomy_fields", [])],
            simulator_internal_fields=[str(value) for value in payload.get("simulator_internal_fields", [])],
            derived_fields=[str(value) for value in payload.get("derived_fields", [])],
            notes=[str(value) for value in payload.get("notes", [])],
        )


def default_state_interface_contract() -> StateInterfaceContract:
    return StateInterfaceContract(
        version="v2026-06-admission-draft",
        stable_core_fields=[
            "crop_name",
            "crop_type",
            "cultivar_id",
            "cultivar_name",
            "site_name",
            "planting_date",
            "irrigation_budget_mm",
            "nitrogen_budget_kg_ha",
            "objective_id",
            "decision_interval_days",
            "forecast_horizon_days",
            "day_index",
            "decision_date",
            "stage",
            "precipitation_mm",
            "remaining_irrigation_mm",
            "remaining_nitrogen_kg_ha",
            "forecast_weather_window",
        ],
        pending_agronomy_fields=[
            "weather_year",
            "soil_name",
            "initial_root_zone_water_mm",
            "initial_nitrogen_kg_ha",
            "irrigation_min_gap_days",
            "nitrogen_min_gap_days",
            "allow_combined_actions",
            "soil_moisture",
            "canopy_cover",
            "biomass_kg_ha",
            "et0_mm",
            "radiation_mj_m2",
        ],
        simulator_internal_fields=[
            "cultivar_parameter_vector",
            "parameter_names",
            "parameter_units",
            "dssat_cultivar_code",
            "dssat_genotype_file",
            "dssat_ecotype_code",
            "field_capacity_mm",
            "wilting_point_mm",
            "saturation_mm",
            "drainage_coeff",
            "reward_weights",
            "root_zone_water_mm",
            "soil_nitrogen_kg_ha",
            "water_stress",
            "nitrogen_stress",
        ],
        derived_fields=[
            "stage_index",
            "tmean_c",
            "action_constraints",
        ],
        notes=[
            "stable_core_fields are the most conservative candidate inputs shared across current schema/export paths",
            "pending_agronomy_fields remain revision-friendly until field collection and agronomy review confirm availability",
            "simulator_internal_fields may stay in proxy or DSSAT internals but should not be treated as farmer-side direct inputs",
            "derived_fields are emitted system summaries rather than raw source observations",
        ],
    )


@dataclass(slots=True)
class DecisionContext:
    decision_interval_days: int = 5
    weather_mode: str = "realistic"
    forecast_horizon_days: int = 7
    irrigation_min_gap_days: int = 5
    nitrogen_min_gap_days: int = 10
    action_space_id: str = "v2_joint_continuous"
    action_table_id: str = "deprecated_v1_joint_discrete"
    allow_combined_actions: bool = True
    state_interface_version: str = "v2026-06-admission-draft"
    full_state_fields: list[str] = field(
        default_factory=lambda: [
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
        ]
    )
    partial_observation_fields: list[str] = field(
        default_factory=lambda: [
            "day_index",
            "stage",
            "soil_moisture",
            "canopy_cover",
            "biomass_kg_ha",
            "precipitation_mm",
            "forecast_weather_window",
            "remaining_irrigation_mm",
            "remaining_nitrogen_kg_ha",
        ]
    )
    stable_core_fields: list[str] = field(
        default_factory=lambda: list(default_state_interface_contract().stable_core_fields)
    )
    pending_agronomy_fields: list[str] = field(
        default_factory=lambda: list(default_state_interface_contract().pending_agronomy_fields)
    )
    simulator_internal_fields: list[str] = field(
        default_factory=lambda: list(default_state_interface_contract().simulator_internal_fields)
    )
    derived_fields: list[str] = field(
        default_factory=lambda: list(default_state_interface_contract().derived_fields)
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "DecisionContext":
        return cls(
            decision_interval_days=int(payload.get("decision_interval_days", 5)),
            weather_mode=str(payload.get("weather_mode", "realistic")),
            forecast_horizon_days=int(payload.get("forecast_horizon_days", 7)),
            irrigation_min_gap_days=int(payload.get("irrigation_min_gap_days", 5)),
            nitrogen_min_gap_days=int(payload.get("nitrogen_min_gap_days", 10)),
            action_space_id=str(payload.get("action_space_id", "v2_joint_continuous")),
            action_table_id=str(payload.get("action_table_id", "deprecated_v1_joint_discrete")),
            allow_combined_actions=bool(payload.get("allow_combined_actions", True)),
            state_interface_version=str(payload.get("state_interface_version", "v2026-06-admission-draft")),
            full_state_fields=[str(value) for value in payload.get("full_state_fields", [])],
            partial_observation_fields=[str(value) for value in payload.get("partial_observation_fields", [])],
            stable_core_fields=[str(value) for value in payload.get("stable_core_fields", [])],
            pending_agronomy_fields=[str(value) for value in payload.get("pending_agronomy_fields", [])],
            simulator_internal_fields=[str(value) for value in payload.get("simulator_internal_fields", [])],
            derived_fields=[str(value) for value in payload.get("derived_fields", [])],
        )


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

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "WeatherDay":
        return cls(
            day_index=int(payload["day_index"]),
            tmin_c=float(payload["tmin_c"]),
            tmax_c=float(payload["tmax_c"]),
            precipitation_mm=float(payload["precipitation_mm"]),
            radiation_mj_m2=float(payload["radiation_mj_m2"]),
            et0_mm=float(payload["et0_mm"]),
        )


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
    weather_year: int = 2025
    planting_date: str = ""
    cultivar_code: str = ""
    template_name: str = ""
    experiment_file: str = ""
    site_name: str = "quzhou"
    crop_context: CropContext | None = None
    objective_context: ObjectiveContext = field(default_factory=lambda: default_objective_context())
    decision_context: DecisionContext = field(default_factory=DecisionContext)

    @property
    def cultivar_id(self) -> str:
        if self.crop_context is None:
            return ""
        return self.crop_context.cultivar.cultivar_id

    @property
    def crop_type(self) -> str:
        if self.crop_context is None:
            return self.crop_spec.crop_name
        return self.crop_context.crop_type

    def state_interface_contract(self) -> StateInterfaceContract:
        return default_state_interface_contract()

    def state_interface_contract_dict(self) -> dict[str, Any]:
        return self.state_interface_contract().to_dict()

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "engine_name": self.engine_name,
            "crop_spec": asdict(self.crop_spec),
            "soil_profile": asdict(self.soil_profile),
            "weather_regime": self.weather_regime,
            "weather": [asdict(day) for day in self.weather],
            "irrigation_budget_mm": self.irrigation_budget_mm,
            "nitrogen_budget_kg_ha": self.nitrogen_budget_kg_ha,
            "management_mode": self.management_mode,
            "seed": self.seed,
            "weather_year": self.weather_year,
            "planting_date": self.planting_date,
            "cultivar_code": self.cultivar_code,
            "cultivar_id": self.cultivar_id,
            "crop_type": self.crop_type,
            "template_name": self.template_name,
            "experiment_file": self.experiment_file,
            "site_name": self.site_name,
            "crop_context": self.crop_context.to_dict() if self.crop_context is not None else None,
            "objective_context": self.objective_context.to_dict(),
            "decision_context": self.decision_context.to_dict(),
            "state_interface_contract": self.state_interface_contract_dict(),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "SimulationScenario":
        crop_context_payload = payload.get("crop_context")
        objective_context_payload = payload.get("objective_context")
        decision_context_payload = payload.get("decision_context")
        return cls(
            scenario_id=str(payload["scenario_id"]),
            engine_name=str(payload["engine_name"]),
            crop_spec=CropSpec.from_dict(dict(payload["crop_spec"])),
            soil_profile=SoilProfile.from_dict(dict(payload["soil_profile"])),
            weather_regime=str(payload["weather_regime"]),
            weather=[WeatherDay.from_dict(dict(day)) for day in payload.get("weather", [])],
            irrigation_budget_mm=float(payload["irrigation_budget_mm"]),
            nitrogen_budget_kg_ha=float(payload["nitrogen_budget_kg_ha"]),
            management_mode=str(payload["management_mode"]),
            seed=int(payload["seed"]),
            weather_year=int(payload.get("weather_year", 2025)),
            planting_date=str(payload.get("planting_date", "")),
            cultivar_code=str(payload.get("cultivar_code", "")),
            template_name=str(payload.get("template_name", "")),
            experiment_file=str(payload.get("experiment_file", "")),
            site_name=str(payload.get("site_name", "quzhou")),
            crop_context=None if not crop_context_payload else CropContext.from_dict(dict(crop_context_payload)),
            objective_context=(
                default_objective_context()
                if not objective_context_payload
                else ObjectiveContext.from_dict(dict(objective_context_payload))
            ),
            decision_context=(
                DecisionContext()
                if not decision_context_payload
                else DecisionContext.from_dict(dict(decision_context_payload))
            ),
        )


def scenario_yield_floor_reference(scenario: SimulationScenario) -> float:
    soft_preferences = scenario.objective_context.soft_preferences
    explicit_floor = soft_preferences.get("yield_floor_reference_kg_ha")
    if explicit_floor is not None:
        return float(explicit_floor)

    crop_name = scenario.crop_spec.crop_name
    site_name = str(scenario.site_name or "").strip().lower()
    if crop_name == "maize" and site_name == "quzhou":
        return 700.0 * 15.0
    if crop_name == "wheat" and site_name == "quzhou":
        return 450.0 * 15.0

    budget_floor = scenario.irrigation_budget_mm * 12.0 + scenario.nitrogen_budget_kg_ha * 12.0
    if crop_name == "wheat":
        return max(2200.0, budget_floor * 0.88)
    return max(2800.0, budget_floor)


def default_objective_context() -> ObjectiveContext:
    return ObjectiveContext(
        objective_id="profit",
        objective_name="profit_with_resource_penalties",
        primary_metric="mean_reward",
        reward_contract="reward_v2",
        reward_weights={
            "yield_revenue": 1.0,
            "irrigation_cost": 1.0,
            "nitrogen_cost": 1.0,
            "operation_cost": 1.0,
            "water_penalty": 0.6,
            "nitrogen_leaching_penalty": 0.8,
            "risk_penalty": 0.3,
        },
        budget_constraints={
            "irrigation_budget_mm": {
                "semantic_role": "hard_constraint",
                "unit": "mm",
                "enforced_by": [
                    "stepwise_action_validation",
                    "remaining_budget_tracking",
                    "terminal_budget_penalty",
                ],
            },
            "nitrogen_budget_kg_ha": {
                "semantic_role": "hard_constraint",
                "unit": "kg/ha",
                "enforced_by": [
                    "stepwise_action_validation",
                    "remaining_budget_tracking",
                    "terminal_budget_penalty",
                ],
            },
        },
        soft_preferences={
            "semantic_role": "objective_conditioning",
            "environmental_priority_weights": {
                "water_penalty": 0.6,
                "nitrogen_leaching_penalty": 0.8,
                "risk_penalty": 0.3,
            },
            "anti_collapse_guardrail": {
                "enabled": False,
                "apply_when_yield_below_floor": True,
                "minimum_budget_for_guardrail": 80.0,
                "minimum_irrigation_ratio": 0.12,
                "minimum_nitrogen_ratio": 0.15,
                "shortfall_penalty_weight": 24.0,
                "irrigation_shortfall_penalty_weight": 24.0,
                "nitrogen_shortfall_penalty_weight": 36.0,
                "yield_gap_multiplier": 2.0,
                "zero_irrigation_extra_penalty": 0.0,
                "zero_nitrogen_extra_penalty": 3.0,
                "active_channels": ["irrigation", "nitrogen"],
            },
            "resource_settlement": {
                "enabled": False,
                "irrigation_cost_exponent": 2.0,
                "nitrogen_cost_exponent": 2.2,
                "direct_input_cost_scale": 0.35,
                "under_budget_cost_scale": 0.0,
            },
            "training_activity_regularizer": {
                "enabled": False,
                "minimum_expected_irrigation_ratio": 0.08,
                "minimum_expected_nitrogen_ratio": 0.12,
                "irrigation_penalty_weight": 0.8,
                "nitrogen_penalty_weight": 1.6,
            },
            "training_behavior_anchor": {
                "enabled": False,
                "retention_ratio": 0.9,
                "minimum_anchor_irrigation_ratio": 0.08,
                "minimum_anchor_nitrogen_ratio": 0.12,
                "irrigation_penalty_weight": 1.2,
                "nitrogen_penalty_weight": 2.4,
            },
            "training_policy_anchor": {
                "enabled": False,
                "gate_penalty_weight": 0.25,
                "irrigation_amount_penalty_weight": 0.8,
                "nitrogen_amount_penalty_weight": 1.2,
                "minimum_sample_weight": 0.2,
                "negative_advantage_scale": 0.35,
                "positive_advantage_scale": 0.8,
            },
            "training_advantage_activity_anchor": {
                "enabled": False,
                "retention_ratio": 0.92,
                "positive_advantage_threshold": 0.0,
                "minimum_anchor_irrigation_ratio": 0.08,
                "minimum_anchor_nitrogen_ratio": 0.12,
                "irrigation_penalty_weight": 0.8,
                "nitrogen_penalty_weight": 1.6,
            },
            "training_update_admission": {
                "enabled": False,
                "minimum_irrigation_ratio": 0.05,
                "minimum_nitrogen_ratio": 0.08,
                "irrigation_penalty_weight": 1.0,
                "nitrogen_penalty_weight": 2.0,
                "soft_penalty_weight": 1.0,
                "soft_rollout_penalty_weight_scale": 1.0,
                "soft_expected_penalty_weight_scale": 1.0,
                "soft_greedy_penalty_weight_scale": 0.0,
                "hard_rejection_threshold": 0.02,
                "hard_rollout_penalty_weight_scale": 1.0,
                "hard_expected_penalty_weight_scale": 0.0,
                "hard_greedy_penalty_weight_scale": 1.0,
                "enforce_expected_activity": True,
                "expected_activity_retention_ratio": 0.9,
                "minimum_expected_irrigation_ratio": 0.05,
                "minimum_expected_nitrogen_ratio": 0.08,
                "expected_irrigation_penalty_weight": 1.0,
                "expected_nitrogen_penalty_weight": 2.0,
                "enforce_greedy_activity": True,
                "greedy_activity_retention_ratio": 0.9,
                "minimum_greedy_irrigation_ratio": 0.05,
                "minimum_greedy_nitrogen_ratio": 0.08,
                "greedy_irrigation_penalty_weight": 1.0,
                "greedy_nitrogen_penalty_weight": 2.0,
            },
            "training_auxiliary_penalty_budget": {
                "enabled": False,
                "max_auxiliary_to_core_ratio": 0.6,
                "minimum_core_loss": 0.25,
                "include_entropy_magnitude": True,
            },
            "notes": [
                "budgets remain constraint semantics rather than optimization targets to fully consume",
                "environmental preference weights may change reward and evaluation emphasis without weakening budget checks",
                "the collapse-mitigation stack is disabled here so the default training path matches the pre-collapse baseline rerun contract",
            ],
        },
        report_metrics=[
            "yield_kg_ha",
            "cumulative_reward",
            "total_irrigation_mm",
            "total_nitrogen_kg_ha",
            "water_use_efficiency",
            "nitrogen_use_efficiency",
            "avg_water_stress",
            "avg_nitrogen_stress",
            "total_drainage_mm",
            "total_nitrogen_leached_kg_ha",
            "terminal_root_zone_water_mm",
            "terminal_soil_nitrogen_kg_ha",
        ],
        environmental_metric_specs=[
            {
                "metric_id": "avg_water_stress",
                "display_name": "average water stress",
                "unit": "fraction_0_1",
                "reward_channel": "risk_penalty",
                "proxy_status": "available",
                "official_status": "available",
                "source": "proxy daily states / PlantGro.OUT stress factors",
            },
            {
                "metric_id": "avg_nitrogen_stress",
                "display_name": "average nitrogen stress",
                "unit": "fraction_0_1",
                "reward_channel": "risk_penalty",
                "proxy_status": "available",
                "official_status": "available",
                "source": "proxy daily states / PlantGro.OUT stress factors",
            },
            {
                "metric_id": "terminal_root_zone_water_mm",
                "display_name": "terminal root-zone water",
                "unit": "mm",
                "reward_channel": "report_only",
                "proxy_status": "available",
                "official_status": "available",
                "source": "proxy terminal state / SoilWat.OUT final row",
            },
            {
                "metric_id": "terminal_soil_nitrogen_kg_ha",
                "display_name": "terminal soil nitrogen",
                "unit": "kg/ha",
                "reward_channel": "report_only",
                "proxy_status": "available",
                "official_status": "available",
                "source": "proxy terminal state / SoilNi.OUT final row",
            },
            {
                "metric_id": "total_drainage_mm",
                "display_name": "season drainage approximation",
                "unit": "mm",
                "reward_channel": "water_penalty",
                "proxy_status": "conservative_approximation",
                "official_status": "missing_details",
                "source": "proxy excess-water balance approximation",
            },
            {
                "metric_id": "total_nitrogen_leached_kg_ha",
                "display_name": "season nitrogen leaching approximation",
                "unit": "kg/ha",
                "reward_channel": "nitrogen_leaching_penalty",
                "proxy_status": "conservative_approximation",
                "official_status": "missing_details",
                "source": "proxy mineral-N balance approximation",
            },
        ],
        missing_details=[
            "official_total_drainage_mm_not_yet_extracted_from_current_DSSAT_parser",
            "official_total_nitrogen_leached_kg_ha_not_yet_extracted_from_current_DSSAT_parser",
        ],
        notes="CPU-safe default objective context for schema/export, proxy rollout validation, and objective-aware reward wiring.",
    )


def crop_type_name(crop_name: str) -> str:
    return {
        "maize": "玉米",
        "wheat": "小麦",
    }.get(crop_name, crop_name)


_RICE_CULTIVAR_CODES = ("IB2002", "WHR006")

def _select_rice_cultivar_code(rng):
    """Select a calibrated rice cultivar from the available pool."""
    return rng.choice(_RICE_CULTIVAR_CODES)

def build_cultivar_context(crop_name: str, cultivar_code: str, site_name: str = "quzhou") -> CropContext:
    if crop_name == "rice":
        if cultivar_code == "WHR006":
            cultivar = CultivarParameterRecord(
                cultivar_id="meixiangzhan2-wh",
                cultivar_name="美香占2号",
                crop_name="rice",
                cultivar_reference="Meixiangzhan2_WH_calibrated_v1",
                parameter_vector=[448.8, 121.0, 663.0, 12.97, 60.01, 0.0270, 1.00, 83.0, 29.5, 15.0, 15.0],
                parameter_names=["P1", "P2R", "P5", "P2O", "G1", "G2", "G3", "PHINT", "THOT", "TCLDP", "TCLDF"],
                parameter_units=["degree_days", "degree_days_per_hour", "degree_days", "hours", "spikelets_per_g", "g_per_grain", "scalar", "degree_days", "celsius", "celsius", "celsius"],
                parameter_description="GenCalc calibrated DSSAT rice genetic parameters for Meixiangzhan 2 (Wuhu WHR006).",
                dssat_cultivar_code="WHR006",
                dssat_genotype_file="RICER048.CUL",
                dssat_ecotype_code="IB0001",
                data_source="作物模型_20260616/02_自己校准模型_芜湖水稻",
                missing_details=[],
            )
            return CropContext(
                crop_name="rice",
                crop_type="水稻",
                cultivar=cultivar,
                site_name=site_name,
                notes="Schema carries Meixiangzhan 2 (WHR006 variant) GenCalc calibrated DSSAT rice parameters.",
            )
        cultivar = CultivarParameterRecord(
            cultivar_id="meixiangzhan2",
            cultivar_name="美香占2号",
            crop_name="rice",
            cultivar_reference="Meixiangzhan2_calibrated_v1",
            parameter_vector=[724.9, 97.04, 416.0, 11.69, 71.09, 0.0170, 1.17, 57.46, 35.0, 15.0, 15.0],
            parameter_names=["P1", "P2R", "P5", "P2O", "G1", "G2", "G3", "PHINT", "THOT", "TCLDP", "TCLDF"],
            parameter_units=["degree_days", "degree_days_per_hour", "degree_days", "hours", "spikelets_per_g", "g_per_grain", "scalar", "degree_days", "celsius", "celsius", "celsius"],
            parameter_description="Calibrated DSSAT rice genetic parameters for Meixiangzhan 2.",
            dssat_cultivar_code="IB2002",
            dssat_genotype_file="RICER048.CUL",
            dssat_ecotype_code="IB0001",
            data_source="作物模型_20260616/02_自己校准模型_芜湖水稻",
            missing_details=[],
        )
        return CropContext(
            crop_name="rice",
            crop_type="水稻",
            cultivar=cultivar,
            site_name=site_name,
            notes="Schema carries Meixiangzhan 2 calibrated DSSAT rice genetic parameters.",
        )

    if crop_name == "maize":
        cultivar = CultivarParameterRecord(
            cultivar_id="denghai605",
            cultivar_name="登海605",
            crop_name="maize",
            cultivar_reference="Denghai605_calibrated_v1",
            parameter_vector=[340.9, 1.61, 700.0, 600.0, 10.5, 60.0],
            parameter_names=["P1", "P2", "P5", "G2", "G3", "PHINT"],
            parameter_units=["degree_days", "days_per_hour", "degree_days", "kernels_per_plant", "mg_per_day", "degree_days"],
            parameter_description="Calibrated DSSAT maize genetic parameters ordered as P1, P2, P5, G2, G3, PHINT.",
            dssat_cultivar_code="DH6051",
            dssat_genotype_file="MZCER048.CUL",
            dssat_ecotype_code="IB0001",
            data_source="农业同学校准结果",
            missing_details=[],
        )
        return CropContext(
            crop_name="maize",
            crop_type="玉米",
            cultivar=cultivar,
            site_name=site_name,
            notes=(
                "Schema carries Denghai605 calibrated DSSAT maize genetic parameters, "
                "mapped to official DSSAT MZCER048 cultivar coefficients while retaining "
                "the legacy scenario cultivar_code field for compatibility."
            ),
        )

    cultivar = CultivarParameterRecord(
        cultivar_id=cultivar_code.lower().replace("_", "-") or f"{crop_name}-default",
        cultivar_name=cultivar_code or f"{crop_name}_default",
        crop_name=crop_name,
        cultivar_reference=f"{crop_name}_placeholder_v1",
        parameter_description="missing_details",
        dssat_cultivar_code=cultivar_code,
        data_source="project placeholder",
        missing_details=[
            "cultivar_parameter_vector_unavailable",
            "parameter_names_unknown",
            "parameter_units_unknown",
        ],
    )
    return CropContext(
        crop_name=crop_name,
        crop_type=crop_type_name(crop_name),
        cultivar=cultivar,
        site_name=site_name,
        notes="Placeholder cultivar metadata until a crop-specific calibrated record is added.",
    )


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


def quzhou_soil_library() -> tuple[SoilProfile, ...]:
    return (
        quzhou_typical_soil(),
        SoilProfile(
            soil_name="quzhou_deep_loam",
            field_capacity_mm=248.0,
            wilting_point_mm=101.0,
            saturation_mm=316.0,
            initial_root_zone_water_mm=192.0,
            initial_nitrogen_kg_ha=104.0,
            drainage_coeff=0.10,
        ),
        SoilProfile(
            soil_name="quzhou_fast_drain",
            field_capacity_mm=218.0,
            wilting_point_mm=88.0,
            saturation_mm=286.0,
            initial_root_zone_water_mm=166.0,
            initial_nitrogen_kg_ha=84.0,
            drainage_coeff=0.16,
        ),
        SoilProfile(
            soil_name="quzhou_fertile_silt",
            field_capacity_mm=242.0,
            wilting_point_mm=98.0,
            saturation_mm=309.0,
            initial_root_zone_water_mm=188.0,
            initial_nitrogen_kg_ha=118.0,
            drainage_coeff=0.11,
        ),
        SoilProfile(
            soil_name="quzhou_water_limited",
            field_capacity_mm=224.0,
            wilting_point_mm=92.0,
            saturation_mm=292.0,
            initial_root_zone_water_mm=148.0,
            initial_nitrogen_kg_ha=76.0,
            drainage_coeff=0.14,
        ),
    )


def objective_context_for_id(objective_id: str) -> ObjectiveContext:
    base = default_objective_context()
    if objective_id == "profit":
        return base
    if objective_id == "water_saving":
        return ObjectiveContext(
            objective_id="water_saving",
            objective_name="yield_with_water_penalty",
            primary_metric="mean_reward",
            reward_contract="reward_v2",
            reward_weights={
                "yield_revenue": 1.0,
                "irrigation_cost": 1.2,
                "nitrogen_cost": 0.9,
                "operation_cost": 1.0,
                "water_penalty": 1.6,
                "nitrogen_leaching_penalty": 0.6,
                "risk_penalty": 0.35,
            },
            budget_constraints=dict(base.budget_constraints),
            soft_preferences={
                **dict(base.soft_preferences),
                "environmental_priority_weights": {
                    "water_penalty": 1.6,
                    "nitrogen_leaching_penalty": 0.6,
                    "risk_penalty": 0.35,
                },
            },
            report_metrics=list(base.report_metrics),
            environmental_metric_specs=list(base.environmental_metric_specs),
            missing_details=list(base.missing_details),
            notes="Scenario preset prioritizing water productivity under fixed budgets.",
        )
    if objective_id == "nitrogen_saving":
        return ObjectiveContext(
            objective_id="nitrogen_saving",
            objective_name="yield_with_nitrogen_penalty",
            primary_metric="mean_reward",
            reward_contract="reward_v2",
            reward_weights={
                "yield_revenue": 1.0,
                "irrigation_cost": 0.9,
                "nitrogen_cost": 1.3,
                "operation_cost": 1.0,
                "water_penalty": 0.7,
                "nitrogen_leaching_penalty": 1.5,
                "risk_penalty": 0.35,
            },
            budget_constraints=dict(base.budget_constraints),
            soft_preferences={
                **dict(base.soft_preferences),
                "environmental_priority_weights": {
                    "water_penalty": 0.7,
                    "nitrogen_leaching_penalty": 1.5,
                    "risk_penalty": 0.35,
                },
            },
            report_metrics=list(base.report_metrics),
            environmental_metric_specs=list(base.environmental_metric_specs),
            missing_details=list(base.missing_details),
            notes="Scenario preset prioritizing nitrogen efficiency and low leaching.",
        )
    if objective_id == "balanced_resource":
        return ObjectiveContext(
            objective_id="balanced_resource",
            objective_name="balanced_profit_resource_tradeoff",
            primary_metric="mean_reward",
            reward_contract="reward_v2",
            reward_weights={
                "yield_revenue": 1.0,
                "irrigation_cost": 1.05,
                "nitrogen_cost": 1.05,
                "operation_cost": 1.0,
                "water_penalty": 1.0,
                "nitrogen_leaching_penalty": 1.0,
                "risk_penalty": 0.4,
            },
            budget_constraints=dict(base.budget_constraints),
            soft_preferences={
                **dict(base.soft_preferences),
                "environmental_priority_weights": {
                    "water_penalty": 1.0,
                    "nitrogen_leaching_penalty": 1.0,
                    "risk_penalty": 0.4,
                },
            },
            report_metrics=list(base.report_metrics),
            environmental_metric_specs=list(base.environmental_metric_specs),
            missing_details=list(base.missing_details),
            notes="Scenario preset balancing resource penalties more evenly than profit mode.",
        )
    raise ValueError(f"Unsupported objective preset: {objective_id}")


def objective_context_library() -> tuple[ObjectiveContext, ...]:
    return tuple(
        objective_context_for_id(objective_id)
        for objective_id in ("profit", "water_saving", "nitrogen_saving", "balanced_resource")
    )


def clone_objective_context_with_reward_contract(
    objective_context: ObjectiveContext,
    reward_contract: str,
) -> ObjectiveContext:
    cloned = copy.deepcopy(objective_context)
    cloned.reward_contract = reward_contract
    return cloned


def shifted_planting_date(base_date: str, offset_days: int) -> str:
    return (date.fromisoformat(base_date) + timedelta(days=offset_days)).isoformat()


def perturbed_soil_profile(base_soil: SoilProfile, rng: random.Random) -> SoilProfile:
    water_multiplier = rng.uniform(0.78, 1.08)
    nitrogen_multiplier = rng.uniform(0.65, 1.30)
    drainage_shift = rng.uniform(-0.025, 0.025)
    return SoilProfile(
        soil_name=base_soil.soil_name,
        field_capacity_mm=base_soil.field_capacity_mm,
        wilting_point_mm=base_soil.wilting_point_mm,
        saturation_mm=base_soil.saturation_mm,
        initial_root_zone_water_mm=round(base_soil.initial_root_zone_water_mm * water_multiplier, 3),
        initial_nitrogen_kg_ha=round(base_soil.initial_nitrogen_kg_ha * nitrogen_multiplier, 3),
        drainage_coeff=round(max(0.05, min(0.25, base_soil.drainage_coeff + drainage_shift)), 4),
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
        "rice": CropSpec(
            crop_name="rice",
            season_length_days=130,
            base_temperature_c=10.0,
            optimal_temperature_c=28.0,
            radiation_use_efficiency=2.2,
            harvest_index=0.48,
            stage_water_demand={
                "emergence": 0.80,
                "vegetative": 1.10,
                "reproductive": 1.15,
                "grain_fill": 0.90,
            },
            stage_nitrogen_demand={
                "emergence": 0.6,
                "vegetative": 1.6,
                "reproductive": 1.3,
                "grain_fill": 0.5,
            },
            stage_canopy_growth={
                "emergence": 0.012,
                "vegetative": 0.018,
                "reproductive": 0.010,
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


def _realistic_management_modes(weather_regime: str) -> tuple[str, ...]:
    if weather_regime == "dry":
        return ("balanced", "reproductive_focus")
    if weather_regime == "wet":
        return ("balanced", "vegetative_focus")
    return ("balanced", "vegetative_focus", "reproductive_focus")


def _realistic_budget_profile(
    *,
    crop_name: str,
    weather_regime: str,
    soil_profile: SoilProfile,
    objective_id: str,
    management_mode: str,
    rng: random.Random,
) -> tuple[float, float]:
    crop_water_base = {"maize": 348.0, "wheat": 316.0}.get(crop_name, 320.0)
    crop_n_base = {"maize": 372.0, "wheat": 332.0}.get(crop_name, 340.0)
    regime_water_adj = {"dry": 42.0, "normal": 16.0, "wet": -8.0}.get(weather_regime, 0.0)
    regime_n_adj = {"dry": 18.0, "normal": 8.0, "wet": -4.0}.get(weather_regime, 0.0)
    objective_water_adj = {
        "profit": 0.0,
        "water_saving": -22.0,
        "nitrogen_saving": -6.0,
        "balanced_resource": -10.0,
    }.get(objective_id, 0.0)
    objective_n_adj = {
        "profit": 0.0,
        "water_saving": -4.0,
        "nitrogen_saving": -24.0,
        "balanced_resource": -10.0,
    }.get(objective_id, 0.0)
    management_water_adj = {
        "balanced": 0.0,
        "vegetative_focus": 12.0,
        "reproductive_focus": 20.0,
    }.get(management_mode, 0.0)
    management_n_adj = {
        "balanced": 0.0,
        "vegetative_focus": 14.0,
        "reproductive_focus": 10.0,
    }.get(management_mode, 0.0)
    soil_water_adj = max(-28.0, min(28.0, (235.0 - soil_profile.field_capacity_mm) * 0.35 + (110.0 - soil_profile.wilting_point_mm) * 0.12))
    soil_n_adj = max(-24.0, min(24.0, (110.0 - soil_profile.initial_nitrogen_kg_ha) * 0.08))
    irrigation_budget_mm = crop_water_base + regime_water_adj + objective_water_adj + management_water_adj + soil_water_adj + rng.uniform(-12.0, 16.0)
    nitrogen_budget_kg_ha = crop_n_base + regime_n_adj + objective_n_adj + management_n_adj + soil_n_adj + rng.uniform(-14.0, 16.0)
    return (
        round(max(300.0, min(480.0, irrigation_budget_mm)), 1),
        round(max(300.0, min(480.0, nitrogen_budget_kg_ha)), 1),
    )


def build_realistic_quzhou_scenarios(
    target_count: int = 216,
    engines: tuple[str, ...] = ("dssat_official",),
    crops_filter: tuple[str, ...] | None = None,
    seed: int = 20260417,
    weather_xlsx_path: str | Path | None = None,
    soil_root_path: str | Path | None = None,
) -> list[SimulationScenario]:
    from transdssat.real_world_data import (
        build_real_weather_catalog,
        build_realistic_soil_profile,
        load_real_soil_samples,
        load_real_weather_archive,
        soil_sample_label,
    )

    crops = build_crop_specs()
    if crops_filter:
        allowed = set(crops_filter)
        crops = {name: spec for name, spec in crops.items() if name in allowed}
    if not crops or not engines or target_count <= 0:
        return []

    default_weather_xlsx = next((path for path in PROJECT_ROOT.glob("*.xlsx") if "数据" in path.name), None)
    if default_weather_xlsx is None:
        raise FileNotFoundError("Could not locate the real weather workbook under the project root.")
    default_soil_root = next(
        (path for path in PROJECT_ROOT.iterdir() if path.is_dir() and list(path.glob("*/*_test_results_wide.csv"))),
        None,
    )
    if default_soil_root is None:
        raise FileNotFoundError("Could not locate the real soil sample root under the project root.")

    weather_archive = load_real_weather_archive(weather_xlsx_path or default_weather_xlsx)
    soil_samples = load_real_soil_samples(soil_root_path or default_soil_root)
    objective_library = list(objective_context_library())
    combo_cycle = [(engine_name, crop_name, crop_spec) for engine_name in engines for crop_name, crop_spec in crops.items()]
    weather_catalog: dict[str, list[Any]] = {
        crop_name: build_real_weather_catalog(crop_name, crop_spec.season_length_days, archive=weather_archive)
        for crop_name, crop_spec in crops.items()
    }
    rng = random.Random(seed)

    for templates in weather_catalog.values():
        rng.shuffle(templates)
    rng.shuffle(soil_samples)
    rng.shuffle(objective_library)

    weather_counts: dict[tuple[str, str], int] = {}
    scenarios: list[SimulationScenario] = []
    for scenario_index in range(target_count):
        engine_name, crop_name, crop_spec = combo_cycle[scenario_index % len(combo_cycle)]
        pair_key = (engine_name, crop_name)
        local_index = weather_counts.get(pair_key, 0)
        weather_counts[pair_key] = local_index + 1
        templates = weather_catalog[crop_name]
        management_modes = ("balanced", "vegetative_focus", "reproductive_focus")
        combo_space = len(templates) * len(soil_samples) * len(objective_library) * len(management_modes)
        step = (seed + sum(ord(char) for char in f"{engine_name}:{crop_name}") * 7 + 1) % combo_space
        step = step or 1
        while math.gcd(step, combo_space) != 1:
            step = (step + 1) % combo_space or 1
        offset = (seed + sum(ord(char) for char in crop_name) * 13 + sum(ord(char) for char in engine_name) * 17) % combo_space
        rank = (local_index * step + offset) % combo_space
        management_idx = rank % len(management_modes)
        rank //= len(management_modes)
        objective_idx = rank % len(objective_library)
        rank //= len(objective_library)
        soil_idx = rank % len(soil_samples)
        rank //= len(soil_samples)
        weather_idx = rank % len(templates)
        template = templates[weather_idx]
        soil_sample = soil_samples[soil_idx]
        objective_context = objective_library[objective_idx]
        management_mode = management_modes[management_idx]
        scenario_seed = seed + scenario_index * 97 + int(template.station_id)
        scenario_rng = random.Random(scenario_seed)
        soil_profile = build_realistic_soil_profile(
            soil_sample,
            weather_archive,
            template.station_id,
            template.planting_date,
            scenario_rng,
        )
        irrigation_budget_mm, nitrogen_budget_kg_ha = _realistic_budget_profile(
            crop_name=crop_name,
            weather_regime=template.weather_regime,
            soil_profile=soil_profile,
            objective_id=objective_context.objective_id,
            management_mode=management_mode,
            rng=scenario_rng,
        )
        scenario_id = (
            f"{engine_name}-{crop_name}-real{scenario_index:05d}-st{template.station_id}-wy{template.weather_year}-"
            f"{template.weather_regime}-irr{int(round(irrigation_budget_mm))}-n{int(round(nitrogen_budget_kg_ha))}-"
            f"{management_mode}-{objective_context.objective_id}-{soil_sample_label(soil_sample)}"
        )
        scenarios.append(
            SimulationScenario(
                scenario_id=scenario_id,
                engine_name=engine_name,
                crop_spec=crop_spec,
                soil_profile=soil_profile,
                weather_regime=template.weather_regime,
                weather=list(template.weather),
                irrigation_budget_mm=irrigation_budget_mm,
                nitrogen_budget_kg_ha=nitrogen_budget_kg_ha,
                management_mode=management_mode,
                seed=scenario_seed,
                weather_year=template.weather_year,
                planting_date=template.planting_date.isoformat(),
                cultivar_code={"wheat": "QM6-WH", "maize": "ZD958-MZ"}[crop_name],
                template_name=f"{crop_name}_quzhou_base",
                experiment_file={"wheat": "KSAS8101.WHX", "maize": "UFGA8201.MZX"}[crop_name],
                crop_context=build_cultivar_context(
                    crop_name=crop_name,
                    cultivar_code={"wheat": "QM6-WH", "maize": "ZD958-MZ"}[crop_name],
                ),
                objective_context=objective_context,
                decision_context=DecisionContext(
                    weather_mode="realistic",
                ),
            )
        )

    return scenarios


def build_quzhou_scenarios(
    target_count: int = 216,
    engines: tuple[str, ...] = ("dssat_official",),
    crops_filter: tuple[str, ...] | None = None,
    sampling_mode: str = "grid",
    seed: int = 20260417,
    real_weather_xlsx: str | Path | None = None,
    real_soil_root: str | Path | None = None,
) -> list[SimulationScenario]:
    if sampling_mode == "realistic":
        return build_realistic_quzhou_scenarios(
            target_count=target_count,
            engines=engines,
            crops_filter=crops_filter,
            seed=seed,
            weather_xlsx_path=real_weather_xlsx,
            soil_root_path=real_soil_root,
        )
    soil = quzhou_typical_soil()
    crops = build_crop_specs()
    if crops_filter:
        allowed = set(crops_filter)
        crops = {name: spec for name, spec in crops.items() if name in allowed}
    if not crops or not engines or target_count <= 0:
        return []
    scenarios: list[SimulationScenario] = []
    weather_regimes = ("dry", "normal", "wet")
    irrigation_budgets = (300.0, 360.0, 420.0)
    nitrogen_budgets = (300.0, 360.0, 420.0)
    planting_dates = {"wheat": "2025-10-08", "maize": "2025-06-18"}
    cultivar_codes = {"wheat": "QM6-WH", "maize": "ZD958-MZ"}
    experiment_files = {"wheat": "KSAS8101.WHX", "maize": "UFGA8201.MZX"}

    if sampling_mode == "grid":
        management_modes = ("balanced", "reproductive_focus")
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
                                        weather_year=2025,
                                        planting_date=planting_dates[crop_name],
                                        cultivar_code=cultivar_codes[crop_name],
                                        template_name=f"{crop_name}_quzhou_base",
                                        experiment_file=experiment_files[crop_name],
                                        crop_context=build_cultivar_context(
                                            crop_name=crop_name,
                                            cultivar_code=cultivar_codes[crop_name],
                                        ),
                                        objective_context=default_objective_context(),
                                        decision_context=DecisionContext(),
                                    )
                                )
        return scenarios[:target_count]

    if sampling_mode != "random":
        raise ValueError(f"Unsupported sampling mode: {sampling_mode}")

    management_modes = ("balanced", "reproductive_focus", "vegetative_focus")
    combo_cycle = [(engine_name, crop_name, crop_spec) for engine_name in engines for crop_name, crop_spec in crops.items()]
    weather_years = tuple(range(2014, 2024))
    soil_library = quzhou_soil_library()
    objective_library = objective_context_library()
    budget_profiles = (
        (300.0, 300.0),
        (300.0, 360.0),
        (300.0, 420.0),
        (360.0, 300.0),
        (360.0, 360.0),
        (360.0, 420.0),
        (420.0, 320.0),
        (420.0, 380.0),
        (420.0, 440.0),
    )
    planting_windows = {
        "wheat": ((-12, -6), (-5, 4), (5, 12)),
        "maize": ((-8, -4), (-3, 3), (4, 8)),
    }
    rng = random.Random(seed)

    for scenario_index in range(target_count):
        engine_name, crop_name, crop_spec = combo_cycle[scenario_index % len(combo_cycle)]
        weather_year = weather_years[(scenario_index + rng.randrange(len(weather_years))) % len(weather_years)]
        scenario_seed = seed + scenario_index * 97 + weather_year
        regime = weather_regimes[(scenario_index + rng.randrange(len(weather_regimes))) % len(weather_regimes)]
        base_irrigation, base_nitrogen = budget_profiles[
            (scenario_index + rng.randrange(len(budget_profiles))) % len(budget_profiles)
        ]
        irrigation_budget_mm = round(max(300.0, min(480.0, base_irrigation + rng.uniform(-20.0, 20.0))), 1)
        nitrogen_budget_kg_ha = round(max(300.0, min(480.0, base_nitrogen + rng.uniform(-24.0, 24.0))), 1)
        management_mode = management_modes[rng.randrange(len(management_modes))]
        objective_context = objective_library[
            (scenario_index + rng.randrange(len(objective_library))) % len(objective_library)
        ]
        weather = build_representative_weather(
            crop_name=crop_name,
            regime=regime,
            season_length_days=crop_spec.season_length_days,
            seed=scenario_seed,
        )
        local_rng = random.Random(scenario_seed + 11)
        planting_window = planting_windows[crop_name][
            (scenario_index + local_rng.randrange(len(planting_windows[crop_name]))) % len(planting_windows[crop_name])
        ]
        planting_shift = local_rng.randint(planting_window[0], planting_window[1])
        base_soil = soil_library[(scenario_index + local_rng.randrange(len(soil_library))) % len(soil_library)]
        scenario_soil = perturbed_soil_profile(base_soil, local_rng)
        planting_date = shifted_planting_date(planting_dates[crop_name], planting_shift)
        scenario_id = (
            f"{engine_name}-{crop_name}-rand{scenario_index:05d}-wy{weather_year}-{regime}-"
            f"irr{int(round(irrigation_budget_mm))}-n{int(round(nitrogen_budget_kg_ha))}-"
            f"{management_mode}-{objective_context.objective_id}-{scenario_soil.soil_name}-"
            f"sw{int(round(scenario_soil.initial_root_zone_water_mm))}-"
            f"sn{int(round(scenario_soil.initial_nitrogen_kg_ha))}-pd{planting_shift:+d}"
        )
        scenarios.append(
            SimulationScenario(
                scenario_id=scenario_id,
                engine_name=engine_name,
                crop_spec=crop_spec,
                soil_profile=scenario_soil,
                weather_regime=regime,
                weather=weather,
                irrigation_budget_mm=irrigation_budget_mm,
                nitrogen_budget_kg_ha=nitrogen_budget_kg_ha,
                management_mode=management_mode,
                seed=scenario_seed,
                weather_year=weather_year,
                planting_date=planting_date,
                cultivar_code=cultivar_codes[crop_name],
                                        template_name=f"{crop_name}_quzhou_base",
                experiment_file=experiment_files[crop_name],
                crop_context=build_cultivar_context(
                    crop_name=crop_name,
                    cultivar_code=cultivar_codes[crop_name],
                ),
                objective_context=objective_context,
                decision_context=DecisionContext(),
            )
        )

    return scenarios
