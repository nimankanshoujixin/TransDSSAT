from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
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

        template_dir = None
        if self.config.template_root is not None:
            template_root = self.config.template_root.resolve()
            candidate_names = [scenario.template_name, f"{scenario.crop_spec.crop_name}_quzhou_base", scenario.crop_spec.crop_name]
            for candidate_name in candidate_names:
                if not candidate_name:
                    continue
                candidate_dir = template_root / candidate_name
                if candidate_dir.exists():
                    template_dir = candidate_dir
                    self._copy_tree(candidate_dir, run_dir)
                    break

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

    def _copy_tree(self, source_dir: Path, target_dir: Path) -> None:
        for path in source_dir.rglob("*"):
            relative = path.relative_to(source_dir)
            destination = target_dir / relative
            if path.is_dir():
                destination.mkdir(parents=True, exist_ok=True)
            else:
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, destination)

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
