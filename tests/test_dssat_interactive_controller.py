from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest import mock

from transdssat.domain import CropOutcome, CropState
from transdssat.dssat.interactive import FileSystemInteractiveProtocol
from transdssat.dssat.interactive_controller import (
    build_interactive_controller_driver,
    InteractiveEvaluationSnapshot,
    INTERACTIVE_DRIVER_MODE_PATCHED_SUBPROCESS,
    load_interaction_metadata_from_manifest,
    ReplayBridgeInteractiveController,
    resolve_interactive_driver_mode,
    load_scenario_from_manifest,
    PROJECT_ROOT,
    validate_interaction_metadata,
)
from transdssat.scenarios import SimulationScenario, build_quzhou_scenarios
from transdssat.season import StageDecision


class _FakeReplayEvaluator:
    def __init__(self) -> None:
        self.calls: list[list[StageDecision]] = []

    def evaluate_actions(self, actions: list[StageDecision]) -> InteractiveEvaluationSnapshot:
        self.calls.append(list(actions))
        if not actions:
            return InteractiveEvaluationSnapshot(
                trajectory_states=[
                    CropState(0, "vegetative", 1, 0.50, 180.0, 120.0, 0.20, 100.0, 0.10, 0.10, 22.0, 0.0, 4.0, 18.0),
                    CropState(5, "vegetative", 1, 0.48, 182.0, 118.0, 0.28, 160.0, 0.08, 0.09, 23.0, 2.0, 4.2, 18.5),
                ],
                outcome=CropOutcome(7000.0, 160.0, 0.0, 0.0, 0.0, 0.0, 0.0, {}),
                cumulative_reward=0.0,
                daily_trace=[{"day_index": 0, "reward": 0.0, "done": False}],
                run_dir="run-0",
            )
        return InteractiveEvaluationSnapshot(
            trajectory_states=[
                CropState(0, "vegetative", 1, 0.50, 180.0, 120.0, 0.20, 100.0, 0.10, 0.10, 22.0, 0.0, 4.0, 18.0),
                CropState(5, "reproductive", 2, 0.52, 190.0, 112.0, 0.35, 220.0, 0.05, 0.06, 24.0, 1.5, 4.1, 19.0),
            ],
            outcome=CropOutcome(7600.0, 220.0, 12.0, 18.0, 0.0, 0.0, 3.25, {}),
            cumulative_reward=3.25,
            daily_trace=[{"day_index": 0, "reward": 3.25, "done": True}],
            run_dir="run-1",
        )


class InteractiveControllerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.scenario = build_quzhou_scenarios(
            target_count=1,
            engines=("dssat_official",),
            crops_filter=("maize",),
            sampling_mode="random",
            seed=20260621,
        )[0]

    def test_scenario_roundtrip_from_dict(self) -> None:
        restored = SimulationScenario.from_dict(self.scenario.to_dict())
        self.assertEqual(restored.scenario_id, self.scenario.scenario_id)
        self.assertEqual(restored.crop_spec.crop_name, self.scenario.crop_spec.crop_name)
        self.assertEqual(restored.soil_profile.soil_name, self.scenario.soil_profile.soil_name)
        self.assertEqual(len(restored.weather), len(self.scenario.weather))
        self.assertEqual(restored.crop_context.cultivar.cultivar_id, self.scenario.crop_context.cultivar.cultivar_id)

    def test_replay_bridge_controller_handles_protocol_loop(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            protocol = FileSystemInteractiveProtocol(root_dir=root / "protocol")
            protocol.root_dir.mkdir(parents=True, exist_ok=True)
            manifest_path = protocol.session_manifest_path
            manifest_path.write_text(
                json.dumps(
                    {
                        "scenario": self.scenario.to_dict(),
                        "protocol": protocol.to_dict(),
                        "interaction": {
                            "protocol_version": "patched-dssat-v1",
                            "engine_name": "dssat_official",
                            "backend_mode": "interactive_patched",
                            "runtime_role": "patched",
                            "run_dir": str(root / "run"),
                            "crop_name": self.scenario.crop_spec.crop_name,
                            "action_channels": ["irrigation_mm", "nitrogen_kg_ha"],
                            "decision_interval_days": self.scenario.decision_context.decision_interval_days,
                            "state_interface_contract": self.scenario.state_interface_contract_dict(),
                            "poll_interval_seconds": 0.01,
                        },
                    },
                    indent=2,
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            loaded = load_scenario_from_manifest(json.loads(manifest_path.read_text(encoding="utf-8")))
            self.assertEqual(loaded.scenario_id, self.scenario.scenario_id)
            interaction = load_interaction_metadata_from_manifest(
                json.loads(manifest_path.read_text(encoding="utf-8"))
            )
            self.assertEqual(interaction["protocol_version"], "patched-dssat-v1")

            evaluator = _FakeReplayEvaluator()
            controller = ReplayBridgeInteractiveController(
                scenario=loaded,
                protocol=protocol,
                evaluator=evaluator,
                poll_interval_seconds=0.01,
            )
            worker = threading.Thread(target=controller.run, daemon=True)
            worker.start()

            deadline = time.time() + 2.0
            while not protocol.session_ready_path.exists() and time.time() < deadline:
                time.sleep(0.01)
            self.assertTrue(protocol.session_ready_path.exists())
            ready_payload = json.loads(protocol.session_ready_path.read_text(encoding="utf-8"))
            self.assertEqual(
                ready_payload["info"]["backend_mode"],
                "season_replay_wrapper_external_controller",
            )

            protocol.request_path(0).write_text(
                json.dumps(
                    {
                        "step_index": 0,
                        "decision_interval_days": 5,
                        "action": {"irrigation_mm": 12.0, "nitrogen_kg_ha": 18.0},
                    },
                    indent=2,
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            while not protocol.response_path(0).exists() and time.time() < deadline:
                time.sleep(0.01)
            self.assertTrue(protocol.response_path(0).exists())
            response = json.loads(protocol.response_path(0).read_text(encoding="utf-8"))
            self.assertTrue(response["done"])
            self.assertEqual(response["reward"], 3.25)
            self.assertEqual(response["next_state"]["day_index"], 5)
            self.assertEqual(response["final_outcome"]["yield_kg_ha"], 7600.0)

            protocol.close_request_path.write_text(json.dumps({"close": True}), encoding="utf-8")
            while not protocol.final_outcome_path.exists() and time.time() < deadline:
                time.sleep(0.01)
            self.assertTrue(protocol.final_outcome_path.exists())
            final_outcome = json.loads(protocol.final_outcome_path.read_text(encoding="utf-8"))
            self.assertEqual(final_outcome["yield_kg_ha"], 7600.0)
            self.assertEqual(len(evaluator.calls), 2)

    def test_patched_runtime_subprocess_driver_launches_runtime_with_protocol_env(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            protocol = FileSystemInteractiveProtocol(root_dir=root / "protocol")
            protocol.root_dir.mkdir(parents=True, exist_ok=True)
            run_dir = root / "run"
            run_dir.mkdir(parents=True, exist_ok=True)
            runtime_root = root / "runtime"
            runtime_root.mkdir(parents=True, exist_ok=True)
            manifest_path = protocol.session_manifest_path
            manifest_payload = {
                "scenario": self.scenario.to_dict(),
                "protocol": protocol.to_dict(),
                "interaction": {
                    "protocol_version": "patched-dssat-v1",
                    "engine_name": "dssat_official",
                    "backend_mode": "interactive_patched",
                    "runtime_role": "patched",
                    "run_dir": str(run_dir),
                    "crop_name": self.scenario.crop_spec.crop_name,
                    "action_channels": ["irrigation_mm", "nitrogen_kg_ha"],
                    "decision_interval_days": self.scenario.decision_context.decision_interval_days,
                    "state_interface_contract": self.scenario.state_interface_contract_dict(),
                    "poll_interval_seconds": 0.01,
                },
            }
            manifest_path.write_text(
                json.dumps(manifest_payload, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            interaction = validate_interaction_metadata(
                load_interaction_metadata_from_manifest(
                    json.loads(manifest_path.read_text(encoding="utf-8"))
                )
            )
            scenario = load_scenario_from_manifest(json.loads(manifest_path.read_text(encoding="utf-8")))
            driver_mode = resolve_interactive_driver_mode(
                INTERACTIVE_DRIVER_MODE_PATCHED_SUBPROCESS,
                interaction=interaction,
            )
            driver = build_interactive_controller_driver(
                driver_mode=driver_mode,
                manifest_path=manifest_path,
                scenario=scenario,
                protocol=protocol,
                interaction=interaction,
            )
            previous = {name: os.environ.get(name) for name in ("DSSAT_PATCHED_HOME", "DSSAT_PATCHED_RUN_COMMAND")}
            fake_runtime_path = root / "fake_interactive_runtime.py"
            fake_runtime_path.write_text(
                "\n".join(
                    [
                        "import json",
                        "import os",
                        "from pathlib import Path",
                        "",
                        "protocol_dir = Path(os.environ['DSSAT_INTERACTIVE_PROTOCOL_DIR'])",
                        "protocol_dir.mkdir(parents=True, exist_ok=True)",
                        "ready_payload = {",
                        "    'state': {",
                        "        'day_index': 0,",
                        "        'stage': 'vegetative',",
                        "        'stage_index': 1,",
                        "        'soil_moisture': 0.5,",
                        "        'root_zone_water_mm': 180.0,",
                        "        'soil_nitrogen_kg_ha': 120.0,",
                        "        'canopy_cover': 0.2,",
                        "        'biomass_kg_ha': 100.0,",
                        "        'water_stress': 0.1,",
                        "        'nitrogen_stress': 0.1,",
                        "        'tmean_c': 22.0,",
                        "        'precipitation_mm': 0.0,",
                        "        'et0_mm': 4.0,",
                        "        'radiation_mj_m2': 18.0,",
                        "    },",
                        "    'run_dir': os.getcwd(),",
                        "    'info': {",
                        "        'protocol_version': os.environ['DSSAT_INTERACTIVE_PROTOCOL_VERSION'],",
                        "        'engine_name': os.environ['DSSAT_INTERACTIVE_ENGINE_NAME'],",
                        "        'backend_mode': os.environ['DSSAT_INTERACTIVE_BACKEND_MODE'],",
                        "        'runtime_role': os.environ['DSSAT_INTERACTIVE_RUNTIME_ROLE'],",
                        "        'run_dir_env': os.environ['DSSAT_INTERACTIVE_RUN_DIR'],",
                        "        'crop_name': os.environ['DSSAT_INTERACTIVE_CROP_NAME'],",
                        "        'action_channels': os.environ['DSSAT_INTERACTIVE_ACTION_CHANNELS'],",
                        "        'decision_interval_days': os.environ['DSSAT_INTERACTIVE_DECISION_INTERVAL_DAYS'],",
                        "        'helper_command': os.environ['DSSAT_INTERACTIVE_HELPER_COMMAND'],",
                        "        'state_interface_contract_json': os.environ['DSSAT_INTERACTIVE_STATE_INTERFACE_CONTRACT_JSON'],",
                        "    },",
                        "}",
                        "(protocol_dir / 'session_ready.json').write_text(",
                        "    json.dumps(ready_payload, indent=2),",
                        "    encoding='utf-8',",
                        ")",
                        "final_payload = {",
                        "    'yield_kg_ha': 7000.0,",
                        "    'biomass_kg_ha': 150.0,",
                        "    'total_irrigation_mm': 0.0,",
                        "    'total_nitrogen_kg_ha': 0.0,",
                        "    'water_use_efficiency': 0.0,",
                        "    'nitrogen_use_efficiency': 0.0,",
                        "    'cumulative_reward': 0.0,",
                        "    'environmental_metrics': {},",
                        "}",
                        "(protocol_dir / 'final_outcome.json').write_text(",
                        "    json.dumps(final_payload, indent=2),",
                        "    encoding='utf-8',",
                        ")",
                    ]
                ),
                encoding="utf-8",
            )
            os.environ["DSSAT_PATCHED_HOME"] = str(runtime_root)
            os.environ["DSSAT_PATCHED_RUN_COMMAND"] = f"python {fake_runtime_path}"
            try:
                driver.run()
            finally:
                for name, value in previous.items():
                    if value is None:
                        os.environ.pop(name, None)
                    else:
                        os.environ[name] = value

            ready_payload = json.loads(protocol.session_ready_path.read_text(encoding="utf-8"))
            self.assertEqual(ready_payload["info"]["protocol_version"], "patched-dssat-v1")
            self.assertEqual(ready_payload["info"]["engine_name"], "dssat_official")
            self.assertEqual(ready_payload["info"]["backend_mode"], "interactive_patched")
            self.assertEqual(ready_payload["info"]["runtime_role"], "patched")
            self.assertEqual(ready_payload["info"]["run_dir_env"], str(run_dir))
            self.assertEqual(ready_payload["info"]["crop_name"], self.scenario.crop_spec.crop_name)
            self.assertEqual(ready_payload["info"]["action_channels"], "irrigation_mm,nitrogen_kg_ha")
            self.assertEqual(
                ready_payload["info"]["decision_interval_days"],
                str(self.scenario.decision_context.decision_interval_days),
            )
            helper_command = ready_payload["info"]["helper_command"]
            self.assertTrue(helper_command.startswith("python "))
            self.assertEqual(
                Path(helper_command.split(" ", 1)[1]),
                PROJECT_ROOT / "scripts" / "dssat_interactive_protocol_helper.py",
            )
            self.assertEqual(
                json.loads(ready_payload["info"]["state_interface_contract_json"]),
                self.scenario.state_interface_contract_dict(),
            )
            final_outcome = json.loads(protocol.final_outcome_path.read_text(encoding="utf-8"))
            self.assertEqual(final_outcome["yield_kg_ha"], 7000.0)

    def test_patched_runtime_subprocess_driver_formats_repo_root_placeholder(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            protocol = FileSystemInteractiveProtocol(root_dir=root / "protocol")
            protocol.root_dir.mkdir(parents=True, exist_ok=True)
            run_dir = root / "run"
            run_dir.mkdir(parents=True, exist_ok=True)
            runtime_root = root / "runtime"
            runtime_root.mkdir(parents=True, exist_ok=True)
            manifest_path = protocol.session_manifest_path
            manifest_payload = {
                "scenario": self.scenario.to_dict(),
                "protocol": protocol.to_dict(),
                "interaction": {
                    "protocol_version": "patched-dssat-v1",
                    "engine_name": "dssat_official",
                    "backend_mode": "interactive_patched",
                    "runtime_role": "patched",
                    "run_dir": str(run_dir),
                    "crop_name": self.scenario.crop_spec.crop_name,
                    "action_channels": ["irrigation_mm", "nitrogen_kg_ha"],
                    "decision_interval_days": self.scenario.decision_context.decision_interval_days,
                    "state_interface_contract": self.scenario.state_interface_contract_dict(),
                    "poll_interval_seconds": 0.01,
                },
            }
            manifest_path.write_text(json.dumps(manifest_payload, indent=2, ensure_ascii=False), encoding="utf-8")
            interaction = validate_interaction_metadata(
                load_interaction_metadata_from_manifest(json.loads(manifest_path.read_text(encoding="utf-8")))
            )
            scenario = load_scenario_from_manifest(json.loads(manifest_path.read_text(encoding="utf-8")))
            driver = build_interactive_controller_driver(
                driver_mode=INTERACTIVE_DRIVER_MODE_PATCHED_SUBPROCESS,
                manifest_path=manifest_path,
                scenario=scenario,
                protocol=protocol,
                interaction=interaction,
            )
            previous = {name: os.environ.get(name) for name in ("DSSAT_PATCHED_HOME", "DSSAT_PATCHED_RUN_COMMAND")}
            os.environ["DSSAT_PATCHED_HOME"] = str(runtime_root)
            os.environ["DSSAT_PATCHED_RUN_COMMAND"] = (
                "python {repo_root}/scripts/dssat_interactive_boundary_probe.py --mark-done-after-step"
            )
            completed = mock.Mock(returncode=0)
            try:
                with mock.patch("transdssat.dssat.interactive_controller.subprocess.run", return_value=completed) as run_mock:
                    driver.run()
            finally:
                for name, value in previous.items():
                    if value is None:
                        os.environ.pop(name, None)
                    else:
                        os.environ[name] = value

            argv = run_mock.call_args.args[0]
            self.assertEqual(argv[0], "python")
            self.assertEqual(
                Path(argv[1]),
                PROJECT_ROOT / "scripts" / "dssat_interactive_boundary_probe.py",
            )
            self.assertEqual(argv[2], "--mark-done-after-step")

    def test_replay_bridge_read_json_retries_partial_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "step_request_0000.json"
            path.write_text("", encoding="utf-8")

            def complete_file() -> None:
                time.sleep(0.03)
                path.write_text(
                    json.dumps(
                        {
                            "step_index": 0,
                            "decision_interval_days": 5,
                            "action": {"irrigation_mm": 12.0, "nitrogen_kg_ha": 18.0},
                        },
                        indent=2,
                        ensure_ascii=False,
                    ),
                    encoding="utf-8",
                )

            worker = threading.Thread(target=complete_file, daemon=True)
            worker.start()
            payload = ReplayBridgeInteractiveController._read_json(path)
            self.assertEqual(payload["action"]["irrigation_mm"], 12.0)


if __name__ == "__main__":
    unittest.main()
