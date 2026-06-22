from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest import mock

from transdssat.domain import CropAction
from transdssat.dssat import (
    build_filesystem_interactive_transport_from_env,
    FileSystemInteractiveControllerConfig,
    FileSystemInteractiveDSSATTransport,
    FileSystemInteractiveProtocol,
    INTERACTIVE_CONTROLLER_SCRIPT_PATH,
    INTERACTIVE_ACTION_CHANNELS,
    INTERACTIVE_PROTOCOL_VERSION,
)
from transdssat.scenarios import build_quzhou_scenarios


class FileSystemInteractiveTransportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.scenario = build_quzhou_scenarios(
            target_count=1,
            engines=("dssat_official",),
            crops_filter=("maize",),
            sampling_mode="random",
            seed=20260621,
        )[0]

    def test_filesystem_transport_exchanges_reset_step_and_final_outcome(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            protocol = FileSystemInteractiveProtocol(root_dir=root / "protocol")
            run_dir = root / "run"
            run_dir.mkdir(parents=True, exist_ok=True)
            controller = FileSystemInteractiveControllerConfig(
                launch_command="python -c \"pass\"",
                poll_interval_seconds=0.01,
                ready_timeout_seconds=2.0,
                step_timeout_seconds=2.0,
                close_timeout_seconds=2.0,
            )
            transport = FileSystemInteractiveDSSATTransport(
                protocol=protocol,
                controller=controller,
                run_dir=run_dir,
            )

            def controller_thread() -> None:
                while not protocol.session_manifest_path.exists():
                    time.sleep(0.01)
                manifest_payload = json.loads(protocol.session_manifest_path.read_text(encoding="utf-8"))
                self.assertEqual(manifest_payload["interaction"]["protocol_version"], INTERACTIVE_PROTOCOL_VERSION)
                self.assertEqual(manifest_payload["interaction"]["action_channels"], list(INTERACTIVE_ACTION_CHANNELS))
                self.assertEqual(manifest_payload["interaction"]["backend_mode"], "interactive_patched")
                protocol.session_ready_path.write_text(
                    json.dumps(
                        {
                            "state": {
                                "day_index": 0,
                                "stage": "vegetative",
                                "stage_index": 1,
                                "soil_moisture": 0.5,
                                "root_zone_water_mm": 180.0,
                                "soil_nitrogen_kg_ha": 120.0,
                                "canopy_cover": 0.2,
                                "biomass_kg_ha": 100.0,
                                "water_stress": 0.1,
                                "nitrogen_stress": 0.1,
                                "tmean_c": 22.0,
                                "precipitation_mm": 0.0,
                                "et0_mm": 4.0,
                                "radiation_mj_m2": 18.0,
                            },
                            "run_dir": str(run_dir),
                            "info": {
                                "mode": "fake",
                                "protocol_version": INTERACTIVE_PROTOCOL_VERSION,
                            },
                        },
                        indent=2,
                    ),
                    encoding="utf-8",
                )
                request_path = protocol.request_path(0)
                while not request_path.exists():
                    time.sleep(0.01)
                request_payload = json.loads(request_path.read_text(encoding="utf-8"))
                self.assertEqual(request_payload["action"]["irrigation_mm"], 10.0)
                protocol.response_path(0).write_text(
                    json.dumps(
                        {
                            "next_state": {
                                "day_index": 5,
                                "stage": "vegetative",
                                "stage_index": 1,
                                "soil_moisture": 0.48,
                                "root_zone_water_mm": 182.0,
                                "soil_nitrogen_kg_ha": 116.0,
                                "canopy_cover": 0.3,
                                "biomass_kg_ha": 150.0,
                                "water_stress": 0.08,
                                "nitrogen_stress": 0.09,
                                "tmean_c": 23.0,
                                "precipitation_mm": 2.0,
                                "et0_mm": 4.1,
                                "radiation_mj_m2": 18.5,
                            },
                            "reward": 4.5,
                            "done": True,
                            "daily_trace": [{"day_index": 5, "reward": 4.5, "done": True}],
                            "final_outcome": {
                                "yield_kg_ha": 7100.0,
                                "biomass_kg_ha": 150.0,
                                "total_irrigation_mm": 10.0,
                                "total_nitrogen_kg_ha": 20.0,
                                "water_use_efficiency": 0.0,
                                "nitrogen_use_efficiency": 0.0,
                                "cumulative_reward": 4.5,
                                "environmental_metrics": {},
                            },
                            "run_dir": str(run_dir),
                            "info": {"decision_interval_days": 5},
                        },
                        indent=2,
                    ),
                    encoding="utf-8",
                )
                while not protocol.close_request_path.exists():
                    time.sleep(0.01)
                protocol.final_outcome_path.write_text(
                    json.dumps(
                        {
                            "yield_kg_ha": 7100.0,
                            "biomass_kg_ha": 150.0,
                            "total_irrigation_mm": 10.0,
                            "total_nitrogen_kg_ha": 20.0,
                            "water_use_efficiency": 0.0,
                            "nitrogen_use_efficiency": 0.0,
                            "cumulative_reward": 4.5,
                            "environmental_metrics": {},
                        },
                        indent=2,
                    ),
                    encoding="utf-8",
                )

            worker = threading.Thread(target=controller_thread, daemon=True)
            worker.start()

            reset_result = transport.start_session(self.scenario)
            self.assertEqual(reset_result.state.day_index, 0)

            step_result = transport.step_session(
                CropAction(irrigation_mm=10.0, nitrogen_kg_ha=20.0),
                decision_interval_days=5,
            )
            self.assertTrue(step_result.done)
            self.assertEqual(step_result.next_state.day_index, 5)
            self.assertEqual(step_result.reward, 4.5)

            final_outcome = transport.close_session()
            self.assertIsNotNone(final_outcome)
            assert final_outcome is not None
            self.assertEqual(final_outcome.yield_kg_ha, 7100.0)

    def test_build_filesystem_transport_from_env_uses_interactive_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            template_root = root / "templates"
            runtime_root = root / "runtime"
            work_root = root / "runs"
            (template_root / "maize_quzhou_base").mkdir(parents=True, exist_ok=True)
            runtime_root.mkdir(parents=True, exist_ok=True)
            previous = {name: os.environ.get(name) for name in (
                "DSSAT_PATCHED_HOME",
                "DSSAT_WORK_ROOT",
                "DSSAT_TEMPLATE_ROOT",
                "DSSAT_PATCHED_INTERACTIVE_LAUNCH_COMMAND",
                "DSSAT_INTERACTIVE_PROTOCOL_DIRNAME",
                "DSSAT_INTERACTIVE_CONTROLLER_LOG_FILENAME",
                "DSSAT_INTERACTIVE_POLL_INTERVAL_SECONDS",
                "DSSAT_INTERACTIVE_READY_TIMEOUT_SECONDS",
                "DSSAT_INTERACTIVE_STEP_TIMEOUT_SECONDS",
                "DSSAT_INTERACTIVE_CLOSE_TIMEOUT_SECONDS",
            )}
            os.environ["DSSAT_PATCHED_HOME"] = str(runtime_root)
            os.environ["DSSAT_WORK_ROOT"] = str(work_root)
            os.environ["DSSAT_TEMPLATE_ROOT"] = str(template_root)
            os.environ["DSSAT_PATCHED_INTERACTIVE_LAUNCH_COMMAND"] = "python -c \"pass\""
            os.environ["DSSAT_INTERACTIVE_PROTOCOL_DIRNAME"] = "proto"
            os.environ["DSSAT_INTERACTIVE_CONTROLLER_LOG_FILENAME"] = "patched-controller.log"
            os.environ["DSSAT_INTERACTIVE_POLL_INTERVAL_SECONDS"] = "0.05"
            os.environ["DSSAT_INTERACTIVE_READY_TIMEOUT_SECONDS"] = "11"
            os.environ["DSSAT_INTERACTIVE_STEP_TIMEOUT_SECONDS"] = "12"
            os.environ["DSSAT_INTERACTIVE_CLOSE_TIMEOUT_SECONDS"] = "13"
            try:
                transport = build_filesystem_interactive_transport_from_env(self.scenario, runtime_role="patched")
            finally:
                for name, value in previous.items():
                    if value is None:
                        os.environ.pop(name, None)
                    else:
                        os.environ[name] = value

            self.assertEqual(transport.protocol.root_dir.name, "proto")
            self.assertEqual(transport.controller.log_filename, "patched-controller.log")
            self.assertEqual(transport.controller_log_path.name, "patched-controller.log")
            self.assertEqual(transport.controller.poll_interval_seconds, 0.05)
            self.assertEqual(transport.controller.ready_timeout_seconds, 11.0)
            self.assertEqual(transport.controller.step_timeout_seconds, 12.0)
            self.assertEqual(transport.controller.close_timeout_seconds, 13.0)
            self.assertIn(str(work_root), str(transport.run_dir))

    def test_launch_controller_formats_absolute_controller_script_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            protocol = FileSystemInteractiveProtocol(root_dir=root / "protocol")
            run_dir = root / "run"
            run_dir.mkdir(parents=True, exist_ok=True)
            controller = FileSystemInteractiveControllerConfig(
                launch_command="python {controller_script} --driver-mode patched_runtime_subprocess {session_manifest}",
            )
            transport = FileSystemInteractiveDSSATTransport(
                protocol=protocol,
                controller=controller,
                run_dir=run_dir,
            )
            with mock.patch("transdssat.dssat.interactive.subprocess.Popen") as popen:
                transport._launch_controller()
            if transport._controller_log_handle is not None:
                transport._controller_log_handle.close()
                transport._controller_log_handle = None

            self.assertTrue(popen.called)
            command = popen.call_args.args[0]
            self.assertIn(str(INTERACTIVE_CONTROLLER_SCRIPT_PATH), command)
            self.assertIn(str(protocol.session_manifest_path), command)
            self.assertEqual(popen.call_args.kwargs["cwd"], run_dir)
            self.assertEqual(popen.call_args.kwargs["stderr"], mock.ANY)
            self.assertNotEqual(popen.call_args.kwargs["stdout"], None)
            self.assertTrue(transport.controller_log_path.exists())

    def test_wait_for_json_surfaces_controller_log_tail_on_early_exit(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            protocol = FileSystemInteractiveProtocol(root_dir=root / "protocol")
            run_dir = root / "run"
            run_dir.mkdir(parents=True, exist_ok=True)
            controller = FileSystemInteractiveControllerConfig(
                launch_command="python -c \"pass\"",
                log_filename="controller.log",
                poll_interval_seconds=0.01,
            )
            transport = FileSystemInteractiveDSSATTransport(
                protocol=protocol,
                controller=controller,
                run_dir=run_dir,
            )
            transport.controller_log_path.write_text("line1\nfatal startup mismatch\n", encoding="utf-8")

            class FakeProcess:
                def poll(self) -> int:
                    return 1

            transport.process = FakeProcess()

            with self.assertRaises(RuntimeError) as ctx:
                transport._wait_for_json(
                    protocol.session_ready_path,
                    timeout_seconds=0.02,
                    timeout_label="interactive session ready state",
                )

            message = str(ctx.exception)
            self.assertIn("controller.log", message)
            self.assertIn("fatal startup mismatch", message)

    def test_wait_for_json_recovers_terminal_step_response_from_final_outcome(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            protocol = FileSystemInteractiveProtocol(root_dir=root / "protocol")
            protocol.root_dir.mkdir(parents=True, exist_ok=True)
            run_dir = root / "run"
            run_dir.mkdir(parents=True, exist_ok=True)
            controller = FileSystemInteractiveControllerConfig(
                launch_command="python -c \"pass\"",
                log_filename="controller.log",
                poll_interval_seconds=0.01,
            )
            transport = FileSystemInteractiveDSSATTransport(
                protocol=protocol,
                controller=controller,
                run_dir=run_dir,
            )
            transport.controller_log_path.write_text("normal season end\n", encoding="utf-8")
            transport.current_step_index = 7
            transport._last_cumulative_reward = 1.25
            (protocol.root_dir / "interactive_progress.json").write_text(
                json.dumps(
                    {
                        "run_dir": str(run_dir),
                        "last_state": {
                            "day_index": 125,
                            "stage": "in_season",
                            "stage_index": 1,
                            "soil_moisture": 0.78,
                            "root_zone_water_mm": 22.9,
                            "soil_nitrogen_kg_ha": 4.56,
                            "canopy_cover": 0.02,
                            "biomass_kg_ha": 0.0,
                            "water_stress": 1.0,
                            "nitrogen_stress": 0.75,
                            "tmean_c": 18.7,
                            "precipitation_mm": 5.8,
                            "et0_mm": 0.35,
                            "radiation_mj_m2": 18.6,
                        },
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            protocol.final_outcome_path.write_text(
                json.dumps(
                    {
                        "yield_kg_ha": 1623.0,
                        "biomass_kg_ha": 3391.0,
                        "total_irrigation_mm": 0.0,
                        "total_nitrogen_kg_ha": 0.0,
                        "water_use_efficiency": 0.0,
                        "nitrogen_use_efficiency": 0.0,
                        "cumulative_reward": 1.815426,
                        "environmental_metrics": {},
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )

            class FakeProcess:
                def poll(self) -> int:
                    return 0

            transport.process = FakeProcess()
            payload = transport._wait_for_json(
                protocol.response_path(7),
                timeout_seconds=0.02,
                timeout_label="interactive step response 7",
            )

            self.assertTrue(payload["done"])
            self.assertTrue(payload["info"]["terminal_response_recovered"])
            self.assertEqual(payload["next_state"]["day_index"], 125)
            self.assertAlmostEqual(payload["reward"], 1.815426 - 1.25, places=6)
            self.assertTrue(protocol.response_path(7).exists())

    def test_step_session_writes_request_atomically_without_tmp_suffix_leak(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            protocol = FileSystemInteractiveProtocol(root_dir=root / "protocol")
            run_dir = root / "run"
            run_dir.mkdir(parents=True, exist_ok=True)
            controller = FileSystemInteractiveControllerConfig(
                launch_command="python -c \"pass\"",
                poll_interval_seconds=0.01,
                ready_timeout_seconds=2.0,
                step_timeout_seconds=2.0,
                close_timeout_seconds=2.0,
            )
            transport = FileSystemInteractiveDSSATTransport(
                protocol=protocol,
                controller=controller,
                run_dir=run_dir,
            )

            def controller_thread() -> None:
                while not protocol.session_manifest_path.exists():
                    time.sleep(0.01)
                protocol.session_ready_path.write_text(
                    json.dumps(
                        {
                            "state": {
                                "day_index": 0,
                                "stage": "vegetative",
                                "stage_index": 1,
                                "soil_moisture": 0.5,
                                "root_zone_water_mm": 180.0,
                                "soil_nitrogen_kg_ha": 120.0,
                                "canopy_cover": 0.2,
                                "biomass_kg_ha": 100.0,
                                "water_stress": 0.1,
                                "nitrogen_stress": 0.1,
                                "tmean_c": 22.0,
                                "precipitation_mm": 0.0,
                                "et0_mm": 4.0,
                                "radiation_mj_m2": 18.0,
                            },
                            "run_dir": str(run_dir),
                            "info": {},
                        },
                        indent=2,
                    ),
                    encoding="utf-8",
                )
                request_path = protocol.request_path(0)
                while not request_path.exists():
                    self.assertFalse(request_path.with_name(f"{request_path.name}.tmp").exists())
                    time.sleep(0.01)
                payload = json.loads(request_path.read_text(encoding="utf-8"))
                self.assertEqual(payload["action"]["irrigation_mm"], 3.0)
                self.assertFalse(request_path.with_name(f"{request_path.name}.tmp").exists())
                protocol.response_path(0).write_text(
                    json.dumps(
                        {
                            "next_state": {
                                "day_index": 5,
                                "stage": "vegetative",
                                "stage_index": 1,
                                "soil_moisture": 0.48,
                                "root_zone_water_mm": 182.0,
                                "soil_nitrogen_kg_ha": 116.0,
                                "canopy_cover": 0.3,
                                "biomass_kg_ha": 150.0,
                                "water_stress": 0.08,
                                "nitrogen_stress": 0.09,
                                "tmean_c": 23.0,
                                "precipitation_mm": 2.0,
                                "et0_mm": 4.1,
                                "radiation_mj_m2": 18.5,
                            },
                            "reward": 1.0,
                            "done": False,
                            "daily_trace": [],
                            "run_dir": str(run_dir),
                            "info": {},
                        },
                        indent=2,
                    ),
                    encoding="utf-8",
                )

            worker = threading.Thread(target=controller_thread, daemon=True)
            worker.start()

            transport.start_session(self.scenario)
            step_result = transport.step_session(
                CropAction(irrigation_mm=3.0, nitrogen_kg_ha=0.0),
                decision_interval_days=5,
            )
            self.assertEqual(step_result.next_state.day_index, 5)
            transport._cleanup_process()


if __name__ == "__main__":
    unittest.main()
