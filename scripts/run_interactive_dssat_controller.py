from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from transdssat.dssat.interactive_controller import (
    build_interactive_controller_driver,
    load_interaction_metadata_from_manifest,
    load_protocol_from_manifest,
    load_scenario_from_manifest,
    resolve_interactive_driver_mode,
    validate_interaction_metadata,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the external official-DSSAT interactive controller for a TransDSSAT session."
    )
    parser.add_argument("session_manifest", help="Path to session_manifest.json written by the transport.")
    parser.add_argument(
        "--driver-mode",
        default="auto",
        help="Interactive controller driver mode: auto, replay_bridge, or patched_runtime_subprocess.",
    )
    args = parser.parse_args()

    manifest_path = Path(args.session_manifest)
    if not manifest_path.is_absolute():
        manifest_path = (Path.cwd() / manifest_path).resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    scenario = load_scenario_from_manifest(manifest)
    protocol = load_protocol_from_manifest(manifest)
    interaction = validate_interaction_metadata(load_interaction_metadata_from_manifest(manifest))
    driver_mode = resolve_interactive_driver_mode(args.driver_mode, interaction=interaction)
    controller = build_interactive_controller_driver(
        driver_mode=driver_mode,
        manifest_path=manifest_path,
        scenario=scenario,
        protocol=protocol,
        interaction=interaction,
    )
    controller.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
