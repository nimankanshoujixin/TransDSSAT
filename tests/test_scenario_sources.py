from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from transdssat.scenario_sources import load_scenario_from_json, resolve_scenario
from transdssat.scenarios import build_quzhou_scenarios


class ScenarioSourceTests(unittest.TestCase):
    def test_load_scenario_from_json_round_trips_simulation_scenario(self) -> None:
        scenario = build_quzhou_scenarios(
            target_count=1,
            engines=("dssat_official",),
            crops_filter=("maize",),
            sampling_mode="random",
            seed=20260622,
        )[0]
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "scenario.json"
            path.write_text(json.dumps(scenario.to_dict(), ensure_ascii=False), encoding="utf-8")
            restored = load_scenario_from_json(path)

        self.assertEqual(restored.scenario_id, scenario.scenario_id)
        self.assertEqual(restored.crop_spec.crop_name, "maize")
        self.assertEqual(restored.experiment_file, scenario.experiment_file)

    def test_resolve_scenario_supports_real_subset_rice(self) -> None:
        scenario = resolve_scenario(
            source="real_subset",
            subset_id="wuhu_rice_calibrated",
            treatment_no=11,
        )

        self.assertEqual(scenario.crop_spec.crop_name, "rice")
        self.assertEqual(scenario.site_name, "wuhu")
        self.assertTrue(scenario.experiment_file.endswith(".RIX"))
        self.assertTrue(Path(scenario.template_name).is_absolute())

    def test_resolve_scenario_requires_json_path_for_json_source(self) -> None:
        with self.assertRaises(ValueError):
            resolve_scenario(source="json")
