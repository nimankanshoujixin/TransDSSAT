from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class PrepareRealSubsetReplacementTests(unittest.TestCase):
    def test_cli_writes_plan_and_policy_tsv(self) -> None:
        root = Path(__file__).resolve().parents[1]
        script_path = root / "scripts" / "prepare_real_subset_replacement.py"

        candidate_policy = {
            "policy_id": "candidate",
            "scenario_id": "mx475_migrated-tr01",
            "actions": [
                {
                    "stage": "emergence",
                    "day_index": 0,
                    "date": "2021-07-05",
                    "irrigation_mm": 15.0,
                    "nitrogen_kg_ha": 10.0,
                },
                {
                    "stage": "vegetative",
                    "day_index": 20,
                    "date": "2021-07-25",
                    "irrigation_mm": 10.0,
                    "nitrogen_kg_ha": 8.0,
                },
            ],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            candidate_path = tmp / "candidate_policy.json"
            output_dir = tmp / "prepared"
            candidate_path.write_text(json.dumps(candidate_policy, ensure_ascii=False), encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(script_path),
                    "--subset-id",
                    "mx475_migrated",
                    "--treatment-no",
                    "1",
                    "--candidate-policy-json",
                    str(candidate_path),
                    "--control-mode",
                    "water_only",
                    "--output-dir",
                    str(output_dir),
                ],
                cwd=root,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            payload = json.loads(result.stdout)
            plan_path = Path(payload["plan_path"])
            policy_tsv_path = Path(payload["policy_tsv_path"])

            self.assertTrue(plan_path.exists())
            self.assertTrue(policy_tsv_path.exists())

            plan = json.loads(plan_path.read_text(encoding="utf-8"))
            self.assertEqual(plan["subset_id"], "mx475_migrated")
            self.assertEqual(plan["control_mode"], "water_only")
            self.assertEqual(plan["observed_phenology"]["anthesis"]["yyddd"], "21256")

            policy_lines = policy_tsv_path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(policy_lines[0], "stage\tdate\tday_index\tirrigation_mm\tnitrogen_kg_ha")
            self.assertIn("emergence\t2021-07-05\t0\t15.0\t0.0", policy_lines[1])


if __name__ == "__main__":
    unittest.main()
