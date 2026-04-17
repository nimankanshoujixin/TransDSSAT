from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from transdssat.domain import CropOutcome, CropState
from transdssat.scenarios import SimulationScenario, stage_for_day


def _to_float(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _first_float(row: dict[str, str], keys: tuple[str, ...], default: float) -> float:
    for key in keys:
        value = _to_float(row.get(key))
        if value is not None:
            return value
    return default


@dataclass(slots=True)
class ParsedDSSATOutputs:
    daily_states: list[CropState]
    outcome: CropOutcome
    avg_water_stress: float
    avg_nitrogen_stress: float


class DSSATOutputParser:
    def parse(self, run_dir: Path, scenario: SimulationScenario) -> ParsedDSSATOutputs:
        summary_rows = self.parse_table(run_dir / "Summary.OUT")
        plant_rows = self.parse_table(run_dir / "PlantGro.OUT")
        soil_water_rows = self.parse_table(run_dir / "SoilWat.OUT")
        soil_n_rows = self.parse_table(run_dir / "SoilNi.OUT")

        daily_states = self._build_daily_states(
            scenario=scenario,
            plant_rows=plant_rows,
            soil_water_rows=soil_water_rows,
            soil_n_rows=soil_n_rows,
        )
        outcome = self._parse_outcome(summary_rows, scenario, daily_states)
        avg_water_stress = round(
            sum(state.water_stress for state in daily_states) / max(1, len(daily_states)),
            6,
        )
        avg_nitrogen_stress = round(
            sum(state.nitrogen_stress for state in daily_states) / max(1, len(daily_states)),
            6,
        )
        return ParsedDSSATOutputs(
            daily_states=daily_states,
            outcome=outcome,
            avg_water_stress=avg_water_stress,
            avg_nitrogen_stress=avg_nitrogen_stress,
        )

    def parse_table(self, path: Path) -> list[dict[str, str]]:
        if not path.exists():
            return []
        rows: list[dict[str, str]] = []
        columns: list[str] | None = None
        for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = raw_line.rstrip()
            if not line:
                continue
            if line.startswith("@"):
                columns = line[1:].split()
                continue
            if columns is None or line.startswith("*") or line.startswith("!"):
                continue
            values = line.split()
            if len(values) < len(columns):
                values.extend([""] * (len(columns) - len(values)))
            rows.append(dict(zip(columns, values[: len(columns)])))
        return rows

    def _build_daily_states(
        self,
        scenario: SimulationScenario,
        plant_rows: list[dict[str, str]],
        soil_water_rows: list[dict[str, str]],
        soil_n_rows: list[dict[str, str]],
    ) -> list[CropState]:
        if not plant_rows:
            raise RuntimeError(
                "PlantGro.OUT could not be parsed. The official DSSAT backend requires daily "
                "PlantGro.OUT output to reconstruct trajectory states."
            )

        soil_water_by_day = self._index_rows(soil_water_rows)
        soil_n_by_day = self._index_rows(soil_n_rows)
        states: list[CropState] = []
        previous_root_zone_water = scenario.soil_profile.initial_root_zone_water_mm
        previous_n = scenario.soil_profile.initial_nitrogen_kg_ha

        for row_index, row in enumerate(plant_rows):
            day_index = self._row_day_index(row, row_index)
            weather = scenario.weather[min(day_index, len(scenario.weather) - 1)]
            stage, stage_index = stage_for_day(day_index, scenario.crop_spec.season_length_days)
            soil_water_row = soil_water_by_day.get(day_index, {})
            soil_n_row = soil_n_by_day.get(day_index, {})

            lai = _first_float(row, ("LAID", "LAI"), 0.0)
            canopy_cover = max(0.0, min(0.98, 1.0 - pow(2.718281828, -0.65 * lai)))
            biomass = _first_float(row, ("CWAD", "BIOMAS", "VWAD", "TOPWT"), 0.0)
            root_zone_water = _first_float(
                soil_water_row,
                ("TSW", "SWTD", "AVSW", "SWXD"),
                previous_root_zone_water,
            )
            soil_n = _first_float(
                soil_n_row,
                ("NIAD", "NINUM", "AMTNIT", "TNIT"),
                previous_n,
            )
            water_factor = _first_float(row, ("SWFAC", "TURFAC"), 1.0)
            n_factor = _first_float(row, ("NSTRES", "NSTRS"), 1.0)
            water_stress = max(0.0, min(1.0, 1.0 - min(1.0, water_factor)))
            nitrogen_stress = max(0.0, min(1.0, 1.0 - min(1.0, n_factor)))
            soil = scenario.soil_profile
            soil_moisture = max(
                0.0,
                min(
                    1.2,
                    (root_zone_water - soil.wilting_point_mm)
                    / max(1e-6, soil.field_capacity_mm - soil.wilting_point_mm),
                ),
            )

            states.append(
                CropState(
                    day_index=day_index,
                    stage=stage,
                    stage_index=stage_index,
                    soil_moisture=round(soil_moisture, 4),
                    root_zone_water_mm=round(root_zone_water, 3),
                    soil_nitrogen_kg_ha=round(soil_n, 3),
                    canopy_cover=round(canopy_cover, 4),
                    biomass_kg_ha=round(biomass, 3),
                    water_stress=round(water_stress, 4),
                    nitrogen_stress=round(nitrogen_stress, 4),
                    tmean_c=round(weather.tmean_c, 3),
                    precipitation_mm=weather.precipitation_mm,
                    et0_mm=weather.et0_mm,
                    radiation_mj_m2=weather.radiation_mj_m2,
                )
            )
            previous_root_zone_water = root_zone_water
            previous_n = soil_n
        return states

    def _index_rows(self, rows: list[dict[str, str]]) -> dict[int, dict[str, str]]:
        indexed: dict[int, dict[str, str]] = {}
        for row_index, row in enumerate(rows):
            indexed[self._row_day_index(row, row_index)] = row
        return indexed

    def _row_day_index(self, row: dict[str, str], fallback_index: int) -> int:
        for key in ("DAS", "DAP"):
            value = _to_float(row.get(key))
            if value is not None:
                return max(0, int(value))
        return fallback_index

    def _parse_outcome(
        self,
        summary_rows: list[dict[str, str]],
        scenario: SimulationScenario,
        states: list[CropState],
    ) -> CropOutcome:
        summary = summary_rows[-1] if summary_rows else {}
        yield_kg_ha = _first_float(summary, ("HWAM", "GWAM", "HWAH"), 0.0)
        biomass_kg_ha = _first_float(summary, ("CWAM", "VWAM", "BIOMAS"), states[-1].biomass_kg_ha)
        irrigation = _first_float(summary, ("IRCM", "TOTIR", "IRRAMT"), 0.0)
        nitrogen = _first_float(summary, ("NICM", "AMTNIT", "TOTN"), 0.0)
        if irrigation <= 0.0:
            irrigation = 0.0
        if nitrogen <= 0.0:
            nitrogen = 0.0
        return CropOutcome(
            yield_kg_ha=round(yield_kg_ha, 3),
            biomass_kg_ha=round(biomass_kg_ha, 3),
            total_irrigation_mm=round(irrigation, 3),
            total_nitrogen_kg_ha=round(nitrogen, 3),
            water_use_efficiency=round(yield_kg_ha / max(1.0, irrigation + 1.0), 5),
            nitrogen_use_efficiency=round(yield_kg_ha / max(1.0, nitrogen + 1.0), 5),
            cumulative_reward=0.0,
        )
