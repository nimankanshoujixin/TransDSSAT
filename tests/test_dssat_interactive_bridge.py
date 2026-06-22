from __future__ import annotations

import json
from pathlib import Path
import tempfile
import threading
import time
import unittest

from transdssat.dssat.interactive_bridge import main as helper_main
from transdssat.scenarios import build_quzhou_scenarios


def _scenario_dict() -> dict[str, object]:
    scenario = build_quzhou_scenarios(
        target_count=1,
        engines=("dssat_official",),
        crops_filter=("maize",),
    )[0]
    return scenario.to_dict()


def _manifest(protocol_dir: Path) -> dict[str, object]:
    return {
        "scenario": _scenario_dict(),
        "interaction": {
            "protocol_version": "patched-dssat-v1",
            "engine_name": "dssat_official",
            "backend_mode": "interactive_patched",
            "runtime_role": "patched",
            "run_dir": str(protocol_dir.parent / "run"),
            "crop_name": "maize",
            "action_channels": ["irrigation_mm", "nitrogen_kg_ha"],
            "decision_interval_days": 5,
            "state_interface_contract": {
                "fields": [
                    "day_index",
                    "stage",
                    "stage_index",
                    "soil_moisture",
                ]
            },
        }
    }


def _state_payload() -> str:
    return "\n".join(
        [
            "day_index=0",
            "stage=vegetative",
            "stage_index=1",
            "soil_moisture=0.5",
            "root_zone_water_mm=180.0",
            "soil_nitrogen_kg_ha=120.0",
            "canopy_cover=0.2",
            "biomass_kg_ha=100.0",
            "water_stress=0.1",
            "nitrogen_stress=0.1",
            "tmean_c=22.0",
            "precipitation_mm=0.0",
            "et0_mm=4.0",
            "radiation_mj_m2=18.0",
        ]
    ) + "\n"


def _outcome_payload() -> str:
    return "\n".join(
        [
            "yield_kg_ha=7000.0",
            "biomass_kg_ha=15000.0",
            "total_irrigation_mm=12.0",
            "total_nitrogen_kg_ha=18.0",
            "water_use_efficiency=1.2",
            "nitrogen_use_efficiency=0.8",
            "cumulative_reward=3.5",
        ]
    ) + "\n"


