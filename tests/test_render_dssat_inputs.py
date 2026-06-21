from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest


def load_render_module():
    root = Path(__file__).resolve().parents[1]
    script_path = root / "scripts" / "render_dssat_inputs.py"
    spec = importlib.util.spec_from_file_location("render_dssat_inputs_for_tests", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load module from {script_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


render = load_render_module()


class RenderDSSATInputsTests(unittest.TestCase):
    def test_find_experiment_file_supports_rice_rix(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            experiment_path = run_dir / "WHRI2101.RIX"
            experiment_path.write_text("*EXP.DETAILS: TEST\n", encoding="utf-8")

            selected = render.find_experiment_file(
                run_dir,
                {"experiment_file": "WHRI2101.RIX"},
            )

        self.assertEqual(selected.name, "WHRI2101.RIX")

    def test_preferred_experiment_name_accepts_rice_suffix_from_run_command(self) -> None:
        previous = os.environ.get("DSSAT_RUN_COMMAND")
        os.environ["DSSAT_RUN_COMMAND"] = "/fs/fast/runtime/dscsm048 B WHRI2101.RIX"
        try:
            selected = render.preferred_experiment_name({})
        finally:
            if previous is None:
                os.environ.pop("DSSAT_RUN_COMMAND", None)
            else:
                os.environ["DSSAT_RUN_COMMAND"] = previous

        self.assertEqual(selected, "WHRI2101.RIX")

    def test_build_cultivar_override_for_denghai605(self) -> None:
        scenario_payload = {
            "crop_name": "maize",
            "crop_context": {
                "crop_name": "maize",
                "cultivar": {
                    "cultivar_id": "denghai605",
                    "cultivar_name": "登海605",
                    "parameter_names": ["P1", "P2", "P5", "G2", "G3", "PHINT"],
                    "parameter_vector": [340.9, 1.61, 700.0, 600.0, 10.5, 60.0],
                    "dssat_cultivar_code": "DH6051",
                    "dssat_genotype_file": "MZCER048.CUL",
                    "dssat_ecotype_code": "IB0001",
                },
            },
        }

        override = render.build_cultivar_override(scenario_payload)

        self.assertIsNotNone(override)
        self.assertEqual(override.cultivar_code, "DH6051")
        self.assertEqual(override.cultivar_name, "DENGHAI605")
        self.assertEqual(override.genotype_file, "MZCER048.CUL")
        self.assertEqual(override.parameter_values, [340.9, 1.61, 700.0, 600.0, 10.5, 60.0])

    def test_materialize_cultivar_file_and_replace_block(self) -> None:
        scenario_payload = {
            "crop_name": "maize",
            "crop_context": {
                "crop_name": "maize",
                "cultivar": {
                    "cultivar_id": "denghai605",
                    "cultivar_name": "登海605",
                    "parameter_names": ["P1", "P2", "P5", "G2", "G3", "PHINT"],
                    "parameter_vector": [340.9, 1.61, 700.0, 600.0, 10.5, 60.0],
                    "dssat_cultivar_code": "DH6051",
                    "dssat_genotype_file": "MZCER048.CUL",
                    "dssat_ecotype_code": "IB0001",
                },
            },
        }
        override = render.build_cultivar_override(scenario_payload)
        assert override is not None

        experiment_lines = [
            "*EXP.DETAILS: TEST",
            "*TREATMENTS",
            "@N R O C TNAME.................... CU FL SA IC MP MI MF MR MC MT ME MH SM",
            " 1 1 0 0 DEMO                      1  1  0  1  1  1  1  0  0  0  0  0  1",
            "*CULTIVARS",
            "@C CR INGENO CNAME",
            " 1 MZ IB0035 McCurdy 84aa",
            "*FIELDS",
            "@L ID_FIELD WSTA....  FLSA  FLOB  FLDT  FLDD  FLDS  FLST SLTX  SLDP  ID_SOIL    FLNAME",
            " 1 UFGA0002 UFGA       -99     0 DR000     0     0 00000 -99    180  IBMZ910014 Field section",
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            runtime_genotype_dir = root / "runtime" / "Genotype"
            runtime_genotype_dir.mkdir(parents=True, exist_ok=True)
            (runtime_genotype_dir / "MZCER048.CUL").write_text(
                "\n".join(
                    [
                        "*MAIZE CULTIVAR COEFFICIENTS: MZCER048 MODEL",
                        "@VAR#  VRNAME.......... EXPNO   ECO#    P1    P2    P5    G2    G3 PHINT",
                        "IB0035 McCurdy 84aa         . IB0001 259.0 1.193 947.1 924.3 8.168 43.00",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            run_dir = root / "run"
            run_dir.mkdir(parents=True, exist_ok=True)
            scenario_path = run_dir / "transdssat_scenario.json"
            scenario_path.write_text(json.dumps(scenario_payload, ensure_ascii=False), encoding="utf-8")

            previous_home = os.environ.get("DSSAT_HOME")
            os.environ["DSSAT_HOME"] = str(root / "runtime")
            try:
                cultivar_path = render.materialize_cultivar_file(run_dir, override)
                updated_lines = render.replace_cultivar_block(experiment_lines, override)
            finally:
                if previous_home is None:
                    os.environ.pop("DSSAT_HOME", None)
                else:
                    os.environ["DSSAT_HOME"] = previous_home

            written = cultivar_path.read_text(encoding="utf-8")
            self.assertIn("DH6051", written)
            self.assertIn("DENGHAI605", written)
            self.assertIn(" 340.9 1.610 700.0 600.0 10.500 60.00", written)
            self.assertEqual(updated_lines[6], " 1 MZ DH6051 DENGHAI605")


if __name__ == "__main__":
    unittest.main()
