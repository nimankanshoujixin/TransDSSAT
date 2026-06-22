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

    def test_replace_fertilizer_block_preserves_harvest_details_section(self) -> None:
        lines = [
            "*FERTILIZERS (INORGANIC)",
            "@F FDATE  FMCD FACD FDEP  FAMN  FAMP  FAMK  FAMC  FAMO FOCD FERNAME",
            " 1 21185 FE005 AP001    5  47.2   0.0   0.0   0.0   0.0 -99  N_FERT",
            "",
            "*HARVEST DETAILS",
            "@H HDATE  HSTG  HCOM HSIZE   HPC  HBPC HNAME",
            " 1 21309 GS000   -99   -99   -99   -99 HARV_11",
            "",
            "*SIMULATION CONTROLS",
            "@N GENERAL     NYERS NREPS START SDATE RSEED SNAME.................... SMODEL",
        ]

        updated = render.replace_fertilizer_block(
            lines,
            [
                "@F FDATE  FMCD  FACD  FDEP  FAMN  FAMP  FAMK  FAMC  FAMO  FOCD FERNAME",
                " 1 21190 FE001 AP001    10  11.9     0     0     0     0   -99 TRNSDAT",
            ],
        )

        self.assertIn("*HARVEST DETAILS", updated)
        harvest_index = updated.index("*HARVEST DETAILS")
        self.assertEqual(updated[harvest_index + 2], " 1 21309 GS000   -99   -99   -99   -99 HARV_11")

    def test_replace_primary_dates_shifts_harvest_details_dates_by_planting_delta(self) -> None:
        lines = [
            "*PLANTING DETAILS",
            "@P PDATE EDATE  PPOP  PPOE  PLME  PLDS  PLRS  PLRD  PLDP  PLWT  PAGE  PENV  PLPH  SPRL                        PLNAME",
            " 1 21185   -99    30    30     T     H    25     0     3     0    30    25     1     0                        TRANSPLANT",
            "",
            "*HARVEST DETAILS",
            "@H HDATE  HSTG  HCOM HSIZE   HPC  HBPC HNAME",
            " 1 21309 GS000   -99   -99   -99   -99 HARV_11",
            " 2 21312 GS000   -99   -99   -99   -99 HARV_12",
        ]

        updated = render.replace_primary_dates(lines, "21200")

        self.assertEqual(updated[2].split()[1], "21200")
        self.assertEqual(updated[6].split()[1], "21324")
        self.assertEqual(updated[7].split()[1], "21327")

    def test_replace_primary_dates_keeps_multi_treatment_start_before_earliest_planting(self) -> None:
        lines = [
            "@N GENERAL     NYERS NREPS START SDATE RSEED SNAME.................... SMODEL",
            " 1 GE              1     1     S 21184  2150 WUHU_RICE_2021          RICE",
            "*INITIAL CONDITIONS",
            "@C   PCR ICDAT  ICRT  ICND  ICRN  ICRE  ICWD ICRES ICREN ICREP ICRIP ICRID ICNAME",
            " 1    WH 21150   500   -99     1     1   -99     0     0     0   100    15 INIT_01",
            " 2    WH 21151   500   -99     1     1   -99     0     0     0   100    15 INIT_02",
            "*PLANTING DETAILS",
            "@P PDATE EDATE  PPOP  PPOE  PLME  PLDS  PLRS  PLRD  PLDP  PLWT  PAGE  PENV  PLPH  SPRL                        PLNAME",
            " 1 21151   -99    30    30     T     H    30     0     3     0    30    25     1     0                        TRANSPLANT",
            " 2 21152   -99    30    30     T     H    30     0     3     0    30    25     1     0                        TRANSPLANT",
        ]

        updated = render.replace_primary_dates(lines, "21185")

        self.assertEqual(updated[1].split()[5], "21184")
        self.assertEqual(updated[4].split()[2], "21184")
        self.assertEqual(updated[5].split()[2], "21185")
        self.assertEqual(updated[8].split()[1], "21185")
        self.assertEqual(updated[9].split()[1], "21186")

    def test_single_treatment_policy_replacement_preserves_other_treatments(self) -> None:
        lines = [
            "*IRRIGATION AND WATER MANAGEMENT",
            "@I  EFIR  IDEP  ITHR  IEPT  IOFF  IAME  IAMT IRNAME",
            " 1     1   -99   -99   -99   -99   -99     2 WATER_01",
            "@I IDATE  IROP IRVAL",
            " 1 21151 IR003    30",
            " 2     1   -99   -99   -99   -99   -99     2 WATER_02",
            "@I IDATE  IROP IRVAL",
            " 2 21152 IR003    30",
            "*FERTILIZERS (INORGANIC)",
            "@F FDATE  FMCD FACD FDEP  FAMN  FAMP  FAMK  FAMC  FAMO FOCD FERNAME",
            " 1 21151 FE005 AP001    5 127.0   0.0   0.0   0.0   0.0 -99  N_FERT",
            " 2 21152 FE005 AP001    5 135.1   0.0   0.0   0.0   0.0 -99  N_FERT",
            "*SIMULATION CONTROLS",
        ]
        policy = [
            render.PolicyRow(stage="event_01", date="2021-07-04", day_index=0, irrigation_mm=8.8, nitrogen_kg_ha=11.9),
            render.PolicyRow(stage="event_02", date="2021-07-14", day_index=10, irrigation_mm=4.7, nitrogen_kg_ha=7.5),
        ]

        updated = render.replace_single_treatment_irrigation_block(lines, 1, policy)
        updated = render.replace_single_treatment_fertilizer_block(updated, 1, policy)
        text = "\n".join(updated)

        self.assertIn(" 1 21185 IR003   8.8", text)
        self.assertIn(" 1 21195 IR003   4.7", text)
        self.assertIn(" 2 21152 IR003    30", text)
        self.assertIn(" 1 21185 FE005 AP001     5  11.9", text)
        self.assertIn(" 1 21195 FE005 AP001     5   7.5", text)
        self.assertIn(" 2 21152 FE005 AP001    5 135.1", text)

    def test_single_treatment_zero_action_policy_keeps_original_management_blocks(self) -> None:
        lines = [
            "*IRRIGATION AND WATER MANAGEMENT",
            "@I  EFIR  IDEP  ITHR  IEPT  IOFF  IAME  IAMT IRNAME",
            "11     1   -99   -99   -99   -99   -99     2 WATER_11",
            "@I IDATE  IROP IRVAL",
            "11 21185 IR003    30",
            "*FERTILIZERS (INORGANIC)",
            "@F FDATE  FMCD FACD FDEP  FAMN  FAMP  FAMK  FAMC  FAMO FOCD FERNAME",
            "11 21185 FE005 AP001    5 127.0   0.0   0.0   0.0   0.0 -99  N_FERT",
            "*SIMULATION CONTROLS",
        ]

        updated = render.replace_single_treatment_irrigation_block(lines, 11, [])
        updated = render.replace_single_treatment_fertilizer_block(updated, 11, [])

        self.assertEqual(updated, lines)

    def test_extract_treatment_planting_date_returns_requested_treatment(self) -> None:
        lines = [
            "*PLANTING DETAILS",
            "@P PDATE EDATE  PPOP  PPOE  PLME  PLDS  PLRS  PLRD  PLDP  PLWT  PAGE  PENV  PLPH  SPRL                        PLNAME",
            " 1 21151   -99    30    30     T     H    30     0     3     0    30    25     1     0                        TRANSPLANT",
            "11 21185   -99    28    28     T     H    25     0     3     0    30    25     1     0                        TRANSPLANT",
        ]

        self.assertEqual(render.extract_treatment_planting_date(lines, 11), "21185")


if __name__ == "__main__":
    unittest.main()
