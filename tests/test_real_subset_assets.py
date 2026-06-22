from __future__ import annotations

import unittest
from pathlib import Path
import tempfile

from transdssat.real_subset_assets import load_real_subset_asset
from transdssat.real_subset_replay import (
    build_real_subset_replacement_plan,
    compose_real_subset_management_policy,
    load_real_subset_replay_case,
    write_real_subset_policy_tsv,
)
from transdssat.season import SeasonPolicy, StageDecision
from transdssat.real_subset_runner import (
    _format_fertilizer_event_line,
    _format_rice_cultivar_row,
    _normalize_phenology_token,
    _normalize_cultivar_expno,
    _prepare_runtime_clone,
    prepare_real_subset_management_replacement,
    _rewrite_cultivar_expno,
    _rewrite_dssat_profile,
    _validate_rice_cultivar_row,
    _write_single_treatment_batch,
)
from transdssat.testset import load_real_data_test_subset, load_real_data_test_subsets


class RealSubsetAssetTests(unittest.TestCase):
    def test_load_mx475_migrated_asset(self) -> None:
        asset = load_real_subset_asset("mx475_migrated")

        self.assertEqual(asset.crop_name, "rice")
        self.assertEqual(asset.treatments[0].cultivar_code, "IB2002")
        self.assertEqual(asset.treatments[0].observed_yield_kg_ha, 4815.0)
        self.assertEqual(len(asset.treatments), 8)

    def test_load_wuhu_calibrated_asset(self) -> None:
        asset = load_real_subset_asset("wuhu_rice_calibrated")

        self.assertEqual(asset.crop_name, "rice")
        self.assertEqual(asset.treatments[0].cultivar_code, "WHR006")
        self.assertEqual(asset.treatments[0].observed_yield_kg_ha, 6365.0)
        self.assertEqual(len(asset.treatments), 12)

    def test_real_subset_bundle_entrypoints(self) -> None:
        first = load_real_data_test_subset("mx475_migrated")
        both = load_real_data_test_subsets()

        self.assertEqual(first.asset.subset_id, "mx475_migrated")
        self.assertEqual(first.validated_treatments, [1, 2, 3, 4, 5, 6, 7, 8])
        self.assertEqual([case.treatment.treatment_no for case in first.replay_cases], [1, 2, 3, 4, 5, 6, 7, 8])
        self.assertEqual([bundle.asset.subset_id for bundle in both], ["mx475_migrated", "wuhu_rice_calibrated"])
        self.assertEqual(both[1].validated_treatments, [11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 22, 23])

    def test_real_subset_replay_case_entrypoint(self) -> None:
        case = load_real_subset_replay_case("mx475_migrated", 1)

        self.assertEqual(case.crop_name, "rice")
        self.assertEqual(case.treatment.treatment_no, 1)
        self.assertEqual(case.observed_yield_kg_ha, 4815.0)
        self.assertEqual(case.cultivar_id, "meixiangzhan2")
        self.assertEqual(case.management_anchor, "original_management_replay")
        self.assertTrue(case.compatibility_notes)
        self.assertGreater(case.baseline_policy.total_irrigation_mm, 0.0)
        self.assertGreater(case.baseline_policy.total_nitrogen_kg_ha, 0.0)

    def test_compose_real_subset_management_policy_can_replace_only_irrigation(self) -> None:
        reference = SeasonPolicy(
            policy_id="reference",
            scenario_id="subset-tr01",
            actions=[
                StageDecision("emergence", 0, "2021-05-01", 0.0, 30.0),
                StageDecision("vegetative", 20, "2021-05-21", 40.0, 20.0),
            ],
        )
        candidate = SeasonPolicy(
            policy_id="candidate",
            scenario_id="subset-tr01",
            actions=[
                StageDecision("emergence", 0, "2021-05-01", 15.0, 0.0),
                StageDecision("vegetative", 20, "2021-05-21", 10.0, 0.0),
            ],
        )

        merged = compose_real_subset_management_policy(reference, candidate, control_mode="water_only")

        self.assertEqual([item.irrigation_mm for item in merged.actions], [15.0, 10.0])
        self.assertEqual([item.nitrogen_kg_ha for item in merged.actions], [30.0, 20.0])

    def test_compose_real_subset_management_policy_can_replace_only_nitrogen(self) -> None:
        reference = SeasonPolicy(
            policy_id="reference",
            scenario_id="subset-tr01",
            actions=[
                StageDecision("emergence", 0, "2021-05-01", 5.0, 30.0),
                StageDecision("vegetative", 20, "2021-05-21", 40.0, 20.0),
            ],
        )
        candidate = SeasonPolicy(
            policy_id="candidate",
            scenario_id="subset-tr01",
            actions=[
                StageDecision("emergence", 0, "2021-05-01", 15.0, 12.0),
                StageDecision("vegetative", 20, "2021-05-21", 10.0, 8.0),
            ],
        )

        merged = compose_real_subset_management_policy(reference, candidate, control_mode="nitrogen_only")

        self.assertEqual([item.irrigation_mm for item in merged.actions], [5.0, 40.0])
        self.assertEqual([item.nitrogen_kg_ha for item in merged.actions], [12.0, 8.0])

    def test_compose_real_subset_management_policy_joint_keeps_candidate(self) -> None:
        reference = SeasonPolicy(
            policy_id="reference",
            scenario_id="subset-tr01",
            actions=[StageDecision("emergence", 0, "2021-05-01", 5.0, 30.0)],
        )
        candidate = SeasonPolicy(
            policy_id="candidate",
            scenario_id="subset-tr01",
            actions=[StageDecision("emergence", 0, "2021-05-01", 15.0, 12.0)],
        )

        merged = compose_real_subset_management_policy(reference, candidate, control_mode="joint")

        self.assertEqual([item.irrigation_mm for item in merged.actions], [15.0])
        self.assertEqual([item.nitrogen_kg_ha for item in merged.actions], [12.0])

    def test_build_real_subset_replacement_plan_carries_anchor_and_composed_policy(self) -> None:
        case = load_real_subset_replay_case("mx475_migrated", 1)
        reference = SeasonPolicy(
            policy_id="reference",
            scenario_id="mx475_migrated-tr01",
            actions=[
                StageDecision("emergence", 0, "2021-07-05", 0.0, 30.0),
                StageDecision("vegetative", 20, "2021-07-25", 40.0, 20.0),
            ],
        )
        candidate = SeasonPolicy(
            policy_id="candidate",
            scenario_id="mx475_migrated-tr01",
            actions=[
                StageDecision("emergence", 0, "2021-07-05", 15.0, 10.0),
                StageDecision("vegetative", 20, "2021-07-25", 10.0, 8.0),
            ],
        )

        plan = build_real_subset_replacement_plan(
            case,
            candidate,
            control_mode="water_only",
            reference_policy=reference,
        )

        self.assertEqual(plan.subset_id, "mx475_migrated")
        self.assertEqual(plan.treatment_no, 1)
        self.assertEqual(plan.control_mode, "water_only")
        self.assertEqual([item.irrigation_mm for item in plan.composed_policy.actions], [15.0, 10.0])
        self.assertEqual([item.nitrogen_kg_ha for item in plan.composed_policy.actions], [30.0, 20.0])
        self.assertEqual(plan.observed_phenology["anthesis"]["yyddd"], "21256")
        self.assertEqual(plan.observed_phenology["maturity"]["yyddd"], "21286")

    def test_real_subset_replay_case_baseline_policy_comes_from_source_management(self) -> None:
        case = load_real_subset_replay_case("wuhu_rice_calibrated", 11)

        self.assertGreaterEqual(len(case.baseline_policy.actions), 4)
        self.assertGreater(case.baseline_policy.total_irrigation_mm, 0.0)
        self.assertGreater(case.baseline_policy.total_nitrogen_kg_ha, 0.0)

    def test_write_real_subset_policy_tsv_emits_render_compatible_layout(self) -> None:
        policy = SeasonPolicy(
            policy_id="candidate",
            scenario_id="mx475_migrated-tr01",
            actions=[
                StageDecision("emergence", 0, "2021-07-05", 15.0, 10.0),
                StageDecision("vegetative", 20, "2021-07-25", 10.0, 8.0),
            ],
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            path = write_real_subset_policy_tsv(policy, Path(tmpdir) / "transdssat_policy.tsv")
            text = path.read_text(encoding="utf-8").splitlines()

        self.assertEqual(text[0], "stage\tdate\tday_index\tirrigation_mm\tnitrogen_kg_ha")
        self.assertEqual(text[1], "emergence\t2021-07-05\t0\t15.0\t10.0")
        self.assertEqual(text[2], "vegetative\t2021-07-25\t20\t10.0\t8.0")

    def test_prepare_real_subset_management_replacement_rewrites_management_blocks(self) -> None:
        candidate = SeasonPolicy(
            policy_id="candidate",
            scenario_id="mx475_migrated-tr01",
            actions=[
                StageDecision("emergence", 0, "2021-07-05", 15.0, 10.0),
                StageDecision("vegetative", 20, "2021-07-25", 10.0, 8.0),
            ],
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            runtime_root = tmp / "runtime"
            output_root = tmp / "output"
            (runtime_root / "Genotype").mkdir(parents=True)
            (runtime_root / "StandardData").mkdir(parents=True)
            (runtime_root / "dscsm048").write_text("", encoding="utf-8")
            (runtime_root / "DSSATPRO.L48").write_text("MRI // /old/runtime dscsm048 RICER048\n", encoding="utf-8")
            (runtime_root / "DSSATPRO.L48.bak").write_text("MRI // /old/runtime dscsm048 RICER048\n", encoding="utf-8")
            (runtime_root / "Genotype" / "RICER048.CUL").write_text(
                "\n".join(
                    [
                        "999991 MINIMA               . DFAULT 150.0   5.0 150.0  11.0  50.0 .0150  0.70  55.0  24.0  12.0  10.0",
                        "999992 MAXIMA               . DFAULT 800.0 300.0 850.0  13.0  72.0 .0300  1.30  90.0  35.0  18.0  20.0",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            (runtime_root / "Genotype" / "RICER048.SPE").write_text("rice species\n", encoding="utf-8")
            for standard_name in (
                "CO2048.WDA",
                "FERCH048.SDA",
                "RESCH048.SDA",
                "SOMFR048.SDA",
                "SOMFX048.SDA",
                "TILOP048.SDA",
            ):
                (runtime_root / "StandardData" / standard_name).write_text("stub\n", encoding="utf-8")

            result = prepare_real_subset_management_replacement(
                "mx475_migrated",
                1,
                candidate,
                control_mode="water_only",
                runtime_root=runtime_root,
                output_root=output_root,
            )

            experiment_text = Path(result["experiment_path"]).read_text(encoding="utf-8", errors="ignore")
            policy_text = Path(result["policy_tsv_path"]).read_text(encoding="utf-8")
            plan_text = Path(result["replacement_plan_path"]).read_text(encoding="utf-8")

        self.assertIn(" 1 21186 IR010    15", experiment_text)
        self.assertIn(" 1 21206 IR009    10", experiment_text)
        self.assertIn("FE005 AP002", experiment_text)
        self.assertIn("FE005 AP012", experiment_text)
        self.assertIn("water_only", plan_text)
        self.assertIn("stage\tdate\tday_index\tirrigation_mm\tnitrogen_kg_ha", policy_text)

    def test_format_fertilizer_event_line_preserves_fixed_width_and_zeroes_non_nitrogen_fields(self) -> None:
        template = [
            "1",
            "21185",
            "FE005",
            "AP002",
            "5",
            "32",
            "14",
            "27",
            "-99",
            "-99",
            "-99",
            "level",
            "1",
            "H23",
            "Wan",
            "Dao",
            "Mei",
            "Xiangzhan2",
            "Fertilizer",
        ]

        line = _format_fertilizer_event_line(1, "21187", template, 42.26, zero_non_nitrogen=True)

        self.assertEqual(len(line), 108)
        self.assertEqual(line[:2], " 1")
        self.assertIn(" 21187 FE005 AP002", line)
        self.assertIn("     5    42     0     0", line)
        self.assertTrue(line.endswith("level 1 H23 Wan Dao Mei Xiangzhan2 Fertilizer"))

    def test_prepare_real_subset_management_replacement_joint_rewrites_fertilizer_with_integer_n_only(self) -> None:
        candidate = SeasonPolicy(
            policy_id="candidate",
            scenario_id="mx475_migrated-tr01",
            actions=[
                StageDecision("event_01", 0, "2021-06-16", 15.0, 42.26),
                StageDecision("event_02", 20, "2021-07-06", 10.0, 8.4),
            ],
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            runtime_root = tmp / "runtime"
            output_root = tmp / "output"
            (runtime_root / "Genotype").mkdir(parents=True)
            (runtime_root / "StandardData").mkdir(parents=True)
            (runtime_root / "dscsm048").write_text("", encoding="utf-8")
            (runtime_root / "DSSATPRO.L48").write_text("MRI // /old/runtime dscsm048 RICER048\n", encoding="utf-8")
            (runtime_root / "DSSATPRO.L48.bak").write_text("MRI // /old/runtime dscsm048 RICER048\n", encoding="utf-8")
            (runtime_root / "Genotype" / "RICER048.CUL").write_text(
                "\n".join(
                    [
                        "999991 MINIMA               . DFAULT 150.0   5.0 150.0  11.0  50.0 .0150  0.70  55.0  24.0  12.0  10.0",
                        "999992 MAXIMA               . DFAULT 800.0 300.0 850.0  13.0  72.0 .0300  1.30  90.0  35.0  18.0  20.0",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            (runtime_root / "Genotype" / "RICER048.SPE").write_text("rice species\n", encoding="utf-8")
            for standard_name in (
                "CO2048.WDA",
                "FERCH048.SDA",
                "RESCH048.SDA",
                "SOMFR048.SDA",
                "SOMFX048.SDA",
                "TILOP048.SDA",
            ):
                (runtime_root / "StandardData" / standard_name).write_text("stub\n", encoding="utf-8")

            result = prepare_real_subset_management_replacement(
                "mx475_migrated",
                1,
                candidate,
                control_mode="joint",
                runtime_root=runtime_root,
                output_root=output_root,
            )
            experiment_lines = Path(result["experiment_path"]).read_text(encoding="utf-8", errors="ignore").splitlines()

        self.assertTrue(any("IR010    15" in line for line in experiment_lines))
        self.assertTrue(any("IR009    10" in line for line in experiment_lines))
        tr1_fertilizer_lines = [line for line in experiment_lines if line.startswith(" 1 ") and "FE005" in line]
        self.assertEqual(len(tr1_fertilizer_lines), 2)
        self.assertEqual(len(tr1_fertilizer_lines[0]), 108)
        self.assertIn("    42     0     0", tr1_fertilizer_lines[0])
        self.assertIn("     8     0     0", tr1_fertilizer_lines[1])

    def test_prepare_wuhu_water_only_replacement_preserves_original_irrigation_code(self) -> None:
        candidate = SeasonPolicy(
            policy_id="candidate",
            scenario_id="wuhu_rice_calibrated-tr11",
            actions=[
                StageDecision("event_01", 0, "2021-07-04", 30.0, 0.0),
                StageDecision("event_03", 42, "2021-08-15", 35.0, 0.0),
            ],
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            runtime_root = tmp / "runtime"
            output_root = tmp / "output"
            for path in (
                runtime_root / "Genotype",
                runtime_root / "Weather",
                runtime_root / "Soil",
                runtime_root / "Rice",
                runtime_root / "StandardData",
            ):
                path.mkdir(parents=True, exist_ok=True)
            (runtime_root / "dscsm048").write_text("", encoding="utf-8")
            (runtime_root / "DSSATPRO.L48").write_text("MRI // /old/runtime dscsm048 RICER048\n", encoding="utf-8")
            (runtime_root / "DSSATPRO.L48.bak").write_text("MRI // /old/runtime dscsm048 RICER048\n", encoding="utf-8")
            (runtime_root / "Genotype" / "RICER048.CUL").write_text(
                "\n".join(
                    [
                        "999991 MINIMA               . DFAULT 150.0   5.0 150.0  11.0  50.0 .0150  0.70  55.0  24.0  12.0  10.0",
                        "999992 MAXIMA               . DFAULT 800.0 300.0 850.0  13.0  72.0 .0300  1.30  90.0  35.0  18.0  20.0",
                        "WHR009 QUANYOU280           . IB0001 540.0 160.0 490.0  12.0  50.0 .0250  1.10  83.0  28.0  15.0  15.0",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            (runtime_root / "Genotype" / "RICER048.SPE").write_text("rice species\n", encoding="utf-8")
            for standard_name in (
                "CO2048.WDA",
                "FERCH048.SDA",
                "RESCH048.SDA",
                "SOMFR048.SDA",
                "SOMFX048.SDA",
                "TILOP048.SDA",
            ):
                (runtime_root / "StandardData" / standard_name).write_text("stub\n", encoding="utf-8")
            for soil_name in ("CN.SOL", "SOIL.SOL", "SOIL.V48"):
                (runtime_root / "Soil" / soil_name).write_text("stub\n", encoding="utf-8")

            result = prepare_real_subset_management_replacement(
                "wuhu_rice_calibrated",
                11,
                candidate,
                control_mode="water_only",
                runtime_root=runtime_root,
                output_root=output_root,
            )
            experiment_text = Path(result["experiment_path"]).read_text(encoding="utf-8", errors="ignore")

        self.assertIn("11     1   -99   -99   -99   -99   -99     2 WATER_11", experiment_text)
        self.assertIn("11 21185 IR003    30", experiment_text)
        self.assertIn("11 21227 IR003    35", experiment_text)
        self.assertIn("FE005 AP001", experiment_text)

    def test_prepare_wuhu_joint_replacement_preserves_harvest_row_for_target_treatment(self) -> None:
        candidate = SeasonPolicy(
            policy_id="candidate",
            scenario_id="wuhu_rice_calibrated-tr11",
            actions=[
                StageDecision("event_01", 0, "2021-07-04", 0.0, 65.256),
                StageDecision("event_03", 10, "2021-07-14", 31.02, 30.471),
                StageDecision("event_06", 25, "2021-07-29", 0.0, 13.652),
            ],
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            runtime_root = tmp / "runtime"
            output_root = tmp / "output"
            for path in (
                runtime_root / "Genotype",
                runtime_root / "Weather",
                runtime_root / "Soil",
                runtime_root / "Rice",
                runtime_root / "StandardData",
            ):
                path.mkdir(parents=True, exist_ok=True)
            (runtime_root / "dscsm048").write_text("", encoding="utf-8")
            (runtime_root / "DSSATPRO.L48").write_text("MRI // /old/runtime dscsm048 RICER048\n", encoding="utf-8")
            (runtime_root / "DSSATPRO.L48.bak").write_text("MRI // /old/runtime dscsm048 RICER048\n", encoding="utf-8")
            (runtime_root / "Genotype" / "RICER048.CUL").write_text(
                "\n".join(
                    [
                        "999991 MINIMA               . DFAULT 150.0   5.0 150.0  11.0  50.0 .0150  0.70  55.0  24.0  12.0  10.0",
                        "999992 MAXIMA               . DFAULT 800.0 300.0 850.0  13.0  72.0 .0300  1.30  90.0  35.0  18.0  20.0",
                        "WHR009 QUANYOU280           . IB0001 540.0 160.0 490.0  12.0  50.0 .0250  1.10  83.0  28.0  15.0  15.0",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            (runtime_root / "Genotype" / "RICER048.SPE").write_text("rice species\n", encoding="utf-8")
            for standard_name in (
                "CO2048.WDA",
                "FERCH048.SDA",
                "RESCH048.SDA",
                "SOMFR048.SDA",
                "SOMFX048.SDA",
                "TILOP048.SDA",
            ):
                (runtime_root / "StandardData" / standard_name).write_text("stub\n", encoding="utf-8")
            for soil_name in ("CN.SOL", "SOIL.SOL", "SOIL.V48"):
                (runtime_root / "Soil" / soil_name).write_text("stub\n", encoding="utf-8")

            result = prepare_real_subset_management_replacement(
                "wuhu_rice_calibrated",
                11,
                candidate,
                control_mode="joint",
                runtime_root=runtime_root,
                output_root=output_root,
            )
            experiment_text = Path(result["experiment_path"]).read_text(encoding="utf-8", errors="ignore")

        self.assertIn("11 21309 GS000   -99   -99   -99   -99 HARV_11", experiment_text)

    def test_normalize_phenology_token_handles_fixed_width_summary_noise(self) -> None:
        normalized = _normalize_phenology_token("21253 20", 2021)

        self.assertEqual(normalized["token"], "21253")
        self.assertEqual(normalized["yyddd"], "21253")
        self.assertEqual(normalized["year"], 2021)
        self.assertEqual(normalized["doy"], 253)
        self.assertEqual(normalized["iso_date"], "2021-09-10")

    def test_normalize_phenology_token_can_promote_observed_doy_with_year_hint(self) -> None:
        normalized = _normalize_phenology_token("253", 2021)

        self.assertEqual(normalized["token"], "253")
        self.assertEqual(normalized["yyddd"], "21253")
        self.assertEqual(normalized["year"], 2021)
        self.assertEqual(normalized["doy"], 253)
        self.assertEqual(normalized["iso_date"], "2021-09-10")

    def test_rice_cultivar_append_row_is_reformatted_to_fixed_width(self) -> None:
        row = _format_rice_cultivar_row(
            "IB2002 Meixiangzhan 2       . IB0001 724.9 97.04 416.0 11.69 71.09 .0170  1.17 57.46  35.0  15.0  15.0"
        )

        self.assertEqual(len(row), 102)
        self.assertTrue(row.startswith("IB2002 Meixiangzhan 2"))
        self.assertIn(" IB0001", row)

    def test_rice_cultivar_validation_reports_out_of_range_fields(self) -> None:
        cultivar_path = Path("artifacts/test_rice_runtime_reference.cul")
        cultivar_path.parent.mkdir(parents=True, exist_ok=True)
        cultivar_path.write_text(
            "\n".join(
                [
                    "999991 MINIMA               . DFAULT 150.0   5.0 150.0  11.0  50.0 .0150  0.70  55.0  25.0  12.0  10.0",
                    "999992 MAXIMA               . DFAULT 800.0 300.0 850.0  13.0  70.0 .0300  1.30  90.0  34.0  18.0  20.0",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        issues = _validate_rice_cultivar_row(
            "IB2002 Meixiangzhan 2       . IB0001 724.9 97.04 416.0 11.69 71.09 .0170  1.17 57.46  35.0  15.0  15.0",
            cultivar_path,
        )

        self.assertIn("G1=71.09 outside [50.0, 70.0]", issues)
        self.assertIn("THOT=35.0 outside [25.0, 34.0]", issues)

    def test_append_unique_lines_can_downgrade_runtime_range_check_to_warning(self) -> None:
        from transdssat.real_subset_runner import _append_unique_lines

        runtime_cultivar = Path("artifacts/test_runtime_append_warning.CUL")
        append_file = Path("artifacts/test_runtime_append_warning_append.CUL")
        runtime_cultivar.write_text(
            "\n".join(
                [
                    "999991 MINIMA               . DFAULT 150.0   5.0 150.0  11.0  50.0 .0150  0.70  55.0  25.0  12.0  10.0",
                    "999992 MAXIMA               . DFAULT 800.0 300.0 850.0  13.0  70.0 .0300  1.30  90.0  34.0  18.0  20.0",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        append_file.write_text(
            "IB2002 Meixiangzhan 2       . IB0001 724.9 97.04 416.0 11.69 71.09 .0170  1.17 57.46  35.0  15.0  15.0\n",
            encoding="utf-8",
        )

        warnings: list[str] = []
        _append_unique_lines(
            runtime_cultivar,
            append_file,
            strict_validation=False,
            validation_warnings=warnings,
        )

        text = runtime_cultivar.read_text(encoding="utf-8")
        self.assertIn("IB2002", text)
        self.assertEqual(len(warnings), 1)
        self.assertIn("G1=71.09 outside [50.0, 70.0]", warnings[0])

    def test_rewrite_dssat_profile_points_entries_to_run_root(self) -> None:
        profile = Path("artifacts/test_dssat_profile.L48")
        profile.write_text(
            "DDB // /old/runtime\nMRI // /old/runtime dscsm048 RICER048\nDCG // /old/runtime/TOOLS/GENCALC GENCALC2.EXE\n",
            encoding="utf-8",
        )

        _rewrite_dssat_profile(profile, Path("/new/runtime"))

        rewritten = profile.read_text(encoding="utf-8")
        self.assertIn("DDB // .", rewritten)
        self.assertIn("MRI // . dscsm048 RICER048", rewritten)
        self.assertIn("DCG // .", rewritten)
        self.assertLessEqual(max(len(line) for line in rewritten.splitlines()), 32)

    def test_write_single_treatment_batch_limits_runlist_to_requested_treatment(self) -> None:
        batch_path = Path("artifacts/test_single_treatment.DSSBatch.v48")
        _write_single_treatment_batch(batch_path, "WHRI2101.RIX", 11)

        text = batch_path.read_text(encoding="utf-8")
        self.assertIn("$BATCH(RICE)", text)
        self.assertIn("WHRI2101.RIX", text)
        self.assertIn("    11", text)
        self.assertNotIn("    10      1", text)

    def test_rewrite_cultivar_expno_can_clear_whr006_style_range_token(self) -> None:
        rewritten = _rewrite_cultivar_expno(
            "WHR006 MEIXIANGZHAN2     1,12 IB0001 448.8 121.0 663.0 12.97 60.01 .0270  1.00  83.0  29.5  15.0  15.0",
            ".",
        )

        self.assertIn(" . IB0001 ", f" {rewritten} ")
        self.assertNotIn("1,12", rewritten)

    def test_normalize_cultivar_expno_rewrites_existing_file_row(self) -> None:
        cultivar_path = Path("artifacts/test_normalize_expno.CUL")
        cultivar_path.write_text(
            "WHR009 MEIXIANGZHAN2        1,12 IB0001 448.8 121.0 663.0 12.97 60.01 .0270  1.00  83.0  29.5  15.0  15.0\n",
            encoding="utf-8",
        )

        _normalize_cultivar_expno(cultivar_path, "WHR009", ".")

        text = cultivar_path.read_text(encoding="utf-8")
        self.assertIn("WHR009 MEIXIANGZHAN2        . IB0001", text)
        self.assertNotIn("1,12", text)

    def test_wuhu_runtime_clone_mirrors_soil_files_into_run_root(self) -> None:
        asset = load_real_subset_asset("wuhu_rice_calibrated")
        case = load_real_subset_replay_case("wuhu_rice_calibrated", 11)

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            runtime_root = tmp / "runtime"
            output_root = tmp / "output"
            (runtime_root / "Genotype").mkdir(parents=True)
            (runtime_root / "Weather").mkdir(parents=True)
            (runtime_root / "Soil").mkdir(parents=True)
            (runtime_root / "Rice").mkdir(parents=True)
            (runtime_root / "StandardData").mkdir(parents=True)
            (runtime_root / "dscsm048").write_text("", encoding="utf-8")
            (runtime_root / "DSSATPRO.L48").write_text("MRI // /old/runtime dscsm048 RICER048\n", encoding="utf-8")
            (runtime_root / "DSSATPRO.L48.bak").write_text("MRI // /old/runtime dscsm048 RICER048\n", encoding="utf-8")
            (runtime_root / "Genotype" / "RICER048.CUL").write_text(
                "\n".join(
                    [
                        "999991 MINIMA               . DFAULT 150.0   5.0 150.0  11.0  50.0 .0150  0.70  55.0  24.0  12.0  10.0",
                        "999992 MAXIMA               . DFAULT 800.0 300.0 850.0  13.0  72.0 .0300  1.30  90.0  35.0  18.0  20.0",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            (runtime_root / "Genotype" / "RICER048.SPE").write_text("rice species\n", encoding="utf-8")
            (runtime_root / "Soil" / "CN.SOL").write_text("CN soil\n", encoding="utf-8")
            (runtime_root / "Soil" / "SOIL.SOL").write_text("SOIL catalog\n", encoding="utf-8")
            (runtime_root / "Soil" / "SOIL.V48").write_text("SOIL v48\n", encoding="utf-8")
            (runtime_root / "StandardData" / "CO2048.WDA").write_text("co2 data\n", encoding="utf-8")
            (runtime_root / "StandardData" / "FERCH048.SDA").write_text("fert data\n", encoding="utf-8")
            (runtime_root / "StandardData" / "RESCH048.SDA").write_text("residue data\n", encoding="utf-8")
            (runtime_root / "StandardData" / "SOMFR048.SDA").write_text("somfr data\n", encoding="utf-8")
            (runtime_root / "StandardData" / "SOMFX048.SDA").write_text("somfx data\n", encoding="utf-8")
            (runtime_root / "StandardData" / "TILOP048.SDA").write_text("tillage data\n", encoding="utf-8")
            (runtime_root / "StandardData" / "FERCH048.SDA").write_text("fert data\n", encoding="utf-8")
            (runtime_root / "StandardData" / "RESCH048.SDA").write_text("residue data\n", encoding="utf-8")
            (runtime_root / "StandardData" / "SOMFR048.SDA").write_text("somfr data\n", encoding="utf-8")
            (runtime_root / "StandardData" / "SOMFX048.SDA").write_text("somfx data\n", encoding="utf-8")
            (runtime_root / "StandardData" / "TILOP048.SDA").write_text("tillage data\n", encoding="utf-8")
            calibrated_dir = tmp / "subset_root" / "02_自己校准模型_芜湖水稻" / "美香占2号校准参数" / "Genotype"
            calibrated_dir.mkdir(parents=True, exist_ok=True)
            (calibrated_dir / "RICER048_WHR006_CALIBRATED.CUL").write_text(
                "WHR006 MEIXIANGZHAN2     1,12 IB0001 448.8 121.0 663.0 12.97 60.01 .0270  1.00  83.0  29.5  15.0  15.0\n",
                encoding="utf-8",
            )

            run_root, _, _ = _prepare_runtime_clone(asset, case, runtime_root, output_root)

            self.assertTrue((run_root / "CN.SOL").exists())
            self.assertTrue((run_root / "SOIL.SOL").exists())
            self.assertTrue((run_root / "SOIL.V48").exists())
            self.assertTrue((run_root / "RICER048.CUL").exists())
            self.assertTrue((run_root / "RICER048.SPE").exists())
            self.assertTrue((run_root / "CO2048.WDA").exists())
            self.assertTrue((run_root / "FERCH048.SDA").exists())
            self.assertTrue((run_root / "RESCH048.SDA").exists())
            self.assertTrue((run_root / "SOMFR048.SDA").exists())
            self.assertTrue((run_root / "SOMFX048.SDA").exists())
            self.assertTrue((run_root / "TILOP048.SDA").exists())

    def test_mx475_runtime_clone_writes_single_treatment_batch(self) -> None:
        asset = load_real_subset_asset("mx475_migrated")
        case = load_real_subset_replay_case("mx475_migrated", 1)

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            runtime_root = tmp / "runtime"
            output_root = tmp / "output"
            (runtime_root / "Genotype").mkdir(parents=True)
            (runtime_root / "dscsm048").write_text("", encoding="utf-8")
            (runtime_root / "DSSATPRO.L48").write_text("MRI // /old/runtime dscsm048 RICER048\n", encoding="utf-8")
            (runtime_root / "DSSATPRO.L48.bak").write_text("MRI // /old/runtime dscsm048 RICER048\n", encoding="utf-8")
            (runtime_root / "Genotype" / "RICER048.CUL").write_text(
                "\n".join(
                    [
                        "999991 MINIMA               . DFAULT 150.0   5.0 150.0  11.0  50.0 .0150  0.70  55.0  24.0  12.0  10.0",
                        "999992 MAXIMA               . DFAULT 800.0 300.0 850.0  13.0  72.0 .0300  1.30  90.0  35.0  18.0  20.0",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            (runtime_root / "Genotype" / "RICER048.SPE").write_text("rice species\n", encoding="utf-8")
            (runtime_root / "StandardData").mkdir(parents=True)
            (runtime_root / "StandardData" / "CO2048.WDA").write_text("co2 data\n", encoding="utf-8")
            (runtime_root / "StandardData" / "FERCH048.SDA").write_text("fert data\n", encoding="utf-8")
            (runtime_root / "StandardData" / "RESCH048.SDA").write_text("residue data\n", encoding="utf-8")
            (runtime_root / "StandardData" / "SOMFR048.SDA").write_text("somfr data\n", encoding="utf-8")
            (runtime_root / "StandardData" / "SOMFX048.SDA").write_text("somfx data\n", encoding="utf-8")
            (runtime_root / "StandardData" / "TILOP048.SDA").write_text("tillage data\n", encoding="utf-8")

            run_root, _, _ = _prepare_runtime_clone(asset, case, runtime_root, output_root)
            batch_text = (run_root / "DSSBatch.v48").read_text(encoding="utf-8")

            self.assertIn("MX232107.RIX", batch_text)
            self.assertIn("     1", batch_text)
            self.assertTrue((run_root / "RICER048.CUL").exists())
            self.assertTrue((run_root / "RICER048.SPE").exists())
            self.assertTrue((run_root / "CO2048.WDA").exists())
            self.assertTrue((run_root / "FERCH048.SDA").exists())
            self.assertTrue((run_root / "RESCH048.SDA").exists())
            self.assertTrue((run_root / "SOMFR048.SDA").exists())
            self.assertTrue((run_root / "SOMFX048.SDA").exists())
            self.assertTrue((run_root / "TILOP048.SDA").exists())

    def test_wuhu_runtime_clone_remaps_whr006_to_compatibility_code_for_replay_only(self) -> None:
        asset = load_real_subset_asset("wuhu_rice_calibrated")
        case = load_real_subset_replay_case("wuhu_rice_calibrated", 11)

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            runtime_root = tmp / "runtime"
            output_root = tmp / "output"
            subset_root = tmp / "subset_root"
            source_root = subset_root / "02_自己校准模型_芜湖水稻" / "dssat_native"
            calibrated_dir = subset_root / "02_自己校准模型_芜湖水稻" / "美香占2号校准参数" / "Genotype"

            for path in (
                runtime_root / "Genotype",
                runtime_root / "Weather",
                runtime_root / "Soil",
                runtime_root / "Rice",
                runtime_root / "StandardData",
                source_root / "Rice",
                calibrated_dir,
            ):
                path.mkdir(parents=True, exist_ok=True)

            (runtime_root / "dscsm048").write_text("", encoding="utf-8")
            (runtime_root / "DSSATPRO.L48").write_text("MRI // /old/runtime dscsm048 RICER048\n", encoding="utf-8")
            (runtime_root / "DSSATPRO.L48.bak").write_text("MRI // /old/runtime dscsm048 RICER048\n", encoding="utf-8")
            (runtime_root / "Genotype" / "RICER048.CUL").write_text(
                "\n".join(
                    [
                        "999991 MINIMA               . DFAULT 150.0   5.0 150.0  11.0  50.0 .0150  0.70  55.0  24.0  12.0  10.0",
                        "999992 MAXIMA               . DFAULT 800.0 300.0 850.0  13.0  72.0 .0300  1.30  90.0  35.0  18.0  20.0",
                        "WHR009 QUANYOU280           . IB0001 540.0 160.0 490.0  12.0  50.0 .0250  1.10  83.0  28.0  15.0  15.0",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            (runtime_root / "Genotype" / "RICER048.SPE").write_text("rice species\n", encoding="utf-8")
            (runtime_root / "StandardData" / "CO2048.WDA").write_text("co2 data\n", encoding="utf-8")
            (runtime_root / "StandardData" / "FERCH048.SDA").write_text("fert data\n", encoding="utf-8")
            (runtime_root / "StandardData" / "RESCH048.SDA").write_text("residue data\n", encoding="utf-8")
            (runtime_root / "StandardData" / "SOMFR048.SDA").write_text("somfr data\n", encoding="utf-8")
            (runtime_root / "StandardData" / "SOMFX048.SDA").write_text("somfx data\n", encoding="utf-8")
            (runtime_root / "StandardData" / "TILOP048.SDA").write_text("tillage data\n", encoding="utf-8")
            (source_root / "Rice" / "WHRI2101.RIX").write_text(
                "\n".join(
                    [
                        "*TREATMENTS                        -------------FACTOR LEVELS------------",
                        "@N R O C TNAME.................... CU FL SA IC MP MI MF MR MC MT ME MH SM",
                        "11 1 1 0 1 T11_MEIXIANGZHAN       6  0  0  0  0  0  0  0  0  0  0  0  0",
                        "*CULTIVARS",
                        "@C CR INGENO CNAME",
                        " 6 RI WHR006 MEIXIANGZHAN2",
                        " 9 RI WHR009 QUANYOU280",
                        "*END",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            (source_root / "Rice" / "WHRI2101.RIA").write_text(
                "\n".join(
                    [
                        "@TRNO DATE ADAT MDAT HWAM",
                        "11 21200 21180 21280 7000",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            (source_root / "Rice" / "DSSBatch.v48").write_text("", encoding="utf-8")
            (source_root / "Genotype").mkdir(parents=True, exist_ok=True)
            (source_root / "Genotype" / "RICER048_WHRI_APPEND.CUL").write_text(
                "WHR006 MEIXIANGZHAN2     1,12 IB0001 448.8 121.0 663.0 12.97 60.01 .0270  1.00  83.0  29.5  15.0  15.0\n",
                encoding="utf-8",
            )
            (calibrated_dir / "RICER048_WHR006_CALIBRATED.CUL").write_text(
                "WHR006 MEIXIANGZHAN2     1,12 IB0001 448.8 121.0 663.0 12.97 60.01 .0270  1.00  83.0  29.5  15.0  15.0\n",
                encoding="utf-8",
            )

            patched_asset = load_real_subset_asset("wuhu_rice_calibrated", root=subset_root)
            patched_case = load_real_subset_replay_case("wuhu_rice_calibrated", 11, root=subset_root)
            run_root, _, _ = _prepare_runtime_clone(patched_asset, patched_case, runtime_root, output_root)

            experiment_text = (run_root / "WHRI2101.RIX").read_text(encoding="utf-8")
            cultivar_text = (run_root / "Genotype" / "RICER048.CUL").read_text(encoding="utf-8")

            self.assertIn("WHR009 MEIXIANGZHAN2", cultivar_text)
            self.assertIn("WHR009 MEIXIANGZHAN2        . IB0001", cultivar_text)
            self.assertNotIn("WHR006 MEIXIANGZHAN2", cultivar_text)
            self.assertIn("WHR009 MEIXIANGZHAN2", experiment_text)
            self.assertNotIn("WHR006 MEIXIANGZHAN2", experiment_text)


if __name__ == "__main__":
    unittest.main()
