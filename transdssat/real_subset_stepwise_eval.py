from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from transdssat.real_subset_replay import RealSubsetReplayCase, load_real_subset_replay_case
from transdssat.scenarios import (
    SimulationScenario,
    SoilProfile,
    WeatherDay,
    build_crop_specs,
    build_cultivar_context,
    default_objective_context,
)
from transdssat.season import SeasonPolicy, StageDecision


ROOT_ZONE_DEPTH_CM = 40.0


@dataclass(slots=True)
class RealSubsetScenarioMaterialization:
    case: RealSubsetReplayCase
    scenario: SimulationScenario
    source_weather_file: str
    source_soil_file: str
    source_soil_id: str
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "subset_id": self.case.subset_id,
            "treatment_no": self.case.treatment.treatment_no,
            "scenario_id": self.scenario.scenario_id,
            "source_weather_file": self.source_weather_file,
            "source_soil_file": self.source_soil_file,
            "source_soil_id": self.source_soil_id,
            "notes": list(self.notes),
        }


def _yyddd_to_date(value: str) -> date:
    token = str(value).strip()
    year = int(token[:2])
    doy = int(token[2:])
    full_year = 1900 + year if year >= 50 else 2000 + year
    return date(full_year, 1, 1) + timedelta(days=doy - 1)


def _parse_treatment_planting_dates(lines: list[str]) -> dict[int, str]:
    result: dict[int, str] = {}
    in_block = False
    for raw in lines:
        line = raw.rstrip("\n")
        if line.startswith("*PLANTING DETAILS"):
            in_block = True
            continue
        if in_block and line.startswith("*") and not line.startswith("*PLANTING DETAILS"):
            break
        if not in_block or not line.strip() or line.lstrip().startswith("@"):
            continue
        parts = line.split()
        if len(parts) >= 2 and parts[0].isdigit():
            result[int(parts[0])] = parts[1]
    return result


def _parse_treatment_initial_condition_levels(lines: list[str]) -> dict[int, int]:
    result: dict[int, int] = {}
    in_block = False
    for raw in lines:
        line = raw.rstrip("\n")
        if line.startswith("*TREATMENTS"):
            in_block = True
            continue
        if in_block and line.startswith("*") and not line.startswith("*TREATMENTS"):
            break
        if not in_block or not line.strip() or line.lstrip().startswith("@"):
            continue
        parts = line.split()
        if len(parts) < 18 or not parts[0].isdigit():
            continue
        factor_values = parts[-13:]
        if len(factor_values) != 13:
            continue
        treatment_no = int(parts[0])
        ic_level = int(factor_values[3])
        result[treatment_no] = ic_level
    return result


def _parse_initial_conditions(lines: list[str], treatment_no: int) -> tuple[list[float], list[float], list[float]]:
    water_by_depth: list[float] = []
    nh4_by_depth: list[float] = []
    no3_by_depth: list[float] = []
    ic_levels = _parse_treatment_initial_condition_levels(lines)
    block_no = ic_levels.get(treatment_no, treatment_no)
    capture = False
    for raw in lines:
        line = raw.rstrip("\n")
        if line.startswith("*INITIAL CONDITIONS"):
            capture = False
            continue
        if line.startswith("@C   PCR ICDAT"):
            parts = line.split()
            capture = False
            continue
        if line.startswith("@C  ICBL"):
            capture = True
            continue
        if capture and line.startswith("*"):
            break
        if not capture or not line.strip() or line.lstrip().startswith("@"):
            continue
        parts = line.split()
        if len(parts) >= 5 and parts[0].isdigit() and int(parts[0]) == block_no:
            water_by_depth.append(float(parts[2]))
            nh4_by_depth.append(float(parts[3]))
            no3_by_depth.append(float(parts[4]))
    if not water_by_depth:
        raise ValueError(
            f"Could not locate initial condition layers for treatment {treatment_no} "
            f"(initial condition block {block_no})"
        )
    return water_by_depth, nh4_by_depth, no3_by_depth


def _parse_field_context(lines: list[str]) -> tuple[str, str]:
    in_block = False
    for raw in lines:
        line = raw.rstrip("\n")
        if line.startswith("*FIELDS"):
            in_block = True
            continue
        if in_block and line.startswith("*") and not line.startswith("*FIELDS"):
            break
        if not in_block or not line.strip() or line.lstrip().startswith("@"):
            continue
        parts = line.split()
        if len(parts) >= 12 and parts[0].isdigit():
            return parts[2], parts[11]
    raise ValueError("Could not locate field context in experiment file.")


def _estimate_et0_mm(tmin_c: float, tmax_c: float, radiation_mj_m2: float) -> float:
    diurnal_range = max(0.0, tmax_c - tmin_c)
    return round(max(0.5, 0.12 * radiation_mj_m2 + 0.08 * diurnal_range), 3)


