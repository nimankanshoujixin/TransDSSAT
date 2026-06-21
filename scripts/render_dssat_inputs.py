from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date, timedelta
import json
import os
from pathlib import Path
import re
import shlex


SUPPORTED_EXPERIMENT_SUFFIXES = (".MZX", ".WHX", ".RIX")


@dataclass(slots=True)
class PolicyRow:
    stage: str
    date: str
    day_index: int
    irrigation_mm: float
    nitrogen_kg_ha: float


@dataclass(slots=True)
class WeatherRow:
    day_index: int
    tmin_c: float
    tmax_c: float
    precipitation_mm: float
    radiation_mj_m2: float
    et0_mm: float


@dataclass(slots=True)
class CultivarOverride:
    crop_code: str
    cultivar_code: str
    cultivar_name: str
    genotype_file: str
    ecotype_code: str
    parameter_values: list[float]


def parse_policy(policy_path: Path) -> list[PolicyRow]:
    lines = policy_path.read_text(encoding="utf-8").splitlines()
    rows: list[PolicyRow] = []
    for raw_line in lines[1:]:
        if not raw_line.strip():
            continue
        parts = raw_line.split()
        rows.append(
            PolicyRow(
                stage=parts[0],
                date=parts[1],
                day_index=int(parts[2]),
                irrigation_mm=float(parts[3]),
                nitrogen_kg_ha=float(parts[4]),
            )
        )
    return rows


def parse_weather(weather_path: Path) -> list[WeatherRow]:
    lines = weather_path.read_text(encoding="utf-8").splitlines()
    rows: list[WeatherRow] = []
    for raw_line in lines[1:]:
        if not raw_line.strip():
            continue
        parts = raw_line.split(",")
        rows.append(
            WeatherRow(
                day_index=int(parts[0]),
                tmin_c=float(parts[1]),
                tmax_c=float(parts[2]),
                precipitation_mm=float(parts[3]),
                radiation_mj_m2=float(parts[4]),
                et0_mm=float(parts[5]),
            )
        )
    return rows


def yyddd_to_date(value: str) -> date:
    value = value.strip()
    year = int(value[:2])
    doy = int(value[2:])
    full_year = 1900 + year if year >= 50 else 2000 + year
    return date(full_year, 1, 1) + timedelta(days=doy - 1)


def date_to_yyddd(value: date) -> str:
    year = value.year % 100
    doy = (value - date(value.year, 1, 1)).days + 1
    return f"{year:02d}{doy:03d}"


def preferred_experiment_name(manifest: dict[str, object]) -> str | None:
    explicit = os.environ.get("DSSAT_EXPERIMENT_FILE", "").strip()
    if explicit:
        return Path(explicit).name

    manifest_value = str(manifest.get("experiment_file", "")).strip()
    if manifest_value:
        return Path(manifest_value).name

    run_command = os.environ.get("DSSAT_RUN_COMMAND", "").strip()
    if not run_command:
        return None

    tokens = shlex.split(run_command, posix=os.name != "nt")
    if not tokens:
        return None

    candidate = Path(tokens[-1]).name
    if candidate.upper().endswith(SUPPORTED_EXPERIMENT_SUFFIXES):
        return candidate
    return None


def find_experiment_file(run_dir: Path, manifest: dict[str, object]) -> Path:
    candidates: list[Path] = []
    for suffix in SUPPORTED_EXPERIMENT_SUFFIXES:
        candidates.extend(sorted(run_dir.glob(f"*{suffix}")))
    if not candidates:
        supported = " or ".join(f"*{suffix}" for suffix in SUPPORTED_EXPERIMENT_SUFFIXES)
        raise RuntimeError(f"No DSSAT experiment file ({supported}) found in {run_dir}")

    preferred = preferred_experiment_name(manifest)
    if preferred:
        preferred_path = run_dir / preferred
        if preferred_path.exists():
            return preferred_path

    return candidates[0]


def resolve_manifest_path(path_value: object, run_dir: Path) -> Path:
    path = Path(str(path_value))
    if not path.is_absolute():
        path = (run_dir / path.name).resolve()
    return path


