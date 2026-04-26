from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from transdssat.domain import CropOutcome, CropState
from transdssat.rewarding import input_use_efficiency
from transdssat.scenarios import SimulationScenario, stage_for_day


def _to_float(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _is_missing(value: float | None) -> bool:
    return value is None or value <= -90.0


def _first_float(row: dict[str, str], keys: tuple[str, ...], default: float) -> float:
    for key in keys:
        value = _to_float(row.get(key))
        if value is not None:
            return value
    return default


def _first_present_float(row: dict[str, str], keys: tuple[str, ...]) -> float | None:
    for key in keys:
        value = _to_float(row.get(key))
        if not _is_missing(value):
            return value
    return None


@dataclass(slots=True)
class ParsedDSSATOutputs:
    daily_states: list[CropState]
    outcome: CropOutcome
    avg_water_stress: float
    avg_nitrogen_stress: float


class DSSATOutputParser:
    def parse(self, run_dir: Path, scenario: SimulationScenario, run_number: int = 1) -> ParsedDSSATOutputs:
        summary_rows = self.parse_table(run_dir / "Summary.OUT", fixed_width=True)
        plant_rows = self.parse_table(run_dir / "PlantGro.OUT", run_number=run_number)
        soil_water_rows = self.parse_table(run_dir / "SoilWat.OUT", run_number=run_number)
        soil_n_rows = self.parse_table(run_dir / "SoilNi.OUT", run_number=run_number)

        daily_states = self._build_daily_states(
            scenario=scenario,
            plant_rows=plant_rows,
            soil_water_rows=soil_water_rows,
            soil_n_rows=soil_n_rows,
        )
        outcome = self._parse_outcome(
            summary_rows,
            scenario,
            daily_states,
            plant_rows,
            run_number=run_number,
        )
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

    def parse_table(
        self,
        path: Path,
        run_number: int | None = None,
        fixed_width: bool = False,
    ) -> list[dict[str, str]]:
        if not path.exists():
            return []
        rows: list[dict[str, str]] = []
        columns: list[str] | None = None
        current_run: int | None = None
        has_run_sections = False
        slices: list[tuple[str, int, int | None]] | None = None

        for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = raw_line.rstrip()
            if not line:
                continue
            if line.startswith("*RUN"):
                parsed_run = self._parse_run_header(line)
                if parsed_run is not None:
                    current_run = parsed_run
                    has_run_sections = True
                continue
            if line.startswith("@"):
                if fixed_width:
                    slices = self._header_slices(line[1:])
                    columns = [name for name, _, _ in slices]
                else:
                    columns = line[1:].split()
                continue
            if columns is None or line.startswith("*") or line.startswith("!"):
                continue
            if run_number is not None and has_run_sections and current_run != run_number:
                continue
            if fixed_width and slices is not None:
                rows.append(self._parse_fixed_width_row(line, slices))
            else:
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

    def _parse_run_header(self, line: str) -> int | None:
        tokens = line.split()
        if len(tokens) < 2:
            return None
        return int(tokens[1]) if tokens[1].isdigit() else None

    def _header_slices(self, header: str) -> list[tuple[str, int, int | None]]:
        matches = list(re.finditer(r"\S+", header))
        slices: list[tuple[str, int, int | None]] = []
        for index, match in enumerate(matches):
            name = match.group(0)
            start = match.start()
            end = matches[index + 1].start() if index + 1 < len(matches) else None
            slices.append((name, start, end))
        return slices

    def _parse_fixed_width_row(
        self,
        row: str,
        slices: list[tuple[str, int, int | None]],
    ) -> dict[str, str]:
        parsed: dict[str, str] = {}
        for name, start, end in slices:
            parsed[name] = row[start:end].strip() if end is not None else row[start:].strip()
        return parsed

    def _parse_outcome(
        self,
        summary_rows: list[dict[str, str]],
        scenario: SimulationScenario,
        states: list[CropState],
        plant_rows: list[dict[str, str]],
        run_number: int,
    ) -> CropOutcome:
        summary = self._select_summary_row(summary_rows, run_number)
        final_plant_row = plant_rows[-1] if plant_rows else {}
        yield_kg_ha = _first_present_float(summary, ("HWAM", "GWAM", "HWAH"))
        if yield_kg_ha is None:
            yield_kg_ha = self._plant_state_value(final_plant_row, ("HWAD", "GWAD", "PWAD"), 0.0)

        biomass_kg_ha = _first_present_float(summary, ("CWAM", "VWAM", "BWAH", "PWAM", "BIOMAS"))
        if biomass_kg_ha is None:
            biomass_kg_ha = self._plant_state_value(final_plant_row, ("TWAD", "CWAD", "VWAD", "SDWAD"), states[-1].biomass_kg_ha)
        if biomass_kg_ha > max(100000.0, states[-1].biomass_kg_ha * 10.0):
            biomass_kg_ha = states[-1].biomass_kg_ha
        irrigation = _first_present_float(summary, ("IRCM", "TOTIR", "IRRAMT"))
        if irrigation is None:
            irrigation = 0.0
        nitrogen = _first_present_float(summary, ("NICM", "AMTNIT", "TOTN"))
        if nitrogen is None:
            nitrogen = 0.0
        if irrigation <= 0.0:
            irrigation = 0.0
        if nitrogen <= 0.0:
            nitrogen = 0.0
        return CropOutcome(
            yield_kg_ha=round(yield_kg_ha, 3),
            biomass_kg_ha=round(biomass_kg_ha, 3),
            total_irrigation_mm=round(irrigation, 3),
            total_nitrogen_kg_ha=round(nitrogen, 3),
            water_use_efficiency=input_use_efficiency(yield_kg_ha, irrigation),
            nitrogen_use_efficiency=input_use_efficiency(yield_kg_ha, nitrogen),
            cumulative_reward=0.0,
        )

    def _select_summary_row(self, summary_rows: list[dict[str, str]], run_number: int) -> dict[str, str]:
        if not summary_rows:
            return {}
        for row in summary_rows:
            value = _to_float(row.get("RUNNO"))
            if value is not None and int(value) == run_number:
                return row
        return summary_rows[0]

    def _plant_state_value(
        self,
        row: dict[str, str],
        keys: tuple[str, ...],
        default: float,
    ) -> float:
        value = _first_present_float(row, keys)
        return default if value is None else value
