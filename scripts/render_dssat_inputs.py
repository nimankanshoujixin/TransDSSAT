from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date, timedelta
import json
from pathlib import Path


@dataclass(slots=True)
class PolicyRow:
    stage: str
    date: str
    day_index: int
    irrigation_mm: float
    nitrogen_kg_ha: float


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


def find_experiment_file(run_dir: Path) -> Path:
    candidates = sorted(run_dir.glob("*.MZX")) + sorted(run_dir.glob("*.WHX"))
    if not candidates:
        raise RuntimeError(f"No DSSAT experiment file (*.MZX or *.WHX) found in {run_dir}")
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


def build_irrigation_lines(policy: list[PolicyRow], planting_yyddd: str) -> list[str]:
    planting_date = yyddd_to_date(planting_yyddd)
    lines = [
        "@I  EFIR  IDEP  ITHR  IEPT  IOFF  IAME  IAMT IRNAME",
        " 1     1   -99   -99   -99   -99   -99   -99 IR001",
        "@I IDATE  IROP IRVAL",
    ]
    for row in policy:
        event_date = planting_date + timedelta(days=row.day_index)
        lines.append(f" 1 {date_to_yyddd(event_date)} IR001 {row.irrigation_mm:5.1f}")
    return lines


def build_fertilizer_lines(policy: list[PolicyRow], planting_yyddd: str) -> list[str]:
    planting_date = yyddd_to_date(planting_yyddd)
    lines = ["@F FDATE  FMCD  FACD  FDEP  FAMN  FAMP  FAMK  FAMC  FAMO  FOCD FERNAME"]
    for row in policy:
        event_date = planting_date + timedelta(days=row.day_index)
        lines.append(
            f" 1 {date_to_yyddd(event_date)} FE001 AP001    10 {row.nitrogen_kg_ha:5.1f}"
            "     0     0     0     0   -99 TRNSDAT"
        )
    return lines


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

    experiment_path = find_experiment_file(run_dir)
    policy = parse_policy(policy_path)
    lines = experiment_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    planting_yyddd = extract_template_planting_date(lines)
    irrigation_lines = build_irrigation_lines(policy, planting_yyddd)
    fertilizer_lines = build_fertilizer_lines(policy, planting_yyddd)
    updated = replace_irrigation_block(lines, irrigation_lines)
    updated = replace_fertilizer_block(updated, fertilizer_lines)
    experiment_path.write_text("\n".join(updated) + "\n", encoding="utf-8")

    summary = {
        "experiment_file": str(experiment_path),
        "policy_events": len(policy),
        "template_planting_yyddd": planting_yyddd,
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
