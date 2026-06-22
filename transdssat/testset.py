from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, field, replace
from datetime import date, timedelta
import random
from typing import Any

from transdssat.discrete_actions import (
    default_action_constraint_rules,
    default_continuous_action_space,
    default_discrete_action_table,
)
from transdssat.data_generator import generate_training_data
from transdssat.policy_registry import PolicyRegistry, PolicyRegistryEntry
from transdssat.real_subset_assets import RealSubsetAsset, load_real_subset_asset
from transdssat.real_subset_replay import RealSubsetReplayCase, load_real_subset_replay_case
from transdssat.scenarios import STAGES, SimulationScenario, build_quzhou_scenarios, stage_for_day


@dataclass(slots=True)
class ScenarioSliceMetadata:
    slice_id: str
    slice_name: str
    slice_type: str
    paper_id: str
    title: str
    source_url: str
    matched_conditions: dict[str, Any] = field(default_factory=dict)
    reproduced_conditions: list[str] = field(default_factory=list)
    approximated_conditions: list[str] = field(default_factory=list)
    missing_conditions: list[str] = field(default_factory=list)
    scenario_constraints: dict[str, Any] = field(default_factory=dict)
    applicable_original_strategies: list[str] = field(default_factory=list)
    applicable_generalized_rules: list[str] = field(default_factory=list)
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class TestScenarioRecord:
    scenario: SimulationScenario
    crop_system: str
    season_name: str
    split: str
    sampling_mode: str
    budget_level_water: str
    budget_level_nitrogen: str
    growth_stage_boundaries: dict[str, dict[str, int]]
    slice_metadata: ScenarioSliceMetadata | None = None

    def weather_series(self) -> list[dict[str, Any]]:
        planting = date.fromisoformat(self.scenario.planting_date)
        rows: list[dict[str, Any]] = []
        for day in self.scenario.weather:
            rows.append(
                {
                    "date": (planting + timedelta(days=day.day_index)).isoformat(),
                    "tmin_c": day.tmin_c,
                    "tmax_c": day.tmax_c,
                    "precipitation_mm": day.precipitation_mm,
                    "radiation_mj_m2": day.radiation_mj_m2,
                    "et0_mm": day.et0_mm,
                }
            )
        return rows

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "scenario_id": self.scenario.scenario_id,
            "engine_name": self.scenario.engine_name,
            "crop_system": self.crop_system,
            "crop_name": self.scenario.crop_spec.crop_name,
            "crop_type": self.scenario.crop_type,
            "season_name": self.season_name,
            "planting_date": self.scenario.planting_date,
            "season_length_days": self.scenario.crop_spec.season_length_days,
            "weather_series": self.weather_series(),
            "soil_profile": asdict(self.scenario.soil_profile),
            "initial_root_zone_water_mm": self.scenario.soil_profile.initial_root_zone_water_mm,
            "initial_nitrogen_kg_ha": self.scenario.soil_profile.initial_nitrogen_kg_ha,
            "irrigation_budget_mm": self.scenario.irrigation_budget_mm,
            "nitrogen_budget_kg_ha": self.scenario.nitrogen_budget_kg_ha,
            "growth_stage_boundaries": self.growth_stage_boundaries,
            "management_mode": self.scenario.management_mode,
            "weather_regime": self.scenario.weather_regime,
            "weather_year": self.scenario.weather_year,
            "split": self.split,
            "sampling_mode": self.sampling_mode,
            "budget_level_water": self.budget_level_water,
            "budget_level_nitrogen": self.budget_level_nitrogen,
            "site_name": self.scenario.site_name,
            "cultivar_code": self.scenario.cultivar_code,
            "cultivar_id": self.scenario.cultivar_id,
            "crop_context": self.scenario.crop_context.to_dict() if self.scenario.crop_context is not None else {},
            "objective_context": self.scenario.objective_context.to_dict(),
            "decision_context": self.scenario.decision_context.to_dict(),
            "state_interface_contract": self.scenario.state_interface_contract_dict(),
            "continuous_action_space": default_continuous_action_space(self.scenario).to_dict(),
            "discrete_action_table": default_discrete_action_table(self.scenario).to_dict(),
            "action_constraint_rules": default_action_constraint_rules(self.scenario).to_dict(),
        }
        if self.slice_metadata is not None:
            payload["slice_metadata"] = self.slice_metadata.to_dict()
            payload["slice_id"] = self.slice_metadata.slice_id
            payload["paper_id"] = self.slice_metadata.paper_id
            payload["slice_type"] = self.slice_metadata.slice_type
            payload["matched_conditions"] = self.slice_metadata.matched_conditions
            payload["approximated_conditions"] = self.slice_metadata.approximated_conditions
            payload["missing_conditions"] = self.slice_metadata.missing_conditions
            payload["applicable_original_strategies"] = self.slice_metadata.applicable_original_strategies
            payload["applicable_generalized_rules"] = self.slice_metadata.applicable_generalized_rules
        return payload


