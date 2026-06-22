from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re
import shutil

from transdssat.scenarios import SimulationScenario
from transdssat.season import SeasonPolicy

from .config import DSSATRunConfig


@dataclass(slots=True)
class DSSATRunContext:
    run_dir: Path
    manifest_path: Path
    policy_path: Path
    weather_path: Path
    soil_path: Path
    scenario_path: Path
    template_dir: Path | None
    crop_name: str
    experiment_file: str


class DSSATInputBuilder:
    def __init__(self, config: DSSATRunConfig) -> None:
        self.config = config

    def build(self, scenario: SimulationScenario, policy: SeasonPolicy) -> DSSATRunContext:
        working_root = self.config.working_root.resolve()
        working_root.mkdir(parents=True, exist_ok=True)
        run_dir = (working_root / policy.policy_id).resolve()
        if run_dir.exists():
            shutil.rmtree(run_dir)
        run_dir.mkdir(parents=True, exist_ok=True)

        self._copy_runtime_default_assets(run_dir)
        template_dir = self._resolve_template_dir(scenario)
        if template_dir is not None:
            self._copy_tree(template_dir, run_dir)
            self._copy_adjacent_runtime_assets(template_dir, run_dir)
            self._apply_scenario_asset_overrides(scenario, template_dir, run_dir)
            self._apply_batch_mode_overrides(scenario, run_dir)

        policy_path = (run_dir / "transdssat_policy.tsv").resolve()
        weather_path = (run_dir / "transdssat_weather.csv").resolve()
        soil_path = (run_dir / "transdssat_soil.json").resolve()
        scenario_path = (run_dir / "transdssat_scenario.json").resolve()
        manifest_path = (run_dir / "transdssat_manifest.json").resolve()

        self._write_policy(policy_path, policy)
        self._write_weather(weather_path, scenario)
        soil_path.write_text(
            json.dumps(asdict(scenario.soil_profile), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        scenario_path.write_text(
            json.dumps(scenario.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        manifest = {
            "runtime_root": str(self.config.runtime_root),
            "run_dir": str(run_dir),
            "template_dir": str(template_dir) if template_dir is not None else "",
            "policy_path": str(policy_path),
            "weather_path": str(weather_path),
            "soil_path": str(soil_path),
            "scenario_path": str(scenario_path),
            "crop_name": scenario.crop_spec.crop_name,
            "experiment_file": scenario.experiment_file,
            "expected_outputs": [
                "Summary.OUT",
                "PlantGro.OUT",
                "SoilWat.OUT",
                "SoilNi.OUT",
                "Weather.OUT",
            ],
        }
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
        return DSSATRunContext(
            run_dir=run_dir,
            manifest_path=manifest_path,
            policy_path=policy_path,
            weather_path=weather_path,
            soil_path=soil_path,
            scenario_path=scenario_path,
            template_dir=template_dir,
            crop_name=scenario.crop_spec.crop_name,
            experiment_file=scenario.experiment_file,
        )

    def _resolve_template_dir(self, scenario: SimulationScenario) -> Path | None:
        if self.config.template_root is None:
            return None
        template_root = self.config.template_root.resolve()
        candidate_names = [scenario.template_name, f"{scenario.crop_spec.crop_name}_quzhou_base", scenario.crop_spec.crop_name]
        for candidate_name in candidate_names:
            candidate_dir = _resolve_template_candidate(template_root, candidate_name)
            if candidate_dir is not None:
                return candidate_dir
        return None

    def _copy_tree(self, source_dir: Path, target_dir: Path) -> None:
        for path in source_dir.rglob("*"):
            relative = path.relative_to(source_dir)
            destination = target_dir / relative
            if path.is_dir():
                destination.mkdir(parents=True, exist_ok=True)
            else:
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, destination)

    def _copy_runtime_default_assets(self, run_dir: Path) -> None:
        runtime_root = self.config.runtime_root.resolve()
        for asset_dir_name in ("Weather", "Soil", "Genotype", "StandardData"):
            asset_dir = runtime_root / asset_dir_name
            if not asset_dir.is_dir():
                continue
            self._copy_tree(asset_dir, run_dir / asset_dir_name)
            self._copy_root_level_asset_files(asset_dir, run_dir)

    def _copy_adjacent_runtime_assets(self, template_dir: Path, run_dir: Path) -> None:
        source_root = template_dir.parent
        if source_root == template_dir:
            return

        for asset_dir_name in ("Weather", "Soil", "Genotype", "StandardData"):
            asset_dir = source_root / asset_dir_name
            if not asset_dir.is_dir():
                continue
            self._copy_tree(asset_dir, run_dir / asset_dir_name)
            self._copy_root_level_asset_files(asset_dir, run_dir)

    def _copy_root_level_asset_files(self, asset_dir: Path, run_dir: Path) -> None:
        for path in asset_dir.iterdir():
            if path.is_file():
                shutil.copy2(path, run_dir / path.name)

    def _apply_scenario_asset_overrides(self, scenario: SimulationScenario, template_dir: Path, run_dir: Path) -> None:
        if scenario.crop_spec.crop_name != "rice":
            return
        self._apply_rice_cultivar_compatibility(scenario, template_dir, run_dir)

    def _apply_batch_mode_overrides(self, scenario: SimulationScenario, run_dir: Path) -> None:
        treatment_no = _infer_active_treatment_no(scenario.scenario_id)
        if treatment_no <= 0:
            return
        batch_path = run_dir / "DSSBatch.v48"
        experiment_name = scenario.experiment_file.strip()
        if not batch_path.exists() or not experiment_name:
            return
        crop_code = _batch_crop_code_for_scenario(scenario)
        _write_single_treatment_batch(batch_path, experiment_name, treatment_no, crop_code=crop_code)

    def _apply_rice_cultivar_compatibility(self, scenario: SimulationScenario, template_dir: Path, run_dir: Path) -> None:
        source_root = template_dir.parent
        runtime_cultivar = run_dir / "RICER048.CUL"
        append_fragment = source_root / "Genotype" / "RICER048_WHRI_APPEND.CUL"
        if runtime_cultivar.exists() and append_fragment.exists():
            _append_unique_cultivar_lines(runtime_cultivar, append_fragment)

        if scenario.cultivar_code != "WHR006":
            return

        calibrated_fragment = _find_calibrated_whr006_fragment(source_root)
        if calibrated_fragment is None or not runtime_cultivar.exists():
            return

        calibrated_lines = calibrated_fragment.read_text(encoding="utf-8", errors="ignore").splitlines()
        calibrated_row = next((line for line in calibrated_lines if line.startswith("WHR006 ")), "")
        if not calibrated_row:
            return

        replacement_row = calibrated_row.replace("WHR006", "WHR009", 1)
        replacement_row = _rewrite_rice_cultivar_expno(replacement_row, ".")
        _replace_rice_cultivar_row(runtime_cultivar, "WHR009", replacement_row)
        _drop_rice_cultivar_row(runtime_cultivar, "WHR006")
        _normalize_rice_cultivar_expno(runtime_cultivar, "WHR009", ".")

        experiment_path = run_dir / scenario.experiment_file
        if experiment_path.exists():
            _rewrite_rice_experiment_cultivar_slot(experiment_path, "WHR006", "WHR009", "MEIXIANGZHAN2")

    def _write_policy(self, policy_path: Path, policy: SeasonPolicy) -> None:
        lines = ["stage\tdate\tday_index\tirrigation_mm\tnitrogen_kg_ha"]
        for action in policy.actions:
            lines.append(
                f"{action.stage}\t{action.date}\t{action.day_index}\t"
                f"{action.irrigation_mm}\t{action.nitrogen_kg_ha}"
            )
        policy_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _write_weather(self, weather_path: Path, scenario: SimulationScenario) -> None:
        lines = ["day_index,tmin_c,tmax_c,precipitation_mm,radiation_mj_m2,et0_mm"]
        for weather in scenario.weather:
            lines.append(
                f"{weather.day_index},{weather.tmin_c},{weather.tmax_c},"
                f"{weather.precipitation_mm},{weather.radiation_mj_m2},{weather.et0_mm}"
            )
        weather_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _find_calibrated_whr006_fragment(source_root: Path) -> Path | None:
    search_root = source_root.parent
    matches = sorted(search_root.rglob("RICER048_WHR006_CALIBRATED.CUL"))
    return matches[0] if matches else None


def _read_rice_cultivar_limits(cultivar_path: Path) -> tuple[list[float], list[float]]:
    minima: list[float] | None = None
    maxima: list[float] | None = None
    for raw_line in cultivar_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if raw_line.startswith("999991 "):
            minima = [float(value) for value in raw_line.split()[-11:]]
        elif raw_line.startswith("999992 "):
            maxima = [float(value) for value in raw_line.split()[-11:]]
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


def _append_unique_cultivar_lines(target_path: Path, append_path: Path) -> None:
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
        _validate_rice_cultivar_row(stripped, target_path)
        formatted = _format_rice_cultivar_row(stripped)
        if formatted in existing:
            continue
        merged.append(formatted)
        existing.add(formatted)
    target_path.write_text("\n".join(merged) + "\n", encoding="utf-8")


def _rewrite_rice_cultivar_expno(raw_line: str, expno: str) -> str:
    parts = raw_line.split()
    if len(parts) < 15:
        raise ValueError(f"Unsupported rice cultivar row: {raw_line}")
    parts[-13] = expno
    return " ".join(parts)


def _replace_rice_cultivar_row(target_path: Path, source_code: str, replacement_line: str) -> None:
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


def _drop_rice_cultivar_row(target_path: Path, cultivar_code: str) -> None:
    lines = target_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    kept = [line for line in lines if not line.startswith(f"{cultivar_code} ")]
    target_path.write_text("\n".join(kept) + "\n", encoding="utf-8")


def _normalize_rice_cultivar_expno(target_path: Path, cultivar_code: str, expno: str) -> None:
    lines = target_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    updated: list[str] = []
    changed = False
    for line in lines:
        if line.startswith(f"{cultivar_code} "):
            line = _format_rice_cultivar_row(_rewrite_rice_cultivar_expno(line, expno))
            changed = True
        updated.append(line)
    if changed:
        target_path.write_text("\n".join(updated) + "\n", encoding="utf-8")


def _rewrite_rice_experiment_cultivar_slot(
    experiment_path: Path,
    source_code: str,
    replacement_code: str,
    replacement_name: str,
) -> None:
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


def _resolve_template_candidate(template_root: Path, candidate_name: str) -> Path | None:
    if not candidate_name:
        return None
    raw_candidate = Path(candidate_name)
    candidate_path = raw_candidate if raw_candidate.is_absolute() else (template_root / raw_candidate)
    if candidate_path.is_dir():
        return candidate_path.resolve()
    if candidate_path.is_file():
        return candidate_path.resolve().parent
    return None


def _infer_active_treatment_no(scenario_id: str) -> int:
    match = re.search(r"-tr(\d+)-", str(scenario_id).strip())
    if not match:
        return 0
    return int(match.group(1))


def _batch_crop_code_for_scenario(scenario: SimulationScenario) -> str:
    crop_name = str(scenario.crop_spec.crop_name).strip().lower()
    if crop_name == "rice":
        return "RICE"
    if crop_name == "maize":
        return "MAIZE"
    return crop_name.upper() or "DSSAT"


def _write_single_treatment_batch(batch_path: Path, experiment_name: str, treatment_no: int, crop_code: str) -> None:
    batch_text = (
        f"$BATCH({crop_code})\n"
        "@FILEX                                                                                        TRTNO     RP     SQ     OP     CO\n"
        f"{experiment_name:<90}{treatment_no:>6}{1:>7}{0:>7}{0:>7}{0:>7}\n"
    )
    batch_path.write_text(batch_text, encoding="utf-8")
