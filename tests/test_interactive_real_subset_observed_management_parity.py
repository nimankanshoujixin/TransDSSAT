from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest

from transdssat.discrete_actions import action_constraints_for_state
from transdssat.dssat.validation import reconstruct_interactive_session_policy
from transdssat.domain import CropState
from transdssat.real_subset_replay import load_real_subset_replay_case


def load_script_module():
    root = Path(__file__).resolve().parents[1]
    script_path = root / "scripts" / "run_interactive_real_subset_observed_management_parity.py"
    spec = importlib.util.spec_from_file_location("interactive_real_subset_observed_management_parity_for_tests", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load module from {script_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


script = load_script_module()


class InteractiveRealSubsetObservedManagementParityTests(unittest.TestCase):
    @staticmethod
    def _semantic_actions(policy) -> list[tuple[int, str, float, float]]:
        return [
            (
                int(action.day_index),
                str(action.date),
                round(float(action.irrigation_mm), 3),
                round(float(action.nitrogen_kg_ha), 3),
            )
            for action in policy.actions
        ]

    def test_observed_management_scenario_uses_daily_stepwise_grid(self) -> None:
        scenario = script._build_observed_management_scenario("wuhu_rice_calibrated", 11)

        self.assertEqual(scenario.decision_context.decision_interval_days, 1)
        self.assertEqual(scenario.decision_context.irrigation_min_gap_days, 1)
        self.assertEqual(scenario.decision_context.nitrogen_min_gap_days, 1)
        self.assertTrue(scenario.decision_context.allow_combined_actions)

    def test_observed_management_stepwise_policy_reconstructs_to_source_policy(self) -> None:
        case = load_real_subset_replay_case("wuhu_rice_calibrated", 11)
        scenario = script._build_observed_management_scenario("wuhu_rice_calibrated", 11)
        stepwise_policy = script.build_stepwise_policy_from_season_policy(
            scenario,
            case.baseline_policy,
            suffix="observed-management-stepwise",
            notes=["real_subset_observed_management_daily_replay"],
        )

        # Reconstruct a SeasonPolicy from the stepwise schedule as the interactive protocol would.
        import json
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            protocol_dir = Path(tmpdir)
            (protocol_dir / "session_manifest.json").write_text(
                json.dumps({"scenario": scenario.to_dict()}),
                encoding="utf-8",
            )
            (protocol_dir / "session_ready.json").write_text(
                json.dumps({"state": {"day_index": 0}}),
                encoding="utf-8",
            )
            current_day = 0
            for index in range(max(stepwise_policy.action_schedule) + 1):
                action = stepwise_policy.action_schedule.get(index, None)
                if action is None:
                    action_payload = {"irrigation_mm": 0.0, "nitrogen_kg_ha": 0.0}
                else:
                    action_payload = action.to_dict()
                (protocol_dir / f"step_request_{index:04d}.json").write_text(
                    json.dumps(
                        {
                            "step_index": index,
                            "decision_interval_days": 1,
                            "action": action_payload,
                        }
                    ),
                    encoding="utf-8",
                )
                current_day += 1
                (protocol_dir / f"step_response_{index:04d}.json").write_text(
                    json.dumps({"next_state": {"day_index": current_day}}),
                    encoding="utf-8",
                )

            reconstructed = reconstruct_interactive_session_policy(protocol_dir)

        self.assertEqual(
            self._semantic_actions(reconstructed),
            self._semantic_actions(case.baseline_policy),
        )

    def test_scheduled_action_for_observation_reads_daily_schedule(self) -> None:
        case = load_real_subset_replay_case("wuhu_rice_calibrated", 11)
        scenario = script._build_observed_management_scenario("wuhu_rice_calibrated", 11)
        stepwise_policy = script.build_stepwise_policy_from_season_policy(
            scenario,
            case.baseline_policy,
            suffix="observed-management-stepwise",
            notes=["real_subset_observed_management_daily_replay"],
        )

        class _Observation:
            def __init__(self, day_index: int) -> None:
                self.day_index = day_index

        self.assertEqual(
            script._scheduled_action_for_observation(stepwise_policy, _Observation(0)),
            {"irrigation_mm": 30.0, "nitrogen_kg_ha": 47.2},
        )
        self.assertEqual(
            script._scheduled_action_for_observation(stepwise_policy, _Observation(5)),
            {"irrigation_mm": 0.0, "nitrogen_kg_ha": 35.9},
        )
        self.assertEqual(
            script._scheduled_action_for_observation(stepwise_policy, _Observation(1)),
            {},
        )

    def test_observed_management_replay_constraint_rules_allow_preplant_actions(self) -> None:
        scenario = script._build_observed_management_scenario("wuhu_rice_calibrated", 11)
        rules = script._observed_management_replay_constraint_rules(scenario)
        state = CropState(
            day_index=0,
            stage="preplant",
            stage_index=0,
            soil_moisture=1.2,
            root_zone_water_mm=420.0,
            soil_nitrogen_kg_ha=50.0,
            canopy_cover=0.0,
            biomass_kg_ha=0.0,
            water_stress=0.0,
            nitrogen_stress=0.0,
            tmean_c=25.0,
            precipitation_mm=0.0,
            et0_mm=4.0,
            radiation_mj_m2=18.0,
        )
        constraints = action_constraints_for_state(
            scenario=scenario,
            state=state,
            remaining_irrigation_mm=100.0,
            remaining_nitrogen_kg_ha=100.0,
            last_irrigation_day=None,
            last_nitrogen_day=None,
            done=False,
            constraint_rules=rules,
        )

        self.assertTrue(constraints.irrigation.allowed)
        self.assertTrue(constraints.nitrogen.allowed)
        self.assertEqual(constraints.irrigation.blocked_reasons, [])
        self.assertEqual(constraints.nitrogen.blocked_reasons, [])


if __name__ == "__main__":
    unittest.main()
