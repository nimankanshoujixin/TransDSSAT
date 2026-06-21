from __future__ import annotations

from datetime import date, timedelta
import unittest

from transdssat.real_world_data import (
    WARM_SEASON_TAIL_GATES,
    build_real_weather_catalog,
    load_real_soil_samples,
    load_real_weather_archive,
)
from transdssat.scenarios import build_quzhou_scenarios
from scripts.render_dssat_inputs import date_to_yyddd, replace_primary_dates, resolve_scenario_planting_yyddd


class RealDataSourceTests(unittest.TestCase):
    def test_real_weather_and_soil_sources_load(self) -> None:
        weather_archive = load_real_weather_archive()
        soil_samples = load_real_soil_samples()

        self.assertGreaterEqual(len(weather_archive.rows_by_station), 2)
        self.assertGreater(len(weather_archive.rows), 1000)
        self.assertGreaterEqual(len(soil_samples), 10)
        self.assertTrue(all(sample.soil_profile.field_capacity_mm > sample.soil_profile.wilting_point_mm for sample in soil_samples))

        maize_catalog = build_real_weather_catalog("maize", 135, archive=weather_archive)
        wheat_catalog = build_real_weather_catalog("wheat", 210, archive=weather_archive)
        self.assertGreater(len(maize_catalog), 0)
        self.assertGreater(len(wheat_catalog), 0)
        self.assertTrue(all(template.weather for template in maize_catalog[:3]))
        maize_gate = WARM_SEASON_TAIL_GATES["maize"]
        for template in maize_catalog[:10]:
            tail = template.weather[-maize_gate["window_days"] :]
            self.assertGreaterEqual(sum(day.tmean_c for day in tail) / len(tail), maize_gate["min_tail_mean_temperature_c"])
            self.assertGreaterEqual(min(day.tmin_c for day in tail), maize_gate["min_tail_min_temperature_c"])

    def test_realistic_scenario_generation_is_valid(self) -> None:
        scenarios = build_quzhou_scenarios(
            target_count=8,
            engines=("dssat_proxy",),
            crops_filter=("maize",),
            sampling_mode="realistic",
            seed=20260615,
        )

        self.assertEqual(len(scenarios), 8)
        self.assertTrue(all(scenario.weather for scenario in scenarios))
        self.assertTrue(all(scenario.soil_profile.field_capacity_mm > scenario.soil_profile.wilting_point_mm for scenario in scenarios))
        self.assertTrue(all(scenario.weather_regime in {"dry", "normal", "wet"} for scenario in scenarios))
        self.assertEqual(len({scenario.scenario_id for scenario in scenarios}), len(scenarios))
        self.assertTrue(all(scenario.irrigation_budget_mm >= 300.0 for scenario in scenarios))
        self.assertTrue(all(scenario.nitrogen_budget_kg_ha >= 300.0 for scenario in scenarios))

    def test_realistic_maize_only_pool_has_maize_template(self) -> None:
        scenarios = build_quzhou_scenarios(
            target_count=4,
            engines=("dssat_official",),
            crops_filter=("maize",),
            sampling_mode="realistic",
            seed=20260616,
        )

        self.assertTrue(all(scenario.crop_spec.crop_name == "maize" for scenario in scenarios))
        self.assertTrue(all(scenario.template_name == "maize_quzhou_base" for scenario in scenarios))
        self.assertTrue(all(scenario.experiment_file == "UFGA8201.MZX" for scenario in scenarios))
        self.assertTrue(all(scenario.irrigation_budget_mm >= 300.0 for scenario in scenarios))
        self.assertTrue(all(scenario.nitrogen_budget_kg_ha >= 300.0 for scenario in scenarios))
        tail_window_days = WARM_SEASON_TAIL_GATES["maize"]["window_days"]
        for scenario in scenarios:
            tail = scenario.weather[-tail_window_days:]
            self.assertGreaterEqual(sum(day.tmean_c for day in tail) / len(tail), WARM_SEASON_TAIL_GATES["maize"]["min_tail_mean_temperature_c"])
            self.assertGreaterEqual(min(day.tmin_c for day in tail), WARM_SEASON_TAIL_GATES["maize"]["min_tail_min_temperature_c"])

    def test_render_dates_follow_realistic_scenario_planting_date(self) -> None:
        scenario = build_quzhou_scenarios(
            target_count=1,
            engines=("dssat_official",),
            crops_filter=("maize",),
            sampling_mode="realistic",
            seed=20260616,
        )[0]
        planting_yyddd = resolve_scenario_planting_yyddd(
            {"planting_date": scenario.planting_date},
            "82057",
        )
        self.assertEqual(planting_yyddd, date_to_yyddd(date.fromisoformat(scenario.planting_date)))

        lines = [
            "@N GENERAL     NYERS NREPS START SDATE RSEED SNAME.................... SMODEL",
            " 1 GE              1     1     S 82056  2150 N X IRRIGATION, GAINESVI",
            "*INITIAL CONDITIONS",
            "@C   PCR ICDAT  ICRT  ICND  ICRN  ICRE  ICWD ICRES ICREN ICREP ICRIP ICRID ICNAME",
            " 1    MZ 82056   100     0     1     1   -99  1000    .8     0   100    15 -99",
            "*PLANTING DETAILS",
            "@P PDATE EDATE  PPOP  PPOE  PLME  PLDS  PLRS  PLRD  PLDP  PLWT  PAGE  PENV  PLPH  SPRL                        PLNAME",
            " 1 82057   -99   7.2   7.2     S     R    61     0     7   -99   -99   -99   -99     0                        -99",
            "@N PLANTING    PFRST PLAST PH2OL PH2OU PH2OD PSTMX PSTMN",
            " 1 PL          82050 82064    40   100    30    40    10",
            "@N HARVEST     HFRST HLAST HPCNP HPCNR",
            " 1 HA              0 83057   100     0",
        ]
        updated = replace_primary_dates(lines, planting_yyddd)
        emergence_yyddd = date_to_yyddd(date.fromisoformat(scenario.planting_date) - timedelta(days=1))
        harvest_yyddd = date_to_yyddd(date.fromisoformat(scenario.planting_date) + timedelta(days=365))

        self.assertEqual(updated[1].split()[5], emergence_yyddd)
        self.assertEqual(updated[4].split()[2], emergence_yyddd)
        self.assertEqual(updated[7].split()[1], planting_yyddd)
        self.assertEqual(updated[9].split()[2], planting_yyddd)
        self.assertEqual(updated[9].split()[3], planting_yyddd)
        self.assertEqual(
            updated[11].split()[2],
            harvest_yyddd,
        )
        self.assertEqual(updated[11].split()[3], harvest_yyddd)


if __name__ == "__main__":
    unittest.main()