@dataclass(slots=True)
class LiteratureMatchedSlice:
    metadata: ScenarioSliceMetadata
    scenarios: list[TestScenarioRecord]

    def to_dict(self) -> dict[str, Any]:
        return {
            "metadata": self.metadata.to_dict(),
            "scenarios": [record.to_dict() for record in self.scenarios],
        }


@dataclass(slots=True)
class ScenarioPoolSummary:
    total_records: int
    split_counts: dict[str, int]
    crop_counts: dict[str, int]
    engine_counts: dict[str, int]
    weather_regime_counts: dict[str, int]
    weather_year_counts: dict[str, int]
    soil_profile_counts: dict[str, int]
    objective_counts: dict[str, int]
    distinct_signature_count: int
    unique_scenario_id_count: int
    pair_coverage: dict[str, int]
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ScenarioPoolBundle:
    records: list[TestScenarioRecord]
    summary: ScenarioPoolSummary
    validation_errors: list[str] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not self.validation_errors

    def to_dict(self) -> dict[str, Any]:
        return {
            "records": [record.to_dict() for record in self.records],
            "summary": self.summary.to_dict(),
            "validation_errors": list(self.validation_errors),
            "valid": self.valid,
        }


@dataclass(slots=True)
class RealSubsetBundle:
    asset: RealSubsetAsset
    replay_cases: list[RealSubsetReplayCase] = field(default_factory=list)
    validated_treatments: list[int] = field(default_factory=list)
    canonical_subset_role: str = "stable_real_data_test_subset"
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset": self.asset.to_dict(),
            "replay_cases": [item.to_dict() for item in self.replay_cases],
            "validated_treatments": list(self.validated_treatments),
            "canonical_subset_role": self.canonical_subset_role,
            "notes": list(self.notes),
        }


REAL_SUBSET_VALIDATED_TREATMENTS: dict[str, tuple[int, ...]] = {
    "mx475_migrated": (1, 2, 3, 4, 5, 6, 7, 8),
    "wuhu_rice_calibrated": (11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 22, 23),
}


def build_growth_stage_boundaries(scenario: SimulationScenario) -> dict[str, dict[str, int]]:
    boundaries: dict[str, dict[str, int]] = {}
    stage_days = {stage: [] for stage in STAGES}
    for day_index in range(scenario.crop_spec.season_length_days):
        stage, _ = stage_for_day(day_index, scenario.crop_spec.season_length_days)
        stage_days[stage].append(day_index)
    for stage in STAGES:
        days = stage_days[stage]
        boundaries[stage] = {
            "start_day_index": days[0],
            "end_day_index": days[-1],
        }
    return boundaries


def _season_name_for_crop(crop_name: str) -> str:
    return {"wheat": "winter_wheat", "maize": "summer_maize"}.get(crop_name, f"{crop_name}_season")


def _crop_system_for_crop(crop_name: str) -> str:
    if crop_name in {"wheat", "maize"}:
        return "wheat-maize rotation"
    return f"{crop_name} only"