def _parse_weather_file(path: Path, planting_date: date, season_length_days: int) -> list[WeatherDay]:
    rows: dict[date, WeatherDay] = {}
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("*") or line.startswith("@"):
            continue
        parts = line.split()
        if len(parts) < 5:
            continue
        token = parts[0]
        if not token.isdigit() or len(token) != 5:
            continue
        current_date = _yyddd_to_date(token)
        radiation = float(parts[1])
        tmax = float(parts[2])
        tmin = float(parts[3])
        rain = float(parts[4])
        rows[current_date] = WeatherDay(
            day_index=0,
            tmin_c=tmin,
            tmax_c=tmax,
            precipitation_mm=rain,
            radiation_mj_m2=radiation,
            et0_mm=_estimate_et0_mm(tmin, tmax, radiation),
        )

    weather: list[WeatherDay] = []
    for day_index in range(season_length_days):
        current_date = planting_date + timedelta(days=day_index)
        if current_date not in rows:
            raise ValueError(f"Missing weather row for {current_date.isoformat()} in {path}")
        day = rows[current_date]
        weather.append(
            WeatherDay(
                day_index=day_index,
                tmin_c=day.tmin_c,
                tmax_c=day.tmax_c,
                precipitation_mm=day.precipitation_mm,
                radiation_mj_m2=day.radiation_mj_m2,
                et0_mm=day.et0_mm,
            )
        )
    return weather


def _find_weather_file(source_root: Path, station_code: str, planting_date: date) -> Path:
    year_suffix = f"{planting_date.year % 100:02d}"
    preferred = list(source_root.rglob(f"{station_code}{year_suffix}*.WTH"))
    if preferred:
        return preferred[0]
    candidates = list(source_root.rglob(f"{station_code}*.WTH"))
    if candidates:
        return candidates[0]
    raise FileNotFoundError(f"Could not find weather file for station {station_code} under {source_root}")


def _find_soil_file(source_root: Path, soil_id: str) -> Path:
    candidates = sorted(source_root.rglob("*.SOL"))
    for path in candidates:
        text = path.read_text(encoding="utf-8", errors="ignore")
        if f"*{soil_id}" in text:
            return path
    if candidates:
        return candidates[0]
    raise FileNotFoundError(f"Could not locate any .SOL file under {source_root}")


def _parse_soil_profile(path: Path, soil_id: str, initial_water: list[float], initial_nh4: list[float], initial_no3: list[float]) -> SoilProfile:
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    marker = f"*{soil_id}"
    start = next((index for index, line in enumerate(lines) if line.startswith(marker)), None)
    if start is None:
        raise ValueError(f"Could not locate soil profile {soil_id} in {path}")

    sl_dr = 0.5
    in_layers = False
    layer_rows: list[list[str]] = []
    for line in lines[start + 1 :]:
        if line.startswith("*") and not line.startswith(marker):
            break
        if line.startswith("@ SCOM"):
            continue
        if line.startswith("@  SLB"):
            in_layers = True
            continue
        if in_layers:
            stripped = line.strip()
            if not stripped or stripped.startswith("@"):
                continue
            parts = stripped.split()
            if len(parts) >= 5:
                layer_rows.append(parts)
        elif line.strip() and not line.lstrip().startswith("@"):
            parts = line.split()
            if len(parts) >= 4:
                try:
                    sl_dr = float(parts[3])
                except ValueError:
                    sl_dr = 0.5

    if not layer_rows:
        raise ValueError(f"Could not parse layer rows for soil profile {soil_id}")

    fc_mm = 0.0
    wp_mm = 0.0
    sat_mm = 0.0
    previous_bottom = 0.0
    for row in layer_rows:
        bottom = float(row[0])
        slll = float(row[2])
        sdul = float(row[3])
        ssat = float(row[4])
        thickness = max(0.0, min(bottom, ROOT_ZONE_DEPTH_CM) - previous_bottom)
        if thickness > 0.0:
            wp_mm += slll * thickness * 10.0
            fc_mm += sdul * thickness * 10.0
            sat_mm += ssat * thickness * 10.0
        previous_bottom = bottom
        if previous_bottom >= ROOT_ZONE_DEPTH_CM:
            break

    initial_root_zone_water_mm = 0.0
    previous_bottom = 0.0
    for depth_index, volumetric_water in enumerate(initial_water):
        bottom = float((depth_index + 1) * 10)
        thickness = max(0.0, min(bottom, ROOT_ZONE_DEPTH_CM) - previous_bottom)
        initial_root_zone_water_mm += volumetric_water * thickness * 10.0
        previous_bottom = bottom
        if previous_bottom >= ROOT_ZONE_DEPTH_CM:
            break

    initial_nitrogen_kg_ha = round(sum(initial_nh4) + sum(initial_no3), 3)
    return SoilProfile(
        soil_name=soil_id,
        field_capacity_mm=round(fc_mm, 3),
        wilting_point_mm=round(wp_mm, 3),
        saturation_mm=round(sat_mm, 3),
        initial_root_zone_water_mm=round(initial_root_zone_water_mm, 3),
        initial_nitrogen_kg_ha=initial_nitrogen_kg_ha,
        drainage_coeff=round(sl_dr, 3),
    )


