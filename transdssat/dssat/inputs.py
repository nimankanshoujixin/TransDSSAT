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


class DSSATInputBuilder:
    def __init__(self, config: DSSATRunConfig) -> None:
        self.config = config

    def build(self, scenario: SimulationScenario, policy: SeasonPolicy) -> DSSATRunContext:
        self.config.working_root.mkdir(parents=True, exist_ok=True)
        run_dir = self.config.working_root / policy.policy_id
        if run_dir.exists():
            shutil.rmtree(run_dir)
        run_dir.mkdir(parents=True, exist_ok=True)

        template_dir = None
        if self.config.template_root is not None:
            template_dir = self.config.template_root / (scenario.template_name or scenario.crop_spec.crop_name)
            if template_dir.exists():
                self._copy_tree(template_dir, run_dir)
            else:
                template_dir = None

        policy_path = run_dir / "transdssat_policy.tsv"
        weather_path = run_dir / "transdssat_weather.csv"
        soil_path = run_dir / "transdssat_soil.json"
        scenario_path = run_dir / "transdssat_scenario.json"
        manifest_path = run_dir / "transdssat_manifest.json"

        self._write_policy(policy_path, policy)
        self._write_weather(weather_path, scenario)
        soil_path.write_text(
            json.dumps(asdict(scenario.soil_profile), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        scenario_path.write_text(
            json.dumps(
                {
                    "scenario_id": scenario.scenario_id,
                    "engine_name": scenario.engine_name,
                    "crop_name": scenario.crop_spec.crop_name,
                    "planting_date": scenario.planting_date,
                    "cultivar_code": scenario.cultivar_code,
                    "template_name": scenario.template_name,
                    "site_name": scenario.site_name,
                    "season_length_days": scenario.crop_spec.season_length_days,
                },
                indent=2,
                ensure_ascii=False,
            ),
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