class InteractiveBridgeHelperTests(unittest.TestCase):
    def test_write_ready_and_final_outcome_from_kv_payloads(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            protocol_dir = root / "protocol"
            protocol_dir.mkdir(parents=True, exist_ok=True)
            manifest_path = protocol_dir / "session_manifest.json"
            manifest_path.write_text(json.dumps(_manifest(protocol_dir), indent=2), encoding="utf-8")
            state_path = root / "state.kv"
            state_path.write_text(_state_payload(), encoding="utf-8")
            outcome_path = root / "outcome.kv"
            outcome_path.write_text(_outcome_payload(), encoding="utf-8")

            helper_main(
                [
                    "write-ready",
                    "--protocol-dir",
                    str(protocol_dir),
                    "--session-manifest",
                    str(manifest_path),
                    "--state-file",
                    str(state_path),
                    "--info-tag",
                    "probe_mode=fortran_bridge",
                ]
            )
            helper_main(
                [
                    "write-final-outcome",
                    "--protocol-dir",
                    str(protocol_dir),
                    "--session-manifest",
                    str(manifest_path),
                    "--outcome-file",
                    str(outcome_path),
                ]
            )

            ready_payload = json.loads((protocol_dir / "session_ready.json").read_text(encoding="utf-8"))
            self.assertEqual(ready_payload["state"]["stage"], "vegetative")
            self.assertEqual(ready_payload["info"]["probe_mode"], "fortran_bridge")
            final_outcome = json.loads((protocol_dir / "final_outcome.json").read_text(encoding="utf-8"))
            self.assertEqual(final_outcome["yield_kg_ha"], 7000.0)
            self.assertEqual(final_outcome["total_nitrogen_kg_ha"], 18.0)

    def test_await_action_writes_fortran_friendly_kv_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            protocol_dir = root / "protocol"
            protocol_dir.mkdir(parents=True, exist_ok=True)
            manifest_path = protocol_dir / "session_manifest.json"
            manifest_path.write_text(json.dumps(_manifest(protocol_dir), indent=2), encoding="utf-8")
            action_path = root / "action.kv"

            def _delayed_request() -> None:
                time.sleep(0.1)
                (protocol_dir / "step_request_0000.json").write_text(
                    json.dumps(
                        {
                            "step_index": 0,
                            "decision_interval_days": 5,
                            "action": {
                                "irrigation_mm": 12.0,
                                "nitrogen_kg_ha": 18.0,
                            },
                        },
                        indent=2,
                    ),
                    encoding="utf-8",
                )

            worker = threading.Thread(target=_delayed_request, daemon=True)
            worker.start()
            helper_main(
                [
                    "await-action",
                    "--protocol-dir",
                    str(protocol_dir),
                    "--session-manifest",
                    str(manifest_path),
                    "--step-index",
                    "0",
                    "--output-action-file",
                    str(action_path),
                    "--timeout-seconds",
                    "2",
                    "--poll-interval-seconds",
                    "0.02",
                ]
            )
            action_payload = dict(
                line.strip().split("=", 1)
                for line in action_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            )
            self.assertEqual(action_payload["step_index"], "0")
            self.assertEqual(action_payload["decision_interval_days"], "5")
            self.assertEqual(action_payload["irrigation_mm"], "12.0")
            self.assertEqual(action_payload["nitrogen_kg_ha"], "18.0")
            self.assertEqual(action_payload["close_requested"], "0")

    def test_write_step_response_supports_json_daily_trace_and_final_outcome(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            protocol_dir = root / "protocol"
            protocol_dir.mkdir(parents=True, exist_ok=True)
            manifest_path = protocol_dir / "session_manifest.json"
            manifest_path.write_text(json.dumps(_manifest(protocol_dir), indent=2), encoding="utf-8")
            state_path = root / "state.kv"
            state_path.write_text(_state_payload(), encoding="utf-8")
            outcome_path = root / "outcome.json"
            outcome_path.write_text(
                json.dumps(
                    {
                        "yield_kg_ha": 7100.0,
                        "biomass_kg_ha": 15100.0,
                        "total_irrigation_mm": 12.0,
                        "total_nitrogen_kg_ha": 18.0,
                        "water_use_efficiency": 1.3,
                        "nitrogen_use_efficiency": 0.9,
                        "cumulative_reward": 4.2,
                        "environmental_metrics": {"n_leaching": 2.1},
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            daily_trace_path = root / "daily_trace.json"
            daily_trace_path.write_text(json.dumps([{"day_index": 0, "reward": 1.0, "done": False}], indent=2), encoding="utf-8")

            helper_main(
                [
                    "write-step-response",
                    "--protocol-dir",
                    str(protocol_dir),
                    "--session-manifest",
                    str(manifest_path),
                    "--step-index",
                    "0",
                    "--state-file",
                    str(state_path),
                    "--reward",
                    "1.5",
                    "--done",
                    "--days-executed",
                    "5",
                    "--daily-trace-file",
                    str(daily_trace_path),
                    "--final-outcome-file",
                    str(outcome_path),
                    "--info-tag",
                    "bridge_mode=kv",
                ]
            )

            response_payload = json.loads((protocol_dir / "step_response_0000.json").read_text(encoding="utf-8"))
            self.assertTrue(response_payload["done"])
            self.assertEqual(response_payload["reward"], 1.5)
            self.assertEqual(response_payload["info"]["days_executed"], 5)
            self.assertEqual(response_payload["info"]["bridge_mode"], "kv")
            self.assertEqual(response_payload["final_outcome"]["environmental_metrics"]["n_leaching"], 2.1)

    def test_write_step_response_computes_reward_and_final_outcome_from_dssat_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            run_dir = root / "run"
            run_dir.mkdir(parents=True, exist_ok=True)
            protocol_dir = root / "protocol"
            protocol_dir.mkdir(parents=True, exist_ok=True)
            manifest = _manifest(protocol_dir)
            manifest["interaction"]["run_dir"] = str(run_dir)
            manifest_path = protocol_dir / "session_manifest.json"
            manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

            ready_state_path = root / "state_ready.kv"
            ready_state_path.write_text(_state_payload(), encoding="utf-8")
            helper_main(
                [
                    "write-ready",
                    "--protocol-dir",
                    str(protocol_dir),
                    "--session-manifest",
                    str(manifest_path),
                    "--state-file",
                    str(ready_state_path),
                ]
            )

            (protocol_dir / "step_request_0000.json").write_text(
                json.dumps(
                    {
                        "step_index": 0,
                        "decision_interval_days": 5,
                        "action": {
                            "irrigation_mm": 12.0,
                            "nitrogen_kg_ha": 18.0,
                        },
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            next_state_path = root / "state_next.kv"
            next_state_path.write_text(
                _state_payload().replace("day_index=0", "day_index=5").replace("biomass_kg_ha=100.0", "biomass_kg_ha=160.0"),
                encoding="utf-8",
            )
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
                        "2025 174 5 192.0",
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
                        "2025 174 5 133.0",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            (run_dir / "Summary.OUT").write_text(
                "\n".join(
                    [
                        "@RUNNO HWAM CWAM IRCM NICM PDAT ADAT MDAT",
                        "1     7100 15100 12   18   2025169 2025195 2025260",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            helper_main(
                [
                    "write-step-response",
                    "--protocol-dir",
                    str(protocol_dir),
                    "--session-manifest",
                    str(manifest_path),
                    "--step-index",
                    "0",
                    "--state-file",
                    str(next_state_path),
                    "--done",
                    "--days-executed",
                    "5",
                ]
            )
            response_payload = json.loads((protocol_dir / "step_response_0000.json").read_text(encoding="utf-8"))
            self.assertTrue(response_payload["done"])
            self.assertGreater(response_payload["reward"], 0.0)
            self.assertEqual(response_payload["final_outcome"]["yield_kg_ha"], 7100.0)
            self.assertEqual(response_payload["final_outcome"]["total_irrigation_mm"], 12.0)

            placeholder_outcome_path = root / "placeholder_outcome.kv"
            placeholder_outcome_path.write_text(_outcome_payload().replace("7000.0", "0.0"), encoding="utf-8")
            helper_main(
                [
                    "write-final-outcome",
                    "--protocol-dir",
                    str(protocol_dir),
                    "--session-manifest",
                    str(manifest_path),
                    "--outcome-file",
                    str(placeholder_outcome_path),
                ]
            )
            final_outcome = json.loads((protocol_dir / "final_outcome.json").read_text(encoding="utf-8"))
            self.assertEqual(final_outcome["yield_kg_ha"], 7100.0)
            self.assertGreater(final_outcome["cumulative_reward"], 0.0)


if __name__ == "__main__":
    unittest.main()
