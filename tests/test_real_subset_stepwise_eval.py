from __future__ import annotations

import unittest
from types import SimpleNamespace

from transdssat.real_subset_stepwise_eval import (
    _parse_initial_conditions,
    _parse_treatment_initial_condition_levels,
    build_real_subset_simulation_scenario,
    rollout_episode_to_season_policy,
    summarize_real_subset_replay_results,
)


class RealSubsetStepwiseEvalTests(unittest.TestCase):
    def test_parse_initial_conditions_can_follow_shared_ic_factor_block(self) -> None:
        lines = [
            "*TREATMENTS                        -------------FACTOR LEVELS------------",
            "@N R O C TNAME.................... CU FL SA IC MP MI MF MR MC MT ME MH SM",
            " 1 1 1 0 level 1                   1  1  0  1  1  1  1  0  0  0  0  0  1",
            " 3 1 1 0 level 3                   1  1  0  1  3  1  3  0  0  0  0  0  1",
            " 8 1 1 0 level 8                   1  1  0  2  8  2  8  0  0  0  0  0  2",
            "*INITIAL CONDITIONS",
            "@C   PCR ICDAT  ICRT  ICND  ICRN  ICRE  ICWD ICRES ICREN ICREP ICRIP ICRID ICNAME",
            "  1   RI 21152   -99   -99     1     1   -99   -99   -99   -99   -99   -99 shared_ic_1",
            "@C  ICBL  SH2O  SNH4  SNO3",
            "  1    10   .54   4.6     1",
            "  1    20   .46   3.4    .8",
            "  2   RI 21060   -99   -99     1     1   -99   -99   -99   -99   -99   -99 shared_ic_2",
            "@C  ICBL  SH2O  SNH4  SNO3",
            "  2    10   .44   2.6     .7",
            "  2    20   .36   2.1     .5",
            "*PLANTING DETAILS",
        ]

        ic_levels = _parse_treatment_initial_condition_levels(lines)
        self.assertEqual(ic_levels[3], 1)
        self.assertEqual(ic_levels[8], 2)

        water, nh4, no3 = _parse_initial_conditions(lines, 3)
        self.assertEqual(water, [0.54, 0.46])
        self.assertEqual(nh4, [4.6, 3.4])
        self.assertEqual(no3, [1.0, 0.8])

    def test_build_mx475_real_subset_simulation_scenario(self) -> None:
        materialized = build_real_subset_simulation_scenario("mx475_migrated", 1)

        self.assertEqual(materialized.scenario.crop_spec.crop_name, "rice")
        self.assertEqual(materialized.scenario.cultivar_code, "IB2002")
        self.assertEqual(materialized.scenario.site_name, "wuhu")
        self.assertGreater(len(materialized.scenario.weather), 100)
        self.assertGreater(materialized.scenario.irrigation_budget_mm, 0.0)
        self.assertGreater(materialized.scenario.nitrogen_budget_kg_ha, 0.0)
        self.assertEqual(
            materialized.scenario.objective_context.soft_preferences["yield_floor_reference_kg_ha"],
            materialized.case.observed_yield_kg_ha,
        )

    def test_build_wuhu_real_subset_simulation_scenario(self) -> None:
        materialized = build_real_subset_simulation_scenario("wuhu_rice_calibrated", 11)

        self.assertEqual(materialized.scenario.crop_spec.crop_name, "rice")
        self.assertEqual(materialized.scenario.cultivar_code, "WHR006")
        self.assertEqual(materialized.source_soil_id, "CNWH000001")
        self.assertTrue(materialized.source_weather_file.endswith("EQAH2101.WTH"))
        self.assertGreater(materialized.scenario.soil_profile.field_capacity_mm, 0.0)
        self.assertGreater(materialized.scenario.soil_profile.initial_root_zone_water_mm, 0.0)

    def test_rollout_episode_to_season_policy_filters_zero_actions(self) -> None:
        episode = SimpleNamespace(
            policy_id="ppo_best",
            scenario_id="subset-tr11",
            transitions=[
                SimpleNamespace(
                    decision_date="2021-07-04",
                    state=SimpleNamespace(day_index=0),
                    action=SimpleNamespace(irrigation_mm=0.0, nitrogen_kg_ha=0.0),
                ),
                SimpleNamespace(
                    decision_date="2021-07-09",
                    state=SimpleNamespace(day_index=5),
                    action=SimpleNamespace(irrigation_mm=15.0, nitrogen_kg_ha=0.0),
                ),
                SimpleNamespace(
                    decision_date="2021-07-14",
                    state=SimpleNamespace(day_index=10),
                    action=SimpleNamespace(irrigation_mm=0.0, nitrogen_kg_ha=8.0),
                ),
            ],
        )

        policy = rollout_episode_to_season_policy(episode)

        self.assertEqual(policy.policy_id, "ppo_best-real-subset")
        self.assertEqual(len(policy.actions), 2)
        self.assertEqual(policy.actions[0].day_index, 5)
        self.assertEqual(policy.actions[1].nitrogen_kg_ha, 8.0)

    def test_summary_exposes_baseline_and_replacement_layers(self) -> None:
        results = [
            {
                "subset_id": "mx475_migrated",
                "baseline_replay": {
                    "observed_yield_kg_ha": 5000.0,
                    "simulated_yield_kg_ha": 5300.0,
                    "yield_gap_kg_ha": 300.0,
                    "yield_gap_ratio": 0.06,
                },
                "replacement_replay": {
                    "observed_yield_kg_ha": 5000.0,
                    "simulated_yield_kg_ha": 5600.0,
                    "yield_gap_kg_ha": 600.0,
                    "yield_gap_ratio": 0.12,
                },
            },
            {
                "subset_id": "mx475_migrated",
                "baseline_replay": {
                    "observed_yield_kg_ha": 6000.0,
                    "simulated_yield_kg_ha": 6100.0,
                    "yield_gap_kg_ha": 100.0,
                    "yield_gap_ratio": 0.016667,
                },
                "replacement_replay": {
                    "observed_yield_kg_ha": 6000.0,
                    "simulated_yield_kg_ha": 5900.0,
                    "yield_gap_kg_ha": -100.0,
                    "yield_gap_ratio": -0.016667,
                },
            },
        ]

        summary = summarize_real_subset_replay_results(results)

        self.assertEqual(summary["case_count"], 2)
        self.assertEqual(summary["subset_counts"]["mx475_migrated"], 2)
        self.assertEqual(summary["reality_facing"]["observed_yield_kg_ha"]["mean"], 5500.0)
        self.assertEqual(summary["reality_facing"]["baseline_minus_observation_kg_ha"]["max"], 300.0)
        self.assertEqual(summary["reality_facing"]["replacement_minus_observation_kg_ha"]["min"], -100.0)
        self.assertEqual(summary["policy_increment"]["replacement_minus_baseline_kg_ha"]["mean"], 50.0)
        self.assertEqual(summary["by_subset"]["mx475_migrated"]["case_count"], 2)
        self.assertEqual(summary["mean_yield_gap_kg_ha"], 250.0)
        self.assertEqual(summary["mean_abs_yield_gap_kg_ha"], 350.0)


if __name__ == "__main__":
    unittest.main()
