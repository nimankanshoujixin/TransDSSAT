from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from functools import lru_cache
import csv
import hashlib
import math
import random
import re
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from transdssat.scenarios import SoilProfile, WeatherDay


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WEATHER_XLSX = PROJECT_ROOT / "逐日数据.xlsx"
DEFAULT_SOIL_ROOT = PROJECT_ROOT / "土壤"

XML_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
OFFICE_REL_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
PACKAGE_REL_NS = "{http://schemas.openxmlformats.org/package/2006/relationships}"

HEADER_PATTERN = re.compile(r"^(?P<label>.*?)\s*\((?P<code>[^)]+)\)\s*$")
MISSING_TOKENS = {"", "NA", "N/A", "null", "NULL", "999999"}
WARM_SEASON_TAIL_GATES = {
    "maize": {
        "window_days": 30,
        "min_tail_mean_temperature_c": 10.0,
        "min_tail_min_temperature_c": 0.0,
    }
}


@dataclass(slots=True)
class RealWeatherObservation:
    station_id: str
    observed_date: date
    tmin_c: float
    tmax_c: float
    precipitation_mm: float
    radiation_mj_m2: float
    et0_mm: float
    mean_temperature_c: float
    relative_humidity_avg: float
    wind_speed_m_s: float


@dataclass(slots=True)
class RealWeatherArchive:
    rows_by_station: dict[str, dict[date, RealWeatherObservation]]
    rows: list[RealWeatherObservation]
    min_date: date
    max_date: date


@dataclass(slots=True)
class RealWeatherSeasonTemplate:
    crop_name: str
    station_id: str
    weather_year: int
    planting_date: date
    season_length_days: int
    weather_regime: str
    total_precipitation_mm: float
    total_et0_mm: float
    mean_temperature_c: float
    weather: list[WeatherDay]
    template_id: str


@dataclass(slots=True)
class RealSoilSampleRecord:
    source_group: str
    sample_code: str
    sample_name: str
    sample_status: str
    sample_weight_g: float | None
    raw_properties: dict[str, float]
    soil_profile: SoilProfile
    sample_id: str


def _slugify(text: str) -> str:
    slug = re.sub(r"[^0-9A-Za-z]+", "_", text.strip().lower())
    return slug.strip("_") or "sample"


def _safe_float(value: str | float | int | None) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        numeric = float(value)
    else:
        text = str(value).strip()
        if text in MISSING_TOKENS:
            return None
        try:
            numeric = float(text)
        except ValueError:
            return None
    if math.isclose(numeric, 999999.0):
        return None
    return numeric


def _stable_seed(*parts: str) -> int:
    digest = hashlib.sha256("::".join(parts).encode("utf-8")).hexdigest()
    return int(digest[:16], 16)


def _read_zip_xml(zf: zipfile.ZipFile, member_name: str) -> ET.Element:
    return ET.fromstring(zf.read(member_name))


