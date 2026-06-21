from __future__ import annotations

from datetime import date
import random
import unittest

from transdssat.data_generator import _validate_record, generate_one_training_scenario
from transdssat.real_world_data import load_real_weather_archive
from transdssat.scenarios import DecisionContext, SimulationScenario, build_crop_specs, build_cultivar_context, default_objective_context
from transdssat.season import SeasonPolicy


class DataGeneratorTests(unittest.TestCase):
    def test_generated_scenario_and_policy_ids_are_unique_and_aligned(self) -> None:
        rng = random.Random(17)
        first = generate_one_training_scenario("rice", rng, scenario_serial=0)
        second = generate_one_training_scenario("rice", rng, scenario_serial=1)

        self.assertNotEqual(first.scenario.scenario_id, second.scenario.scenario_id)
        self.assertEqual(first.policy.scenario_id, first.scenario.scenario_id)
        self.assertEqual(second.policy.scenario_id, second.scenario.scenario_id)
        self.assertIn(first.scenario.scenario_id, first.policy.policy_id)
        self.assertIn(second.scenario.scenario_id, second.policy.policy_id)

    def test_generated_weather_starts_on_record_planting_date(self) -> None:
        rng = random.Random(7)
        record = generate_one_training_scenario("rice", rng)
        archive = load_real_weather_archive()
        first_day = record.scenario.weather[0]
        planting_date = record.planting_date

        temp_row = archive.rows_by_station[record.weather_station_id][
            date(record.weather_temp_year, planting_date.month, planting_date.day)
        ]
        precip_row = archive.rows_by_station[record.weather_station_id][
            date(record.weather_precip_year, planting_date.month, planting_date.day)
        ]

        self.assertEqual(record.scenario.planting_date, planting_date.isoformat())
        self.assertEqual(first_day.tmin_c, temp_row.tmin_c)
        self.assertEqual(first_day.tmax_c, temp_row.tmax_c)
        self.assertEqual(first_day.precipitation_mm, precip_row.precipitation_mm)
        self.assertEqual(first_day.radiation_mj_m2, precip_row.radiation_mj_m2)
        self.assertEqual(first_day.et0_mm, precip_row.et0_mm)

    def test_validate_record_rejects_test_window_overlap(self) -> None:
        crop_spec = build_crop_specs()["rice"]
        scenario = SimulationScenario(
            scenario_id="test_rice_overlap",
            engine_name="real_weather",
            crop_spec=crop_spec,
            soil_profile=generate_one_training_scenario("rice", random.Random(11)).scenario.soil_profile,
            weather_regime="normal",
            weather=[],
            irrigation_budget_mm=255.0,
            nitrogen_budget_kg_ha=120.0,
            management_mode="balanced",
            seed=11,
            weather_year=2021,
            planting_date="2021-07-04",
            cultivar_code="IB2002",
            template_name="rice_training_base",
            site_name="training",
            crop_context=build_cultivar_context("rice", "IB2002", site_name="training"),
            objective_context=default_objective_context(),
            decision_context=DecisionContext(),
        )
        record = generate_one_training_scenario("rice", random.Random(13))
        record.scenario = scenario
        record.planting_date = date(2021, 7, 4)
        record.cultivar_code = "IB2002"
        record.policy = SeasonPolicy(policy_id="noop", scenario_id="test_rice_overlap", actions=[])

        errors = _validate_record(record)
        self.assertTrue(any("test window" in error for error in errors), errors)


if __name__ == "__main__":
    unittest.main()
