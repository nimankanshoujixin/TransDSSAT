from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from scripts.validate_interactive_dssat_action_effect import main as validate_main
from transdssat.scenarios import build_quzhou_scenarios


def _write_run_outputs(run_dir: Path, *, irrigation_mm: float, nitrogen_kg_ha: float, terminal_water_mm: float, terminal_nitrogen_kg_ha: float) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "PlantGro.OUT").write_text(
        "\n".join(
            [
                "@YEAR DOY DAS LAID CWAD SWFAC NSTRES",
                "2025 169 0 0.5 100.0 0.9 0.9",
                "2025 174 5 0.8 160.0 0.92 0.88",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (run_dir / "SoilWat.OUT").write_text(
        "\n".join(
            [
                "@YEAR DOY DAS TSW",
                "2025 169 0 180.0",
                f"2025 174 5 {terminal_water_mm}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (run_dir / "SoilNi.OUT").write_text(
        "\n".join(
            [
                "@YEAR DOY DAS NIAD",
                "2025 169 0 120.0",
                f"2025 174 5 {terminal_nitrogen_kg_ha}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (run_dir / "Summary.OUT").write_text(
        "\n".join(
            [
                "@RUNNO HWAM CWAM IRCM NICM PDAT ADAT MDAT",
                f"1     7100 15100 {irrigation_mm}   {nitrogen_kg_ha}   2025169 2025195 2025260",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


class ValidateInteractiveActionEffectTests(unittest.TestCase):
    def test_validation_script_detects_artifact_level_action_effects(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            scenario = build_quzhou_scenarios(
                target_count=1,
                engines=("dssat_official",),
                crops_filter=("maize",),
                sampling_mode="random",
                seed=20260622,
            )[0]
            manifest_payload = {
                "scenario": scenario.to_dict(),
                "interaction": {
                    "run_dir": "",
                },
            }

            baseline_run = root / "baseline_run"
            action_run = root / "action_run"
            _write_run_outputs(
                baseline_run,
                irrigation_mm=0.0,
                nitrogen_kg_ha=0.0,
                terminal_water_mm=180.0,
                terminal_nitrogen_kg_ha=120.0,
            )
            _write_run_outputs(
                action_run,
                irrigation_mm=12.0,
                nitrogen_kg_ha=18.0,
                terminal_water_mm=192.0,
                terminal_nitrogen_kg_ha=133.0,
            )

            baseline_manifest = root / "baseline_manifest.json"
            baseline_manifest.write_text(
                json.dumps({**manifest_payload, "interaction": {"run_dir": str(baseline_run)}}),
                encoding="utf-8",
            )
            action_manifest = root / "action_manifest.json"
            action_manifest.write_text(
                json.dumps({**manifest_payload, "interaction": {"run_dir": str(action_run)}}),
                encoding="utf-8",
            )

            baseline_report = root / "baseline_report.json"
            baseline_report.write_text(
                json.dumps(
                    {
                        "scenario_id": scenario.scenario_id,
                        "run_dir": str(baseline_run),
                        "archived_run_dir": str(baseline_run),
                        "session_manifest": str(baseline_manifest),
                        "requested_action": {"irrigation_mm": 0.0, "nitrogen_kg_ha": 0.0},
                        "final_outcome": {
                            "yield_kg_ha": 7100.0,
                            "biomass_kg_ha": 15100.0,
                            "total_irrigation_mm": 0.0,
                            "total_nitrogen_kg_ha": 0.0,
                            "water_use_efficiency": 0.0,
                            "nitrogen_use_efficiency": 0.0,
                            "cumulative_reward": -15.0,
                            "environmental_metrics": {
                                "terminal_root_zone_water_mm": 180.0,
                                "terminal_soil_nitrogen_kg_ha": 120.0,
                                "interactive_reward_source": "dssat_output_parser",
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )
            action_report = root / "action_report.json"
            action_report.write_text(
                json.dumps(
                    {
                        "scenario_id": scenario.scenario_id,
                        "run_dir": str(action_run),
                        "archived_run_dir": str(action_run),
                        "session_manifest": str(action_manifest),
                        "requested_action": {"irrigation_mm": 12.0, "nitrogen_kg_ha": 18.0},
                        "final_outcome": {
                            "yield_kg_ha": 7100.0,
                            "biomass_kg_ha": 15100.0,
                            "total_irrigation_mm": 12.0,
                            "total_nitrogen_kg_ha": 18.0,
                            "water_use_efficiency": 0.0,
                            "nitrogen_use_efficiency": 0.0,
                            "cumulative_reward": -15.121284,
                            "environmental_metrics": {
                                "terminal_root_zone_water_mm": 192.0,
                                "terminal_soil_nitrogen_kg_ha": 133.0,
                                "interactive_reward_source": "dssat_output_parser",
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )

            output_json = root / "validation.json"
            exit_code = validate_main(
                [
                    "--baseline-report",
                    str(baseline_report),
                    "--action-report",
                    str(action_report),
                    "--output-json",
                    str(output_json),
                ]
            )
            self.assertEqual(exit_code, 0)
            payload = json.loads(output_json.read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "ok")
            self.assertEqual(payload["deltas"]["total_irrigation_mm"], 12.0)
            self.assertEqual(payload["deltas"]["total_nitrogen_kg_ha"], 18.0)
            self.assertEqual(payload["requested_action_match_error"]["total_irrigation_mm"], 0.0)
            self.assertEqual(payload["requested_action_match_error"]["total_nitrogen_kg_ha"], 0.0)
            self.assertTrue(payload["checks"]["terminal_water_shift_observed"])
            self.assertTrue(payload["checks"]["terminal_nitrogen_shift_observed"])
            self.assertEqual(payload["baseline_outcome"]["cumulative_reward"], -15.0)
            self.assertEqual(payload["action_outcome"]["cumulative_reward"], -15.121284)
            self.assertTrue(payload["checks"]["baseline_protocol_matches_archived"])
            self.assertTrue(payload["checks"]["action_protocol_matches_archived"])
            self.assertTrue(payload["checks"]["baseline_protocol_is_parser_backed"])
            self.assertTrue(payload["checks"]["action_protocol_is_parser_backed"])

    def test_validation_script_rejects_amplified_action_scale(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            scenario = build_quzhou_scenarios(
                target_count=1,
                engines=("dssat_official",),
                crops_filter=("maize",),
                sampling_mode="random",
                seed=20260622,
            )[0]
            manifest_payload = {
                "scenario": scenario.to_dict(),
                "interaction": {
                    "run_dir": "",
                },
            }

            baseline_run = root / "baseline_run"
            action_run = root / "action_run"
            _write_run_outputs(
                baseline_run,
                irrigation_mm=0.0,
                nitrogen_kg_ha=0.0,
                terminal_water_mm=180.0,
                terminal_nitrogen_kg_ha=120.0,
            )
            _write_run_outputs(
                action_run,
                irrigation_mm=60.0,
                nitrogen_kg_ha=90.0,
                terminal_water_mm=240.0,
                terminal_nitrogen_kg_ha=170.0,
            )

            baseline_manifest = root / "baseline_manifest.json"
            baseline_manifest.write_text(
                json.dumps({**manifest_payload, "interaction": {"run_dir": str(baseline_run)}}),
                encoding="utf-8",
            )
            action_manifest = root / "action_manifest.json"
            action_manifest.write_text(
                json.dumps({**manifest_payload, "interaction": {"run_dir": str(action_run)}}),
                encoding="utf-8",
            )

            baseline_report = root / "baseline_report.json"
            baseline_report.write_text(
                json.dumps(
                    {
                        "scenario_id": scenario.scenario_id,
                        "run_dir": str(baseline_run),
                        "archived_run_dir": str(baseline_run),
                        "session_manifest": str(baseline_manifest),
                        "requested_action": {"irrigation_mm": 0.0, "nitrogen_kg_ha": 0.0},
                    }
                ),
                encoding="utf-8",
            )
            action_report = root / "action_report.json"
            action_report.write_text(
                json.dumps(
                    {
                        "scenario_id": scenario.scenario_id,
                        "run_dir": str(action_run),
                        "archived_run_dir": str(action_run),
                        "session_manifest": str(action_manifest),
                        "requested_action": {"irrigation_mm": 12.0, "nitrogen_kg_ha": 18.0},
                    }
                ),
                encoding="utf-8",
            )

            output_json = root / "validation.json"
            exit_code = validate_main(
                [
                    "--baseline-report",
                    str(baseline_report),
                    "--action-report",
                    str(action_report),
                    "--output-json",
                    str(output_json),
                ]
            )
            self.assertEqual(exit_code, 1)
            payload = json.loads(output_json.read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "failed")
            self.assertEqual(payload["deltas"]["total_irrigation_mm"], 60.0)
            self.assertEqual(payload["deltas"]["total_nitrogen_kg_ha"], 90.0)
            self.assertFalse(payload["checks"]["irrigation_scale_matches_request"])
            self.assertFalse(payload["checks"]["nitrogen_scale_matches_request"])


if __name__ == "__main__":
    unittest.main()
