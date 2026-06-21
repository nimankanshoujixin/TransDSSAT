from __future__ import annotations

import unittest

from transdssat.scenarios import build_quzhou_scenarios
from transdssat.season import build_baseline_policy
from transdssat.stepwise_adapter import project_policy_to_stepwise


class StepwiseAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.scenario = build_quzhou_scenarios(
            target_count=1,
            engines=("dssat_proxy",),
            crops_filter=("maize",),
            sampling_mode="random",
            seed=20260526,
        )[0]

    def test_projection_maps_daily_policy_to_stepwise_decisions(self) -> None:
        policy = build_baseline_policy(
            self.scenario,
            baseline_name="literature_ncp",
            decision_granularity="daily",
            budget_source="scenario",
        )
        projected_policy, summary = project_policy_to_stepwise(self.scenario, policy)
        self.assertGreater(summary.decision_count, 0)
        self.assertEqual(summary.decision_interval_days, self.scenario.decision_context.decision_interval_days)
        for action in projected_policy.actions:
            self.assertEqual(action.day_index % summary.decision_interval_days, 0)
        self.assertLessEqual(projected_policy.total_irrigation_mm, self.scenario.irrigation_budget_mm)
        self.assertLessEqual(projected_policy.total_nitrogen_kg_ha, self.scenario.nitrogen_budget_kg_ha)
        self.assertIn("projection_uses_window_totals_clipped_to_legal_continuous_bounds", summary.notes or [])
        self.assertTrue(
            any(
                action.irrigation_mm not in {0.0, 10.0, 20.0, 30.0}
                or action.nitrogen_kg_ha not in {0.0, 20.0, 40.0}
                for action in projected_policy.actions
            )
        )


if __name__ == "__main__":
    unittest.main()
