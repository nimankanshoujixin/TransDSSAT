"""Training data generator 鈥?replacement for the deprecated generate_training_scenario_pool.

Design: docs/data-generator-spec-cn.md
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
import json
import math
import random
from pathlib import Path
from typing import Any

from transdssat.real_world_data import (
    RealSoilSampleRecord,
    RealWeatherArchive,
    RealWeatherSeasonTemplate,
    build_real_weather_catalog,
    build_realistic_soil_profile,
    load_real_soil_samples,
    load_real_weather_archive,
    soil_sample_label,
)
from transdssat.scenarios import (
    CropSpec,
    DecisionContext,
    SimulationScenario,
    SoilProfile,
    WeatherDay,
    build_crop_specs,
    build_cultivar_context,
    default_objective_context,
    default_state_interface_contract,
)
from transdssat.season import SeasonPolicy, StageDecision, apply_control_mode

# ---------------------------------------------------------------------------
# 1.  Test-set exclusion registry
# ---------------------------------------------------------------------------

# Weather stations / years used by real-data test subsets.
# These MUST NOT be sampled for training data.
_EXCLUDED_WEATHER_STATIONS: set[str] = {"WH20", "EQAH"}
_EXCLUDED_WEATHER_YEARS: dict[str, set[int]] = {
    "WH20": set(range(2000, 2022)),
    "EQAH": {2021},
}

# Soil identifiers used by real-data test subsets.
# These MUST NOT be sampled for training data.
_EXCLUDED_SOIL_IDS: set[str] = {
    "SOIL.SOL",   # mx475  test set
    "CN.SOL",     # wuhu  test set
    "WH.SOL",     # wuhu  test set
}

# Planting windows used by test subsets (PDATE anchor).
# Prevent exact date overlap.
_TEST_PLANTING_WINDOWS: dict[str, tuple[date, date]] = {
    "mx475_tr1_7": (date(2021, 6, 16), date(2021, 6, 16)),
    "mx475_tr8":   (date(2021, 3, 23), date(2021, 3, 23)),
    "wuhu_rice":   (date(2021, 7, 4),  date(2021, 7, 4)),
}


def _overlaps_test_planting_window(planting_date: date) -> bool:
    return any(start_date <= planting_date <= end_date for start_date, end_date in _TEST_PLANTING_WINDOWS.values())

# ---------------------------------------------------------------------------
# 2.  Calibrated cultivar table
# ---------------------------------------------------------------------------

_CALIBRATED_CULTIVARS: dict[str, list[str]] = {
    "rice":  ["IB2002", "WHR006"],
    "maize": ["DH6051"],
    "wheat": [],  # no calibrated parameters yet
}

# ---------------------------------------------------------------------------
# 3.  Management baseline generators
# ---------------------------------------------------------------------------

_RICE_SEASON_DAYS: int = 130
_MAIZE_SEASON_DAYS: int = 135

# Literature-based rice management for South China
_RICE_HEURISTIC_IRRIGATION: list[tuple[int, float]] = [
    (0,  30.0),   # transplanting water
    (7,  25.0),   # green-up
    (14, 20.0),   # tillering
    (28, 25.0),   # active tillering
    (42, 30.0),   # panicle initiation
    (56, 35.0),   # booting
    (70, 35.0),   # heading
    (80, 30.0),   # grain fill early
    (95, 25.0),   # grain fill late
]

_RICE_HEURISTIC_NITROGEN: list[tuple[int, float]] = [
    (0,  30.0),   # basal
    (15, 45.0),   # tillering
    (45, 45.0),   # panicle initiation
]

_MAIZE_HEURISTIC_IRRIGATION: list[tuple[int, float]] = [
    (0,  35.0),
    (20, 40.0),
    (45, 45.0),
    (65, 40.0),
    (85, 35.0),
]

_MAIZE_HEURISTIC_NITROGEN: list[tuple[int, float]] = [
    (0,  60.0),
    (35, 90.0),
    (60, 60.0),
]


def _build_heuristic_rice_policy(planting_date: date) -> SeasonPolicy:
    actions: list[StageDecision] = []
    for offset, amount in _RICE_HEURISTIC_IRRIGATION:
        event_date = planting_date + timedelta(days=offset)
        actions.append(StageDecision(
            stage=f"irr_{offset:03d}",
            day_index=offset,
            date=event_date.isoformat(),
            irrigation_mm=amount,
            nitrogen_kg_ha=0.0,
        ))
    for offset, amount in _RICE_HEURISTIC_NITROGEN:
        event_date = planting_date + timedelta(days=offset)
        actions.append(StageDecision(
            stage=f"n_{offset:03d}",
            day_index=offset,
            date=event_date.isoformat(),
            irrigation_mm=0.0,
            nitrogen_kg_ha=amount,
        ))
    actions.sort(key=lambda a: (a.day_index, a.stage))
    return SeasonPolicy(
        policy_id="heuristic_rice_literature",
        scenario_id="training",
        actions=actions,
    )


def _build_heuristic_maize_policy(planting_date: date) -> SeasonPolicy:
    actions: list[StageDecision] = []
    for offset, amount in _MAIZE_HEURISTIC_IRRIGATION:
        event_date = planting_date + timedelta(days=offset)
        actions.append(StageDecision(
            stage=f"irr_{offset:03d}",
            day_index=offset,
            date=event_date.isoformat(),
            irrigation_mm=amount,
            nitrogen_kg_ha=0.0,
        ))
    for offset, amount in _MAIZE_HEURISTIC_NITROGEN:
        event_date = planting_date + timedelta(days=offset)
        actions.append(StageDecision(
            stage=f"n_{offset:03d}",
            day_index=offset,
            date=event_date.isoformat(),
            irrigation_mm=0.0,
            nitrogen_kg_ha=amount,
        ))
    actions.sort(key=lambda a: (a.day_index, a.stage))
    return SeasonPolicy(
        policy_id="heuristic_maize_literature",
        scenario_id="training",
        actions=actions,
    )


HEURISTIC_POLICY_BUILDERS = {
    "rice":  _build_heuristic_rice_policy,
    "maize": _build_heuristic_maize_policy,
}

# ---------------------------------------------------------------------------
# 4.  Data structures
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class TrainingScenarioRecord:
    """One generated training scenario with dual-format output."""
    scenario: SimulationScenario
    policy: SeasonPolicy
    planting_date: date
    cultivar_code: str

    # Weather metadata
    weather_station_id: str = ""
    weather_temp_year: int = 0
    weather_precip_year: int = 0
    year_spliced: bool = False

    # Soil metadata
    soil_sample_id: str = ""
    soil_synthetic: bool = False

    # Management
    plant_density: float = 25.0
    row_spacing: float = 20.0
    planting_method: str = "T"
    planting_depth: float = 3.0
    preplant_date: str = ""
    initial_soil_water_layers: list[float] = field(default_factory=list)
    initial_no3_layers: list[float] = field(default_factory=list)
    initial_nh4_layers: list[float] = field(default_factory=list)
    initial_layer_depths_cm: list[int] = field(default_factory=lambda: [10, 10, 10, 10])

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario": self.scenario.to_dict() if hasattr(self.scenario, "to_dict") else str(self.scenario),
            "policy": self.policy.to_dict(),
            "planting_date": self.planting_date.isoformat(),
            "cultivar_code": self.cultivar_code,
            "weather_station_id": self.weather_station_id,
            "weather_temp_year": self.weather_temp_year,
            "weather_precip_year": self.weather_precip_year,
            "year_spliced": self.year_spliced,
            "soil_sample_id": self.soil_sample_id,
            "soil_synthetic": self.soil_synthetic,
            "plant_density": self.plant_density,
            "row_spacing": self.row_spacing,
            "planting_method": self.planting_method,
            "planting_depth": self.planting_depth,
            "preplant_date": self.preplant_date,
            "initial_soil_water_layers": list(self.initial_soil_water_layers),
            "initial_no3_layers": list(self.initial_no3_layers),
            "initial_nh4_layers": list(self.initial_nh4_layers),
            "initial_layer_depths_cm": list(self.initial_layer_depths_cm),
        }


# ---------------------------------------------------------------------------
# 5.  Core generator functions
# ---------------------------------------------------------------------------

def _splice_weather_years(
    archive: RealWeatherArchive,
    station_id: str,
    temp_year: int,
    precip_year: int,
    planting_date: date,
    season_length_days: int,
) -> list[WeatherDay]:
    """Build a weather sequence where temperature comes from temp_year and
    precipitation/radiation come from precip_year (year-splicing)."""
    station_rows = archive.rows_by_station.get(station_id, {})
    weather: list[WeatherDay] = []
    for day_index in range(season_length_days):
        observed_date = planting_date + timedelta(days=day_index)
        temp_date = date(temp_year, observed_date.month, observed_date.day)
        precip_date = date(precip_year, observed_date.month, observed_date.day)
        temp_obs = station_rows.get(temp_date)
        precip_obs = station_rows.get(precip_date)
        if temp_obs is None or precip_obs is None:
            return []  # gap in data, reject
        weather.append(WeatherDay(
            day_index=day_index,
            tmin_c=temp_obs.tmin_c,
            tmax_c=temp_obs.tmax_c,
            precipitation_mm=precip_obs.precipitation_mm,
            radiation_mj_m2=precip_obs.radiation_mj_m2,
            et0_mm=precip_obs.et0_mm,
        ))
    return weather


def _sample_weather_sequence(
    archive: RealWeatherArchive,
    crop_name: str,
    season_length_days: int,
    rng: random.Random,
    use_splicing: bool = True,
) -> tuple[list[WeatherDay], str, int, int, bool, date]:
    """Sample a weather sequence with station and year selection, optionally splicing."""
    from transdssat.real_world_data import _planting_anchor, _planting_offset_range, _real_weather_candidate_years

    allowed_stations = [
        sid for sid in archive.rows_by_station
        if sid not in _EXCLUDED_WEATHER_STATIONS
    ]
    if not allowed_stations:
        raise RuntimeError("No non-excluded weather stations available")

    station_id = rng.choice(allowed_stations)
    anchor = _planting_anchor(crop_name)
    offsets = tuple(_planting_offset_range(crop_name))
    allowed_years = _real_weather_candidate_years(crop_name, archive)

    # Try up to 100 times to find a valid window
    for _attempt in range(100):
        offset = rng.choice(offsets)
        planting_date = date(2025, anchor.month, anchor.day) + timedelta(days=offset)

        if use_splicing and rng.random() < 0.5:
            temp_year = rng.choice(allowed_years)
            precip_year = rng.choice(allowed_years)
            spliced_planting_date = date(max(temp_year, precip_year), planting_date.month, planting_date.day)
            if _overlaps_test_planting_window(spliced_planting_date):
                continue
            weather = _splice_weather_years(
                archive, station_id, temp_year, precip_year,
                planting_date, season_length_days,
            )
            if weather:
                return weather, station_id, temp_year, precip_year, True, spliced_planting_date
        else:
            year = rng.choice(allowed_years)
            adjusted_date = date(year, planting_date.month, planting_date.day)
            if _overlaps_test_planting_window(adjusted_date):
                continue
            end_date = adjusted_date + timedelta(days=season_length_days - 1)
            if adjusted_date < archive.min_date or end_date > archive.max_date:
                continue
            station_rows = archive.rows_by_station.get(station_id, {})
            weather: list[WeatherDay] = []
            for day_index in range(season_length_days):
                obs = station_rows.get(adjusted_date + timedelta(days=day_index))
                if obs is None:
                    weather = []
                    break
                weather.append(WeatherDay(
                    day_index=day_index,
                    tmin_c=obs.tmin_c,
                    tmax_c=obs.tmax_c,
                    precipitation_mm=obs.precipitation_mm,
                        radiation_mj_m2=obs.radiation_mj_m2,
                        et0_mm=obs.et0_mm,
                    ))
            if weather:
                return weather, station_id, year, year, False, adjusted_date

    raise RuntimeError(f"Failed to sample weather for {crop_name} after 100 attempts")


def _sample_soil_profile(rng: random.Random) -> tuple[SoilProfile, RealSoilSampleRecord, bool]:
    """Sample a soil profile, excluding test-set soils."""
    samples = load_real_soil_samples()
    valid_samples = [
        s for s in samples
        if s.sample_id not in _EXCLUDED_SOIL_IDS
        and s.soil_profile.soil_name not in _EXCLUDED_SOIL_IDS
    ]
    if not valid_samples:
        raise RuntimeError("No non-excluded soil samples available")

    sample = rng.choice(valid_samples)
    # Apply slight perturbation for diversity
    soil = sample.soil_profile
    perturbed = SoilProfile(
        soil_name=soil.soil_name,
        field_capacity_mm=round(soil.field_capacity_mm + rng.uniform(-5, 5), 3),
        wilting_point_mm=round(max(10, soil.wilting_point_mm + rng.uniform(-3, 3)), 3),
        saturation_mm=round(soil.saturation_mm + rng.uniform(-5, 5), 3),
        initial_root_zone_water_mm=round(
            soil.wilting_point_mm + 0.5 * (soil.field_capacity_mm - soil.wilting_point_mm)
            + rng.uniform(-10, 10), 3
        ),
        initial_nitrogen_kg_ha=round(soil.initial_nitrogen_kg_ha + rng.uniform(-8, 8), 3),
        drainage_coeff=round(max(0.01, min(0.3, soil.drainage_coeff + rng.uniform(-0.01, 0.01))), 4),
    )
    # Ensure physical constraints
    perturbed.field_capacity_mm = max(100, perturbed.field_capacity_mm)
    perturbed.saturation_mm = max(perturbed.field_capacity_mm + 20, perturbed.saturation_mm)
    perturbed.initial_root_zone_water_mm = min(
        perturbed.saturation_mm,
        max(20, perturbed.initial_root_zone_water_mm),
    )
    perturbed.initial_nitrogen_kg_ha = max(10, min(200, perturbed.initial_nitrogen_kg_ha))

    synthetic = abs(perturbed.initial_nitrogen_kg_ha - soil.initial_nitrogen_kg_ha) > 1.0

    return perturbed, sample, synthetic


def _select_cultivar(crop_name: str, rng: random.Random) -> str:
    """Select a calibrated cultivar for the given crop."""
    cultivars = _CALIBRATED_CULTIVARS.get(crop_name, [])
    if not cultivars:
        raise ValueError(f"No calibrated cultivars for crop: {crop_name}")
    return rng.choice(cultivars)


def _generate_planting_details(
    crop_name: str,
    planting_date: date,
    season_length_days: int,
    rng: random.Random,
) -> dict[str, Any]:
    """Generate management details beyond water/fertilizer."""
    if crop_name == "rice":
        return dict(
            planting_date=planting_date.isoformat(),
            planting_method=rng.choice(["T", "T", "T", "S"]),  # 75% transplant
            plant_density=round(rng.uniform(20, 35), 0),
            row_spacing=round(rng.uniform(15, 30), 0),
            planting_depth=round(rng.uniform(2, 5), 1),
            preplant_date=(planting_date - timedelta(days=15)).isoformat(),
            initial_no3_top=round(rng.uniform(0.4, 1.5), 2),
            initial_nh4_top=round(rng.uniform(2.0, 6.0), 2),
            initial_no3_mid=round(rng.uniform(0.3, 1.2), 2),
            initial_nh4_mid=round(rng.uniform(1.5, 5.0), 2),
            initial_no3_lower=round(rng.uniform(0.25, 1.0), 2),
            initial_nh4_lower=round(rng.uniform(1.2, 4.0), 2),
            initial_no3_deep=round(rng.uniform(0.2, 0.8), 2),
            initial_nh4_deep=round(rng.uniform(1.0, 3.0), 2),
        )
    elif crop_name == "maize":
        return dict(
            planting_date=planting_date.isoformat(),
            planting_method="S",  # maize is direct-seeded
            plant_density=round(rng.uniform(6, 10), 1),
            row_spacing=round(rng.uniform(50, 70), 0),
            planting_depth=round(rng.uniform(3, 6), 1),
            preplant_date=(planting_date - timedelta(days=15)).isoformat(),
            initial_no3_top=round(rng.uniform(0.5, 2.0), 2),
            initial_nh4_top=round(rng.uniform(2.0, 7.0), 2),
            initial_no3_mid=round(rng.uniform(0.3, 1.5), 2),
            initial_nh4_mid=round(rng.uniform(1.5, 5.5), 2),
            initial_no3_lower=round(rng.uniform(0.25, 1.2), 2),
            initial_nh4_lower=round(rng.uniform(1.2, 4.5), 2),
            initial_no3_deep=round(rng.uniform(0.2, 1.0), 2),
            initial_nh4_deep=round(rng.uniform(1.0, 4.0), 2),
        )
    else:
        raise ValueError(f"Unsupported crop: {crop_name}")


def generate_one_training_scenario(
    crop_name: str,
    rng: random.Random,
    use_splicing: bool = True,
    site_name: str = "training",
    scenario_serial: int | None = None,
) -> TrainingScenarioRecord:
    """Generate a single training scenario with all required dimensions."""

    # --- Cultivar ---
    cultivar_code = _select_cultivar(crop_name, rng)
    crop_context = build_cultivar_context(crop_name, cultivar_code, site_name=site_name)
    crop_specs = build_crop_specs()
    crop_spec = crop_specs[crop_name]
    season_length_days = crop_spec.season_length_days

    # --- Weather ---
    archive = load_real_weather_archive()
    weather, station_id, temp_year, precip_year, spliced, planting_date = _sample_weather_sequence(
        archive, crop_name, season_length_days, rng, use_splicing,
    )

    # --- Soil ---
    soil_profile, soil_sample, is_synthetic = _sample_soil_profile(rng)

    # --- Management (planting details, initial conditions) ---
    mgmt = _generate_planting_details(crop_name, planting_date, season_length_days, rng)
    initial_water_per_layer = round(soil_profile.initial_root_zone_water_mm / 4.0, 3)

    # --- Baseline policy (heuristic/literature) ---
    builder = HEURISTIC_POLICY_BUILDERS.get(crop_name)
    if builder is None:
        policy = SeasonPolicy(policy_id="noop", scenario_id="training", actions=[])
    else:
        policy = builder(planting_date)

    total_irrigation = policy.total_irrigation_mm
    total_nitrogen = policy.total_nitrogen_kg_ha

    # Weather regime classification
    precip_total = sum(d.precipitation_mm for d in weather)
    if precip_total < 400:
        weather_regime = "dry"
    elif precip_total < 800:
        weather_regime = "normal"
    else:
        weather_regime = "wet"

    # --- Build SimulationScenario ---
    serial_token = f"{scenario_serial:05d}" if scenario_serial is not None else f"{rng.randint(0, 999999):06d}"
    scenario_id = f"gen_{crop_name}_{serial_token}_{rng.randint(0, 999999):06d}"
    scenario = SimulationScenario(
        scenario_id=scenario_id,
        engine_name="real_weather",
        crop_spec=crop_spec,
        soil_profile=soil_profile,
        weather_regime=weather_regime,
        weather=weather,
        irrigation_budget_mm=total_irrigation,
        nitrogen_budget_kg_ha=total_nitrogen,
        management_mode="balanced",
        seed=rng.randint(0, 2**31 - 1),
        weather_year=temp_year,
        planting_date=planting_date.isoformat(),
        cultivar_code=cultivar_code,
        template_name=f"{crop_name}_training_base",
        experiment_file="",
        site_name=site_name,
        crop_context=crop_context,
        objective_context=default_objective_context(),
        decision_context=DecisionContext(),
    )
    policy = SeasonPolicy(
        policy_id=f"{policy.policy_id}_{scenario_id}",
        scenario_id=scenario_id,
        actions=policy.actions,
    )

    return TrainingScenarioRecord(
        scenario=scenario,
        policy=policy,
        planting_date=planting_date,
        cultivar_code=cultivar_code,
        weather_station_id=station_id,
        weather_temp_year=temp_year,
        weather_precip_year=precip_year,
        year_spliced=spliced,
        soil_sample_id=soil_sample.sample_id,
        soil_synthetic=is_synthetic,
        plant_density=mgmt["plant_density"],
        row_spacing=mgmt["row_spacing"],
        planting_method=mgmt["planting_method"],
        planting_depth=mgmt["planting_depth"],
        preplant_date=mgmt["preplant_date"],
        initial_soil_water_layers=[
            initial_water_per_layer,
            initial_water_per_layer,
            initial_water_per_layer,
            initial_water_per_layer,
        ],
        initial_no3_layers=[
            mgmt["initial_no3_top"],
            mgmt["initial_no3_mid"],
            mgmt["initial_no3_lower"],
            mgmt["initial_no3_deep"],
        ],
        initial_nh4_layers=[
            mgmt["initial_nh4_top"],
            mgmt["initial_nh4_mid"],
            mgmt["initial_nh4_lower"],
            mgmt["initial_nh4_deep"],
        ],
    )


# ---------------------------------------------------------------------------
# 6.  Bulk generation
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class TrainingDataBundle:
    """A bundle of generated training scenarios."""
    records: list[TrainingScenarioRecord]
    summary: dict[str, Any] = field(default_factory=dict)
    validation_errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "records": [r.to_dict() for r in self.records],
            "summary": self.summary,
            "validation_errors": self.validation_errors,
        }


def _validate_record(record: TrainingScenarioRecord) -> list[str]:
    """Validate a generated record against spec checklist."""
    errors: list[str] = []
    ws = record.weather_station_id
    if ws in _EXCLUDED_WEATHER_STATIONS:
        errors.append(f"Weather station {ws} overlaps with test set")

    si = record.soil_sample_id
    if si in _EXCLUDED_SOIL_IDS:
        errors.append(f"Soil {si} overlaps with test set")

    planting_date = record.planting_date
    for window_name, (start_date, end_date) in _TEST_PLANTING_WINDOWS.items():
        if start_date <= planting_date <= end_date:
            errors.append(
                f"Planting date {planting_date.isoformat()} overlaps with test window {window_name}"
            )

    cv = record.cultivar_code
    allowed = _CALIBRATED_CULTIVARS.get(record.scenario.crop_spec.crop_name, [])
    if cv not in allowed:
        errors.append(f"Cultivar {cv} not in calibrated set {allowed}")

    ctx = record.scenario.crop_context
    if ctx and ctx.cultivar.missing_details:
        errors.append(f"Cultivar {cv} has missing_details: {ctx.cultivar.missing_details}")

    # Weather sanity
    if not record.scenario.weather:
        errors.append("Empty weather sequence")
    else:
        for day in record.scenario.weather:
            if day.precipitation_mm < 0:
                errors.append(f"Negative precipitation on day {day.day_index}")

    # Soil sanity
    soil = record.scenario.soil_profile
    if soil.field_capacity_mm <= soil.wilting_point_mm:
        errors.append("field_capacity <= wilting_point")

    return errors


def generate_training_data(
    count_per_crop: int = 5000,
    crops: tuple[str, ...] = ("rice", "maize"),
    seed: int = 0,
    use_splicing: bool = True,
    country: str = "China",
    season_name: str = "summer",
) -> TrainingDataBundle:
    """Generate a training data bundle.

    Args:
        count_per_crop: number of scenarios per crop.
        crops: crops to generate.
        seed: random seed.
        use_splicing: enable year-splicing weather augmentation.
    """
    rng = random.Random(seed)
    records: list[TrainingScenarioRecord] = []
    errors: list[str] = []

    for crop in crops:
        if crop == "wheat":
            continue  # no calibrated parameters
        for i in range(count_per_crop):
            try:
                record = generate_one_training_scenario(
                    crop_name=crop,
                    rng=rng,
                    use_splicing=use_splicing,
                    scenario_serial=i,
                )
                record_errors = _validate_record(record)
                if record_errors:
                    errors.extend(record_errors)
                else:
                    records.append(record)
            except Exception as exc:
                errors.append(f"[{crop}#{i}] {exc}")

    # Build summary
    summary: dict[str, Any] = {
        "total_records": len(records),
        "total_errors": len(errors),
        "per_crop": {},
        "seed": seed,
        "use_splicing": use_splicing,
    }
    for crop in crops:
        crop_records = [r for r in records if r.scenario.crop_spec.crop_name == crop]
        cultivars = {}
        for r in crop_records:
            cultivars[r.cultivar_code] = cultivars.get(r.cultivar_code, 0) + 1
        summary["per_crop"][crop] = {
            "count": len(crop_records),
            "cultivars": cultivars,
            "spliced_count": sum(1 for r in crop_records if r.year_spliced),
        }

    return TrainingDataBundle(
        records=records,
        summary=summary,
        validation_errors=errors,
    )
