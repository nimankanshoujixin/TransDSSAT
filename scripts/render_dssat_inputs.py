from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date, timedelta
import json
import os
from pathlib import Path
import shlex


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
    if candidate.upper().endswith((".MZX", ".WHX")):
        return candidate
    return None


def find_experiment_file(run_dir: Path, manifest: dict[str, object]) -> Path:
    candidates = sorted(run_dir.glob("*.MZX")) + sorted(run_dir.glob("*.WHX"))
    if not candidates:
        raise RuntimeError(f"No DSSAT experiment file (*.MZX or *.WHX) found in {run_dir}")

    preferred = preferred_experiment_name(manifest)
    if preferred:
        preferred_path = run_dir / preferred
        if preferred_path.exists():
            return preferred_path

    return candidates[0]


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


def build_irrigation_lines(policy: list[PolicyRow], planting_yyddd: str) -> list[str]:
    planting_date = yyddd_to_date(planting_yyddd)
    lines = [
        "@I  EFIR  IDEP  ITHR  IEPT  IOFF  IAME  IAMT IRNAME",
        " 1     1   -99   -99   -99   -99   -99   -99 IR001",
        "@I IDATE  IROP IRVAL",
    ]
    for row in policy:
        if row.irrigation_mm <= 0.0:
            continue
        event_date = planting_date + timedelta(days=row.day_index)
        lines.append(f" 1 {date_to_yyddd(event_date)} IR001 {row.irrigation_mm:5.1f}")
    return lines


def build_fertilizer_lines(policy: list[PolicyRow], planting_yyddd: str) -> list[str]:
    planting_date = yyddd_to_date(planting_yyddd)
    lines = ["@F FDATE  FMCD  FACD  FDEP  FAMN  FAMP  FAMK  FAMC  FAMO  FOCD FERNAME"]
    for row in policy:
        if row.nitrogen_kg_ha <= 0.0:
            continue
        event_date = planting_date + timedelta(days=row.day_index)
        lines.append(
            f" 1 {date_to_yyddd(event_date)} FE001 AP001    10 {row.nitrogen_kg_ha:5.1f}"
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

    original = lines[start:end]
    first_treatment_start = None
    second_treatment_start = None
    for index, line in enumerate(original):
        if line.startswith("@I  EFIR") and first_treatment_start is None:
            first_treatment_start = index
            continue
        if first_treatment_start is not None and line.startswith("@I  EFIR"):
            next_line = original[index + 1] if index + 1 < len(original) else ""
            if next_line.strip().startswith("2"):
                second_treatment_start = index
                break

    if first_treatment_start is None:
        raise RuntimeError("Could not locate treatment 1 irrigation block.")

    kept_prefix = original[:first_treatment_start]
    kept_suffix = original[second_treatment_start:] if second_treatment_start is not None else []
    new_block = kept_prefix + replacement + kept_suffix
    return lines[:start] + new_block + lines[end:]


def replace_fertilizer_block(lines: list[str], replacement: list[str]) -> list[str]:
    start = next(index for index, line in enumerate(lines) if line.startswith("*FERTILIZERS"))
    end = next(
        index
        for index in range(start + 1, len(lines))
        if lines[index].startswith("*SIMULATION CONTROLS")
    )
    original = lines[start:end]
    header_index = next(index for index, line in enumerate(original) if line.startswith("@F"))
    prefix = original[:header_index]
    suffix = [line for line in original[header_index + 1 :] if not line.strip().startswith("1")]
    new_block = prefix + replacement + suffix
    return lines[:start] + new_block + lines[end:]


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

    policy_path = Path(manifest["policy_path"])
    if not policy_path.is_absolute():
        policy_path = (run_dir / policy_path.name).resolve()

    weather_path = Path(manifest["weather_path"])
    if not weather_path.is_absolute():
        weather_path = (run_dir / weather_path.name).resolve()

    experiment_path = find_experiment_file(run_dir, manifest)
    policy = parse_policy(policy_path)
    weather_rows = parse_weather(weather_path)
    lines = experiment_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    planting_yyddd = extract_template_planting_date(lines)
    station_code, latitude, longitude, elevation = extract_field_metadata(lines)
    irrigation_lines = build_irrigation_lines(policy, planting_yyddd)
    fertilizer_lines = build_fertilizer_lines(policy, planting_yyddd)
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
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