def _assign_level_map(values: list[float]) -> dict[float, str]:
    sorted_values = sorted(values)
    count = len(sorted_values)
    lower = sorted_values[max(0, count // 3 - 1)] if count else 0.0
    upper = sorted_values[max(0, (2 * count) // 3 - 1)] if count else 0.0
    mapping: dict[float, str] = {}
    for value in values:
        if value <= lower:
            mapping[value] = "low"
        elif value <= upper:
            mapping[value] = "medium"
        else:
            mapping[value] = "high"
    return mapping


def _enrich_records(
    scenarios: list[SimulationScenario],
    split_names: list[str],
    sampling_mode: str,
    slice_metadata: ScenarioSliceMetadata | None = None,
) -> list[TestScenarioRecord]:
    irrigation_level_map = _assign_level_map([scenario.irrigation_budget_mm for scenario in scenarios])
    nitrogen_level_map = _assign_level_map([scenario.nitrogen_budget_kg_ha for scenario in scenarios])
    records: list[TestScenarioRecord] = []
    for scenario, split in zip(scenarios, split_names):
        records.append(
            TestScenarioRecord(
                scenario=scenario,
                crop_system=_crop_system_for_crop(scenario.crop_spec.crop_name),
                season_name=_season_name_for_crop(scenario.crop_spec.crop_name),
                split=split,
                sampling_mode=sampling_mode,
                budget_level_water=irrigation_level_map[scenario.irrigation_budget_mm],
                budget_level_nitrogen=nitrogen_level_map[scenario.nitrogen_budget_kg_ha],
                growth_stage_boundaries=build_growth_stage_boundaries(scenario),
                slice_metadata=slice_metadata,
            )
        )
    return records


def generate_general_random_test_set(
    train_count: int = 2000,
    val_count: int = 300,
    test_count: int = 500,
    engines: tuple[str, ...] = ("dssat_official",),
    crops_filter: tuple[str, ...] | None = None,
    sampling_mode: str = "random",
    seed: int = 20260519,
) -> list[TestScenarioRecord]:
    total = train_count + val_count + test_count
    if sampling_mode == "training_data":
        requested_crops = tuple(crops_filter) if crops_filter else ("rice", "maize")
        supported_crops = tuple(crop for crop in requested_crops if crop in {"rice", "maize"})
        if not supported_crops:
            raise ValueError("sampling_mode='training_data' supports only rice and maize")
        count_per_crop = (total + len(supported_crops) - 1) // len(supported_crops)
        training_bundle = generate_training_data(
            count_per_crop=count_per_crop,
            crops=supported_crops,
            seed=seed,
            use_splicing=True,
        )
        target_engine = engines[0] if engines else "dssat_official"
        scenarios = [
            replace(record.scenario, engine_name=target_engine)
            for record in training_bundle.records[:total]
        ]
    else:
        scenarios = build_quzhou_scenarios(
            target_count=total,
            engines=engines,
            crops_filter=crops_filter,
            sampling_mode=sampling_mode,
            seed=seed,
        )
    rng = random.Random(seed)
    rng.shuffle(scenarios)
    split_names = ["train"] * train_count + ["val"] * val_count + ["test"] * test_count
    return _enrich_records(scenarios, split_names, sampling_mode=sampling_mode)


def summarize_scenario_pool(records: list[TestScenarioRecord]) -> ScenarioPoolSummary:
    split_counts = Counter(record.split for record in records)
    crop_counts = Counter(record.scenario.crop_spec.crop_name for record in records)
    engine_counts = Counter(record.scenario.engine_name for record in records)
    weather_regime_counts = Counter(record.scenario.weather_regime for record in records)
    weather_year_counts = Counter(str(record.scenario.weather_year) for record in records)
    soil_profile_counts = Counter(record.scenario.soil_profile.soil_name for record in records)
    objective_counts = Counter(record.scenario.objective_context.objective_id for record in records)
    scenario_ids = {record.scenario.scenario_id for record in records}
    signatures = {_scenario_signature(record) for record in records}
    return ScenarioPoolSummary(
        total_records=len(records),
        split_counts=dict(sorted(split_counts.items())),
        crop_counts=dict(sorted(crop_counts.items())),
        engine_counts=dict(sorted(engine_counts.items())),
        weather_regime_counts=dict(sorted(weather_regime_counts.items())),
        weather_year_counts=dict(sorted(weather_year_counts.items())),
        soil_profile_counts=dict(sorted(soil_profile_counts.items())),
        objective_counts=dict(sorted(objective_counts.items())),
        distinct_signature_count=len(signatures),
        unique_scenario_id_count=len(scenario_ids),
        pair_coverage={
            "crop_x_split": _pair_coverage(records, lambda record: record.scenario.crop_spec.crop_name, lambda record: record.split),
            "weather_regime_x_soil": _pair_coverage(
                records,
                lambda record: record.scenario.weather_regime,
                lambda record: record.scenario.soil_profile.soil_name,
            ),
            "weather_year_x_objective": _pair_coverage(
                records,
                lambda record: str(record.scenario.weather_year),
                lambda record: record.scenario.objective_context.objective_id,
            ),
            "budget_water_x_budget_nitrogen": _pair_coverage(
                records,
                lambda record: record.budget_level_water,
                lambda record: record.budget_level_nitrogen,
            ),
        },
        notes=[
            "distinct_signature tracks cross-dimension uniqueness over crop, weather, soil, planting, budget, objective, and initial-state fields",
            "pair_coverage reports how many cross-dimension combinations are represented in the sampled pool",
        ],
    )


def validate_scenario_pool(
    records: list[TestScenarioRecord],
    *,
    expected_total: int | None = None,
    min_weather_regimes: int = 1,
    min_weather_years: int = 1,
    min_soils: int = 1,
    min_objectives: int = 1,
) -> list[str]:
    summary = summarize_scenario_pool(records)
    errors: list[str] = []
    if expected_total is not None and summary.total_records != expected_total:
        errors.append(f"record_count_mismatch:{summary.total_records}!={expected_total}")
    if summary.unique_scenario_id_count != summary.total_records:
        errors.append("duplicate_scenario_id_detected")
    if summary.distinct_signature_count != summary.total_records:
        errors.append("duplicate_cross_dimension_signature_detected")
    if len(summary.weather_regime_counts) < min_weather_regimes:
        errors.append("insufficient_weather_regime_coverage")
    if len(summary.weather_year_counts) < min_weather_years:
        errors.append("insufficient_weather_year_coverage")
    if len(summary.soil_profile_counts) < min_soils:
        errors.append("insufficient_soil_profile_coverage")
    if len(summary.objective_counts) < min_objectives:
        errors.append("insufficient_objective_coverage")
    for record in records:
        if not record.scenario.planting_date:
            errors.append(f"missing_planting_date:{record.scenario.scenario_id}")
        if not record.scenario.weather:
            errors.append(f"missing_weather_series:{record.scenario.scenario_id}")
        if record.scenario.crop_context is None:
            errors.append(f"missing_crop_context:{record.scenario.scenario_id}")
    return errors


def generate_training_scenario_pool(
    train_count: int = 9000,
    val_count: int = 500,
    test_count: int = 500,
    engines: tuple[str, ...] = ("dssat_official",),
    crops_filter: tuple[str, ...] | None = None,
    sampling_mode: str = "random",
    seed: int = 20260519,
) -> ScenarioPoolBundle:
    records = generate_general_random_test_set(
        train_count=train_count,
        val_count=val_count,
        test_count=test_count,
        engines=engines,
        crops_filter=crops_filter,
        sampling_mode=sampling_mode,
        seed=seed,
    )
    total = train_count + val_count + test_count
    validation_errors = validate_scenario_pool(
        records,
        expected_total=total,
        min_weather_regimes=3 if total >= 3 else 1,
        min_weather_years=5 if total >= 1000 else 1,
        min_soils=4 if total >= 1000 else 1,
        min_objectives=(1 if sampling_mode == "training_data" else (4 if total >= 1000 else 1)),
    )
    return ScenarioPoolBundle(
        records=records,
        summary=summarize_scenario_pool(records),
        validation_errors=validation_errors,
    )


def scenario_metadata_map(record: TestScenarioRecord) -> dict[str, Any]:
    return record.to_dict()


def _scenario_signature(record: TestScenarioRecord) -> tuple[Any, ...]:
    return (
        record.scenario.crop_spec.crop_name,
        record.scenario.engine_name,
        record.scenario.weather_regime,
        record.scenario.weather_year,
        record.scenario.soil_profile.soil_name,
        record.scenario.planting_date,
        record.scenario.objective_context.objective_id,
        record.budget_level_water,
        record.budget_level_nitrogen,
        record.scenario.management_mode,
        round(record.scenario.irrigation_budget_mm, 1),
        round(record.scenario.nitrogen_budget_kg_ha, 1),
        round(record.scenario.soil_profile.initial_root_zone_water_mm, 1),
        round(record.scenario.soil_profile.initial_nitrogen_kg_ha, 1),
    )


def _pair_coverage(records: list[TestScenarioRecord], left_key, right_key) -> int:
    return len({(left_key(record), right_key(record)) for record in records})


def _paper_constraints(entry: PolicyRegistryEntry) -> dict[str, Any]:
    crops: list[str] = []
    normalized = entry.crop_system.lower()
    if "wheat" in normalized:
        crops.append("wheat")
    if "maize" in normalized:
        crops.append("maize")
    return {
        "crop_system": entry.crop_system,
        "crop_names": crops,
    }


def scenario_matches_constraints(record: TestScenarioRecord, constraints: dict[str, Any]) -> bool:
    crop_names = constraints.get("crop_names")
    if crop_names and record.scenario.crop_spec.crop_name not in crop_names:
        return False
    crop_system = constraints.get("crop_system")
    if crop_system and record.crop_system != crop_system:
        normalized = crop_system.lower()
        # Current project scenarios are single-season records inside a wheat-maize rotation scaffold.
        # For single-crop literature papers we allow crop-name matching and record the crop-system gap
        # in slice metadata instead of discarding every candidate.
        if "rotation" in normalized:
            return False
    weather_regimes = constraints.get("weather_regimes")
    if weather_regimes and record.scenario.weather_regime not in weather_regimes:
        return False
    management_modes = constraints.get("management_modes")
    if management_modes and record.scenario.management_mode not in management_modes:
        return False
    return True


def generate_literature_matched_slices(
    registry: PolicyRegistry,
    scenario_count_per_slice: int = 100,
    engines: tuple[str, ...] = ("dssat_official",),
    crops_filter: tuple[str, ...] | None = None,
    seed: int = 20260519,
) -> list[LiteratureMatchedSlice]:
    estimated_pool = max(200, scenario_count_per_slice * max(1, len(registry.entries)) * 2)
    base_records = generate_general_random_test_set(
        train_count=estimated_pool,
        val_count=0,
        test_count=0,
        engines=engines,
        crops_filter=crops_filter,
        seed=seed,
    )
    rng = random.Random(seed)
    rng.shuffle(base_records)
    slices: list[LiteratureMatchedSlice] = []
    for entry in registry.entries.values():
        constraints = _paper_constraints(entry)
        candidates = [record for record in base_records if scenario_matches_constraints(record, constraints)]
        selected = candidates[:scenario_count_per_slice]
        metadata = ScenarioSliceMetadata(
            slice_id=entry.required_scenario_slice or f"{entry.paper_id}_matched_slice",
            slice_name=entry.title,
            slice_type="literature_matched",
            paper_id=entry.paper_id,
            title=entry.title,
            source_url=entry.source_url,
            matched_conditions=constraints,
            reproduced_conditions=[f"crop_system={entry.crop_system}"],
            approximated_conditions=[
                "slice built from project random scenario pool under documented crop-system constraints only",
            ],
            missing_conditions=list(entry.missing_details),
            scenario_constraints=constraints,
            applicable_original_strategies=[item.strategy_id for item in entry.original_strategies],
            applicable_generalized_rules=[item.rule_id for item in entry.generalized_rules],
            notes=entry.notes,
        )
        selected_records = _enrich_records(
            [record.scenario for record in selected],
            split_names=["test"] * len(selected),
            sampling_mode="literature_matched",
            slice_metadata=metadata,
        )
        slices.append(LiteratureMatchedSlice(metadata=metadata, scenarios=selected_records))
    return slices


def load_real_data_test_subset(subset_id: str) -> RealSubsetBundle:
    asset = load_real_subset_asset(subset_id)
    validated_treatments = list(REAL_SUBSET_VALIDATED_TREATMENTS.get(subset_id, ()))
    replay_cases = [load_real_subset_replay_case(subset_id, treatment_no) for treatment_no in validated_treatments]
    return RealSubsetBundle(
        asset=asset,
        replay_cases=replay_cases,
        validated_treatments=validated_treatments,
        notes=[
            "This bundle is the canonical stable real-data test subset entrypoint for replay-based rice validation.",
            "Validated treatments are the current original-management replay anchors before irrigation/fertilizer-only replacement experiments.",
        ],
    )


def load_real_data_test_subsets(subset_ids: tuple[str, ...] = ("mx475_migrated", "wuhu_rice_calibrated")) -> list[RealSubsetBundle]:
    return [load_real_data_test_subset(subset_id) for subset_id in subset_ids]
