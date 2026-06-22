from __future__ import annotations

import json
import tempfile
from pathlib import Path
import unittest

from transdssat.dssat.validation import (
    compare_output_file,
    infer_active_output_selector_from_rows,
    normalize_row_for_semantic_comparison,
    reconstruct_interactive_session_policy,
)


class InteractiveSessionPolicyReconstructionTests(unittest.TestCase):
    def test_reconstructs_policy_from_protocol_requests_and_responses(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            protocol_dir = Path(tmpdir)
            manifest = {
                "scenario": {
                    "scenario_id": "demo-scenario",
                    "engine_name": "dssat_official",
                    "crop_name": "maize",
                    "weather_regime": "normal",
                    "planting_date": "2025-06-01",
                    "weather_year": 2025,
                    "cultivar_code": "DH6051",
                    "template_name": "maize",
                    "experiment_file": "DEMO.MZX",
                    "site_name": "demo",
                    "management_mode": "balanced",
                    "seed": 1,
                    "irrigation_budget_mm": 100.0,
                    "nitrogen_budget_kg_ha": 80.0,
                    "crop_spec": {
                        "crop_name": "maize",
                        "season_length_days": 120,
                        "base_temperature_c": 8.0,
                        "optimal_temperature_c": 28.0,
                        "radiation_use_efficiency": 1.4,
                        "harvest_index": 0.5,
                        "stage_water_demand": {
                            "emergence": 0.15,
                            "vegetative": 0.35,
                            "reproductive": 0.35,
                            "grain_fill": 0.15,
                        },
                        "stage_nitrogen_demand": {
                            "emergence": 0.2,
                            "vegetative": 0.4,
                            "reproductive": 0.3,
                            "grain_fill": 0.1,
                        },
                        "stage_canopy_growth": {
                            "emergence": 0.2,
                            "vegetative": 0.5,
                            "reproductive": 0.2,
                            "grain_fill": 0.1,
                        },
                    },
                    "soil_profile": {
                        "soil_name": "demo",
                        "field_capacity_mm": 200.0,
                        "wilting_point_mm": 80.0,
                        "saturation_mm": 260.0,
                        "initial_root_zone_water_mm": 150.0,
                        "initial_nitrogen_kg_ha": 90.0,
                        "drainage_coeff": 0.5,
                    },
                    "weather": [
                        {
                            "day_index": 0,
                            "tmin_c": 20.0,
                            "tmax_c": 30.0,
                            "precipitation_mm": 0.0,
                            "radiation_mj_m2": 18.0,
                            "et0_mm": 4.0,
                        }
                    ],
                    "decision_context": {
                        "decision_interval_days": 5,
                        "weather_mode": "realistic",
                        "forecast_horizon_days": 7,
                        "irrigation_min_gap_days": 5,
                        "nitrogen_min_gap_days": 10,
                        "action_space_id": "v2_joint_continuous",
                        "action_table_id": "deprecated_v1_joint_discrete",
                        "allow_combined_actions": True,
                        "state_interface_version": "v2026-06-admission-draft",
                        "full_state_fields": [],
                        "partial_observation_fields": [],
                        "stable_core_fields": [],
                        "pending_agronomy_fields": [],
                        "simulator_internal_fields": [],
                        "derived_fields": [],
                    },
                    "crop_context": None,
                    "objective_context": {
                        "objective_id": "default",
                        "objective_name": "default",
                        "primary_metric": "yield_kg_ha",
                        "reward_weights": {},
                        "budget_constraints": {},
                        "soft_preferences": {},
                        "report_metrics": [],
                        "environmental_metric_specs": [],
                        "missing_details": [],
                        "reward_contract": "reward_v2",
                    },
                }
            }
            (protocol_dir / "session_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            (protocol_dir / "session_ready.json").write_text(
                json.dumps({"state": {"day_index": 0}}),
                encoding="utf-8",
            )
            (protocol_dir / "step_request_0000.json").write_text(
                json.dumps(
                    {
                        "step_index": 0,
                        "decision_interval_days": 5,
                        "action": {"irrigation_mm": 12.0, "nitrogen_kg_ha": 0.0},
                    }
                ),
                encoding="utf-8",
            )
            (protocol_dir / "step_response_0000.json").write_text(
                json.dumps({"next_state": {"day_index": 5}}),
                encoding="utf-8",
            )
            (protocol_dir / "step_request_0001.json").write_text(
                json.dumps(
                    {
                        "step_index": 1,
                        "decision_interval_days": 5,
                        "action": {"irrigation_mm": 0.0, "nitrogen_kg_ha": 18.0},
                    }
                ),
                encoding="utf-8",
            )
            (protocol_dir / "step_response_0001.json").write_text(
                json.dumps({"next_state": {"day_index": 10}}),
                encoding="utf-8",
            )

            policy = reconstruct_interactive_session_policy(protocol_dir)

            self.assertEqual(policy.scenario_id, "demo-scenario")
            self.assertEqual(len(policy.actions), 2)
            self.assertEqual(policy.actions[0].day_index, 0)
            self.assertEqual(policy.actions[0].date, "2025-06-01")
            self.assertEqual(policy.actions[0].irrigation_mm, 12.0)
            self.assertEqual(policy.actions[1].day_index, 5)
            self.assertEqual(policy.actions[1].date, "2025-06-06")
            self.assertEqual(policy.actions[1].nitrogen_kg_ha, 18.0)


class DSSATSemanticNormalizationTests(unittest.TestCase):
    def test_summary_semantic_normalization_ignores_known_non_semantic_fields(self) -> None:
        left = {
            "CH4EM": "0.0",
            "NI#M": "0",
            "OPAM": "0",
            "OPTAM": "0",
            "HWAM": "1623",
        }
        right = {
            "CH4EM": "0.000",
            "NI#M": "1",
            "OPAM": "-99",
            "OPTAM": "-99",
            "HWAM": "1623.000",
        }
        self.assertEqual(
            normalize_row_for_semantic_comparison("Summary.OUT", left),
            normalize_row_for_semantic_comparison("Summary.OUT", right),
        )

    def test_summary_semantic_normalization_tolerates_ch4em_rounding_difference(self) -> None:
        left = {"CH4EM": "120.9", "HWAM": "1850"}
        right = {"CH4EM": "121.", "HWAM": "1850.0"}
        self.assertEqual(
            normalize_row_for_semantic_comparison("Summary.OUT", left),
            normalize_row_for_semantic_comparison("Summary.OUT", right),
        )

    def test_soilwat_semantic_normalization_ignores_dtwtm_only(self) -> None:
        left = {"YEAR": "2025", "DOY": "174", "SWTD": "214"}
        right = {"YEAR": "2025.0", "DOY": "174.000", "SWTD": "214.0", "DTWTM": "1000"}
        self.assertEqual(
            normalize_row_for_semantic_comparison("SoilWat.OUT", left),
            normalize_row_for_semantic_comparison("SoilWat.OUT", right),
        )

    def test_semantic_normalization_keeps_real_value_differences(self) -> None:
        left = {"HWAM": "1623"}
        right = {"HWAM": "1700"}
        self.assertNotEqual(
            normalize_row_for_semantic_comparison("Summary.OUT", left),
            normalize_row_for_semantic_comparison("Summary.OUT", right),
        )

    def test_compare_output_file_filters_right_side_to_active_treatment_selector(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            left_path = root / "left.Evaluate.OUT"
            right_path = root / "right.Evaluate.OUT"
            left_path.write_text(
                "\n".join(
                    [
                        "@RUNNO TRNO HWAM",
                        "1 2 1623",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            right_path.write_text(
                "\n".join(
                    [
                        "@RUNNO TRNO HWAM",
                        "1 1 1500",
                        "1 2 1623",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            selector = infer_active_output_selector_from_rows(
                [
                    {
                        "RUNNO": "1",
                        "TRNO": "2",
                        "HWAM": "1623",
                    }
                ]
            )
            comparison = compare_output_file(left_path, right_path, file_name="Evaluate.OUT", selector=selector)

        self.assertIsNotNone(selector)
        assert selector is not None
        self.assertEqual(selector.selector_kind, "treatment")
        self.assertEqual(selector.selector_value, 2)
        self.assertTrue(comparison.semantic_match)
        self.assertEqual(comparison.left_row_count, 1)
        self.assertEqual(comparison.right_row_count, 1)

    def test_compare_output_file_preserves_rows_when_selector_column_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            left_path = root / "PlantGro.OUT"
            right_path = root / "vanilla.PlantGro.OUT"
            left_path.write_text(
                "\n".join(
                    [
                        "@YEAR DOY DAS DAP LAID CWAD",
                        "2025 170 0 0 0.1 100.0",
                        "2025 171 1 1 0.2 120.0",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            right_path.write_text(
                "\n".join(
                    [
                        "@YEAR DOY DAS DAP TRNO LAID CWAD",
                        "2025 170 0 0 1 0.1 100.0",
                        "2025 171 1 1 1 0.2 120.0",
                        "2025 170 0 0 2 0.3 180.0",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            comparison = compare_output_file(left_path, right_path, file_name="PlantGro.OUT")

        self.assertFalse(comparison.match)
        self.assertEqual(comparison.left_row_count, 2)
        self.assertEqual(comparison.right_row_count, 3)

    def test_compare_output_file_filters_run_sections_when_daily_rows_have_no_treatment_column(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            left_path = root / "PlantGro.OUT"
            right_path = root / "vanilla.PlantGro.OUT"
            left_path.write_text(
                "\n".join(
                    [
                        "*RUN   1",
                        "@YEAR DOY DAS DAP LAID CWAD",
                        "2025 170 0 0 0.1 100.0",
                        "2025 171 1 1 0.2 120.0",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            right_path.write_text(
                "\n".join(
                    [
                        "*RUN   1",
                        "@YEAR DOY DAS DAP LAID CWAD",
                        "2025 170 0 0 0.1 100.0",
                        "2025 171 1 1 0.2 120.0",
                        "*RUN   2",
                        "@YEAR DOY DAS DAP LAID CWAD",
                        "2025 170 0 0 0.3 180.0",
                        "2025 171 1 1 0.4 220.0",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            selector = infer_active_output_selector_from_rows([{"TRNO": "1"}])
            comparison = compare_output_file(left_path, right_path, file_name="PlantGro.OUT", selector=selector)

        self.assertTrue(comparison.match)
        self.assertTrue(comparison.semantic_match)
        self.assertEqual(comparison.left_row_count, 2)
        self.assertEqual(comparison.right_row_count, 2)


if __name__ == "__main__":
    unittest.main()