def _weather_regime(weather: list[WeatherDay]) -> str:
    precip_total = sum(day.precipitation_mm for day in weather)
    if precip_total < 400.0:
        return "dry"
    if precip_total < 800.0:
        return "normal"
    return "wet"


def build_real_subset_simulation_scenario(
    subset_id: str,
    treatment_no: int,
    *,
    subset_root: str | Path | None = None,
) -> RealSubsetScenarioMaterialization:
    case = load_real_subset_replay_case(subset_id, treatment_no, root=subset_root)
    source_root = Path(case.source_root)
    experiment_lines = Path(case.experiment_file).read_text(encoding="utf-8", errors="ignore").splitlines()
    planting_map = _parse_treatment_planting_dates(experiment_lines)
    planting_yyddd = planting_map.get(treatment_no)
    if not planting_yyddd:
        raise ValueError(f"Could not locate planting date for {subset_id} treatment {treatment_no}")
    planting_date = _yyddd_to_date(planting_yyddd)
    station_code, soil_id = _parse_field_context(experiment_lines)
    initial_water, initial_nh4, initial_no3 = _parse_initial_conditions(experiment_lines, treatment_no)

    crop_specs = build_crop_specs()
    crop_spec = crop_specs[case.crop_name]
    weather_file = _find_weather_file(source_root, station_code, planting_date)
    weather = _parse_weather_file(weather_file, planting_date, crop_spec.season_length_days)
    soil_file = _find_soil_file(source_root, soil_id)
    soil_profile = _parse_soil_profile(soil_file, soil_id, initial_water, initial_nh4, initial_no3)

    objective_context = default_objective_context()
    objective_context.soft_preferences["yield_floor_reference_kg_ha"] = case.observed_yield_kg_ha
    crop_context = build_cultivar_context(case.crop_name, case.treatment.cultivar_code, site_name="wuhu")
    scenario = SimulationScenario(
        scenario_id=f"{subset_id}-tr{treatment_no:02d}-real-subset",
        engine_name="dssat_proxy",
        crop_spec=crop_spec,
        soil_profile=soil_profile,
        weather_regime=_weather_regime(weather),
        weather=weather,
        irrigation_budget_mm=case.baseline_policy.total_irrigation_mm,
        nitrogen_budget_kg_ha=case.baseline_policy.total_nitrogen_kg_ha,
        management_mode="balanced",
        seed=treatment_no,
        weather_year=planting_date.year,
        planting_date=planting_date.isoformat(),
        cultivar_code=case.treatment.cultivar_code,
        template_name=Path(case.experiment_file).name,
        experiment_file=Path(case.experiment_file).name,
        site_name="wuhu",
        crop_context=crop_context,
        objective_context=objective_context,
    )
    return RealSubsetScenarioMaterialization(
        case=case,
        scenario=scenario,
        source_weather_file=str(weather_file),
        source_soil_file=str(soil_file),
        source_soil_id=soil_id,
        notes=[
            "SimulationScenario is reconstructed from the real subset experiment, weather file, and soil profile.",
            "yield_floor_reference_kg_ha is set to the observed treatment yield for real-subset post-training evaluation.",
            "irrigation and nitrogen budgets are anchored to the original source-management totals for the selected treatment.",
        ],
    )


def rollout_episode_to_season_policy(episode: Any, *, scenario_id: str | None = None, policy_id: str | None = None) -> SeasonPolicy:
    actions: list[StageDecision] = []
    for index, transition in enumerate(episode.transitions):
        irrigation_mm = round(float(transition.action.irrigation_mm), 3)
        nitrogen_kg_ha = round(float(transition.action.nitrogen_kg_ha), 3)
        if irrigation_mm <= 0.0 and nitrogen_kg_ha <= 0.0:
            continue
        actions.append(
            StageDecision(
                stage=f"event_{index + 1:02d}",
                day_index=int(transition.state.day_index),
                date=str(transition.decision_date),
                irrigation_mm=irrigation_mm,
                nitrogen_kg_ha=nitrogen_kg_ha,
            )
        )
    return SeasonPolicy(
        policy_id=policy_id or f"{getattr(episode, 'policy_id', 'stepwise_ppo')}-real-subset",
        scenario_id=scenario_id or getattr(episode, "scenario_id", "real-subset"),
        actions=actions,
    )