def sanitize_cultivar_code(value: str, fallback: str) -> str:
    cleaned = "".join(char for char in value.upper() if char.isalnum())
    if len(cleaned) < 6:
        cleaned = (cleaned + fallback)[:6]
    return cleaned[:6]


def ascii_cultivar_name(crop_context: dict[str, object], cultivar: dict[str, object]) -> str:
    candidate = str(cultivar.get("cultivar_id", "") or cultivar.get("cultivar_name", "")).upper()
    cleaned = "".join(char for char in candidate if char.isascii() and (char.isalnum() or char in {"_", " ", "-"}))
    cleaned = cleaned.replace("-", "_").strip("_ ")
    if not cleaned:
        cleaned = str(crop_context.get("crop_name", "CULTIVAR")).upper()
    return cleaned[:16] or "CULTIVAR"


def build_cultivar_override(scenario_payload: dict[str, object]) -> CultivarOverride | None:
    crop_context = scenario_payload.get("crop_context")
    if not isinstance(crop_context, dict):
        return None
    cultivar = crop_context.get("cultivar")
    if not isinstance(cultivar, dict):
        return None

    crop_name = str(scenario_payload.get("crop_name", "")).lower()
    parameter_names = [str(value).upper() for value in cultivar.get("parameter_names", [])]
    parameter_values = [float(value) for value in cultivar.get("parameter_vector", [])]
    if crop_name != "maize":
        return None
    if parameter_names != ["P1", "P2", "P5", "G2", "G3", "PHINT"] or len(parameter_values) != 6:
        return None

    requested_code = str(cultivar.get("dssat_cultivar_code", "")).strip()
    cultivar_code = sanitize_cultivar_code(requested_code, "DH6051")
    return CultivarOverride(
        crop_code="MZ",
        cultivar_code=cultivar_code,
        cultivar_name=ascii_cultivar_name(crop_context, cultivar),
        genotype_file=str(cultivar.get("dssat_genotype_file", "")).strip() or "MZCER048.CUL",
        ecotype_code=str(cultivar.get("dssat_ecotype_code", "")).strip() or "IB0001",
        parameter_values=parameter_values,
    )


def build_cultivar_line(override: CultivarOverride) -> str:
    p1, p2, p5, g2, g3, phint = override.parameter_values
    return (
        f"{override.cultivar_code:<6} {override.cultivar_name:<21}. {override.ecotype_code:<6}"
        f"{p1:6.1f}{p2:6.3f}{p5:6.1f}{g2:6.1f}{g3:7.3f}{phint:6.2f} "
    )


def upsert_cultivar_line(lines: list[str], override: CultivarOverride) -> list[str]:
    updated: list[str] = []
    replaced = False
    prefix = f"{override.cultivar_code:<6}".strip()
    for line in lines:
        stripped = line.rstrip("\x1a")
        if stripped.split(maxsplit=1)[:1] == [prefix]:
            updated.append(build_cultivar_line(override))
            replaced = True
            continue
        updated.append(stripped)
    if not replaced:
        while updated and not updated[-1].strip():
            updated.pop()
        updated.append(build_cultivar_line(override))
    return updated


def materialize_cultivar_file(run_dir: Path, override: CultivarOverride) -> Path:
    dssat_home_value = os.environ.get("DSSAT_HOME", "").strip()
    if not dssat_home_value:
        raise RuntimeError("DSSAT_HOME is required to materialize cultivar overrides.")
    dssat_home = Path(dssat_home_value).expanduser()
    source = dssat_home / "Genotype" / override.genotype_file
    if not source.exists():
        raise RuntimeError(f"Could not locate DSSAT genotype file: {source}")
    target = run_dir / override.genotype_file
    source_lines = source.read_text(encoding="utf-8", errors="ignore").splitlines()
    target.write_text("\n".join(upsert_cultivar_line(source_lines, override)) + "\n", encoding="utf-8")
    return target


