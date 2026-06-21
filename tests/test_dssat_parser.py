from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from transdssat.dssat import DSSATOutputParser
from transdssat.scenarios import build_quzhou_scenarios


class DSSATParserTests(unittest.TestCase):
    def setUp(self) -> None:
        self.scenario = build_quzhou_scenarios(
            target_count=1,
            engines=("dssat_official",),
            crops_filter=("maize",),
            sampling_mode="random",
            seed=20260616,
        )[0]

    def test_parse_outcome_captures_cold_termination_and_phenology(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            (run_dir / "Summary.OUT").write_text(
                "\n".join(
                    [
                        "@RUNNO TRNO PDAT EDAT ADAT MDAT HDAT HYEAR CWAM HWAM IRCM NICM",
                        "1 1 2018176 2018183 2018257 2018294 2018294 2018 9319 0 177 168",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            (run_dir / "PlantGro.OUT").write_text(
                "\n".join(
                    [
                        "@YEAR DOY DAS DAP LAID CWAD TURFAC NSTRES",
                        "2018 175 0 0 0.1 100.0 1.0 1.0",
                        "2018 176 1 1 0.2 120.0 1.0 1.0",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            (run_dir / "SoilWat.OUT").write_text(
                "\n".join(
                    [
                        "@YEAR DOY DAS TSW",
                        "2018 175 0 180.0",
                        "2018 176 1 181.0",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            (run_dir / "SoilNi.OUT").write_text(
                "\n".join(
                    [
                        "@YEAR DOY DAS NIAD",
                        "2018 175 0 90.0",
                        "2018 176 1 89.0",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            (run_dir / "WARNING.OUT").write_text(
                "\n".join(
                    [
                        "*RUN   1",
                        "MZ_GRO  YEAR DOY = 2018 294",
                        "Crop experienced  15 days below   6.0C",
                        "Growth program terminated.",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            parsed = DSSATOutputParser().parse(run_dir, self.scenario)

        self.assertEqual(parsed.outcome.environmental_metrics["termination_reason"], "cold_termination")
        self.assertEqual(parsed.outcome.yield_kg_ha, 0.0)
        self.assertEqual(parsed.outcome.biomass_kg_ha, 120.0)
        self.assertIn("Growth program terminated.", parsed.outcome.environmental_metrics["warning_messages"])

    def test_summary_phenology_recovers_fixed_width_noise_tokens(self) -> None:
        phenology = DSSATOutputParser()._summary_phenology(
            {
                "PDAT": "21186",
                "EDAT": "21228",
                "ADAT": "21253 20",
                "MDAT": "21285 20",
                "HDAT": "21285 20",
                "HYEAR": "2021",
            }
        )

        self.assertEqual(phenology["adat"], 21253.0)
        self.assertEqual(phenology["mdat"], 21285.0)
        self.assertEqual(phenology["hyear"], 2021.0)


if __name__ == "__main__":
    unittest.main()
