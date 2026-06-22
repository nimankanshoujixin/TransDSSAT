from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys
import traceback

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from transdssat.domain import CropAction
from transdssat.dssat import build_filesystem_interactive_transport_from_env
from transdssat.scenarios import build_quzhou_scenarios


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run a minimal official-DSSAT interactive session smoke check through the "
            "configured controller/transport boundary."
        )
    )
    parser.add_argument("--crop", default="maize", choices=("maize", "rice"))
    parser.add_argument("--seed", type=int, default=20260622)
    parser.add_argument("--decision-interval-days", type=int, default=5)
    parser.add_argument("--irrigation-mm", type=float, default=0.0)
    parser.add_argument("--nitrogen-kg-ha", type=float, default=0.0)
    parser.add_argument(
        "--skip-step",
        action="store_true",
        help="Only validate reset/close boundary; do not issue a step request.",
    )
    parser.add_argument(
        "--output-json",
        default="",
        help="Optional path for a structured smoke report.",
    )
    parser.add_argument(
        "--archive-run-dir",
        default="",
        help="Optional path where the DSSAT run directory should be copied after the smoke finishes.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    requested_action = CropAction(
        irrigation_mm=args.irrigation_mm,
        nitrogen_kg_ha=args.nitrogen_kg_ha,
    )
    scenario = build_quzhou_scenarios(
        target_count=1,
        engines=("dssat_official",),
        crops_filter=(args.crop,),
        sampling_mode="random",
        seed=args.seed,
    )[0]
    transport = build_filesystem_interactive_transport_from_env(scenario, runtime_role="patched")
    report: dict[str, object] = {
        "scenario_id": scenario.scenario_id,
        "crop": scenario.crop_spec.crop_name,
        "decision_interval_days": args.decision_interval_days,
        "requested_action": requested_action.to_dict(),
        "skip_step": bool(args.skip_step),
        "protocol_dir": str(transport.protocol.root_dir),
        "session_manifest": str(transport.protocol.session_manifest_path),
        "controller_log_path": str(transport.controller_log_path),
        "status": "started",
    }
    exit_code = 0
    try:
        reset_result = transport.start_session(scenario)
        report["run_dir"] = reset_result.run_dir
        report["reset_info"] = dict(reset_result.info)
        report["initial_state"] = reset_result.state.to_dict()
        if not args.skip_step:
            step_result = transport.step_session(
                requested_action,
                decision_interval_days=args.decision_interval_days,
            )
            report["step"] = {
                "reward": step_result.reward,
                "done": step_result.done,
                "run_dir": step_result.run_dir,
                "info": dict(step_result.info),
                "next_state": step_result.next_state.to_dict(),
                "daily_trace_count": len(step_result.daily_trace),
                "final_outcome": None if step_result.final_outcome is None else step_result.final_outcome.to_dict(),
            }
        final_outcome = transport.close_session()
        report["final_outcome"] = None if final_outcome is None else final_outcome.to_dict()
        archive_run_dir = str(args.archive_run_dir).strip()
        if archive_run_dir:
            archive_path = Path(archive_run_dir)
            if archive_path.exists():
                shutil.rmtree(archive_path)
            shutil.copytree(Path(str(report["run_dir"])), archive_path)
            report["archived_run_dir"] = str(archive_path)
        report["status"] = "ok"
    except Exception as exc:
        report["status"] = "error"
        report["error"] = {
            "type": exc.__class__.__name__,
            "message": str(exc),
            "traceback": traceback.format_exc(),
        }
        exit_code = 1
    rendered = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output_json:
        output_path = Path(args.output_json)
        if not output_path.is_absolute():
            output_path = Path.cwd() / output_path
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered, encoding="utf-8")
    print(rendered)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
