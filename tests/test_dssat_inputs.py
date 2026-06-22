from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from transdssat.dssat.config import DSSATRunConfig
from transdssat.dssat.inputs import DSSATInputBuilder
from transdssat.scenarios import build_quzhou_scenarios
from transdssat.season import SeasonPolicy


class DSSATInputBuilderTests(unittest.TestCase):
    def test_explicit_template_directory_name_is_resolved(self) -> None:
        scenario = build_quzhou_scenarios(
            target_count=1,
            engines=("dssat_official",),
            crops_filter=("maize",),
            sampling_mode="random",
            seed=20260622,
        )[0]
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            template_root = root / "templates"
            custom_dir = template_root / "custom_case"
            custom_dir.mkdir(parents=True, exist_ok=True)
            (custom_dir / "DEMO.MZX").write_text("*EXP.DETAILS: TEST\n", encoding="utf-8")
            config = DSSATRunConfig(
                runtime_role="patched",
                runtime_root=root / "runtime",
                working_root=root / "runs",
                template_root=template_root,
                preprocess_command="",
                run_command="echo demo",
            )
            builder = DSSATInputBuilder(config)
            scenario.template_name = "custom_case"
            scenario.experiment_file = "DEMO.MZX"
            policy = SeasonPolicy(policy_id="demo", scenario_id=scenario.scenario_id, actions=[])

            context = builder.build(scenario, policy)
            self.assertEqual(context.template_dir, custom_dir.resolve())
            self.assertTrue((context.run_dir / "DEMO.MZX").exists())

    def test_explicit_template_file_hint_resolves_parent_directory(self) -> None:
        scenario = build_quzhou_scenarios(
            target_count=1,
            engines=("dssat_official",),
            crops_filter=("maize",),
            sampling_mode="random",
            seed=20260622,
        )[0]
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            template_root = root / "templates"
            custom_dir = template_root / "nested_case"
            custom_dir.mkdir(parents=True, exist_ok=True)
            experiment = custom_dir / "DEMO.MZX"
            experiment.write_text("*EXP.DETAILS: TEST\n", encoding="utf-8")
            config = DSSATRunConfig(
                runtime_role="patched",
                runtime_root=root / "runtime",
                working_root=root / "runs",
                template_root=template_root,
                preprocess_command="",
                run_command="echo demo",
            )
            builder = DSSATInputBuilder(config)
            scenario.template_name = "nested_case/DEMO.MZX"
            scenario.experiment_file = "DEMO.MZX"
            policy = SeasonPolicy(policy_id="demo-file", scenario_id=scenario.scenario_id, actions=[])

            context = builder.build(scenario, policy)
            self.assertEqual(context.template_dir, custom_dir.resolve())
            self.assertTrue((context.run_dir / "DEMO.MZX").exists())

    def test_nested_template_directory_copies_adjacent_runtime_assets(self) -> None:
        scenario = build_quzhou_scenarios(
            target_count=1,
            engines=("dssat_official",),
            crops_filter=("maize",),
            sampling_mode="random",
            seed=20260622,
        )[0]
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_root = root / "real_subset_case"
            rice_dir = source_root / "Rice"
            weather_dir = source_root / "Weather"
            soil_dir = source_root / "Soil"
            genotype_dir = source_root / "Genotype"
            standard_data_dir = source_root / "StandardData"
            for path in (rice_dir, weather_dir, soil_dir, genotype_dir, standard_data_dir):
                path.mkdir(parents=True, exist_ok=True)

            (rice_dir / "WHRI2101.RIX").write_text("*EXP.DETAILS: TEST\n", encoding="utf-8")
            (weather_dir / "EQAH2101.WTH").write_text("*WEATHER\n", encoding="utf-8")
            (soil_dir / "CN.SOL").write_text("*SOILS\n", encoding="utf-8")
            (genotype_dir / "RICER048.CUL").write_text("*GENOTYPE\n", encoding="utf-8")
            (standard_data_dir / "CO2048.WDA").write_text("*STDDATA\n", encoding="utf-8")
            runtime_root = root / "runtime"
            (runtime_root / "Genotype").mkdir(parents=True, exist_ok=True)
            (runtime_root / "StandardData").mkdir(parents=True, exist_ok=True)
            (runtime_root / "Soil").mkdir(parents=True, exist_ok=True)
            (runtime_root / "Genotype" / "BASELINE.CUL").write_text("*BASELINE\n", encoding="utf-8")
            (runtime_root / "StandardData" / "FERCH048.SDA").write_text("*FERTDATA\n", encoding="utf-8")
            (runtime_root / "Soil" / "SOIL.V48").write_text("*SOILV48\n", encoding="utf-8")

            config = DSSATRunConfig(
                runtime_role="patched",
                runtime_root=runtime_root,
                working_root=root / "runs",
                template_root=root / "templates",
                preprocess_command="",
                run_command="echo demo",
            )
            builder = DSSATInputBuilder(config)
            scenario.template_name = str(rice_dir)
            scenario.experiment_file = "WHRI2101.RIX"
            policy = SeasonPolicy(policy_id="demo-nested-assets", scenario_id=scenario.scenario_id, actions=[])

            context = builder.build(scenario, policy)
            self.assertTrue((context.run_dir / "WHRI2101.RIX").exists())
            self.assertTrue((context.run_dir / "Weather" / "EQAH2101.WTH").exists())
            self.assertTrue((context.run_dir / "Soil" / "CN.SOL").exists())
            self.assertTrue((context.run_dir / "Genotype" / "RICER048.CUL").exists())
            self.assertTrue((context.run_dir / "StandardData" / "CO2048.WDA").exists())
            self.assertTrue((context.run_dir / "EQAH2101.WTH").exists())
            self.assertTrue((context.run_dir / "CN.SOL").exists())
            self.assertTrue((context.run_dir / "RICER048.CUL").exists())
            self.assertTrue((context.run_dir / "CO2048.WDA").exists())
            self.assertTrue((context.run_dir / "BASELINE.CUL").exists())
            self.assertTrue((context.run_dir / "FERCH048.SDA").exists())
            self.assertTrue((context.run_dir / "SOIL.V48").exists())

    def test_rice_real_subset_builder_merges_append_and_remaps_whr006(self) -> None:
        scenario = build_quzhou_scenarios(
            target_count=1,
            engines=("dssat_official",),
            crops_filter=("maize",),
            sampling_mode="random",
            seed=20260622,
        )[0]
        scenario.crop_spec.crop_name = "rice"
        scenario.cultivar_code = "WHR006"
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_root = root / "wuhu_case" / "dssat_native"
            rice_dir = source_root / "Rice"
            genotype_dir = source_root / "Genotype"
            soil_dir = source_root / "Soil"
            weather_dir = source_root / "Weather"
            for path in (rice_dir, genotype_dir, soil_dir, weather_dir):
                path.mkdir(parents=True, exist_ok=True)

            (rice_dir / "WHRI2101.RIX").write_text(
                "\n".join(
                    [
                        "*EXP.DETAILS: TEST",
                        "*CULTIVARS",
                        "@C CR INGENO CNAME",
                        " 6 RI WHR006 MEIXIANGZHAN2",
                        " 9 RI WHR009 QUANYOU280",
                        "*FIELDS",
                        "@L ID_FIELD WSTA....  FLSA  FLOB  FLDT  FLDD  FLDS  FLST SLTX  SLDP  ID_SOIL    FLNAME",
                        " 1 F001     EQAH       -99     0 DR000     0     0 00000 CL     102  CNWH000001 EQIAO",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            (genotype_dir / "RICER048_WHRI_APPEND.CUL").write_text(
                "WHR006 MEIXIANGZHAN2     1,12 IB0001 448.8 121.0 663.0 12.97 60.01 .0270  1.00  83.0  29.5  15.0  15.0\n",
                encoding="utf-8",
            )
            (soil_dir / "CN.SOL").write_text("*SOILS\n", encoding="utf-8")
            (weather_dir / "EQAH2101.WTH").write_text("*WEATHER\n", encoding="utf-8")

            calibrated_dir = source_root.parent / "calibrated" / "Genotype"
            calibrated_dir.mkdir(parents=True, exist_ok=True)
            (calibrated_dir / "RICER048_WHR006_CALIBRATED.CUL").write_text(
                "WHR006 MEIXIANGZHAN2     1,12 IB0001 448.8 121.0 663.0 12.97 60.01 .0270  1.00  83.0  29.5  15.0  15.0\n",
                encoding="utf-8",
            )

            runtime_root = root / "runtime"
            (runtime_root / "Genotype").mkdir(parents=True, exist_ok=True)
            (runtime_root / "Genotype" / "RICER048.CUL").write_text(
                "\n".join(
                    [
                        "*RICE CULTIVAR COEFFICIENTS: RICER048 MODEL",
                        "999991 MINIMA               . DFAULT 150.0   5.0 150.0  11.0  50.0 .0150  0.70  55.0  24.0  12.0  10.0",
                        "999992 MAXIMA               . DFAULT 800.0 300.0 850.0  13.0  72.0 .0300  1.30  90.0  35.0  18.0  20.0",
                        "WHR009 QUANYOU280           . IB0001 540.0 160.0 490.0  12.0  50.0 .0250  1.10  83.0  28.0  15.0  15.0",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            config = DSSATRunConfig(
                runtime_role="patched",
                runtime_root=runtime_root,
                working_root=root / "runs",
                template_root=root / "templates",
                preprocess_command="",
                run_command="echo demo",
            )
            builder = DSSATInputBuilder(config)
            scenario.template_name = str(rice_dir)
            scenario.experiment_file = "WHRI2101.RIX"
            policy = SeasonPolicy(policy_id="rice-whr006-remap", scenario_id=scenario.scenario_id, actions=[])

            context = builder.build(scenario, policy)
            cultivar_text = (context.run_dir / "RICER048.CUL").read_text(encoding="utf-8")
            experiment_text = (context.run_dir / "WHRI2101.RIX").read_text(encoding="utf-8")
            self.assertIn("WHR009 MEIXIANGZHAN2", cultivar_text)
            self.assertNotIn("WHR006 MEIXIANGZHAN2", cultivar_text)
            self.assertIn("WHR009 MEIXIANGZHAN2", experiment_text)
            self.assertNotIn("WHR006 MEIXIANGZHAN2", experiment_text)

    def test_real_subset_style_scenario_rewrites_batch_to_single_treatment(self) -> None:
        scenario = build_quzhou_scenarios(
            target_count=1,
            engines=("dssat_official",),
            crops_filter=("maize",),
            sampling_mode="random",
            seed=20260622,
        )[0]
        scenario.crop_spec.crop_name = "rice"
        scenario.scenario_id = "wuhu_rice_calibrated-tr11-real-subset"
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_root = root / "wuhu_case" / "dssat_native"
            rice_dir = source_root / "Rice"
            weather_dir = source_root / "Weather"
            soil_dir = source_root / "Soil"
            genotype_dir = source_root / "Genotype"
            standard_data_dir = source_root / "StandardData"
            for path in (rice_dir, weather_dir, soil_dir, genotype_dir, standard_data_dir):
                path.mkdir(parents=True, exist_ok=True)

            (rice_dir / "WHRI2101.RIX").write_text("*EXP.DETAILS: TEST\n", encoding="utf-8")
            (rice_dir / "DSSBatch.v48").write_text(
                "\n".join(
                    [
                        "$BATCH(RICE)",
                        "@FILEX                                                                                        TRTNO     RP     SQ     OP     CO",
                        f"{'WHRI2101.RIX':<90}{1:>6}{1:>7}{0:>7}{0:>7}{0:>7}",
                        f"{'WHRI2101.RIX':<90}{11:>6}{1:>7}{0:>7}{0:>7}{0:>7}",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            (weather_dir / "EQAH2101.WTH").write_text("*WEATHER\n", encoding="utf-8")
            (soil_dir / "CN.SOL").write_text("*SOILS\n", encoding="utf-8")
            (genotype_dir / "RICER048.CUL").write_text("*GENOTYPE\n", encoding="utf-8")
            (standard_data_dir / "CO2048.WDA").write_text("*STDDATA\n", encoding="utf-8")

            runtime_root = root / "runtime"
            (runtime_root / "Genotype").mkdir(parents=True, exist_ok=True)
            (runtime_root / "Genotype" / "RICER048.CUL").write_text("*BASELINE\n", encoding="utf-8")

            config = DSSATRunConfig(
                runtime_role="patched",
                runtime_root=runtime_root,
                working_root=root / "runs",
                template_root=root / "templates",
                preprocess_command="",
                run_command="echo demo",
            )
            builder = DSSATInputBuilder(config)
            scenario.template_name = str(rice_dir)
            scenario.experiment_file = "WHRI2101.RIX"
            policy = SeasonPolicy(policy_id="rice-single-treatment-batch", scenario_id=scenario.scenario_id, actions=[])

            context = builder.build(scenario, policy)
            batch_text = (context.run_dir / "DSSBatch.v48").read_text(encoding="utf-8")
            self.assertIn("WHRI2101.RIX", batch_text)
            self.assertIn("    11", batch_text)
            self.assertNotIn("     1      1", batch_text)
            self.assertEqual(len([line for line in batch_text.splitlines() if line.strip().startswith("WHRI2101.RIX")]), 1)
