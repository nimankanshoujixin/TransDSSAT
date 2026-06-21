from __future__ import annotations

import copy
import unittest

from transdssat.evaluation import score_trajectory, summarize_scorecards
from transdssat.policy_registry import build_policy_registry
from transdssat.scenarios import build_quzhou_scenarios, objective_context_for_id
from transdssat.stepwise_policy import (
    build_equal_allocation_stepwise_policy,
    build_heuristic_stepwise_policy,
    rollout_stepwise_policy,
)
from transdssat.strategies import ReferenceAIPolicyFamily, build_default_strategies
from transdssat.testset import generate_general_random_test_set, generate_literature_matched_slices
from transdssat.unified_eval import UnifiedEvaluationRunner


class UnifiedEvaluationStepwiseTests(unittest.TestCase):
    def test_runner_supports_stepwise_decision_mode(self) -> None:
        registry = build_policy_registry()
        strategies = build_default_strategies(registry, ai_family=ReferenceAIPolicyFamily())
        general_random = generate_general_random_test_set(
            train_count=1,
            val_count=0,
            test_count=0,
            engines=("dssat_proxy",),
            crops_filter=("maize",),
            seed=20260526,
        )
        matched_slices = generate_literature_matched_slices(
            registry,
            scenario_count_per_slice=1,
            engines=("dssat_proxy",),
            crops_filter=("maize",),
            seed=20260543,
        )
        runner = UnifiedEvaluationRunner(
            strategies,
            decision_granularity="stepwise",
            reference_strategy_id="equal_allocation",
        )

        report = runner.evaluate(general_random, matched_slices)

        self.assertEqual(report["decision_granularity"], "stepwise")
        equal_row = next(
            row for row in report["general_random_summary"]["strategies"] if row["strategy_id"] == "equal_allocation"
        )
        self.assertGreater(equal_row["applicable_count"], 0)
        self.assertIn("mean_total_drainage_mm", equal_row["summary"])
        self.assertIn("mean_total_nitrogen_leached_kg_ha", equal_row["summary"])
        self.assertIn("mean_terminal_root_zone_water_mm", equal_row["summary"])
        self.assertIn("mean_terminal_soil_nitrogen_kg_ha", equal_row["summary"])
        self.assertIn("mean_yield_floor_gap_ratio", equal_row["summary"])
        self.assertIn("mean_yield_floor_attainment_pct", equal_row["summary"])
        self.assertIn("mean_irrigation_budget_violation_ratio", equal_row["summary"])
        self.assertEqual(equal_row["summary"]["mean_irrigation_budget_violation_ratio"], 0.0)
        self.assertEqual(equal_row["summary"]["mean_nitrogen_budget_violation_ratio"], 0.0)
        execution = next(
            item for item in report["general_random_summary"]["executions"] if item["strategy_id"] == "equal_allocation"
        )
        self.assertEqual(execution["execution_interface"], "native_stepwise_policy")
        self.assertIsNotNone(execution["adapter_summary"])
        self.assertEqual(execution["adapter_summary"]["policy_kind"], "scheduled_stepwise_policy")
        self.assertIn("uniform_decision_day_allocation", execution["adapter_summary"]["notes"])

    def test_objective_context_changes_stepwise_scorecard_reward(self) -> None:
        base_scenario = build_quzhou_scenarios(
            target_count=1,
            engines=("dssat_proxy",),
            crops_filter=("maize",),
            sampling_mode="random",
            seed=20260609,
        )[0]
        profit_scenario = copy.deepcopy(base_scenario)
        profit_scenario.objective_context = objective_context_for_id("profit")
        nitrogen_saving_scenario = copy.deepcopy(base_scenario)
        nitrogen_saving_scenario.objective_context = objective_context_for_id("nitrogen_saving")

        profit_candidate = rollout_stepwise_policy(
            profit_scenario,
            build_heuristic_stepwise_policy(profit_scenario),
        )
        profit_baseline = rollout_stepwise_policy(
            profit_scenario,
            build_equal_allocation_stepwise_policy(profit_scenario),
        )
        nitrogen_candidate = rollout_stepwise_policy(
            nitrogen_saving_scenario,
            build_heuristic_stepwise_policy(nitrogen_saving_scenario),
        )
        nitrogen_baseline = rollout_stepwise_policy(
            nitrogen_saving_scenario,
            build_equal_allocation_stepwise_policy(nitrogen_saving_scenario),
        )

        profit_scorecard = score_trajectory(profit_scenario, profit_candidate, profit_baseline)
        nitrogen_scorecard = score_trajectory(
            nitrogen_saving_scenario,
            nitrogen_candidate,
            nitrogen_baseline,
        )

        self.assertNotEqual(profit_scorecard.reward, nitrogen_scorecard.reward)
        self.assertNotEqual(profit_scorecard.reward_gain, nitrogen_scorecard.reward_gain)
        self.assertNotEqual(profit_scorecard.total_score_100, nitrogen_scorecard.total_score_100)

    def test_scorecard_captures_absolute_yield_floor_gap(self) -> None:
        scenario = build_quzhou_scenarios(
            target_count=1,
            engines=("dssat_proxy",),
            crops_filter=("maize",),
            sampling_mode="random",
            seed=20260616,
        )[0]
        candidate = rollout_stepwise_policy(
            scenario,
            build_heuristic_stepwise_policy(scenario),
        )
        baseline = rollout_stepwise_policy(
            scenario,
            build_equal_allocation_stepwise_policy(scenario),
        )
        scorecard = score_trajectory(scenario, candidate, baseline)
        summary = summarize_scorecards([scorecard])

        self.assertGreater(scorecard.yield_floor_reference_kg_ha, 0.0)
        self.assertGreaterEqual(scorecard.yield_floor_gap_ratio, 0.0)
        self.assertLessEqual(scorecard.yield_floor_attainment_pct, 100.0)
        self.assertIn("mean_yield_floor_gap_ratio", summary)
        self.assertIn("mean_yield_floor_attainment_pct", summary)


if __name__ == "__main__":
    unittest.main()
