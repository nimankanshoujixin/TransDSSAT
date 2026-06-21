from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.build_rice_compat_baseline import build_rice_compat_baseline


class BuildRiceCompatBaselineTests(unittest.TestCase):
    def test_build_rice_compat_baseline_updates_limits_and_prefers_calibrated_whr006(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            runtime = tmp / "RICER048.CUL"
            append_fragment = tmp / "RICER048_WHRI_APPEND.CUL"
            calibrated_fragment = tmp / "RICER048_WHR006_CALIBRATED.CUL"
            output = tmp / "generated" / "RICER048.CUL"

            runtime.write_text(
                "\n".join(
                    [
                        "999991 MINIMA               . DFAULT 150.0   5.0 150.0  11.0  50.0 .0150  0.70  55.0  25.0  12.0  10.0",
                        "999992 MAXIMA               . DFAULT 800.0 300.0 850.0  13.0  70.0 .0300  1.30  90.0  34.0  18.0  20.0",
                        "IB0001 IR 8                 . IB0001 880.0  52.0 550.0  12.1  65.0 .0280  1.00  83.0  28.0  15.0  15.0",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            append_fragment.write_text(
                "\n".join(
                    [
                        "WHR001 NANJING5055          . IB0001 400.0 120.0 420.0  13.0  60.0 .0270  1.00  83.0  24.3  15.0  15.0",
                        "WHR006 MEIXIANGZHAN2     1,12 IB0001 448.8 121.0 663.0 12.97 60.01 .0270  1.00  83.0  29.5  15.0  15.0",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            calibrated_fragment.write_text(
                "WHR006 MEIXIANGZHAN2     1,12 IB0001 448.8 121.0 663.0 12.97 60.01 .0270  1.00  83.0  29.5  15.0  15.0\n",
                encoding="utf-8",
            )

            result = build_rice_compat_baseline(runtime, append_fragment, calibrated_fragment, output)
            lines = result.read_text(encoding="utf-8").splitlines()

            self.assertEqual(lines[0], "999991 MINIMA               . DFAULT 150.0   5.0 150.0  11.0  50.0 .0150  0.70  55.0  24.0  12.0  10.0")
            self.assertEqual(lines[1], "999992 MAXIMA               . DFAULT 800.0 300.0 850.0  13.0  72.0 .0300  1.30  90.0  35.0  18.0  20.0")
            self.assertTrue(any(line.startswith("WHR001 ") for line in lines))
            self.assertTrue(any(line.startswith("WHR006 MEIXIANGZHAN2") for line in lines))
            self.assertTrue(any(line.startswith("IB0001 ") for line in lines))


if __name__ == "__main__":
    unittest.main()
