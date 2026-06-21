from __future__ import annotations

import copy
import unittest
from unittest.mock import patch

from transdssat.domain import CropAction, CropOutcome, CropState, Trajectory, TrajectoryStep
from transdssat.environments import StepwiseDecisionEnvironment
from transdssat.environments.adapters import SeasonEvaluationResult
from transdssat.rewarding import anti_collapse_preferences, budget_penalty, reward_from_outcome, RewardWeights, resource_settlement_preferences
from transdssat.scenarios import (
    build_quzhou_scenarios,
    build_cultivar_context,
    clone_objective_context_with_reward_contract,
    objective_context_for_id,
    scenario_yield_floor_reference,
)
from transdssat.stepwise_policy import build_heuristic_stepwise_policy
from transdssat.stepwise_ppo import rollout_stepwise_episode, select_highest_legal_action
from transdssat.testset import generate_general_random_test_set


class StepwiseEnvironmentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.scenario = build_quzhou_scenarios(
            target_count=1,
            engines=("dssat_proxy",),
            crops_filter=("maize",),
            sampling_mode="random",
            seed=20260526,
        )[0]

    def test_general_random_record_exports_crop_and_action_contexts(self) -> None:
        record = generate_general_random_test_set(
            train_count=1,
            val_count=0,
            test_count=0,
            engines=("dssat_proxy",),
            crops_filter=("maize",),
            seed=20260526,
        )[0]
        payload = record.to_dict()
        self.assertEqual(payload["cultivar_id"], "denghai605")
        self.assertEqual(payload["crop_context"]["cultivar"]["cultivar_name"], "登海605")
        self.assertEqual(payload["crop_context"]["cultivar"]["parameter_names"], ["P1", "P2", "P5", "G2", "G3", "PHINT"])
        self.assertEqual(payload["crop_context"]["cultivar"]["parameter_vector"], [340.9, 1.61, 700.0, 600.0, 10.5, 60.0])
        self.assertEqual(
            payload["crop_context"]["cultivar"]["parameter_description"],
            "Calibrated DSSAT maize genetic parameters ordered as P1, P2, P5, G2, G3, PHINT.",
        )
        self.assertEqual(payload["state_interface_contract"]["version"], "v2026-06-admission-draft")
        self.assertIn("cultivar_id", payload["state_interface_contract"]["stable_core_fields"])
        self.assertIn("soil_moisture", payload["state_interface_contract"]["pending_agronomy_fields"])
        self.assertIn("water_stress", payload["state_interface_contract"]["simulator_internal_fields"])
        self.assertEqual(
            payload["objective_context"]["budget_constraints"]["irrigation_budget_mm"]["semantic_role"],
            "hard_constraint",
        )
        self.assertEqual(
            payload["objective_context"]["soft_preferences"]["semantic_role"],
            "objective_conditioning",
        )
        self.assertIn(
            "total_nitrogen_leached_kg_ha",
            payload["objective_context"]["report_metrics"],
        )
        self.assertTrue(
            any(
                spec["metric_id"] == "total_drainage_mm" and spec["proxy_status"] == "conservative_approximation"
                for spec in payload["objective_context"]["environmental_metric_specs"]
            )
        )
        self.assertEqual(payload["continuous_action_space"]["action_space_id"], "v2_joint_continuous")
        self.assertEqual(
            [item["name"] for item in payload["continuous_action_space"]["dimensions"]],
            ["irrigation_mm", "nitrogen_kg_ha"],
        )
        self.assertEqual(payload["discrete_action_table"]["action_table_id"], "deprecated_v1_joint_discrete")
        self.assertEqual(
            [item["action_id"] for item in payload["discrete_action_table"]["actions"]],
            [0, 1, 2, 3, 4, 5, 6],
        )
        self.assertIn("budget_limit", payload["action_constraint_rules"]["notes"])
        self.assertNotIn("water_stress", payload["decision_context"]["partial_observation_fields"])

    def test_rice_cultivar_context_is_calibrated(self) -> None:
        context = build_cultivar_context("rice", "IB2002", site_name="wuhu")

        self.assertEqual(context.crop_name, "rice")
        self.assertEqual(context.crop_type, "水稻")
        self.assertEqual(context.cultivar.cultivar_id, "meixiangzhan2")
        self.assertEqual(context.cultivar.cultivar_name, "美香占2号")
        self.assertEqual(context.cultivar.dssat_cultivar_code, "IB2002")
        self.assertEqual(context.cultivar.dssat_genotype_file, "RICER048.CUL")
        self.assertEqual(
            context.cultivar.parameter_names,
            ["P1", "P2R", "P5", "P2O", "G1", "G2", "G3", "PHINT", "THOT", "TCLDP", "TCLDF"],
        )
        self.assertEqual(len(context.cultivar.parameter_vector), 11)

    def test_nitrogen_gap_constraints_block_followup_actions(self) -> None:
        scenario = copy.deepcopy(self.scenario)
        scenario.soil_profile.initial_root_zone_water_mm = scenario.soil_profile.field_capacity_mm - 30.0
        for day in scenario.weather[:6]:
            day.precipitation_mm = 0.0

        env = StepwiseDecisionEnvironment(scenario)
        observation = env.reset()
        self.assertEqual(observation.state_interface_contract["version"], "v2026-06-admission-draft")
        self.assertIn("remaining_irrigation_mm", observation.state_interface_contract["stable_core_fields"])
        self.assertTrue(observation.action_constraints.nitrogen.allowed)
        self.assertIn(6, observation.discrete_action_mask.legal_action_ids)
        observation, reward, done, info = env.step_discrete(6)
        self.assertGreater(reward, -1e9)
        self.assertFalse(done)
        self.assertEqual(info["discrete_action_id"], 6)
        self.assertFalse(observation.action_constraints.nitrogen.allowed)
        self.assertIn("minimum_gap_active", observation.action_constraints.nitrogen.blocked_reasons)
        self.assertNotIn(4, observation.discrete_action_mask.legal_action_ids)
        self.assertNotIn(5, observation.discrete_action_mask.legal_action_ids)
        self.assertNotIn(6, observation.discrete_action_mask.legal_action_ids)
        self.assertGreaterEqual(observation.action_constraints.irrigation.max_value, 0.0)
        self.assertLess(info["remaining_nitrogen_kg_ha"], self.scenario.nitrogen_budget_kg_ha)

    def test_proxy_rollout_reaches_terminal_state(self) -> None:
        env = StepwiseDecisionEnvironment(self.scenario)
        observation = env.reset()
        steps = 0
        while not observation.done:
            observation, _, done, _ = env.step({"irrigation_mm": 0.0, "nitrogen_kg_ha": 0.0})
            steps += 1
            if done:
                break
        outcome = env.final_outcome()
        self.assertGreater(steps, 0)
        self.assertTrue(observation.done)
        self.assertGreater(outcome.yield_kg_ha, 0.0)

    def test_official_engine_uses_stepwise_replay_backend(self) -> None:
        scenario = copy.deepcopy(self.scenario)
        scenario.engine_name = "dssat_official"

        def fake_evaluate_policy(_, scenario_arg, policy, weights=None):  # noqa: ANN001
            del weights
            states = [
                CropState(
                    day_index=day_index,
                    stage="vegetative",
                    stage_index=1,
                    soil_moisture=0.5,
                    root_zone_water_mm=180.0 + day_index,
                    soil_nitrogen_kg_ha=120.0 - day_index,
                    canopy_cover=min(0.95, 0.1 + 0.05 * day_index),
                    biomass_kg_ha=100.0 + 10.0 * day_index,
                    water_stress=0.1,
                    nitrogen_stress=0.1,
                    tmean_c=22.0,
                    precipitation_mm=0.0,
                    et0_mm=4.0,
                    radiation_mj_m2=18.0,
                )
                for day_index in range(8)
            ]
            steps = [
                TrajectoryStep(
                    state=states[index],
                    action=policy.action_map().get(states[index].day_index, CropAction()),
                    reward=1.0,
                    next_state=states[index + 1],
                    done=index == len(states) - 2,
                    info={"engine_name": "dssat_official"},
                )
                for index in range(len(states) - 1)
            ]
            reward = round(policy.total_irrigation_mm + policy.total_nitrogen_kg_ha * 0.1, 6)
            outcome = CropOutcome(
                yield_kg_ha=7000.0,
                biomass_kg_ha=states[-1].biomass_kg_ha,
                total_irrigation_mm=policy.total_irrigation_mm,
                total_nitrogen_kg_ha=policy.total_nitrogen_kg_ha,
                water_use_efficiency=0.0,
                nitrogen_use_efficiency=0.0,
                cumulative_reward=reward,
                environmental_metrics={"operation_count": float(len(policy.actions))},
            )
            return SeasonEvaluationResult(
                trajectory=Trajectory(
                    scenario_id=scenario_arg.scenario_id,
                    engine_name="dssat_official",
                    crop_name=scenario_arg.crop_spec.crop_name,
                    weather_regime=scenario_arg.weather_regime,
                    management_mode=scenario_arg.management_mode,
                    steps=steps,
                    outcome=outcome,
                    policy=policy.to_dict(),
                ),
                run_dir="/tmp/fake-dssat-run",
                reward=reward,
            )

        with patch("transdssat.environments.stepwise.OfficialDSSATEnvironment.evaluate_policy", new=fake_evaluate_policy):
            env = StepwiseDecisionEnvironment(scenario)
            observation = env.reset()
            self.assertEqual(observation.state.day_index, 0)
            next_observation, reward, done, info = env.step({"irrigation_mm": 10.0, "nitrogen_kg_ha": 20.0})
            self.assertEqual(reward, 12.0)
            self.assertFalse(done)
            self.assertEqual(next_observation.state.day_index, scenario.decision_context.decision_interval_days)
            self.assertEqual(info["daily_trace"][0]["engine_info"]["engine_name"], "dssat_official")
            self.assertEqual(env.final_outcome().cumulative_reward, 12.0)

    def test_budget_penalty_treats_budget_as_upper_bound(self) -> None:
        weights = RewardWeights(contract_id="reward_v2")
        self.assertEqual(
            budget_penalty(120.0, 140.0, 150.0, 170.0, weights),
            0.0,
        )
        self.assertGreater(
            budget_penalty(180.0, 190.0, 150.0, 170.0, weights),
            0.0,
        )

    def test_objective_context_changes_reward_but_not_proxy_dynamics(self) -> None:
        profit_scenario = copy.deepcopy(self.scenario)
        profit_scenario.objective_context = objective_context_for_id("profit")
        water_saving_scenario = copy.deepcopy(self.scenario)
        water_saving_scenario.objective_context = objective_context_for_id("water_saving")

        profit_episode = rollout_stepwise_episode(
            profit_scenario,
            select_highest_legal_action,
            policy_id="objective-profit",
        )
        water_episode = rollout_stepwise_episode(
            water_saving_scenario,
            select_highest_legal_action,
            policy_id="objective-water-saving",
        )

        self.assertAlmostEqual(
            profit_episode.final_outcome.total_irrigation_mm,
            water_episode.final_outcome.total_irrigation_mm,
            places=6,
        )
        self.assertAlmostEqual(
            profit_episode.final_outcome.environmental_metrics["total_drainage_mm"],
            water_episode.final_outcome.environmental_metrics["total_drainage_mm"],
            places=6,
        )
        self.assertNotEqual(
            profit_episode.final_outcome.cumulative_reward,
            water_episode.final_outcome.cumulative_reward,
        )
        self.assertIn("total_nitrogen_leached_kg_ha", profit_episode.final_outcome.environmental_metrics)
        self.assertIn("terminal_soil_nitrogen_kg_ha", water_episode.final_outcome.environmental_metrics)

    def test_heuristic_v2_keeps_illegal_irrigation_budget_as_pending_carryover(self) -> None:
        scenario = copy.deepcopy(self.scenario)
        scenario.soil_profile.initial_root_zone_water_mm = scenario.soil_profile.field_capacity_mm + 15.0
        policy = build_heuristic_stepwise_policy(scenario)
        env = StepwiseDecisionEnvironment(scenario)
        observation = env.reset()

        action = policy.decide(observation)

        self.assertEqual(policy.summary().policy_kind, "reactive_heuristic_stepwise_policy")
        self.assertEqual(action.irrigation_mm, 0.0)
        self.assertGreater(getattr(policy, "pending_irrigation_mm", 0.0), 0.0)

    def test_reward_contract_switch_changes_reward_but_not_proxy_dynamics(self) -> None:
        reward_v1_scenario = copy.deepcopy(self.scenario)
        reward_v1_scenario.objective_context = clone_objective_context_with_reward_contract(
            reward_v1_scenario.objective_context,
            "reward_v1",
        )
        reward_v2_scenario = copy.deepcopy(self.scenario)
        reward_v2_scenario.objective_context = clone_objective_context_with_reward_contract(
            reward_v2_scenario.objective_context,
            "reward_v2",
        )

        reward_v1_episode = rollout_stepwise_episode(
            reward_v1_scenario,
            select_highest_legal_action,
            policy_id="reward-v1",
        )
        reward_v2_episode = rollout_stepwise_episode(
            reward_v2_scenario,
            select_highest_legal_action,
            policy_id="reward-v2",
        )

        self.assertAlmostEqual(
            reward_v1_episode.final_outcome.yield_kg_ha,
            reward_v2_episode.final_outcome.yield_kg_ha,
            places=6,
        )
        self.assertAlmostEqual(
            reward_v1_episode.final_outcome.total_irrigation_mm,
            reward_v2_episode.final_outcome.total_irrigation_mm,
            places=6,
        )
        self.assertNotEqual(
            reward_v1_episode.final_outcome.cumulative_reward,
            reward_v2_episode.final_outcome.cumulative_reward,
        )

    def test_quzhou_maize_uses_expert_yield_floor_reference(self) -> None:
        self.assertEqual(scenario_yield_floor_reference(self.scenario), 10500.0)

        override_scenario = copy.deepcopy(self.scenario)
        override_scenario.objective_context.soft_preferences["yield_floor_reference_kg_ha"] = 9800.0
        self.assertEqual(scenario_yield_floor_reference(override_scenario), 9800.0)

    def test_reward_v2_guardrail_penalizes_zero_activity_when_yield_below_floor(self) -> None:
        objective_payload = self.scenario.objective_context.to_dict()
        guardrail = anti_collapse_preferences(objective_payload)
        guardrail["enabled"] = True
        guarded_reward = reward_from_outcome(
            yield_kg_ha=5000.0,
            total_irrigation_mm=0.0,
            total_nitrogen_kg_ha=0.0,
            irrigation_budget_mm=360.0,
            nitrogen_budget_kg_ha=360.0,
            avg_water_stress=0.3,
            avg_nitrogen_stress=0.3,
            operation_count=0,
            environmental_metrics={},
            weights=RewardWeights(contract_id="reward_v2"),
            yield_floor_reference=10500.0,
            anti_collapse_guardrail=guardrail,
        )
        unguarded_reward = reward_from_outcome(
            yield_kg_ha=5000.0,
            total_irrigation_mm=0.0,
            total_nitrogen_kg_ha=0.0,
            irrigation_budget_mm=360.0,
            nitrogen_budget_kg_ha=360.0,
            avg_water_stress=0.3,
            avg_nitrogen_stress=0.3,
            operation_count=0,
            environmental_metrics={},
            weights=RewardWeights(contract_id="reward_v2"),
            yield_floor_reference=10500.0,
            anti_collapse_guardrail={"enabled": False},
        )

        self.assertLess(guarded_reward, unguarded_reward)

    def test_reward_v2_guardrail_does_not_fire_after_yield_floor_is_met(self) -> None:
        objective_payload = self.scenario.objective_context.to_dict()
        guardrail = anti_collapse_preferences(objective_payload)
        guardrail["enabled"] = True
        guarded_reward = reward_from_outcome(
            yield_kg_ha=11000.0,
            total_irrigation_mm=0.0,
            total_nitrogen_kg_ha=0.0,
            irrigation_budget_mm=360.0,
            nitrogen_budget_kg_ha=360.0,
            avg_water_stress=0.1,
            avg_nitrogen_stress=0.1,
            operation_count=0,
            environmental_metrics={},
            weights=RewardWeights(contract_id="reward_v2"),
            yield_floor_reference=10500.0,
            anti_collapse_guardrail=guardrail,
        )
        unguarded_reward = reward_from_outcome(
            yield_kg_ha=11000.0,
            total_irrigation_mm=0.0,
            total_nitrogen_kg_ha=0.0,
            irrigation_budget_mm=360.0,
            nitrogen_budget_kg_ha=360.0,
            avg_water_stress=0.1,
            avg_nitrogen_stress=0.1,
            operation_count=0,
            environmental_metrics={},
            weights=RewardWeights(contract_id="reward_v2"),
            yield_floor_reference=10500.0,
            anti_collapse_guardrail={"enabled": False},
        )

        self.assertEqual(guarded_reward, unguarded_reward)

    def test_reward_v2_guardrail_penalizes_zero_nitrogen_collapse_more_than_partial_recovery(self) -> None:
        objective_payload = self.scenario.objective_context.to_dict()
        guardrail = anti_collapse_preferences(objective_payload)
        guardrail["enabled"] = True
        zero_nitrogen_reward = reward_from_outcome(
            yield_kg_ha=5400.0,
            total_irrigation_mm=25.0,
            total_nitrogen_kg_ha=0.0,
            irrigation_budget_mm=360.0,
            nitrogen_budget_kg_ha=360.0,
            avg_water_stress=0.25,
            avg_nitrogen_stress=0.25,
            operation_count=0,
            environmental_metrics={},
            weights=RewardWeights(contract_id="reward_v2"),
            yield_floor_reference=10500.0,
            anti_collapse_guardrail=guardrail,
        )
        guarded_minimum_n_reward = reward_from_outcome(
            yield_kg_ha=5400.0,
            total_irrigation_mm=25.0,
            total_nitrogen_kg_ha=60.0,
            irrigation_budget_mm=360.0,
            nitrogen_budget_kg_ha=360.0,
            avg_water_stress=0.25,
            avg_nitrogen_stress=0.25,
            operation_count=0,
            environmental_metrics={},
            weights=RewardWeights(contract_id="reward_v2"),
            yield_floor_reference=10500.0,
            anti_collapse_guardrail=guardrail,
        )

        self.assertLess(zero_nitrogen_reward, guarded_minimum_n_reward)

    def test_reward_v2_guardrail_config_keeps_nitrogen_floor_stricter_than_irrigation_floor(self) -> None:
        objective_payload = self.scenario.objective_context.to_dict()
        guardrail = anti_collapse_preferences(objective_payload)

        self.assertFalse(guardrail["enabled"])
        self.assertEqual(guardrail["minimum_nitrogen_ratio"], 0.15)
        self.assertEqual(guardrail["nitrogen_shortfall_penalty_weight"], 36.0)
        self.assertEqual(guardrail["zero_nitrogen_extra_penalty"], 3.0)

    def test_reward_v2_resource_settlement_is_flat_within_budget(self) -> None:
        objective_payload = self.scenario.objective_context.to_dict()
        settlement = resource_settlement_preferences(objective_payload)
        settlement["enabled"] = True
        weights = RewardWeights(contract_id="reward_v2")

        within_budget_reward = reward_from_outcome(
            yield_kg_ha=8000.0,
            total_irrigation_mm=300.0,
            total_nitrogen_kg_ha=300.0,
            irrigation_budget_mm=360.0,
            nitrogen_budget_kg_ha=360.0,
            avg_water_stress=0.15,
            avg_nitrogen_stress=0.1,
            operation_count=0,
            environmental_metrics={},
            weights=weights,
            yield_floor_reference=10500.0,
            anti_collapse_guardrail={"enabled": False},
            resource_settlement=settlement,
        )
        lower_budget_reward = reward_from_outcome(
            yield_kg_ha=8000.0,
            total_irrigation_mm=60.0,
            total_nitrogen_kg_ha=60.0,
            irrigation_budget_mm=360.0,
            nitrogen_budget_kg_ha=360.0,
            avg_water_stress=0.15,
            avg_nitrogen_stress=0.1,
            operation_count=0,
            environmental_metrics={},
            weights=weights,
            yield_floor_reference=10500.0,
            anti_collapse_guardrail={"enabled": False},
            resource_settlement=settlement,
        )
        zero_budget_reward = reward_from_outcome(
            yield_kg_ha=8000.0,
            total_irrigation_mm=0.0,
            total_nitrogen_kg_ha=0.0,
            irrigation_budget_mm=360.0,
            nitrogen_budget_kg_ha=360.0,
            avg_water_stress=0.15,
            avg_nitrogen_stress=0.1,
            operation_count=0,
            environmental_metrics={},
            weights=weights,
            yield_floor_reference=10500.0,
            anti_collapse_guardrail={"enabled": False},
            resource_settlement=settlement,
        )
        self.assertAlmostEqual(within_budget_reward, lower_budget_reward, places=6)
        self.assertAlmostEqual(lower_budget_reward, zero_budget_reward, places=6)

    def test_reward_v2_resource_settlement_penalizes_overshoot_only(self) -> None:
        objective_payload = self.scenario.objective_context.to_dict()
        settlement = resource_settlement_preferences(objective_payload)
        settlement["enabled"] = True
        weights = RewardWeights(contract_id="reward_v2")

        at_budget_reward = reward_from_outcome(
            yield_kg_ha=8000.0,
            total_irrigation_mm=360.0,
            total_nitrogen_kg_ha=360.0,
            irrigation_budget_mm=360.0,
            nitrogen_budget_kg_ha=360.0,
            avg_water_stress=0.15,
            avg_nitrogen_stress=0.1,
            operation_count=0,
            environmental_metrics={},
            weights=weights,
            yield_floor_reference=10500.0,
            anti_collapse_guardrail={"enabled": False},
            resource_settlement=settlement,
        )
        overshoot_reward = reward_from_outcome(
            yield_kg_ha=8000.0,
            total_irrigation_mm=420.0,
            total_nitrogen_kg_ha=420.0,
            irrigation_budget_mm=360.0,
            nitrogen_budget_kg_ha=360.0,
            avg_water_stress=0.15,
            avg_nitrogen_stress=0.1,
            operation_count=0,
            environmental_metrics={},
            weights=weights,
            yield_floor_reference=10500.0,
            anti_collapse_guardrail={"enabled": False},
            resource_settlement=settlement,
        )

        self.assertGreater(at_budget_reward, overshoot_reward)


if __name__ == "__main__":
    unittest.main()