def summarize_real_subset_replay_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    if not results:
        return {
            "case_count": 0,
            "subset_counts": {},
            "reality_facing": {},
            "policy_increment": {},
            "by_subset": {},
            "mean_yield_gap_kg_ha": 0.0,
            "mean_abs_yield_gap_kg_ha": 0.0,
            "mean_yield_gap_ratio": 0.0,
        }

    def _aggregate(values: list[float], digits: int = 3) -> dict[str, float]:
        if not values:
            return {"mean": 0.0, "min": 0.0, "max": 0.0}
        return {
            "mean": round(sum(values) / len(values), digits),
            "min": round(min(values), digits),
            "max": round(max(values), digits),
        }

    def _build_summary(items: list[dict[str, Any]]) -> dict[str, Any]:
        observed_values: list[float] = []
        baseline_values: list[float] = []
        replacement_values: list[float] = []
        baseline_gap_values: list[float] = []
        baseline_gap_ratio_values: list[float] = []
        replacement_gap_values: list[float] = []
        replacement_gap_ratio_values: list[float] = []
        increment_values: list[float] = []
        increment_ratio_values: list[float] = []

        for item in items:
            baseline_payload = dict(item["baseline_replay"])
            replacement_payload = dict(item.get("replacement_replay", item.get("official_replay", {})))
            observed = float(baseline_payload["observed_yield_kg_ha"])
            baseline = float(baseline_payload["simulated_yield_kg_ha"])
            replacement = float(replacement_payload["simulated_yield_kg_ha"])
            observed_values.append(observed)
            baseline_values.append(baseline)
            replacement_values.append(replacement)
            baseline_gap_values.append(float(baseline_payload["yield_gap_kg_ha"]))
            baseline_gap_ratio_values.append(float(baseline_payload["yield_gap_ratio"]))
            replacement_gap_values.append(float(replacement_payload["yield_gap_kg_ha"]))
            replacement_gap_ratio_values.append(float(replacement_payload["yield_gap_ratio"]))
            increment_values.append(replacement - baseline)
            increment_ratio_values.append(0.0 if abs(baseline) <= 1e-6 else (replacement - baseline) / baseline)

        return {
            "reality_facing": {
                "observed_yield_kg_ha": _aggregate(observed_values, digits=3),
                "baseline_replay_yield_kg_ha": _aggregate(baseline_values, digits=3),
                "replacement_replay_yield_kg_ha": _aggregate(replacement_values, digits=3),
                "baseline_minus_observation_kg_ha": _aggregate(baseline_gap_values, digits=3),
                "baseline_minus_observation_ratio": _aggregate(baseline_gap_ratio_values, digits=6),
                "replacement_minus_observation_kg_ha": _aggregate(replacement_gap_values, digits=3),
                "replacement_minus_observation_ratio": _aggregate(replacement_gap_ratio_values, digits=6),
            },
            "policy_increment": {
                "replacement_minus_baseline_kg_ha": _aggregate(increment_values, digits=3),
                "replacement_minus_baseline_ratio": _aggregate(increment_ratio_values, digits=6),
            },
        }

    subset_counts: dict[str, int] = {}
    for item in results:
        subset_id = str(item["subset_id"])
        subset_counts[subset_id] = subset_counts.get(subset_id, 0) + 1
    full_summary = _build_summary(results)
    mean_gap = full_summary["reality_facing"]["replacement_minus_observation_kg_ha"]["mean"]
    mean_abs_gap = round(
        sum(abs(float(dict(item.get("replacement_replay", item.get("official_replay", {})))["yield_gap_kg_ha"])) for item in results)
        / len(results),
        3,
    )
    mean_gap_ratio = full_summary["reality_facing"]["replacement_minus_observation_ratio"]["mean"]
    by_subset = {
        subset_id: {
            "case_count": len([item for item in results if str(item["subset_id"]) == subset_id]),
            **_build_summary([item for item in results if str(item["subset_id"]) == subset_id]),
        }
        for subset_id in subset_counts
    }
    return {
        "case_count": len(results),
        "subset_counts": subset_counts,
        "reality_facing": full_summary["reality_facing"],
        "policy_increment": full_summary["policy_increment"],
        "by_subset": by_subset,
        "mean_yield_gap_kg_ha": round(mean_gap, 3),
        "mean_abs_yield_gap_kg_ha": round(mean_abs_gap, 3),
        "mean_yield_gap_ratio": round(mean_gap_ratio, 6),
    }