def extract_template_planting_date(lines: list[str]) -> str:
    in_planting = False
    for line in lines:
        if line.startswith("*PLANTING DETAILS"):
            in_planting = True
            continue
        if in_planting and line.startswith("*") and not line.startswith("*PLANTING DETAILS"):
            break
        if in_planting and line.startswith("@P"):
            continue
        if in_planting and line.strip():
            parts = line.split()
            if len(parts) >= 2:
                return parts[1]
    raise RuntimeError("Could not locate planting date in DSSAT experiment file.")


def resolve_scenario_planting_yyddd(scenario_payload: dict[str, object], fallback: str) -> str:
    planting_date = str(scenario_payload.get("planting_date", "")).strip()
    if not planting_date:
        return fallback
    return date_to_yyddd(date.fromisoformat(planting_date))


def extract_field_metadata(lines: list[str]) -> tuple[str, float, float, float]:
    for index, line in enumerate(lines):
        if line.startswith("@L ID_FIELD"):
            field_line = lines[index + 1].split()
            coord_line = lines[index + 3].split()
            station_code = field_line[2]
            latitude = float(coord_line[1])
            longitude = float(coord_line[2])
            elevation = float(coord_line[3])
            return station_code, latitude, longitude, elevation
    raise RuntimeError("Could not locate field metadata in DSSAT experiment file.")


def replace_cultivar_block(lines: list[str], override: CultivarOverride) -> list[str]:
    start = next(index for index, line in enumerate(lines) if line.startswith("*CULTIVARS"))
    end = next(
        index
        for index in range(start + 1, len(lines))
        if lines[index].startswith("*FIELDS")
    )
    replacement = ["@C CR INGENO CNAME"]
    for line in lines[start + 1 : end]:
        stripped = line.strip()
        if not stripped or stripped.startswith("@") or stripped.startswith("!"):
            continue
        parts = stripped.split(maxsplit=3)
        treatment_id = parts[0]
        crop_code = parts[1] if len(parts) > 1 else override.crop_code
        replacement.append(f" {treatment_id} {crop_code} {override.cultivar_code} {override.cultivar_name}")
    if len(replacement) == 1:
        replacement.append(f" 1 {override.crop_code} {override.cultivar_code} {override.cultivar_name}")
    return lines[: start + 1] + replacement + lines[end:]


def extract_treatment_ids(lines: list[str]) -> list[int]:
    start = next(index for index, line in enumerate(lines) if line.startswith("*TREATMENTS"))
    end = next(
        index
        for index in range(start + 1, len(lines))
        if lines[index].startswith("*CULTIVARS")
    )
    treatment_ids: list[int] = []
    for line in lines[start:end]:
        stripped = line.strip()
        if not stripped or stripped.startswith("*") or stripped.startswith("@"):
            continue
        first = stripped.split()[0]
        if first.isdigit():
            treatment_ids.append(int(first))
    return treatment_ids or [1]


def build_irrigation_lines(policy: list[PolicyRow], planting_yyddd: str, treatment_ids: list[int]) -> list[str]:
    planting_date = yyddd_to_date(planting_yyddd)
    lines: list[str] = []
    for treatment_id in treatment_ids:
        lines.extend(
            [
                "@I  EFIR  IDEP  ITHR  IEPT  IOFF  IAME  IAMT IRNAME",
                f" {treatment_id}     1   -99   -99   -99   -99   -99   -99 IR001",
                "@I IDATE  IROP IRVAL",
            ]
        )
        for row in policy:
            if row.irrigation_mm <= 0.0:
                continue
            event_date = planting_date + timedelta(days=row.day_index)
            lines.append(f" {treatment_id} {date_to_yyddd(event_date)} IR001 {row.irrigation_mm:5.1f}")
    return lines


def build_fertilizer_lines(policy: list[PolicyRow], planting_yyddd: str, treatment_ids: list[int]) -> list[str]:
    planting_date = yyddd_to_date(planting_yyddd)
    lines = ["@F FDATE  FMCD  FACD  FDEP  FAMN  FAMP  FAMK  FAMC  FAMO  FOCD FERNAME"]
    for treatment_id in treatment_ids:
        event_count = 0
        for row in policy:
            if row.nitrogen_kg_ha <= 0.0:
                continue
            event_date = planting_date + timedelta(days=row.day_index)
            lines.append(
                f" {treatment_id} {date_to_yyddd(event_date)} FE001 AP001    10 {row.nitrogen_kg_ha:5.1f}"
                "     0     0     0     0   -99 TRNSDAT"
            )
            event_count += 1
        if event_count == 0:
            lines.append(
                f" {treatment_id} {planting_yyddd} FE001 AP001    10   0.0"
                "     0     0     0     0   -99 TRNSDAT"
            )
    return lines


