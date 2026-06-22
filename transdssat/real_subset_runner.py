from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, timedelta
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Any

from transdssat.dssat.parser import DSSATOutputParser
from transdssat.real_subset_assets import RealSubsetAsset, load_real_subset_asset
from transdssat.real_subset_replay import (
    RealSubsetReplayCase,
    build_real_subset_replacement_plan,
    load_real_subset_replay_case,
    write_real_subset_policy_tsv,
)
from transdssat.season import SeasonPolicy


PROJECT_ROOT = Path(__file__).resolve().parents[1]


@dataclass(slots=True)
class RealSubsetReplayResult:
    subset_id: str
    treatment_no: int
    treatment_name: str
    cultivar_code: str
    observed_yield_kg_ha: float
    simulated_yield_kg_ha: float
    yield_gap_kg_ha: float
    yield_gap_ratio: float
    observed_anthesis_yyddd: str = ""
    simulated_anthesis_yyddd: str = ""
    observed_maturity_yyddd: str = ""
    simulated_maturity_yyddd: str = ""
    observed_anthesis: dict[str, Any] | None = None
    simulated_anthesis: dict[str, Any] | None = None
    observed_maturity: dict[str, Any] | None = None
    simulated_maturity: dict[str, Any] | None = None
    run_dir: str = ""
    working_dir: str = ""
    experiment_file: str = ""
    command: list[str] | None = None
    summary_row: dict[str, str] | None = None
    evaluate_row: dict[str, str] | None = None
    notes: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _load_render_module():
    script_path = PROJECT_ROOT / "scripts" / "render_dssat_inputs.py"
    module_name = "transdssat_render_dssat_inputs_runtime"
    existing = sys.modules.get(module_name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load render module from {script_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _fixed_width_rows(path: Path) -> list[dict[str, str]]:
    return DSSATOutputParser().parse_table(path, fixed_width=True)


def _plain_rows(path: Path) -> list[dict[str, str]]:
    return DSSATOutputParser().parse_table(path)


def _first_match(rows: list[dict[str, str]], treatment_no: int) -> dict[str, str]:
    for row in rows:
        for key in ("TRNO", "TRTNO", "TN", "RUNNO"):
            value = str(row.get(key, "")).strip()
            if value.isdigit() and int(value) == treatment_no:
                return row
    return rows[0] if rows else {}


def _format_gap_ratio(observed: float, simulated: float) -> float:
    if abs(observed) <= 1e-6:
        return 0.0
    return round((simulated - observed) / observed, 6)


def _extract_date_token(raw_value: str) -> str:
    value = str(raw_value or "").strip()
    match = re.search(r"\d{3,7}", value)
    return match.group(0) if match else ""


def _normalize_phenology_token(raw_value: str, year_hint: int | None = None) -> dict[str, Any]:
    token = _extract_date_token(raw_value)
    normalized: dict[str, Any] = {
        "raw": str(raw_value or ""),
        "token": token,
        "yyddd": "",
        "year": None,
        "doy": None,
        "iso_date": "",
    }
    if not token:
        return normalized

    year: int | None = None
    doy: int | None = None
    if len(token) == 7:
        year = int(token[:4])
        doy = int(token[4:])
        normalized["yyddd"] = token[2:]
    elif len(token) == 5:
        prefix = int(token[:2])
        year = 2000 + prefix if prefix < 70 else 1900 + prefix
        doy = int(token[2:])
        normalized["yyddd"] = token
    elif len(token) == 3:
        doy = int(token)
        if year_hint is not None:
            year = year_hint
            normalized["yyddd"] = f"{year % 100:02d}{doy:03d}"

    if year is None or doy is None or doy <= 0:
        return normalized

    try:
        iso_date = (date(year, 1, 1) + timedelta(days=doy - 1)).isoformat()
    except ValueError:
        return normalized

    normalized["year"] = year
    normalized["doy"] = doy
    normalized["iso_date"] = iso_date
    return normalized


def _format_rice_cultivar_row(raw_line: str) -> str:
    parts = raw_line.split()
    if len(parts) < 15:
        raise ValueError(f"Unsupported rice cultivar row: {raw_line}")
    var_code = parts[0]
    expno = parts[-13]
    eco_code = parts[-12]
    numeric_fields = parts[-11:]
    cultivar_name = " ".join(parts[1:-13])
    return (
        f"{var_code:<6} "
        f"{cultivar_name:<21.21}"
        f"{expno}"
        " "
        f"{eco_code:<6}"
        f"{numeric_fields[0]:>6}"
        f"{numeric_fields[1]:>6}"
        f"{numeric_fields[2]:>6}"
        f"{numeric_fields[3]:>6}"
        f"{numeric_fields[4]:>6}"
        f"{numeric_fields[5]:>6}"
        f"{numeric_fields[6]:>6}"
        f"{numeric_fields[7]:>6}"
        f"{numeric_fields[8]:>6}"
        f"{numeric_fields[9]:>6}"
        f"{numeric_fields[10]:>6}"
    )


def _read_rice_cultivar_limits(cultivar_path: Path) -> tuple[list[float], list[float]]:
    minima: list[float] | None = None
    maxima: list[float] | None = None
    for raw_line in cultivar_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if raw_line.startswith("999991 "):
            parts = raw_line.split()
            minima = [float(value) for value in parts[-11:]]
        elif raw_line.startswith("999992 "):
            parts = raw_line.split()
            maxima = [float(value) for value in parts[-11:]]
    if minima is None or maxima is None:
        raise ValueError(f"Could not locate rice cultivar min/max rows in {cultivar_path}")
    return minima, maxima


def _validate_rice_cultivar_row(raw_line: str, cultivar_path: Path) -> list[str]:
    parts = raw_line.split()
    numeric_fields = [float(value) for value in parts[-11:]]
    minima, maxima = _read_rice_cultivar_limits(cultivar_path)
    field_names = ["P1", "P2R", "P5", "P2O", "G1", "G2", "G3", "PHINT", "THOT", "TCLDP", "TCLDF"]
    issues: list[str] = []
    for name, value, lower, upper in zip(field_names, numeric_fields, minima, maxima):
        if value < lower or value > upper:
            issues.append(f"{name}={value} outside [{lower}, {upper}]")
    return issues


def _append_unique_lines(
    target_path: Path,
    append_path: Path,
    *,
    strict_validation: bool = True,
    validation_warnings: list[str] | None = None,
) -> None:
    base_lines = target_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    append_lines = append_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    existing = {line.rstrip() for line in base_lines}
    merged = list(base_lines)
    for line in append_lines:
        stripped = line.rstrip().lstrip("\ufeff")
        if not stripped or stripped in existing:
            continue
        if stripped.startswith(("!", "*", "@")):
            continue
        parts = stripped.split()
        if len(parts) < 15:
            continue
        first_token = parts[0]
        if not first_token or not first_token[0].isalnum():
            continue
        validation_issues = _validate_rice_cultivar_row(stripped, target_path)
        if validation_issues:
            message = (
                f"Rice cultivar row {first_token} is incompatible with {target_path.name}: "
                + "; ".join(validation_issues)
            )
            if strict_validation:
                raise ValueError(message)
            if validation_warnings is not None:
                validation_warnings.append(message)
        formatted = _format_rice_cultivar_row(stripped)
        if formatted in existing:
            continue
        merged.append(formatted)
        existing.add(formatted)
    target_path.write_text("\n".join(merged) + "\n", encoding="utf-8")


def _replace_cultivar_row(target_path: Path, source_code: str, replacement_line: str) -> None:
    lines = target_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    formatted = _format_rice_cultivar_row(replacement_line.rstrip())
    replaced = False
    updated: list[str] = []
    for line in lines:
        if line.startswith(f"{source_code} "):
            updated.append(formatted)
            replaced = True
        else:
            updated.append(line)
    if not replaced:
        updated.append(formatted)
    target_path.write_text("\n".join(updated) + "\n", encoding="utf-8")


def _rewrite_cultivar_expno(raw_line: str, expno: str) -> str:
    parts = raw_line.split()
    if len(parts) < 15:
        raise ValueError(f"Unsupported rice cultivar row: {raw_line}")
    parts[-13] = expno
    return " ".join(parts)


def _normalize_cultivar_expno(target_path: Path, cultivar_code: str, expno: str) -> None:
    lines = target_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    updated: list[str] = []
    changed = False
    for line in lines:
        if line.startswith(f"{cultivar_code} "):
            line = _format_rice_cultivar_row(_rewrite_cultivar_expno(line, expno))
            changed = True
        updated.append(line)
    if changed:
        target_path.write_text("\n".join(updated) + "\n", encoding="utf-8")


def _drop_cultivar_row(target_path: Path, cultivar_code: str) -> None:
    lines = target_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    kept = [line for line in lines if not line.startswith(f"{cultivar_code} ")]
    target_path.write_text("\n".join(kept) + "\n", encoding="utf-8")


def _rewrite_wuhu_cultivar_codes(experiment_path: Path, mapping: dict[str, str]) -> None:
    if not mapping or not experiment_path.exists():
        return
    lines = experiment_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    rewritten: list[str] = []
    in_block = False
    for line in lines:
        if line.startswith("*CULTIVARS"):
            in_block = True
            rewritten.append(line)
            continue
        if in_block and line.startswith("*") and not line.startswith("*CULTIVARS"):
            in_block = False
        if not in_block or not line.strip() or line.lstrip().startswith("@"):
            rewritten.append(line)
            continue
        parts = line.split()
        if len(parts) >= 4 and parts[0].isdigit():
            source_code = parts[2]
            if source_code in mapping:
                old_token = f" {source_code} "
                new_token = f" {mapping[source_code]} "
                line = line.replace(old_token, new_token, 1)
        rewritten.append(line)
    experiment_path.write_text("\n".join(rewritten) + "\n", encoding="utf-8")


def _rewrite_wuhu_cultivar_slot(
    experiment_path: Path,
    source_code: str,
    replacement_code: str,
    replacement_name: str,
) -> None:
    if not experiment_path.exists():
        return
    lines = experiment_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    rewritten: list[str] = []
    in_block = False
    for line in lines:
        if line.startswith("*CULTIVARS"):
            in_block = True
            rewritten.append(line)
            continue
        if in_block and line.startswith("*") and not line.startswith("*CULTIVARS"):
            in_block = False
        if not in_block or not line.strip() or line.lstrip().startswith("@"):
            rewritten.append(line)
            continue
        parts = line.split()
        if len(parts) >= 4 and parts[0].isdigit() and parts[2] == source_code:
            slot = parts[0]
            crop_code = parts[1]
            line = f"{int(slot):2d} {crop_code} {replacement_code} {replacement_name}"
        rewritten.append(line)
    experiment_path.write_text("\n".join(rewritten) + "\n", encoding="utf-8")


def _write_single_treatment_batch(batch_path: Path, experiment_name: str, treatment_no: int, crop_code: str = "RICE") -> None:
    batch_text = (
        f"$BATCH({crop_code})\n"
        "@FILEX                                                                                        TRTNO     RP     SQ     OP     CO\n"
        f"{experiment_name:<90}{treatment_no:>6}{1:>7}{0:>7}{0:>7}{0:>7}\n"
    )
    batch_path.write_text(batch_text, encoding="utf-8")


def _copytree_overlay(source_dir: Path, target_dir: Path) -> None:
    for path in source_dir.rglob("*"):
        relative = path.relative_to(source_dir)
        destination = target_dir / relative
        if path.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, destination)


def _rewrite_dssat_profile(profile_path: Path, runtime_root: Path) -> None:
    if not profile_path.exists():
        return
    # DSSAT's profile reader is sensitive to line width; use the run directory
    # as a short relative root instead of embedding long absolute paths.
    runtime_root_str = "."
    lines = profile_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    rewritten: list[str] = []
    pattern = re.compile(r"^([A-Z0-9]{3})\s+(//|[A-Z]:)\s+(.+)$")
    for line in lines:
        match = pattern.match(line)
        if not match:
            rewritten.append(line)
            continue
        code, prefix, remainder = match.groups()
        tokens = remainder.split()
        suffix = ""
        if code.startswith("M") and len(tokens) > 1:
            suffix = " " + " ".join(tokens[-2:])
        rewritten.append(f"{code} {prefix} {runtime_root_str}{suffix}")
    profile_path.write_text("\n".join(rewritten) + "\n", encoding="utf-8")


def _prepare_runtime_clone(
    asset: RealSubsetAsset,
    case: RealSubsetReplayCase,
    runtime_root: Path,
    output_root: Path,
) -> tuple[Path, Path, str]:
    run_root = output_root / f"{asset.subset_id}_tr{case.treatment.treatment_no:02d}"
    if run_root.exists():
        shutil.rmtree(run_root)
    shutil.copytree(runtime_root, run_root)
    _copytree_overlay(Path(asset.source_root), run_root)
    _rewrite_dssat_profile(run_root / "DSSATPRO.L48", run_root)
    _rewrite_dssat_profile(run_root / "DSSATPRO.L48.bak", run_root)

    validation_warnings: list[str] = []
    genotype_dir = run_root / "Genotype"
    genotype_dir.mkdir(parents=True, exist_ok=True)
    cultivar_target = genotype_dir / "RICER048.CUL"
    if not cultivar_target.exists():
        runtime_cultivar = runtime_root / "Genotype" / "RICER048.CUL"
        if not runtime_cultivar.exists():
            raise FileNotFoundError(f"Runtime cultivar file not found: {runtime_cultivar}")
        shutil.copy2(runtime_cultivar, cultivar_target)
    _append_unique_lines(
        cultivar_target,
        Path(asset.genotype_append_file),
        strict_validation=False,
        validation_warnings=validation_warnings,
    )

    if asset.subset_id == "mx475_migrated":
        work_dir = run_root
        experiment_name = Path(asset.experiment_file).name
        _write_single_treatment_batch(run_root / "DSSBatch.v48", experiment_name, case.treatment.treatment_no)
        genotype_dir = run_root / "Genotype"
        for genotype_name in ("RICER048.CUL", "RICER048.SPE"):
            genotype_file = genotype_dir / genotype_name
            if genotype_file.exists():
                shutil.copy2(genotype_file, run_root / genotype_name)
        standard_data_dir = run_root / "StandardData"
        for standard_name in (
            "CO2048.WDA",
            "FERCH048.SDA",
            "RESCH048.SDA",
            "SOMFR048.SDA",
            "SOMFX048.SDA",
            "TILOP048.SDA",
        ):
            standard_file = standard_data_dir / standard_name
            if standard_file.exists():
                shutil.copy2(standard_file, run_root / standard_name)
    elif asset.subset_id == "wuhu_rice_calibrated":
        rice_dir = run_root / "Rice"
        work_dir = run_root
        experiment_name = Path(asset.experiment_file).name
        replay_cultivar_code = case.treatment.cultivar_code
        if case.treatment.cultivar_code == "WHR006":
            replay_cultivar_code = "WHR009"
            calibrated_whr006_path = (
                Path(asset.source_root).parent / "美香占2号校准参数" / "Genotype" / "RICER048_WHR006_CALIBRATED.CUL"
            )
            if calibrated_whr006_path.exists():
                calibrated_lines = calibrated_whr006_path.read_text(encoding="utf-8", errors="ignore").splitlines()
                calibrated_row = next((line for line in calibrated_lines if line.startswith("WHR006 ")), "")
                if calibrated_row:
                    replacement_row = calibrated_row.replace("WHR006", replay_cultivar_code, 1)
                    replacement_row = _rewrite_cultivar_expno(replacement_row, ".")
                    _replace_cultivar_row(cultivar_target, replay_cultivar_code, replacement_row)
                    _drop_cultivar_row(cultivar_target, case.treatment.cultivar_code)
                    _normalize_cultivar_expno(cultivar_target, replay_cultivar_code, ".")
        for file_name in ("WHRI2101.RIX", "WHRI2101.RIA", "DSSBatch.v48"):
            source_file = rice_dir / file_name
            if source_file.exists():
                shutil.copy2(source_file, run_root / file_name)
        if replay_cultivar_code != case.treatment.cultivar_code:
            _rewrite_wuhu_cultivar_slot(
                run_root / experiment_name,
                case.treatment.cultivar_code,
                replay_cultivar_code,
                case.treatment.cultivar_name,
            )
        _write_single_treatment_batch(run_root / "DSSBatch.v48", experiment_name, case.treatment.treatment_no)
        for weather_file in (run_root / "Weather").glob("*.WTH"):
            shutil.copy2(weather_file, run_root / weather_file.name)
        soil_dir = run_root / "Soil"
        for soil_name in ("CN.SOL", "SOIL.SOL", "SOIL.V48"):
            soil_file = soil_dir / soil_name
            if soil_file.exists():
                shutil.copy2(soil_file, run_root / soil_name)
        genotype_dir = run_root / "Genotype"
        for genotype_name in ("RICER048.CUL", "RICER048.SPE"):
            genotype_file = genotype_dir / genotype_name
            if genotype_file.exists():
                shutil.copy2(genotype_file, run_root / genotype_name)
        if replay_cultivar_code != case.treatment.cultivar_code:
            for cultivar_path in (cultivar_target, run_root / "RICER048.CUL"):
                if cultivar_path.exists():
                    _normalize_cultivar_expno(cultivar_path, replay_cultivar_code, ".")
        standard_data_dir = run_root / "StandardData"
        for standard_name in (
            "CO2048.WDA",
            "FERCH048.SDA",
            "RESCH048.SDA",
            "SOMFR048.SDA",
            "SOMFX048.SDA",
            "TILOP048.SDA",
        ):
            standard_file = standard_data_dir / standard_name
            if standard_file.exists():
                shutil.copy2(standard_file, run_root / standard_name)
    else:
        raise ValueError(f"Unsupported subset id: {asset.subset_id}")

    work_dir.mkdir(parents=True, exist_ok=True)
    if validation_warnings:
        (run_root / "transdssat_runtime_clone_warnings.json").write_text(
            json.dumps({"warnings": validation_warnings}, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    return run_root, work_dir, experiment_name


def _apply_replacement_policy_to_experiment(
    run_root: Path,
    experiment_name: str,
    treatment_no: int,
    policy: SeasonPolicy,
    *,
    control_mode: str,
) -> Path:
    experiment_path = run_root / experiment_name
    lines = experiment_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    updated = list(lines)
    if control_mode in {"joint", "water_only"}:
        updated = _replace_treatment_irrigation_block(updated, treatment_no, policy)
    if control_mode in {"joint", "nitrogen_only"}:
        updated = _replace_treatment_fertilizer_block(updated, treatment_no, policy)
    experiment_path.write_text("\n".join(updated) + "\n", encoding="utf-8")
    return experiment_path


def _find_section_bounds(lines: list[str], section_prefix: str, next_prefix: str) -> tuple[int, int]:
    start = next(index for index, line in enumerate(lines) if line.startswith(section_prefix))
    end = next(index for index in range(start + 1, len(lines)) if lines[index].startswith(next_prefix))
    return start, end


def _extract_irrigation_templates(section_lines: list[str], treatment_no: int) -> tuple[str | None, list[tuple[str, str]]]:
    control_line: str | None = None
    event_templates: list[tuple[str, str]] = []
    for line in section_lines:
        parts = line.split()
        if not parts or not parts[0].isdigit() or int(parts[0]) != treatment_no:
            continue
        if len(parts) >= 9 and not (len(parts[1]) == 5 and parts[1].isdigit()):
            control_line = line
            continue
        if len(parts) >= 4 and len(parts[1]) == 5 and parts[1].isdigit():
            irop = parts[2] if len(parts) >= 3 else "IR001"
            suffix = ""
            if len(parts) > 4:
                suffix = " " + " ".join(parts[4:])
            event_templates.append((irop, suffix))
    return control_line, event_templates


def _replace_treatment_irrigation_block(lines: list[str], treatment_no: int, policy: SeasonPolicy) -> list[str]:
    start, end = _find_section_bounds(lines, "*IRRIGATION AND WATER MANAGEMENT", "*FERTILIZERS")
    section_lines = lines[start + 1 : end]
    control_line, event_templates = _extract_irrigation_templates(section_lines, treatment_no)
    positive_events = [action for action in policy.actions if action.irrigation_mm > 0.0]
    if control_line is None:
        control_line = f"{treatment_no:>2}   -99   -99   -99   -99   -99   -99     1 IR001"
    if not event_templates:
        event_templates = [("IR001", "")]
    block_start, block_end = _find_irrigation_block_bounds(section_lines, treatment_no)
    date_header = "@I IDATE  IROP IRVAL"
    if block_start is not None and block_start + 1 < len(section_lines) and section_lines[block_start + 1].startswith("@I IDATE"):
        date_header = section_lines[block_start + 1]

    rebuilt_block = [control_line, date_header]
    for index, action in enumerate(positive_events):
        yyddd = _date_to_yyddd(action.date)
        irop, suffix = event_templates[min(index, len(event_templates) - 1)]
        rebuilt_block.append(_format_irrigation_event_line(treatment_no, yyddd, irop, action.irrigation_mm, suffix))

    if block_start is None or block_end is None:
        rebuilt_section = list(section_lines)
        rebuilt_section.extend(rebuilt_block)
    else:
        rebuilt_section = section_lines[:block_start] + rebuilt_block + section_lines[block_end:]
    return lines[: start + 1] + rebuilt_section + lines[end:]


def _find_irrigation_block_bounds(section_lines: list[str], treatment_no: int) -> tuple[int | None, int | None]:
    block_start: int | None = None
    block_end: int | None = None
    for index, line in enumerate(section_lines):
        parts = line.split()
        if not parts or not parts[0].isdigit():
            continue
        if len(parts) >= 9 and not (len(parts[1]) == 5 and parts[1].isdigit()):
            if int(parts[0]) == treatment_no and block_start is None:
                block_start = index
                continue
            if block_start is not None:
                block_end = index
                break
    if block_start is not None and block_end is None:
        block_end = len(section_lines)
    return block_start, block_end


def _format_irrigation_event_line(
    treatment_no: int,
    yyddd: str,
    irop: str,
    irrigation_mm: float,
    suffix: str,
) -> str:
    if float(irrigation_mm).is_integer():
        amount = f"{int(irrigation_mm):d}"
    else:
        amount = f"{irrigation_mm:.1f}"
    return f"{treatment_no:>2} {yyddd} {irop:<5}{amount:>6}{suffix}"


def _extract_fertilizer_templates(section_lines: list[str], treatment_no: int) -> list[list[str]]:
    templates: list[list[str]] = []
    for line in section_lines:
        if line.startswith("*"):
            break
        parts = line.split()
        if len(parts) >= 12 and parts[0].isdigit() and int(parts[0]) == treatment_no:
            templates.append(parts)
    return templates


def _format_fertilizer_amount(value: float) -> str:
    rounded = int(round(value))
    return str(max(0, rounded))


def _format_fertilizer_event_line(
    treatment_no: int,
    yyddd: str,
    template: list[str],
    nitrogen_kg_ha: float,
    *,
    zero_non_nitrogen: bool,
) -> str:
    fmcd = template[2] if len(template) > 2 else "FE001"
    facd = template[3] if len(template) > 3 else "AP001"
    fdep = template[4] if len(template) > 4 else "5"
    famp = "0" if zero_non_nitrogen else (template[6] if len(template) > 6 else "0")
    famk = "0" if zero_non_nitrogen else (template[7] if len(template) > 7 else "0")
    famc = template[8] if len(template) > 8 else "-99"
    famo = template[9] if len(template) > 9 else "-99"
    focd = template[10] if len(template) > 10 else "-99"
    fername = " ".join(template[11:]) if len(template) > 11 else "TRANSDSSAT FERTILIZER"
    famn = _format_fertilizer_amount(nitrogen_kg_ha)
    if zero_non_nitrogen:
        famc = "-99"
        famo = "-99"
    return (
        f"{treatment_no:>2} {yyddd} {fmcd:<5} {facd:<5}"
        f"{fdep:>6}{famn:>6}{famp:>6}{famk:>6}{famc:>6}{famo:>6}{focd:>6} {fername}"
    )


def _replace_treatment_fertilizer_block(lines: list[str], treatment_no: int, policy: SeasonPolicy) -> list[str]:
    start, end = _find_section_bounds(lines, "*FERTILIZERS", "*SIMULATION CONTROLS")
    section_lines = lines[start + 1 : end]
    templates = _extract_fertilizer_templates(section_lines, treatment_no)
    positive_events = [action for action in policy.actions if action.nitrogen_kg_ha > 0.0]
    if not templates:
        templates = [[str(treatment_no), "00000", "FE001", "AP001", "10", "0.0", "0", "0", "0", "0", "-99", "TRNSDAT"]]

    rebuilt = [lines[start], section_lines[0] if section_lines and section_lines[0].startswith("@F") else "@F FDATE  FMCD FACD FDEP  FAMN  FAMP  FAMK  FAMC  FAMO FOCD FERNAME"]
    tail_start = next((index for index, line in enumerate(section_lines[1:], start=1) if line.startswith("*")), len(section_lines))
    fertilizer_data_lines = section_lines[1:tail_start]
    preserved_other_lines = [
        line
        for line in fertilizer_data_lines
        if not (line.split() and line.split()[0].isdigit() and int(line.split()[0]) == treatment_no)
    ]
    for index, action in enumerate(positive_events):
        template = templates[min(index, len(templates) - 1)]
        rebuilt.append(
            _format_fertilizer_event_line(
                treatment_no,
                _date_to_yyddd(action.date),
                template,
                action.nitrogen_kg_ha,
                zero_non_nitrogen=True,
            )
        )
    rebuilt.extend(preserved_other_lines)
    rebuilt.extend(section_lines[tail_start:])
    return lines[:start] + rebuilt + lines[end:]


def _date_to_yyddd(value: str) -> str:
    event_date = date.fromisoformat(value)
    year = event_date.year % 100
    doy = (event_date - date(event_date.year, 1, 1)).days + 1
    return f"{year:02d}{doy:03d}"


def run_real_subset_original_management(
    subset_id: str,
    treatment_no: int,
    *,
    runtime_root: str | Path,
    output_root: str | Path,
    subset_root: str | Path | None = None,
) -> RealSubsetReplayResult:
    runtime_root = Path(runtime_root).resolve()
    output_root = Path(output_root).resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    asset = load_real_subset_asset(subset_id, root=subset_root)
    case = load_real_subset_replay_case(subset_id, treatment_no, root=subset_root)
    run_root, work_dir, experiment_name = _prepare_runtime_clone(asset, case, runtime_root, output_root)

    executable = run_root / "dscsm048"
    if not executable.exists():
        raise FileNotFoundError(f"DSSAT executable not found: {executable}")

    batch_name = "DSSBatch.v48"
    command = [str(executable), "B", batch_name]
    stdout_path = run_root / "transdssat_real_subset_stdout.log"
    stderr_path = run_root / "transdssat_real_subset_stderr.log"
    with stdout_path.open("w", encoding="utf-8") as stdout_handle:
        with stderr_path.open("w", encoding="utf-8") as stderr_handle:
            result = subprocess.run(
                command,
                cwd=work_dir,
                stdout=stdout_handle,
                stderr=stderr_handle,
                check=False,
            )
    if result.returncode != 0:
        raise RuntimeError(
            f"Real subset replay failed with exit code {result.returncode}. "
            f"See {stdout_path} and {stderr_path}."
        )

    summary_path = work_dir / "Summary.OUT"
    evaluate_path = work_dir / "Evaluate.OUT"
    summary_row = _first_match(_fixed_width_rows(summary_path), treatment_no)
    evaluate_row = _first_match(_plain_rows(evaluate_path), treatment_no) if evaluate_path.exists() else {}
    simulated_yield = float(summary_row.get("HWAM", "0") or 0.0)
    simulated_anthesis = str(summary_row.get("ADAT", "") or "")
    simulated_maturity = str(summary_row.get("MDAT", "") or "")
    harvest_year = int(str(summary_row.get("HYEAR", "") or "0") or 0) or None
    observed_yield = case.observed_yield_kg_ha

    replay_result = RealSubsetReplayResult(
        subset_id=subset_id,
        treatment_no=treatment_no,
        treatment_name=case.treatment.treatment_name,
        cultivar_code=case.treatment.cultivar_code,
        observed_yield_kg_ha=observed_yield,
        simulated_yield_kg_ha=simulated_yield,
        yield_gap_kg_ha=round(simulated_yield - observed_yield, 3),
        yield_gap_ratio=_format_gap_ratio(observed_yield, simulated_yield),
        observed_anthesis_yyddd=case.treatment.observed_anthesis_yyddd,
        simulated_anthesis_yyddd=simulated_anthesis,
        observed_maturity_yyddd=case.treatment.observed_maturity_yyddd,
        simulated_maturity_yyddd=simulated_maturity,
        observed_anthesis=_normalize_phenology_token(case.treatment.observed_anthesis_yyddd, harvest_year),
        simulated_anthesis=_normalize_phenology_token(simulated_anthesis, harvest_year),
        observed_maturity=_normalize_phenology_token(case.treatment.observed_maturity_yyddd, harvest_year),
        simulated_maturity=_normalize_phenology_token(simulated_maturity, harvest_year),
        run_dir=str(run_root),
        working_dir=str(work_dir),
        experiment_file=batch_name,
        command=command,
        summary_row=summary_row,
        evaluate_row=evaluate_row,
        notes=[
            "Current replay path runs the source experiment file under original management.",
            "The next extension point is replacing only irrigation/fertilizer decisions while keeping other management fixed.",
        ],
    )
    report_path = run_root / "real_subset_replay_report.json"
    report_path.write_text(json.dumps(replay_result.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
    return replay_result


def prepare_real_subset_management_replacement(
    subset_id: str,
    treatment_no: int,
    candidate_policy: SeasonPolicy,
    *,
    control_mode: str = "joint",
    runtime_root: str | Path,
    output_root: str | Path,
    subset_root: str | Path | None = None,
) -> dict[str, Any]:
    runtime_root = Path(runtime_root).resolve()
    output_root = Path(output_root).resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    asset = load_real_subset_asset(subset_id, root=subset_root)
    case = load_real_subset_replay_case(subset_id, treatment_no, root=subset_root)
    run_root, work_dir, experiment_name = _prepare_runtime_clone(asset, case, runtime_root, output_root)

    replacement_plan = build_real_subset_replacement_plan(
        case,
        candidate_policy,
        control_mode=control_mode,
    )
    policy_path = write_real_subset_policy_tsv(replacement_plan.composed_policy, run_root / "transdssat_policy.tsv")
    experiment_path = _apply_replacement_policy_to_experiment(
        run_root,
        experiment_name,
        treatment_no,
        replacement_plan.composed_policy,
        control_mode=control_mode,
    )
    plan_path = run_root / "real_subset_replacement_plan.json"
    plan_payload = replacement_plan.to_dict()
    plan_payload["policy_tsv_path"] = str(policy_path)
    plan_payload["experiment_path"] = str(experiment_path)
    plan_payload["work_dir"] = str(work_dir)
    plan_path.write_text(json.dumps(plan_payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return {
        "run_root": str(run_root),
        "work_dir": str(work_dir),
        "experiment_file": experiment_name,
        "experiment_path": str(experiment_path),
        "policy_tsv_path": str(policy_path),
        "replacement_plan_path": str(plan_path),
        "control_mode": control_mode,
    }


def run_real_subset_management_replacement(
    subset_id: str,
    treatment_no: int,
    candidate_policy: SeasonPolicy,
    *,
    control_mode: str = "joint",
    runtime_root: str | Path,
    output_root: str | Path,
    subset_root: str | Path | None = None,
) -> RealSubsetReplayResult:
    prepared = prepare_real_subset_management_replacement(
        subset_id,
        treatment_no,
        candidate_policy,
        control_mode=control_mode,
        runtime_root=runtime_root,
        output_root=output_root,
        subset_root=subset_root,
    )

    run_root = Path(prepared["run_root"])
    work_dir = Path(prepared["work_dir"])
    executable = run_root / "dscsm048"
    if not executable.exists():
        raise FileNotFoundError(f"DSSAT executable not found: {executable}")

    batch_name = "DSSBatch.v48"
    command = [str(executable), "B", batch_name]
    stdout_path = run_root / "transdssat_real_subset_stdout.log"
    stderr_path = run_root / "transdssat_real_subset_stderr.log"
    with stdout_path.open("w", encoding="utf-8") as stdout_handle:
        with stderr_path.open("w", encoding="utf-8") as stderr_handle:
            result = subprocess.run(
                command,
                cwd=work_dir,
                stdout=stdout_handle,
                stderr=stderr_handle,
                check=False,
            )
    if result.returncode != 0:
        raise RuntimeError(
            f"Real subset replacement replay failed with exit code {result.returncode}. "
            f"See {stdout_path} and {stderr_path}."
        )

    case = load_real_subset_replay_case(subset_id, treatment_no, root=subset_root)
    summary_path = work_dir / "Summary.OUT"
    evaluate_path = work_dir / "Evaluate.OUT"
    summary_row = _first_match(_fixed_width_rows(summary_path), treatment_no)
    evaluate_row = _first_match(_plain_rows(evaluate_path), treatment_no) if evaluate_path.exists() else {}
    simulated_yield = float(summary_row.get("HWAM", "0") or 0.0)
    simulated_anthesis = str(summary_row.get("ADAT", "") or "")
    simulated_maturity = str(summary_row.get("MDAT", "") or "")
    harvest_year = int(str(summary_row.get("HYEAR", "") or "0") or 0) or None
    observed_yield = case.observed_yield_kg_ha

    replay_result = RealSubsetReplayResult(
        subset_id=subset_id,
        treatment_no=treatment_no,
        treatment_name=case.treatment.treatment_name,
        cultivar_code=case.treatment.cultivar_code,
        observed_yield_kg_ha=observed_yield,
        simulated_yield_kg_ha=simulated_yield,
        yield_gap_kg_ha=round(simulated_yield - observed_yield, 3),
        yield_gap_ratio=_format_gap_ratio(observed_yield, simulated_yield),
        observed_anthesis_yyddd=case.treatment.observed_anthesis_yyddd,
        simulated_anthesis_yyddd=simulated_anthesis,
        observed_maturity_yyddd=case.treatment.observed_maturity_yyddd,
        simulated_maturity_yyddd=simulated_maturity,
        observed_anthesis=_normalize_phenology_token(case.treatment.observed_anthesis_yyddd, harvest_year),
        simulated_anthesis=_normalize_phenology_token(simulated_anthesis, harvest_year),
        observed_maturity=_normalize_phenology_token(case.treatment.observed_maturity_yyddd, harvest_year),
        simulated_maturity=_normalize_phenology_token(simulated_maturity, harvest_year),
        run_dir=str(run_root),
        working_dir=str(work_dir),
        experiment_file=batch_name,
        command=command,
        summary_row=summary_row,
        evaluate_row=evaluate_row,
        notes=[
            f"Replacement replay path executed with control_mode={control_mode}.",
            "Only the requested management channel is replaced; the untouched channel remains source-managed in the cloned experiment file.",
        ],
    )
    report_path = run_root / "real_subset_replacement_report.json"
    report_path.write_text(json.dumps(replay_result.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
    return replay_result
