from __future__ import annotations

import unittest

from scripts.train_stepwise_ppo import resolve_pool_seed
from transdssat.testset import generate_training_scenario_pool


class ScenarioPoolTests(unittest.TestCase):
    def test_training_scenario_pool_emits_diversity_summary(self) -> None:
        bundle = generate_training_scenario_pool(
            train_count=12,
            val_count=4,
            test_count=4,
            engines=("dssat_proxy",),
            crops_filter=("maize",),
            seed=20260527,
        )

        self.assertTrue(bundle.valid, msg=bundle.validation_errors)
        self.assertEqual(bundle.summary.total_records, 20)
        self.assertEqual(bundle.summary.split_counts, {"test": 4, "train": 12, "val": 4})
        self.assertEqual(bundle.summary.unique_scenario_id_count, bundle.summary.total_records)
        self.assertEqual(bundle.summary.distinct_signature_count, bundle.summary.total_records)
        self.assertEqual(len(bundle.summary.weather_regime_counts), 3)
        self.assertGreaterEqual(len(bundle.summary.weather_year_counts), 3)
        self.assertGreaterEqual(len(bundle.summary.soil_profile_counts), 3)
        self.assertGreaterEqual(len(bundle.summary.objective_counts), 3)
        self.assertGreater(bundle.summary.pair_coverage["weather_regime_x_soil"], 3)

        payload = bundle.records[0].to_dict()
        self.assertIn("weather_year", payload)
        self.assertIn(payload["objective_context"]["objective_id"], bundle.summary.objective_counts)
        self.assertEqual(payload["state_interface_contract"]["version"], "v2026-06-admission-draft")
        self.assertEqual(payload["discrete_action_table"]["action_table_id"], "deprecated_v1_joint_discrete")
        self.assertEqual(payload["discrete_action_table"]["actions"][0]["label"], "noop")

    def test_explicit_pool_seed_keeps_scenario_pool_fixed(self) -> None:
        pool_seed = resolve_pool_seed(20260527, training_seed=20260610)
        first = generate_training_scenario_pool(
            train_count=8,
            val_count=2,
            test_count=2,
            engines=("dssat_proxy",),
            crops_filter=("maize",),
            seed=pool_seed,
        )
        second = generate_training_scenario_pool(
            train_count=8,
            val_count=2,
            test_count=2,
            engines=("dssat_proxy",),
            crops_filter=("maize",),
            seed=pool_seed,
        )

        self.assertEqual(pool_seed, 20260527)
        self.assertEqual(
            [record.scenario.scenario_id for record in first.records],
            [record.scenario.scenario_id for record in second.records],
        )
        self.assertEqual(first.summary.to_dict(), second.summary.to_dict())

    def test_training_data_sampling_mode_supports_rice_maize_pool(self) -> None:
        bundle = generate_training_scenario_pool(
            train_count=12,
            val_count=4,
            test_count=4,
            engines=("dssat_proxy",),
            crops_filter=("rice", "maize"),
            sampling_mode="training_data",
            seed=20260619,
        )

        self.assertTrue(bundle.valid, msg=bundle.validation_errors)
        self.assertEqual(bundle.summary.total_records, 20)
        self.assertEqual(bundle.summary.split_counts, {"test": 4, "train": 12, "val": 4})
        self.assertEqual(bundle.summary.crop_counts, {"maize": 10, "rice": 10})
        self.assertEqual(bundle.summary.objective_counts, {"profit": 20})
        self.assertEqual({record.sampling_mode for record in bundle.records}, {"training_data"})


if __name__ == "__main__":
    unittest.main()