def build_weather_file(
    run_dir: Path,
    station_code: str,
    planting_yyddd: str,
    latitude: float,
    longitude: float,
    elevation: float,
    weather_rows: list[WeatherRow],
) -> Path:
    planting = yyddd_to_date(planting_yyddd)
    weather_year = planting.year % 100
    filename = f"{station_code}{weather_year:02d}01.WTH"
    path = run_dir / filename

    tav = sum((row.tmin_c + row.tmax_c) / 2.0 for row in weather_rows) / max(1, len(weather_rows))
    annual_max = max(row.tmax_c for row in weather_rows)
    annual_min = min(row.tmin_c for row in weather_rows)
    amp = max(0.1, annual_max - annual_min)

    def row_for_offset(offset: int) -> WeatherRow:
        if offset < 0:
            return weather_rows[0]
        if offset >= len(weather_rows):
            return weather_rows[-1]
        return weather_rows[offset]

    lines = [
        "*WEATHER DATA : TransDSSAT generated weather",
        "",
        "@ INSI      LAT     LONG  ELEV   TAV   AMP REFHT WNDHT",
        f"  {station_code:<4} {latitude:7.3f} {longitude:9.3f} {int(elevation):5d} {tav:5.1f} {amp:5.1f}  2.00  3.00",
        "@DATE  SRAD  TMAX  TMIN  RAIN               PAR ",
    ]
    end_date = date(planting.year + 1, 12, 31)
    current = date(planting.year, 1, 1)
    while current <= end_date:
        offset = (current - planting).days
        weather = row_for_offset(offset)
        par = weather.radiation_mj_m2 * 2.1
        yyddd = date_to_yyddd(current)
        lines.append(
            f"{yyddd} {weather.radiation_mj_m2:5.1f} {weather.tmax_c:5.1f} "
            f"{weather.tmin_c:5.1f} {weather.precipitation_mm:5.1f}              {par:5.1f} "
        )
        current += timedelta(days=1)

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def replace_irrigation_block(lines: list[str], replacement: list[str]) -> list[str]:
    start = next(index for index, line in enumerate(lines) if line.startswith("*IRRIGATION AND WATER MANAGEMENT"))
    end = next(
        index
        for index in range(start + 1, len(lines))
        if lines[index].startswith("*FERTILIZERS")
    )
    new_block = [lines[start]] + replacement
    return lines[:start] + new_block + lines[end:]


def replace_fertilizer_block(lines: list[str], replacement: list[str]) -> list[str]:
    start = next(index for index, line in enumerate(lines) if line.startswith("*FERTILIZERS"))
    end = next(
        index
        for index in range(start + 1, len(lines))
        if lines[index].startswith("*SIMULATION CONTROLS")
    )
    new_block = [lines[start]] + replacement
    return lines[:start] + new_block + lines[end:]


def _rewrite_space_separated_date_line(line: str, new_value: str) -> str:
    parts = line.split()
    if len(parts) >= 2:
        parts[1] = new_value
        return " ".join(parts)
    return line


def _replace_token_at(line: str, token_index: int, new_value: str) -> str:
    matches = list(re.finditer(r"\S+", line))
    if len(matches) > token_index:
        match = matches[token_index]
        width = match.end() - match.start()
        replacement = str(new_value)
        if len(replacement) < width:
            replacement = replacement.rjust(width)
        return f"{line[:match.start()]}{replacement}{line[match.end():]}"
    return line


