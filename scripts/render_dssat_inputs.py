from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Template preprocessor for turning a TransDSSAT manifest into DSSAT input files."
    )
    parser.add_argument("manifest", help="Path to transdssat_manifest.json")
    args = parser.parse_args()

    manifest_path = Path(args.manifest)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    run_dir = Path(manifest["run_dir"])
    raise SystemExit(
        "\n".join(
            [
                "render_dssat_inputs.py is a template entrypoint, not a finished renderer.",
                f"Manifest: {manifest_path}",
                f"Run dir: {run_dir}",
                "Customize this script on the server to:",
                "1. read transdssat_scenario.json and transdssat_policy.tsv,",
                "2. update or render the DSSAT experiment files inside the run directory,",
                "3. ensure the selected DSSAT executable can run in that directory.",
            ]
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
