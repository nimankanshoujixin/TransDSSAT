from __future__ import annotations

import math
import unittest

from transdssat.scenarios import build_quzhou_scenarios
from transdssat.stepwise_ppo import (
    STEPWISE_OBSERVATION_DIM,
    STEPWISE_SEQUENCE_FEATURE_DIM,
    TORCH_AVAILABLE,
    StepwiseGatedContinuousTransformerActorCritic,
    StepwisePolicyDecision,
    StepwiseTransformerActorCritic,
    _apply_auxiliary_penalty_budget,
    _evaluate_rollout_activity_admission,
    _mean_activity_shortfall_penalty,
    _mean_advantage_activity_anchor_penalty,
    _mean_behavior_anchor_penalty,
    _mean_policy_anchor_penalty,
    build_stepwise_baseline_trajectory,
    build_checkpoint_guardrail_summary,
    collate_sequence_features,
    collect_ppo_rollout_batch,
    compute_activity_ratio,
    compute_gae_advantages,
    encode_stepwise_observation,
    rollout_stepwise_episode,
    run_ppo_update,
    select_highest_legal_action,
    summarize_rollout_episodes,
)


class StepwisePPOTests(unittest.TestCase):
    def setUp(self) -> None:
        self.scenario = build_quzhou_scenarios(
            target_count=1,
            engines=("dssat_proxy",),
            crops_filter=("maize",),
            sampling_mode="random",
            seed=20260608,
        )[0]

    def test_encode_stepwise_observation_returns_fixed_dim(self) -> None:
        from transdssat.environments import StepwiseDecisionEnvironment

        env = StepwiseDecisionEnvironment(self.scenario)
        observation = env.reset()
        features = encode_stepwise_observation(observation)
        self.assertEqual(len(features), STEPWISE_OBSERVATION_DIM)
        self.assertTrue(all(math.isfinite(value) for value in features))

    def test_rollout_stepwise_episode_reaches_terminal_state(self) -> None:
        episode = rollout_stepwise_episode(
            self.scenario,
            select_highest_legal_action,
            policy_id="unit_test_stepwise_ppo",
        )
        self.assertGreater(episode.decision_count, 0)
        self.assertTrue(episode.transitions[-1].done)
        self.assertAlmostEqual(episode.total_reward, episode.final_outcome.cumulative_reward, places=4)
        trajectory = episode.to_trajectory()
        self.assertEqual(len(trajectory.steps), episode.decision_count)
        self.assertEqual(trajectory.policy["policy_kind"], "discrete_stepwise_rollout")
        self.assertEqual(episode.transitions[0].sequence_length, 1)
        self.assertEqual(len(episode.transitions[0].sequence_features[0]), STEPWISE_SEQUENCE_FEATURE_DIM)
        if episode.decision_count > 1:
            self.assertEqual(episode.transitions[1].sequence_length, 2)
            self.assertEqual(len(episode.transitions[1].sequence_features), 2)

    def test_baseline_builder_supports_new_and_legacy_heuristics(self) -> None:
        heuristic_v2 = build_stepwise_baseline_trajectory(self.scenario, baseline_name="heuristic")
        heuristic_legacy = build_stepwise_baseline_trajectory(self.scenario, baseline_name="heuristic_legacy")
        self.assertEqual(heuristic_v2.policy["policy_kind"], "reactive_heuristic_stepwise_policy")
        self.assertEqual(heuristic_legacy.policy["policy_kind"], "scheduled_stepwise_policy")
        self.assertNotEqual(
            heuristic_v2.policy["policy_id"],
            heuristic_legacy.policy["policy_id"],
        )

    def test_gated_continuous_rollout_reaches_terminal_state(self) -> None:
        def gated_selector(observation, _, sequence):  # noqa: ANN001
            del sequence
            return StepwisePolicyDecision(
                action_mode="continuous",
                control_mode="joint",
                irrigation_amount_mm=min(10.0, observation.action_constraints.irrigation.max_value),
                nitrogen_amount_kg_ha=min(20.0, observation.action_constraints.nitrogen.max_value),
            )

        episode = rollout_stepwise_episode(
            self.scenario,
            gated_selector,
            policy_id="unit_test_stepwise_continuous",
        )
        self.assertGreater(episode.decision_count, 0)
        self.assertEqual(episode.action_mode, "continuous")
        self.assertEqual(episode.control_mode, "joint")
        self.assertEqual(episode.transitions[0].action_mode, "continuous")
        self.assertIn(episode.transitions[0].action_family, {"noop", "water_only", "nitrogen_only", "joint"})
        self.assertTrue(episode.transitions[-1].done)
        self.assertAlmostEqual(episode.total_reward, episode.final_outcome.cumulative_reward, places=4)

    def test_continuous_amounts_imply_positive_gates(self) -> None:
        decision = StepwisePolicyDecision(
            action_mode="continuous",
            control_mode="joint",
            irrigation_amount_mm=10.0,
            nitrogen_amount_kg_ha=20.0,
        )

        episode = rollout_stepwise_episode(
            self.scenario,
            lambda observation, _, sequence: decision,  # noqa: ARG005
            policy_id="unit_test_continuous_gate_inference",
        )

        self.assertGreater(episode.decision_count, 0)
        first = episode.transitions[0]
        self.assertGreaterEqual(first.action.irrigation_mm, 0.0)
        self.assertGreaterEqual(first.action.nitrogen_kg_ha, 0.0)
        self.assertEqual(first.irrigation_gate, 1)
        self.assertEqual(first.nitrogen_gate, 1)

    def test_rollout_summary_and_gae_helper(self) -> None:
        episode = rollout_stepwise_episode(self.scenario, select_highest_legal_action)
        summary = summarize_rollout_episodes([episode])
        self.assertEqual(summary["episode_count"], 1)
        self.assertEqual(summary["transition_count"], episode.decision_count)
        self.assertGreaterEqual(summary["mean_sequence_length"], 1.0)
        self.assertGreaterEqual(summary["max_sequence_length"], 1)

        advantages, returns = compute_gae_advantages(
            rewards=[1.0, 2.0],
            values=[0.5, 0.25],
            dones=[False, True],
            gamma=0.9,
            gae_lambda=0.95,
        )
        self.assertAlmostEqual(advantages[1], 1.75, places=6)
        self.assertAlmostEqual(returns[1], 2.0, places=6)
        self.assertAlmostEqual(advantages[0], 2.22125, places=6)
        self.assertAlmostEqual(returns[0], 2.72125, places=6)

    def test_checkpoint_guardrail_summary_rejects_zero_activity_collapse(self) -> None:
        baseline_summary = {
            "mean_irrigation_mm": 200.0,
            "mean_nitrogen_kg_ha": 100.0,
        }
        collapsed_summary = {
            "mean_irrigation_mm": 0.0,
            "mean_nitrogen_kg_ha": 0.0,
            "mean_yield_floor_attainment_pct": 54.0,
            "mean_yield_floor_gap_ratio": 0.46,
            "mean_reward_gain": -0.7,
            "mean_total_score_100": 42.0,
        }

        guardrail = build_checkpoint_guardrail_summary(
            collapsed_summary,
            baseline_summary,
            control_mode="joint",
            min_activity_ratio=0.05,
            min_yield_floor_attainment_pct=55.0,
            primary_metric="yield_floor_gap",
        )

        self.assertFalse(guardrail["eligible_for_best_checkpoint"])
        self.assertFalse(guardrail["meets_activity_floor"])
        self.assertFalse(guardrail["meets_yield_floor"])
        self.assertEqual(guardrail["activity_reference"]["min_enabled_activity_ratio"], 0.0)
        self.assertGreater(guardrail["guardrail_shortfall"], 0.0)

    def test_checkpoint_guardrail_summary_keeps_viable_mid_training_checkpoint(self) -> None:
        baseline_summary = {
            "mean_irrigation_mm": 200.0,
            "mean_nitrogen_kg_ha": 100.0,
        }
        candidate_summary = {
            "mean_irrigation_mm": 170.0,
            "mean_nitrogen_kg_ha": 60.0,
            "mean_yield_floor_attainment_pct": 58.8,
            "mean_yield_floor_gap_ratio": 0.412,
            "mean_reward_gain": 1.5,
            "mean_total_score_100": 61.0,
        }

        guardrail = build_checkpoint_guardrail_summary(
            candidate_summary,
            baseline_summary,
            control_mode="joint",
            min_activity_ratio=0.05,
            min_yield_floor_attainment_pct=55.0,
            primary_metric="yield_floor_gap",
        )

        self.assertTrue(guardrail["eligible_for_best_checkpoint"])
        self.assertTrue(guardrail["meets_activity_floor"])
        self.assertTrue(guardrail["meets_yield_floor"])
        self.assertAlmostEqual(guardrail["activity_reference"]["min_enabled_activity_ratio"], 0.6, places=6)
        self.assertEqual(guardrail["guardrail_shortfall"], 0.0)

    def test_compute_activity_ratio_handles_zero_baseline(self) -> None:
        self.assertEqual(compute_activity_ratio(0.0, 0.0), 1.0)
        self.assertTrue(math.isinf(compute_activity_ratio(5.0, 0.0)))

    @unittest.skipUnless(TORCH_AVAILABLE, "PyTorch is required for activity-regularizer tests.")
    def test_activity_regularizer_penalizes_near_zero_expected_activity(self) -> None:
        import torch

        gate_logits = torch.full((4, 2), -8.0, dtype=torch.float32)
        amount_alpha = torch.full((4, 2), 1.2, dtype=torch.float32)
        amount_beta = torch.full((4, 2), 3.8, dtype=torch.float32)
        amount_maxima = torch.full((4, 2), 40.0, dtype=torch.float32)

        penalty, metrics = _mean_activity_shortfall_penalty(
            gate_logits,
            amount_alpha,
            amount_beta,
            amount_maxima,
            control_mode="joint",
            regularizer={
                "enabled": True,
                "minimum_expected_irrigation_ratio": 0.08,
                "minimum_expected_nitrogen_ratio": 0.12,
                "irrigation_penalty_weight": 0.8,
                "nitrogen_penalty_weight": 1.6,
            },
        )

        self.assertGreater(float(penalty.item()), 0.0)
        self.assertGreater(metrics["irrigation_activity_shortfall"], 0.0)
        self.assertGreater(metrics["nitrogen_activity_shortfall"], 0.0)

    @unittest.skipUnless(TORCH_AVAILABLE, "PyTorch is required for activity-regularizer tests.")
    def test_activity_regularizer_drops_to_zero_for_healthy_expected_activity(self) -> None:
        import torch

        gate_logits = torch.full((4, 2), 8.0, dtype=torch.float32)
        amount_alpha = torch.full((4, 2), 4.5, dtype=torch.float32)
        amount_beta = torch.full((4, 2), 1.5, dtype=torch.float32)
        amount_maxima = torch.full((4, 2), 40.0, dtype=torch.float32)

        penalty, metrics = _mean_activity_shortfall_penalty(
            gate_logits,
            amount_alpha,
            amount_beta,
            amount_maxima,
            control_mode="joint",
            regularizer={
                "enabled": True,
                "minimum_expected_irrigation_ratio": 0.08,
                "minimum_expected_nitrogen_ratio": 0.12,
                "irrigation_penalty_weight": 0.8,
                "nitrogen_penalty_weight": 1.6,
            },
        )

        self.assertEqual(float(penalty.item()), 0.0)
        self.assertEqual(metrics["irrigation_activity_shortfall"], 0.0)
        self.assertEqual(metrics["nitrogen_activity_shortfall"], 0.0)

    @unittest.skipUnless(TORCH_AVAILABLE, "PyTorch is required for behavior-anchor tests.")
    def test_behavior_anchor_penalizes_drift_below_rollout_activity(self) -> None:
        import torch

        gate_logits = torch.full((4, 2), -6.0, dtype=torch.float32)
        amount_alpha = torch.full((4, 2), 1.2, dtype=torch.float32)
        amount_beta = torch.full((4, 2), 4.8, dtype=torch.float32)
        gate_actions = torch.ones((4, 2), dtype=torch.float32)
        amount_actions = torch.tensor(
            [[24.0, 20.0], [20.0, 18.0], [22.0, 16.0], [18.0, 14.0]],
            dtype=torch.float32,
        )
        amount_maxima = torch.full((4, 2), 40.0, dtype=torch.float32)

        penalty, metrics = _mean_behavior_anchor_penalty(
            gate_logits,
            amount_alpha,
            amount_beta,
            gate_actions,
            amount_actions,
            amount_maxima,
            control_mode="joint",
            anchor={
                "enabled": True,
                "retention_ratio": 0.9,
                "minimum_anchor_irrigation_ratio": 0.08,
                "minimum_anchor_nitrogen_ratio": 0.12,
                "irrigation_penalty_weight": 1.2,
                "nitrogen_penalty_weight": 2.4,
            },
        )

        self.assertGreater(float(penalty.item()), 0.0)
        self.assertGreater(metrics["irrigation_anchor_target_ratio"], 0.08)
        self.assertGreater(metrics["nitrogen_anchor_target_ratio"], 0.12)
        self.assertGreater(metrics["irrigation_anchor_shortfall"], 0.0)
        self.assertGreater(metrics["nitrogen_anchor_shortfall"], 0.0)

    @unittest.skipUnless(TORCH_AVAILABLE, "PyTorch is required for behavior-anchor tests.")
    def test_behavior_anchor_drops_to_zero_when_expected_activity_tracks_rollout(self) -> None:
        import torch

        gate_logits = torch.full((4, 2), 8.0, dtype=torch.float32)
        amount_alpha = torch.full((4, 2), 4.5, dtype=torch.float32)
        amount_beta = torch.full((4, 2), 1.5, dtype=torch.float32)
        gate_actions = torch.ones((4, 2), dtype=torch.float32)
        amount_actions = torch.full((4, 2), 28.0, dtype=torch.float32)
        amount_maxima = torch.full((4, 2), 40.0, dtype=torch.float32)

        penalty, metrics = _mean_behavior_anchor_penalty(
            gate_logits,
            amount_alpha,
            amount_beta,
            gate_actions,
            amount_actions,
            amount_maxima,
            control_mode="joint",
            anchor={
                "enabled": True,
                "retention_ratio": 0.9,
                "minimum_anchor_irrigation_ratio": 0.08,
                "minimum_anchor_nitrogen_ratio": 0.12,
                "irrigation_penalty_weight": 1.2,
                "nitrogen_penalty_weight": 2.4,
            },
        )

        self.assertEqual(float(penalty.item()), 0.0)
        self.assertEqual(metrics["irrigation_anchor_shortfall"], 0.0)
        self.assertEqual(metrics["nitrogen_anchor_shortfall"], 0.0)

    @unittest.skipUnless(TORCH_AVAILABLE, "PyTorch is required for policy-anchor tests.")
    def test_policy_anchor_penalizes_drift_from_rollout_actions(self) -> None:
        import torch

        gate_logits = torch.full((4, 2), -5.0, dtype=torch.float32)
        amount_alpha = torch.full((4, 2), 1.2, dtype=torch.float32)
        amount_beta = torch.full((4, 2), 4.8, dtype=torch.float32)
        gate_actions = torch.ones((4, 2), dtype=torch.float32)
        amount_actions = torch.tensor(
            [[24.0, 20.0], [20.0, 18.0], [22.0, 16.0], [18.0, 14.0]],
            dtype=torch.float32,
        )
        amount_maxima = torch.full((4, 2), 40.0, dtype=torch.float32)

        penalty, metrics = _mean_policy_anchor_penalty(
            gate_logits,
            amount_alpha,
            amount_beta,
            gate_actions,
            amount_actions,
            amount_maxima,
            control_mode="joint",
            anchor={
                "enabled": True,
                "gate_penalty_weight": 0.25,
                "irrigation_amount_penalty_weight": 0.8,
                "nitrogen_amount_penalty_weight": 1.2,
            },
            advantages=torch.tensor([1.0, 0.5, -0.5, -1.0], dtype=torch.float32),
        )

        self.assertGreater(float(penalty.item()), 0.0)
        self.assertGreater(metrics["gate_penalty"], 0.0)
        self.assertLess(metrics["gate_match_ratio"], 0.5)
        self.assertGreater(metrics["irrigation_amount_abs_error"], 0.0)
        self.assertGreater(metrics["nitrogen_amount_abs_error"], 0.0)
        self.assertGreater(metrics["positive_advantage_fraction"], 0.0)

    @unittest.skipUnless(TORCH_AVAILABLE, "PyTorch is required for policy-anchor tests.")
    def test_policy_anchor_drops_when_policy_matches_rollout_actions(self) -> None:
        import torch

        gate_logits = torch.full((4, 2), 8.0, dtype=torch.float32)
        amount_alpha = torch.full((4, 2), 7.0, dtype=torch.float32)
        amount_beta = torch.full((4, 2), 3.0, dtype=torch.float32)
        gate_actions = torch.ones((4, 2), dtype=torch.float32)
        amount_actions = torch.full((4, 2), 28.0, dtype=torch.float32)
        amount_maxima = torch.full((4, 2), 40.0, dtype=torch.float32)

        penalty, metrics = _mean_policy_anchor_penalty(
            gate_logits,
            amount_alpha,
            amount_beta,
            gate_actions,
            amount_actions,
            amount_maxima,
            control_mode="joint",
            anchor={
                "enabled": True,
                "gate_penalty_weight": 0.25,
                "irrigation_amount_penalty_weight": 0.8,
                "nitrogen_amount_penalty_weight": 1.2,
            },
            advantages=torch.tensor([1.0, 0.5, -0.5, -1.0], dtype=torch.float32),
        )

        self.assertLess(float(penalty.item()), 0.02)
        self.assertLess(metrics["gate_penalty"], 0.01)
        self.assertGreater(metrics["gate_match_ratio"], 0.99)
        self.assertEqual(metrics["irrigation_amount_abs_error"], 0.0)
        self.assertEqual(metrics["nitrogen_amount_abs_error"], 0.0)

    @unittest.skipUnless(TORCH_AVAILABLE, "PyTorch is required for policy-anchor tests.")
    def test_policy_anchor_upweights_positive_advantage_samples(self) -> None:
        import torch

        gate_logits = torch.full((4, 2), -4.0, dtype=torch.float32)
        amount_alpha = torch.full((4, 2), 1.5, dtype=torch.float32)
        amount_beta = torch.full((4, 2), 4.5, dtype=torch.float32)
        gate_actions = torch.ones((4, 2), dtype=torch.float32)
        amount_actions = torch.full((4, 2), 24.0, dtype=torch.float32)
        amount_maxima = torch.full((4, 2), 40.0, dtype=torch.float32)
        advantages = torch.tensor([2.0, 1.0, -0.25, -0.5], dtype=torch.float32)

        _, metrics = _mean_policy_anchor_penalty(
            gate_logits,
            amount_alpha,
            amount_beta,
            gate_actions,
            amount_actions,
            amount_maxima,
            control_mode="joint",
            anchor={
                "enabled": True,
                "gate_penalty_weight": 0.25,
                "irrigation_amount_penalty_weight": 0.8,
                "nitrogen_amount_penalty_weight": 1.2,
                "minimum_sample_weight": 0.2,
                "negative_advantage_scale": 0.35,
                "positive_advantage_scale": 0.8,
            },
            advantages=advantages,
        )

        self.assertAlmostEqual(metrics["positive_advantage_fraction"], 0.5, places=6)
        self.assertGreater(metrics["mean_positive_advantage_anchor_weight"], metrics["mean_negative_advantage_anchor_weight"])
        self.assertLess(metrics["mean_negative_advantage_anchor_weight"], 0.2)
        self.assertLessEqual(metrics["gate_match_ratio"], 1.0)

    @unittest.skipUnless(TORCH_AVAILABLE, "PyTorch is required for advantage-activity-anchor tests.")
    def test_advantage_activity_anchor_penalizes_drift_below_positive_advantage_activity(self) -> None:
        import torch

        gate_logits = torch.full((4, 2), -6.0, dtype=torch.float32)
        amount_alpha = torch.full((4, 2), 1.2, dtype=torch.float32)
        amount_beta = torch.full((4, 2), 4.8, dtype=torch.float32)
        gate_actions = torch.tensor(
            [[1.0, 1.0], [1.0, 1.0], [0.0, 0.0], [0.0, 0.0]],
            dtype=torch.float32,
        )
        amount_actions = torch.tensor(
            [[24.0, 20.0], [20.0, 18.0], [0.0, 0.0], [0.0, 0.0]],
            dtype=torch.float32,
        )
        amount_maxima = torch.full((4, 2), 40.0, dtype=torch.float32)
        advantages = torch.tensor([1.2, 0.8, -0.5, -1.0], dtype=torch.float32)

        penalty, metrics = _mean_advantage_activity_anchor_penalty(
            gate_logits,
            amount_alpha,
            amount_beta,
            gate_actions,
            amount_actions,
            amount_maxima,
            control_mode="joint",
            anchor={
                "enabled": True,
                "retention_ratio": 0.92,
                "minimum_anchor_irrigation_ratio": 0.08,
                "minimum_anchor_nitrogen_ratio": 0.12,
                "irrigation_penalty_weight": 0.8,
                "nitrogen_penalty_weight": 1.6,
            },
            advantages=advantages,
        )

        self.assertGreater(float(penalty.item()), 0.0)
        self.assertAlmostEqual(metrics["positive_advantage_fraction"], 0.5, places=6)
        self.assertGreater(metrics["irrigation_positive_anchor_target_ratio"], 0.08)
        self.assertGreater(metrics["nitrogen_positive_anchor_target_ratio"], 0.12)
        self.assertGreater(metrics["irrigation_positive_anchor_shortfall"], 0.0)
        self.assertGreater(metrics["nitrogen_positive_anchor_shortfall"], 0.0)

    @unittest.skipUnless(TORCH_AVAILABLE, "PyTorch is required for advantage-activity-anchor tests.")
    def test_advantage_activity_anchor_drops_when_positive_advantage_activity_is_retained(self) -> None:
        import torch

        gate_logits = torch.full((4, 2), 8.0, dtype=torch.float32)
        amount_alpha = torch.full((4, 2), 4.5, dtype=torch.float32)
        amount_beta = torch.full((4, 2), 1.5, dtype=torch.float32)
        gate_actions = torch.tensor(
            [[1.0, 1.0], [1.0, 1.0], [0.0, 0.0], [0.0, 0.0]],
            dtype=torch.float32,
        )
        amount_actions = torch.full((4, 2), 28.0, dtype=torch.float32)
        amount_maxima = torch.full((4, 2), 40.0, dtype=torch.float32)
        advantages = torch.tensor([1.0, 0.5, -0.25, -0.5], dtype=torch.float32)

        penalty, metrics = _mean_advantage_activity_anchor_penalty(
            gate_logits,
            amount_alpha,
            amount_beta,
            gate_actions,
            amount_actions,
            amount_maxima,
            control_mode="joint",
            anchor={
                "enabled": True,
                "retention_ratio": 0.9,
                "minimum_anchor_irrigation_ratio": 0.08,
                "minimum_anchor_nitrogen_ratio": 0.12,
                "irrigation_penalty_weight": 0.8,
                "nitrogen_penalty_weight": 1.6,
            },
            advantages=advantages,
        )

        self.assertEqual(float(penalty.item()), 0.0)
        self.assertEqual(metrics["irrigation_positive_anchor_shortfall"], 0.0)
        self.assertEqual(metrics["nitrogen_positive_anchor_shortfall"], 0.0)

    @unittest.skipUnless(TORCH_AVAILABLE, "PyTorch is required for update-admission tests.")
    def test_update_admission_rejects_low_activity_rollout_minibatch(self) -> None:
        import torch

        gate_actions = torch.zeros((4, 2), dtype=torch.float32)
        amount_actions = torch.zeros((4, 2), dtype=torch.float32)
        amount_maxima = torch.full((4, 2), 40.0, dtype=torch.float32)

        metrics = _evaluate_rollout_activity_admission(
            gate_actions,
            amount_actions,
            amount_maxima,
            control_mode="joint",
            admission={
                "enabled": True,
                "minimum_irrigation_ratio": 0.05,
                "minimum_nitrogen_ratio": 0.08,
                "irrigation_penalty_weight": 1.0,
                "nitrogen_penalty_weight": 2.0,
            },
        )

        self.assertFalse(metrics["admitted"])
        self.assertGreater(metrics["penalty"], 0.0)
        self.assertEqual(metrics["minimum_enabled_activity_ratio"], 0.0)

    @unittest.skipUnless(TORCH_AVAILABLE, "PyTorch is required for update-admission tests.")
    def test_update_admission_accepts_healthy_rollout_minibatch(self) -> None:
        import torch

        gate_actions = torch.ones((4, 2), dtype=torch.float32)
        amount_actions = torch.full((4, 2), 20.0, dtype=torch.float32)
        amount_maxima = torch.full((4, 2), 40.0, dtype=torch.float32)

        metrics = _evaluate_rollout_activity_admission(
            gate_actions,
            amount_actions,
            amount_maxima,
            control_mode="joint",
            admission={
                "enabled": True,
                "minimum_irrigation_ratio": 0.05,
                "minimum_nitrogen_ratio": 0.08,
                "irrigation_penalty_weight": 1.0,
                "nitrogen_penalty_weight": 2.0,
            },
        )

        self.assertTrue(metrics["admitted"])
        self.assertEqual(metrics["penalty"], 0.0)

    @unittest.skipUnless(TORCH_AVAILABLE, "PyTorch is required for update-admission tests.")
    def test_update_admission_rejects_greedy_gate_collapse_even_when_expected_activity_looks_healthy(self) -> None:
        import torch

        gate_actions = torch.ones((4, 2), dtype=torch.float32)
        amount_actions = torch.full((4, 2), 20.0, dtype=torch.float32)
        amount_maxima = torch.full((4, 2), 40.0, dtype=torch.float32)
        gate_logits = torch.full((4, 2), -0.04, dtype=torch.float32)
        amount_alpha = torch.full((4, 2), 1.0, dtype=torch.float32)
        amount_beta = torch.full((4, 2), 1.0, dtype=torch.float32)

        metrics = _evaluate_rollout_activity_admission(
            gate_actions,
            amount_actions,
            amount_maxima,
            control_mode="joint",
            admission={
                "enabled": True,
                "minimum_irrigation_ratio": 0.05,
                "minimum_nitrogen_ratio": 0.08,
                "irrigation_penalty_weight": 1.0,
                "nitrogen_penalty_weight": 2.0,
                "enforce_expected_activity": True,
                "expected_activity_retention_ratio": 0.9,
                "minimum_expected_irrigation_ratio": 0.05,
                "minimum_expected_nitrogen_ratio": 0.08,
                "expected_irrigation_penalty_weight": 1.0,
                "expected_nitrogen_penalty_weight": 2.0,
                "enforce_greedy_activity": True,
                "greedy_activity_retention_ratio": 0.9,
                "minimum_greedy_irrigation_ratio": 0.05,
                "minimum_greedy_nitrogen_ratio": 0.08,
                "greedy_irrigation_penalty_weight": 1.0,
                "greedy_nitrogen_penalty_weight": 2.0,
            },
            gate_logits=gate_logits,
            amount_alpha=amount_alpha,
            amount_beta=amount_beta,
        )

        self.assertGreater(metrics["irrigation_expected_activity_ratio"], 0.24)
        self.assertGreater(metrics["nitrogen_expected_activity_ratio"], 0.24)
        self.assertEqual(metrics["irrigation_greedy_activity_ratio"], 0.0)
        self.assertEqual(metrics["nitrogen_greedy_activity_ratio"], 0.0)
        self.assertFalse(metrics["admitted"])
        self.assertGreater(metrics["penalty"], 0.0)

    @unittest.skipUnless(TORCH_AVAILABLE, "PyTorch is required for update-admission tests.")
    def test_update_admission_admits_small_shortfall_under_hard_threshold(self) -> None:
        import torch

        gate_actions = torch.ones((4, 2), dtype=torch.float32)
        amount_actions = torch.full((4, 2), 20.0, dtype=torch.float32)
        amount_maxima = torch.full((4, 2), 40.0, dtype=torch.float32)
        gate_logits = torch.full((4, 2), 0.0, dtype=torch.float32)
        amount_alpha = torch.full((4, 2), 8.5, dtype=torch.float32)
        amount_beta = torch.ones((4, 2), dtype=torch.float32)

        metrics = _evaluate_rollout_activity_admission(
            gate_actions,
            amount_actions,
            amount_maxima,
            control_mode="joint",
            admission={
                "enabled": True,
                "minimum_irrigation_ratio": 0.05,
                "minimum_nitrogen_ratio": 0.08,
                "irrigation_penalty_weight": 1.0,
                "nitrogen_penalty_weight": 2.0,
                "soft_penalty_weight": 1.0,
                "hard_rejection_threshold": 0.02,
                "hard_rollout_penalty_weight_scale": 1.0,
                "hard_expected_penalty_weight_scale": 0.0,
                "hard_greedy_penalty_weight_scale": 1.0,
                "enforce_expected_activity": True,
                "expected_activity_retention_ratio": 0.9,
                "minimum_expected_irrigation_ratio": 0.05,
                "minimum_expected_nitrogen_ratio": 0.08,
                "expected_irrigation_penalty_weight": 1.0,
                "expected_nitrogen_penalty_weight": 2.0,
                "enforce_greedy_activity": True,
                "greedy_activity_retention_ratio": 0.9,
                "minimum_greedy_irrigation_ratio": 0.05,
                "minimum_greedy_nitrogen_ratio": 0.08,
                "greedy_irrigation_penalty_weight": 1.0,
                "greedy_nitrogen_penalty_weight": 2.0,
            },
            gate_logits=gate_logits,
            amount_alpha=amount_alpha,
            amount_beta=amount_beta,
        )

        self.assertTrue(metrics["admitted"])
        self.assertGreater(metrics["penalty"], 0.0)
        self.assertLess(metrics["hard_shortfall"], metrics["hard_rejection_threshold"])
        self.assertEqual(metrics["soft_penalty_weight"], 1.0)

    @unittest.skipUnless(TORCH_AVAILABLE, "PyTorch is required for update-admission tests.")
    def test_update_admission_keeps_expected_only_shortfall_soft_when_greedy_path_is_healthy(self) -> None:
        import torch

        gate_actions = torch.ones((4, 2), dtype=torch.float32)
        amount_actions = torch.full((4, 2), 20.0, dtype=torch.float32)
        amount_maxima = torch.full((4, 2), 40.0, dtype=torch.float32)
        gate_logits = torch.full((4, 2), 0.0, dtype=torch.float32)
        amount_alpha = torch.tensor([[11.0, 5.0]] * 4, dtype=torch.float32)
        amount_beta = torch.ones((4, 2), dtype=torch.float32)

        metrics = _evaluate_rollout_activity_admission(
            gate_actions,
            amount_actions,
            amount_maxima,
            control_mode="joint",
            admission={
                "enabled": True,
                "minimum_irrigation_ratio": 0.05,
                "minimum_nitrogen_ratio": 0.08,
                "irrigation_penalty_weight": 1.0,
                "nitrogen_penalty_weight": 2.0,
                "soft_penalty_weight": 1.0,
                "hard_rejection_threshold": 0.02,
                "hard_rollout_penalty_weight_scale": 1.0,
                "hard_expected_penalty_weight_scale": 0.0,
                "hard_greedy_penalty_weight_scale": 1.0,
                "enforce_expected_activity": True,
                "expected_activity_retention_ratio": 0.9,
                "minimum_expected_irrigation_ratio": 0.05,
                "minimum_expected_nitrogen_ratio": 0.08,
                "expected_irrigation_penalty_weight": 1.0,
                "expected_nitrogen_penalty_weight": 2.0,
                "enforce_greedy_activity": True,
                "greedy_activity_retention_ratio": 0.9,
                "minimum_greedy_irrigation_ratio": 0.05,
                "minimum_greedy_nitrogen_ratio": 0.08,
                "greedy_irrigation_penalty_weight": 1.0,
                "greedy_nitrogen_penalty_weight": 2.0,
            },
            gate_logits=gate_logits,
            amount_alpha=amount_alpha,
            amount_beta=amount_beta,
        )

        self.assertTrue(metrics["admitted"])
        self.assertGreater(metrics["nitrogen_expected_activity_shortfall"], 0.02)
        self.assertEqual(metrics["nitrogen_greedy_activity_shortfall"], 0.0)
        self.assertGreater(metrics["penalty"], metrics["hard_rejection_threshold"])
        self.assertEqual(metrics["hard_shortfall"], 0.0)

    @unittest.skipUnless(TORCH_AVAILABLE, "PyTorch is required for update-admission tests.")
    def test_update_admission_can_keep_greedy_shortfall_hard_only_when_soft_greedy_scale_is_zero(self) -> None:
        import torch

        gate_actions = torch.ones((4, 2), dtype=torch.float32)
        amount_actions = torch.full((4, 2), 20.0, dtype=torch.float32)
        amount_maxima = torch.full((4, 2), 40.0, dtype=torch.float32)
        gate_logits = torch.full((4, 2), -0.04, dtype=torch.float32)
        amount_alpha = torch.full((4, 2), 1.0, dtype=torch.float32)
        amount_beta = torch.full((4, 2), 1.0, dtype=torch.float32)

        metrics = _evaluate_rollout_activity_admission(
            gate_actions,
            amount_actions,
            amount_maxima,
            control_mode="joint",
            admission={
                "enabled": True,
                "minimum_irrigation_ratio": 0.05,
                "minimum_nitrogen_ratio": 0.08,
                "irrigation_penalty_weight": 1.0,
                "nitrogen_penalty_weight": 2.0,
                "soft_penalty_weight": 1.0,
                "soft_greedy_penalty_weight_scale": 0.0,
                "hard_rejection_threshold": 0.02,
                "hard_rollout_penalty_weight_scale": 1.0,
                "hard_expected_penalty_weight_scale": 0.0,
                "hard_greedy_penalty_weight_scale": 1.0,
                "enforce_expected_activity": False,
                "expected_activity_retention_ratio": 0.9,
                "minimum_expected_irrigation_ratio": 0.05,
                "minimum_expected_nitrogen_ratio": 0.08,
                "expected_irrigation_penalty_weight": 1.0,
                "expected_nitrogen_penalty_weight": 2.0,
                "enforce_greedy_activity": True,
                "greedy_activity_retention_ratio": 0.9,
                "minimum_greedy_irrigation_ratio": 0.05,
                "minimum_greedy_nitrogen_ratio": 0.08,
                "greedy_irrigation_penalty_weight": 1.0,
                "greedy_nitrogen_penalty_weight": 2.0,
            },
            gate_logits=gate_logits,
            amount_alpha=amount_alpha,
            amount_beta=amount_beta,
        )

        self.assertFalse(metrics["admitted"])
        self.assertGreater(metrics["nitrogen_greedy_activity_shortfall"], 0.02)
        self.assertEqual(metrics["nitrogen_expected_activity_shortfall"], 0.0)
        self.assertEqual(metrics["soft_greedy_penalty_weight_scale"], 0.0)
        self.assertEqual(metrics["penalty"], 0.0)
        self.assertGreater(metrics["hard_shortfall"], metrics["hard_rejection_threshold"])

    @unittest.skipUnless(TORCH_AVAILABLE, "PyTorch is required for auxiliary-budget tests.")
    def test_auxiliary_penalty_budget_caps_combined_soft_losses(self) -> None:
        import torch

        scaled_penalties, metrics = _apply_auxiliary_penalty_budget(
            torch.tensor(0.1, dtype=torch.float32),
            torch.tensor(0.2, dtype=torch.float32),
            torch.tensor(0.05, dtype=torch.float32),
            {
                "activity_regularizer": torch.tensor(0.3, dtype=torch.float32),
                "behavior_anchor": torch.tensor(0.2, dtype=torch.float32),
                "policy_anchor": torch.tensor(0.1, dtype=torch.float32),
            },
            value_coef=0.5,
            entropy_coef=0.01,
            budget={
                "enabled": True,
                "max_auxiliary_to_core_ratio": 0.5,
                "minimum_core_loss": 0.0,
                "include_entropy_magnitude": True,
            },
        )

        self.assertTrue(metrics["enabled"])
        self.assertLess(metrics["penalty_scale"], 1.0)
        self.assertAlmostEqual(metrics["core_loss_magnitude"], 0.2005, places=6)
        self.assertAlmostEqual(metrics["max_allowed_penalty"], 0.10025, places=6)
        self.assertAlmostEqual(metrics["raw_penalty"], 0.6, places=6)
        self.assertAlmostEqual(metrics["applied_penalty"], 0.10025, places=6)
        self.assertAlmostEqual(float(scaled_penalties["activity_regularizer"].item()), 0.050125, places=6)

    @unittest.skipUnless(TORCH_AVAILABLE, "PyTorch is required for Transformer PPO tests.")
    def test_transformer_actor_critic_accepts_padded_sequences(self) -> None:
        import torch

        episode = rollout_stepwise_episode(self.scenario, select_highest_legal_action)
        sequences = [transition.sequence_features for transition in episode.transitions[:2]]
        batch_sequences, padding_mask = collate_sequence_features(sequences, device="cpu")
        model = StepwiseTransformerActorCritic(hidden_dim=32, num_heads=4, num_layers=1, max_sequence_length=64)
        logits, values = model(batch_sequences, padding_mask=padding_mask)
        self.assertEqual(tuple(logits.shape), (len(sequences), 7))
        self.assertEqual(tuple(values.shape), (len(sequences),))
        self.assertTrue(torch.isfinite(logits).all().item())
        self.assertTrue(torch.isfinite(values).all().item())

    @unittest.skipUnless(TORCH_AVAILABLE, "PyTorch is required for Transformer PPO tests.")
    def test_transformer_rollout_batch_and_update_smoke(self) -> None:
        import torch

        model = StepwiseTransformerActorCritic(hidden_dim=32, num_heads=4, num_layers=1, max_sequence_length=64)
        optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
        batch, summary, episodes = collect_ppo_rollout_batch(
            model,
            [self.scenario],
            device="cpu",
            episode_count=2,
            seed=20260609,
        )
        self.assertEqual(len(episodes), 2)
        self.assertEqual(batch.size, summary["transition_count"])
        update = run_ppo_update(
            model,
            optimizer,
            batch,
            update_epochs=1,
            minibatch_size=min(8, batch.size),
            max_grad_norm=0.5,
        )
        self.assertIn("policy_loss", update)
        self.assertIn("explained_variance", update)

    @unittest.skipUnless(TORCH_AVAILABLE, "PyTorch is required for gated continuous PPO tests.")
    def test_gated_continuous_transformer_rollout_batch_and_update_smoke(self) -> None:
        import torch

        model = StepwiseGatedContinuousTransformerActorCritic(
            hidden_dim=32,
            control_mode="joint",
            num_heads=4,
            num_layers=1,
            max_sequence_length=64,
        )
        optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
        batch, summary, episodes = collect_ppo_rollout_batch(
            model,
            [self.scenario],
            device="cpu",
            episode_count=2,
            seed=20260611,
        )
        self.assertEqual(len(episodes), 2)
        self.assertEqual(summary["action_mode"], "continuous")
        self.assertEqual(batch.action_mode, "continuous")
        self.assertIsNotNone(batch.gate_actions)
        self.assertIsNotNone(batch.amount_actions)
        self.assertIsNotNone(batch.amount_maxima)
        self.assertEqual(batch.size, summary["transition_count"])
        update = run_ppo_update(
            model,
            optimizer,
            batch,
            update_epochs=1,
            minibatch_size=min(8, batch.size),
            max_grad_norm=0.5,
        )
        self.assertIn("policy_loss", update)
        self.assertIn("explained_variance", update)
        self.assertIn("activity_regularizer_penalty", update)
        self.assertIn("mean_expected_nitrogen_activity_ratio", update)
        self.assertIn("behavior_anchor_penalty", update)
        self.assertIn("mean_nitrogen_anchor_target_ratio", update)
        self.assertIn("policy_anchor_penalty", update)
        self.assertIn("mean_policy_anchor_gate_match_ratio", update)
        self.assertIn("mean_policy_anchor_positive_advantage_weight", update)
        self.assertIn("advantage_activity_anchor_penalty", update)
        self.assertIn("mean_advantage_activity_positive_fraction", update)
        self.assertIn("update_admission_penalty", update)
        self.assertIn("admitted_update_count", update)
        self.assertIn("rejected_update_count", update)
        self.assertIn("mean_update_admission_shortfall", update)
        self.assertIn("auxiliary_penalty_budget_applied_penalty", update)
        self.assertIn("mean_auxiliary_penalty_budget_scale", update)

    @unittest.skipUnless(TORCH_AVAILABLE, "PyTorch is required for PPO KL-stop tests.")
    def test_ppo_update_reports_kl_early_stop_metadata(self) -> None:
        import torch

        model = StepwiseGatedContinuousTransformerActorCritic(
            hidden_dim=32,
            control_mode="joint",
            num_heads=4,
            num_layers=1,
            max_sequence_length=64,
        )
        optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
        batch, _, _ = collect_ppo_rollout_batch(
            model,
            [self.scenario],
            device="cpu",
            episode_count=2,
            seed=20260617,
        )
        update = run_ppo_update(
            model,
            optimizer,
            batch,
            update_epochs=2,
            minibatch_size=min(8, batch.size),
            max_grad_norm=0.5,
            target_kl=0.0,
        )
        self.assertTrue(update["early_stopped_on_kl"])
        self.assertEqual(update["target_kl"], 0.0)


if __name__ == "__main__":
    unittest.main()