def replace_primary_dates(lines: list[str], planting_yyddd: str) -> list[str]:
    updated = list(lines)
    planting_date = yyddd_to_date(planting_yyddd)
    emergence_yyddd = date_to_yyddd(planting_date - timedelta(days=1))
    last_harvest_yyddd = date_to_yyddd(planting_date + timedelta(days=365))

    section: str | None = None
    for index, line in enumerate(updated):
        if line.startswith("*"):
            section = line
            continue
        if section == "*INITIAL CONDITIONS" and line.strip() and not line.startswith("@") and not line.startswith("!"):
            updated[index] = _replace_token_at(line, 2, emergence_yyddd)
            section = None
            continue
        if section == "*PLANTING DETAILS" and line.strip() and not line.startswith("@") and not line.startswith("!"):
            updated[index] = _replace_token_at(line, 1, planting_yyddd)
            section = None
            continue
        if line.startswith("@N PLANTING"):
            continue
        if line.startswith("@N HARVEST"):
            continue
        if line.strip().startswith("1 PL"):
            updated[index] = _replace_token_at(line, 2, planting_yyddd)
            updated[index] = _replace_token_at(updated[index], 3, planting_yyddd)
            continue
        if line.strip().startswith("1 HA"):
            updated[index] = _replace_token_at(line, 2, last_harvest_yyddd)
            updated[index] = _replace_token_at(updated[index], 3, last_harvest_yyddd)
            continue
        if line.strip().startswith("1 GE"):
            updated[index] = _replace_token_at(line, 5, emergence_yyddd)
            continue
    return updated


def main() -> int:
    parser = argparse.ArgumentParser(description="Inject TransDSSAT season policy into a DSSAT experiment template.")
    parser.add_argument("manifest", help="Path to transdssat_manifest.json")
    args = parser.parse_args()

    manifest_path = Path(args.manifest)
    if not manifest_path.is_absolute():
        manifest_path = (Path.cwd() / manifest_path).resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_dir = manifest_path.parent

    run_dir = Path(manifest["run_dir"])
    if not run_dir.is_absolute():
        run_dir = (manifest_dir / run_dir.name).resolve()

    policy_path = resolve_manifest_path(manifest["policy_path"], run_dir)
    weather_path = resolve_manifest_path(manifest["weather_path"], run_dir)
    scenario_path = resolve_manifest_path(manifest["scenario_path"], run_dir)

    experiment_path = find_experiment_file(run_dir, manifest)
    policy = parse_policy(policy_path)
    weather_rows = parse_weather(weather_path)
    scenario_payload = json.loads(scenario_path.read_text(encoding="utf-8"))
    lines = experiment_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    cultivar_override = build_cultivar_override(scenario_payload)
    cultivar_file = None
    if cultivar_override is not None:
        cultivar_file = materialize_cultivar_file(run_dir, cultivar_override)
        lines = replace_cultivar_block(lines, cultivar_override)
    treatment_ids = extract_treatment_ids(lines)
    planting_yyddd = resolve_scenario_planting_yyddd(
        scenario_payload,
        extract_template_planting_date(lines),
    )
    lines = replace_primary_dates(lines, planting_yyddd)
    station_code, latitude, longitude, elevation = extract_field_metadata(lines)
    irrigation_lines = build_irrigation_lines(policy, planting_yyddd, treatment_ids)
    fertilizer_lines = build_fertilizer_lines(policy, planting_yyddd, treatment_ids)
    updated = replace_irrigation_block(lines, irrigation_lines)
    updated = replace_fertilizer_block(updated, fertilizer_lines)
    experiment_path.write_text("\n".join(updated) + "\n", encoding="utf-8")
    weather_file = build_weather_file(
        run_dir=run_dir,
        station_code=station_code,
        planting_yyddd=planting_yyddd,
        latitude=latitude,
        longitude=longitude,
        elevation=elevation,
        weather_rows=weather_rows,
    )

    summary = {
        "experiment_file": str(experiment_path),
        "weather_file": str(weather_file),
        "policy_events": len(policy),
        "template_planting_yyddd": planting_yyddd,
        "cultivar_file": str(cultivar_file) if cultivar_file is not None else "",
        "cultivar_code": cultivar_override.cultivar_code if cultivar_override is not None else "",
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