def _shared_strings(zf: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in zf.namelist():
        return []
    root = _read_zip_xml(zf, "xl/sharedStrings.xml")
    return ["".join(node.itertext()) for node in root.findall(f"{XML_NS}si")]


def _cell_value(cell: ET.Element, shared_strings: list[str]) -> str:
    cell_type = cell.attrib.get("t")
    value = cell.findtext(f"{XML_NS}v", default="")
    if cell_type == "s" and value:
        index = int(value)
        return shared_strings[index] if index < len(shared_strings) else ""
    if cell_type == "inlineStr":
        text = cell.find(f"{XML_NS}is")
        return "".join(text.itertext()) if text is not None else ""
    return value or ""


def _load_sheet_rows(xlsx_path: Path) -> list[dict[str, str]]:
    with zipfile.ZipFile(xlsx_path) as zf:
        workbook = _read_zip_xml(zf, "xl/workbook.xml")
        rels = _read_zip_xml(zf, "xl/_rels/workbook.xml.rels")
        shared_strings = _shared_strings(zf)

        rel_map = {
            rel.attrib["Id"]: rel.attrib["Target"]
            for rel in rels.findall(f"{PACKAGE_REL_NS}Relationship")
        }
        sheet = workbook.find(f"{XML_NS}sheets/{XML_NS}sheet")
        if sheet is None:
            raise ValueError(f"No sheet found in workbook: {xlsx_path}")
        rel_id = sheet.attrib[f"{OFFICE_REL_NS}id"]
        target = rel_map[rel_id]
        sheet_root = _read_zip_xml(zf, f"xl/{target}")
        rows = sheet_root.findall(f".//{XML_NS}sheetData/{XML_NS}row")
        if not rows:
            return []

        headers = [_cell_value(cell, shared_strings) for cell in rows[0].findall(f"{XML_NS}c")]
        parsed_rows: list[dict[str, str]] = []
        for row in rows[1:]:
            cells = row.findall(f"{XML_NS}c")
            values = [_cell_value(cell, shared_strings) for cell in cells]
            record = {header: values[idx] if idx < len(values) else "" for idx, header in enumerate(headers)}
            parsed_rows.append(record)
        return parsed_rows


@lru_cache(maxsize=1)
def load_real_weather_archive(xlsx_path: str | Path = DEFAULT_WEATHER_XLSX) -> RealWeatherArchive:
    path = Path(xlsx_path)
    rows = _load_sheet_rows(path)
    rows_by_station: dict[str, dict[date, RealWeatherObservation]] = {}
    all_rows: list[RealWeatherObservation] = []

    for record in rows:
        station_id = str(record.get("Station_Id_C", "")).strip()
        year = int(float(record.get("Year", "0") or 0))
        month = int(float(record.get("Mon", "0") or 0))
        day = int(float(record.get("Day", "0") or 0))
        observed_date = date(year, month, day)
        tmax_c = _safe_float(record.get("TEM_Max")) or _safe_float(record.get("TEM_Avg")) or 0.0
        tmin_c = _safe_float(record.get("TEM_Min")) or _safe_float(record.get("TEM_Avg")) or 0.0
        mean_temperature_c = _safe_float(record.get("TEM_Avg")) or ((tmax_c + tmin_c) / 2.0)
        precipitation_mm = _safe_float(record.get("PRE_Time_2020"))
        if precipitation_mm is None:
            precipitation_mm = sum(
                value or 0.0
                for value in (
                    _safe_float(record.get("PRE_Time_2008")),
                    _safe_float(record.get("PRE_Time_0820")),
                )
            )
        relative_humidity_avg = _safe_float(record.get("RHU_Avg")) or _safe_float(record.get("RHU_Min")) or 60.0
        wind_speed_m_s = _safe_float(record.get("WIN_S_2mi_Avg")) or 0.0
        doy = observed_date.timetuple().tm_yday
        humidity_term = max(0.0, 1.0 - relative_humidity_avg / 100.0)
        temperature_range = max(0.0, tmax_c - tmin_c)
        precipitation_term = min(1.0, precipitation_mm / 25.0)
        seasonal_term = 1.8 * math.sin(2.0 * math.pi * (doy - 172) / 365.0)
        station_term = 0.35 if station_id == "53893" else 0.0
        radiation_mj_m2 = max(
            5.0,
            min(
                29.5,
                7.4
                + 0.42 * temperature_range
                + 0.14 * max(mean_temperature_c - 10.0, 0.0)
                + 6.6 * humidity_term
                + seasonal_term
                + station_term
                - 1.4 * precipitation_term,
            ),
        )
        et0_mm = max(
            0.8,
            min(
                10.0,
                0.18 * radiation_mj_m2 + 0.05 * max(mean_temperature_c, 0.0) + 0.08 * wind_speed_m_s - 0.03 * precipitation_mm,
            ),
        )
        observation = RealWeatherObservation(
            station_id=station_id,
            observed_date=observed_date,
            tmin_c=round(tmin_c, 2),
            tmax_c=round(tmax_c, 2),
            precipitation_mm=round(max(0.0, precipitation_mm), 2),
            radiation_mj_m2=round(radiation_mj_m2, 2),
            et0_mm=round(et0_mm, 2),
            mean_temperature_c=round(mean_temperature_c, 2),
            relative_humidity_avg=round(relative_humidity_avg, 2),
            wind_speed_m_s=round(wind_speed_m_s, 2),
        )
        rows_by_station.setdefault(station_id, {})[observed_date] = observation
        all_rows.append(observation)

    if not all_rows:
        raise ValueError(f"No weather rows parsed from {path}")
    min_date = min(row.observed_date for row in all_rows)
    max_date = max(row.observed_date for row in all_rows)
    return RealWeatherArchive(rows_by_station=rows_by_station, rows=all_rows, min_date=min_date, max_date=max_date)


def _real_weather_candidate_years(crop_name: str, archive: RealWeatherArchive) -> list[int]:
    if crop_name == "maize":
        max_year = archive.max_date.year - 1
        return [year for year in range(archive.min_date.year, max_year + 1)]
    if crop_name == "wheat":
        max_year = archive.max_date.year - 2
        return [year for year in range(archive.min_date.year, max_year + 1)]
    return [year for year in range(archive.min_date.year, archive.max_date.year + 1)]


def _planting_anchor(crop_name: str) -> date:
    return {
        "maize": date(2025, 6, 18),
        "wheat": date(2024, 10, 8),
    }.get(crop_name, date(2025, 6, 18))


def _planting_offset_range(crop_name: str) -> range:
    return {
        "maize": range(-8, 9),
        "wheat": range(-12, 13),
    }.get(crop_name, range(-8, 9))


def _weather_regime_for_precipitation(total_precipitation_mm: float, quantiles: tuple[float, float]) -> str:
    lower, upper = quantiles
    if total_precipitation_mm <= lower:
        return "dry"
    if total_precipitation_mm <= upper:
        return "normal"
    return "wet"


def _season_tail_temperature_stats(weather: list[WeatherDay], window_days: int) -> tuple[float, float]:
    tail = weather[-min(len(weather), window_days) :]
    if not tail:
        return 0.0, 0.0
    mean_temperature = sum(day.tmean_c for day in tail) / len(tail)
    min_temperature = min(day.tmin_c for day in tail)
    return mean_temperature, min_temperature


def _template_matches_crop_climate_gate(template: RealWeatherSeasonTemplate) -> bool:
    gate = WARM_SEASON_TAIL_GATES.get(template.crop_name)
    if gate is None:
        return True
    tail_mean_temperature_c, tail_min_temperature_c = _season_tail_temperature_stats(
        template.weather,
        int(gate["window_days"]),
    )
    return (
        tail_mean_temperature_c >= float(gate["min_tail_mean_temperature_c"])
        and tail_min_temperature_c >= float(gate["min_tail_min_temperature_c"])
    )


def build_real_weather_catalog(
    crop_name: str,
    season_length_days: int,
    archive: RealWeatherArchive | None = None,
) -> list[RealWeatherSeasonTemplate]:
    archive = archive or load_real_weather_archive()
    anchor = _planting_anchor(crop_name)
    candidates: list[RealWeatherSeasonTemplate] = []
    allowed_years = _real_weather_candidate_years(crop_name, archive)
    offsets = tuple(_planting_offset_range(crop_name))

    for station_id in sorted(archive.rows_by_station):
        station_rows = archive.rows_by_station[station_id]
        for year in allowed_years:
            for offset in offsets:
                planting_date = date(year, anchor.month, anchor.day) + timedelta(days=offset)
                end_date = planting_date + timedelta(days=season_length_days - 1)
                if planting_date < archive.min_date or end_date > archive.max_date:
                    continue
                weather: list[WeatherDay] = []
                total_precipitation = 0.0
                total_et0 = 0.0
                total_temperature = 0.0
                for day_index in range(season_length_days):
                    observed_date = planting_date + timedelta(days=day_index)
                    observation = station_rows.get(observed_date)
                    if observation is None:
                        weather = []
                        break
                    weather.append(
                        WeatherDay(
                            day_index=day_index,
                            tmin_c=observation.tmin_c,
                            tmax_c=observation.tmax_c,
                            precipitation_mm=observation.precipitation_mm,
                            radiation_mj_m2=observation.radiation_mj_m2,
                            et0_mm=observation.et0_mm,
                        )
                    )
                    total_precipitation += observation.precipitation_mm
                    total_et0 += observation.et0_mm
                    total_temperature += observation.mean_temperature_c
                if len(weather) != season_length_days:
                    continue
                template_id = f"{crop_name}-{station_id}-{planting_date.isoformat()}"
                candidates.append(
                    RealWeatherSeasonTemplate(
                        crop_name=crop_name,
                        station_id=station_id,
                        weather_year=planting_date.year,
                        planting_date=planting_date,
                        season_length_days=season_length_days,
                        weather_regime="normal",
                        total_precipitation_mm=round(total_precipitation, 3),
                        total_et0_mm=round(total_et0, 3),
                        mean_temperature_c=round(total_temperature / max(1, season_length_days), 3),
                        weather=weather,
                        template_id=template_id,
                    )
                )

    if not candidates:
        raise ValueError(f"No real weather windows available for crop={crop_name}")

    precip_values = sorted(template.total_precipitation_mm for template in candidates)
    lower_index = max(0, len(precip_values) // 3 - 1)
    upper_index = max(0, (2 * len(precip_values)) // 3 - 1)
    quantiles = (precip_values[lower_index], precip_values[upper_index])
    for template in candidates:
        template.weather_regime = _weather_regime_for_precipitation(template.total_precipitation_mm, quantiles)
    filtered_candidates = [template for template in candidates if _template_matches_crop_climate_gate(template)]
    if filtered_candidates:
        return filtered_candidates
    raise ValueError(f"No climate-admissible real weather windows available for crop={crop_name}")


def _parse_sample_info(sample_info_path: Path) -> dict[str, dict[str, str]]:
    if not sample_info_path.exists():
        return {}
    with sample_info_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        result: dict[str, dict[str, str]] = {}
        for row in reader:
            code = row.get("样品编号") or row.get("样品编号 ", "") or ""
            if code:
                result[code.strip()] = row
        return result


def _parse_measurement_wide_csv(wide_csv_path: Path) -> dict[str, dict[str, float]]:
    with wide_csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        rows = list(reader)
    if not rows:
        return {}
    header = rows[0]
    sample_columns = header[4:]
    sample_codes: list[str] = []
    sample_labels: list[str] = []
    for column in sample_columns:
        match = HEADER_PATTERN.match(column.strip())
        if match is None:
            sample_labels.append(column.strip())
            sample_codes.append(_slugify(column))
            continue
        sample_labels.append(match.group("label").strip())
        sample_codes.append(match.group("code").strip())
    properties_by_sample: dict[str, dict[str, float]] = {code: {} for code in sample_codes}
    for row in rows[1:]:
        if len(row) < 5:
            continue
        metric = row[1].strip()
        for idx, code in enumerate(sample_codes):
            cell = row[idx + 4] if idx + 4 < len(row) else ""
            value = _safe_float(cell)
            if value is not None:
                properties_by_sample[code][metric] = value
    return properties_by_sample


def _normalize_metric(value: float | None, lower: float, upper: float) -> float:
    if value is None:
        return 0.5
    if math.isclose(lower, upper):
        return 0.5
    return max(0.0, min(1.0, (value - lower) / (upper - lower)))


def _build_soil_profile_from_sample(
    *,
    source_group: str,
    sample_code: str,
    sample_name: str,
    sample_status: str,
    sample_weight_g: float | None,
    raw_properties: dict[str, float],
) -> SoilProfile:
    organic_matter = raw_properties.get("有机质")
    total_n = raw_properties.get("全氮")
    available_p = raw_properties.get("有效磷")
    available_k = raw_properties.get("速效钾")
    ph = raw_properties.get("pH值")
    ec = raw_properties.get("电导率")

    fertility_index = (
        0.32 * _normalize_metric(organic_matter, 5.0, 110.0)
        + 0.24 * _normalize_metric(total_n, 0.03, 0.45)
        + 0.18 * _normalize_metric(available_p, 1.0, 80.0)
        + 0.18 * _normalize_metric(available_k, 30.0, 300.0)
        + 0.08 * (1.0 - abs((ph or 6.2) - 6.2) / 2.8)
        - 0.10 * _normalize_metric(ec, 2.0, 12.0)
    )
    fertility_index = max(0.0, min(1.0, fertility_index))
    ph_balance = 1.0 - min(1.0, abs((ph or 6.2) - 6.2) / 2.8)
    ec_penalty = _normalize_metric(ec, 2.0, 12.0)
    organic = organic_matter or 0.0
    total_n_pct = total_n or 0.0
    available_p_mgkg = available_p or 0.0
    available_k_mgkg = available_k or 0.0

    field_capacity_mm = 182.0 + 48.0 * fertility_index + 0.22 * organic + 0.10 * available_k_mgkg + 1.3 * total_n_pct * 100.0
    wilting_point_mm = field_capacity_mm - (96.0 - 11.0 * fertility_index + 4.0 * (1.0 - ph_balance))
    saturation_mm = field_capacity_mm + (48.0 + 10.0 * (1.0 - fertility_index) + 6.0 * ec_penalty)
    drainage_coeff = 0.075 + 0.07 * (1.0 - fertility_index) + 0.015 * ec_penalty

    status_text = sample_status or ""
    if "微潮" in status_text:
        moisture_fraction = 0.72
    elif "潮湿" in status_text or "湿" in status_text:
        moisture_fraction = 0.82
    elif "干" in status_text:
        moisture_fraction = 0.62
    else:
        moisture_fraction = 0.74

    moisture_fraction = max(0.55, min(0.92, moisture_fraction))
    root_zone_water_mm = wilting_point_mm + moisture_fraction * max(25.0, field_capacity_mm - wilting_point_mm)
    soil_nitrogen_kg_ha = 24.0 + 38.0 * total_n_pct + 0.24 * organic + 0.05 * available_p_mgkg + 0.03 * available_k_mgkg
    if sample_weight_g is not None:
        soil_nitrogen_kg_ha += min(8.0, sample_weight_g / 400.0)

    source_slug = _slugify(source_group)
    sample_slug = _slugify(sample_code)
    soil_name = f"real_{source_slug}_{sample_slug}"
    return SoilProfile(
        soil_name=soil_name,
        field_capacity_mm=round(field_capacity_mm, 3),
        wilting_point_mm=round(max(20.0, wilting_point_mm), 3),
        saturation_mm=round(max(field_capacity_mm + 20.0, saturation_mm), 3),
        initial_root_zone_water_mm=round(max(20.0, min(saturation_mm, root_zone_water_mm)), 3),
        initial_nitrogen_kg_ha=round(max(10.0, min(180.0, soil_nitrogen_kg_ha)), 3),
        drainage_coeff=round(max(0.05, min(0.22, drainage_coeff)), 4),
    )


@lru_cache(maxsize=1)
def load_real_soil_samples(soil_root: str | Path = DEFAULT_SOIL_ROOT) -> list[RealSoilSampleRecord]:
    root = Path(soil_root)
    sample_records: list[RealSoilSampleRecord] = []
    for wide_csv_path in sorted(root.glob("*/*_test_results_wide.csv")):
        source_group = wide_csv_path.parent.name
        sample_info_candidates = sorted(wide_csv_path.parent.glob("*_sample_info.csv"))
        sample_info_path = sample_info_candidates[0] if sample_info_candidates else None
        sample_info_by_code = _parse_sample_info(sample_info_path) if sample_info_path is not None else {}
        properties_by_sample = _parse_measurement_wide_csv(wide_csv_path)
        for sample_code, raw_properties in properties_by_sample.items():
            sample_info = sample_info_by_code.get(sample_code, {})
            sample_name = sample_info.get("样品名称") or sample_code
            sample_status = sample_info.get("样品状态") or ""
            sample_weight_g = _safe_float(sample_info.get("样品重量_g"))
            soil_profile = _build_soil_profile_from_sample(
                source_group=source_group,
                sample_code=sample_code,
                sample_name=sample_name,
                sample_status=sample_status,
                sample_weight_g=sample_weight_g,
                raw_properties=raw_properties,
            )
            sample_records.append(
                RealSoilSampleRecord(
                    source_group=source_group,
                    sample_code=sample_code,
                    sample_name=sample_name,
                    sample_status=sample_status,
                    sample_weight_g=sample_weight_g,
                    raw_properties=raw_properties,
                    soil_profile=soil_profile,
                    sample_id=f"{_slugify(source_group)}:{_slugify(sample_code)}",
                )
            )

    if not sample_records:
        raise ValueError(f"No soil samples parsed from {root}")
    return sample_records


def _season_preplanting_moisture_bonus(
    archive: RealWeatherArchive,
    station_id: str,
    planting_date: date,
) -> float:
    station_rows = archive.rows_by_station.get(station_id, {})
    total_precip = 0.0
    total_et0 = 0.0
    for offset in range(1, 15):
        row = station_rows.get(planting_date - timedelta(days=offset))
        if row is None:
            continue
        total_precip += row.precipitation_mm
        total_et0 += row.et0_mm
    return total_precip - total_et0


def build_realistic_soil_profile(
    sample: RealSoilSampleRecord,
    archive: RealWeatherArchive,
    station_id: str,
    planting_date: date,
    rng: random.Random,
) -> SoilProfile:
    bonus = _season_preplanting_moisture_bonus(archive, station_id, planting_date)
    if bonus > 18.0:
        moisture_shift = 0.05
        nitrogen_shift = -3.0
    elif bonus > 0.0:
        moisture_shift = 0.02
        nitrogen_shift = -1.0
    elif bonus < -12.0:
        moisture_shift = -0.04
        nitrogen_shift = 2.5
    else:
        moisture_shift = 0.0
        nitrogen_shift = 0.0

    soil = sample.soil_profile
    field_capacity = soil.field_capacity_mm + rng.uniform(-4.0, 4.0)
    wilting_point = min(field_capacity - 28.0, soil.wilting_point_mm + rng.uniform(-2.5, 2.5))
    saturation = max(field_capacity + 28.0, soil.saturation_mm + rng.uniform(-5.0, 5.0))
    water_fraction = 0.70 + moisture_shift + rng.uniform(-0.04, 0.04)
    initial_root_zone_water = wilting_point + water_fraction * max(35.0, field_capacity - wilting_point)
    initial_nitrogen = soil.initial_nitrogen_kg_ha + nitrogen_shift + rng.uniform(-4.0, 4.0)
    drainage_coeff = soil.drainage_coeff + rng.uniform(-0.008, 0.008)
    return SoilProfile(
        soil_name=soil.soil_name,
        field_capacity_mm=round(max(120.0, field_capacity), 3),
        wilting_point_mm=round(max(20.0, wilting_point), 3),
        saturation_mm=round(max(field_capacity + 20.0, saturation), 3),
        initial_root_zone_water_mm=round(max(20.0, min(saturation, initial_root_zone_water)), 3),
        initial_nitrogen_kg_ha=round(max(10.0, min(180.0, initial_nitrogen)), 3),
        drainage_coeff=round(max(0.05, min(0.22, drainage_coeff)), 4),
    )


def soil_sample_label(sample: RealSoilSampleRecord) -> str:
    return f"{_slugify(sample.source_group)}-{_slugify(sample.sample_code)}"
