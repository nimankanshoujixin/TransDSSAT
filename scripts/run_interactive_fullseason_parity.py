from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from transdssat.dssat import DSSATOutputParser, DSSATRunConfig, DSSATRunner, build_filesystem_interactive_transport_from_env
from transdssat.dssat.validation import compare_output_file, infer_active_output_selector
from transdssat.environments.stepwise import StepwiseDecisionEnvironment
from transdssat.scenario_sources import resolve_scenario
from transdssat.season import SeasonPolicy, StageDecision
from transdssat.stepwise_policy import build_heuristic_stepwise_policy


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run a full-season interactive patched-DSSAT episode, reconstruct the executed action schedule, "
            "replay the same schedule on vanilla DSSAT, and compare outputs."
        )
    )
    parser.add_argument("--crop", default="maize", choices=("maize", "rice"))
    parser.add_argument("--scenario-source", default="quzhou", choices=("quzhou", "real_subset", "json"))
    parser.add_argument("--seed", type=int, default=20260622)
    parser.add_argument("--scenario-index", type=int, default=0)
    parser.add_argument("--sampling-mode", default="random", choices=("random", "grid"))
    parser.add_argument("--scenario-json", default="")
    parser.add_argument("--subset-id", default="")
    parser.add_argument("--treatment-no", type=int, default=0)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--report-name", default="interactive_fullseason_parity_report.json")
    parser.add_argument("--vanilla-runtime-root", default="")
    parser.add_argument("--baseline-name", default="heuristic", choices=("heuristic",))
    return parser


def _run_interactive_fullseason(scenario) -> tuple[Path, SeasonPolicy, dict]:
    transport = build_filesystem_interactive_transport_from_env(scenario, runtime_role="patched")
    env = StepwiseDecisionEnvironment(
        scenario,
        official_backend_mode="interactive_patched",
        official_interactive_transport=transport,
    )
    policy = build_heuristic_stepwise_policy(scenario)
    observation = env.reset()
    policy.reset(scenario)

    executed_actions: list[StageDecision] = []
    transition_log: list[dict] = []
    last_run_dir = Path(transport.run_dir)
    termination = {"mode": "normal", "message": ""}

    while not observation.done:
        action = policy.decide(observation)
        try:
            next_observation, reward, done, info = env.step(action)
        except RuntimeError as exc:
            summary_out = last_run_dir / "Summary.OUT"
            if summary_out.exists():
                termination = {
                    "mode": "controller_exit_with_dssat_outputs",
                    "message": str(exc),
                }
                break
            raise
        executed = dict(info.get("executed_action", {}))
        run_dir = str(info.get("run_dir", "")).strip()
        if run_dir:
            last_run_dir = Path(run_dir)
        irrigation_mm = round(float(executed.get("irrigation_mm", 0.0)), 3)
        nitrogen_kg_ha = round(float(executed.get("nitrogen_kg_ha", 0.0)), 3)
        if irrigation_mm > 0.0 or nitrogen_kg_ha > 0.0:
            executed_actions.append(
                StageDecision(
                    stage=f"interactive_step_{len(executed_actions) + 1:02d}",
                    day_index=int(observation.state.day_index),
                    date=str(observation.decision_date),
                    irrigation_mm=irrigation_mm,
                    nitrogen_kg_ha=nitrogen_kg_ha,
                )
            )
        transition_log.append(
            {
                "decision_date": str(observation.decision_date),
                "day_index": int(observation.state.day_index),
                "reward": float(reward),
                "done": bool(done),
                "executed_action": executed,
                "run_dir": str(last_run_dir),
                "backend_mode": str(info.get("backend_mode", "")),
            }
        )
        observation = next_observation

    return (
        last_run_dir,
        SeasonPolicy(
            policy_id=f"{scenario.scenario_id}-interactive-fullseason-executed",
            scenario_id=scenario.scenario_id,
            actions=executed_actions,
        ),
        {
            "transition_count": len(transition_log),
            "transitions": transition_log,
            "termination": termination,
        },
    )


def _compare_environmental_metric(left: dict, right: dict, field: str) -> float:
    left_env = dict(left.get("environmental_metrics", {}))
    right_env = dict(right.get("environmental_metrics", {}))
    return round(abs(float(left_env.get(field, 0.0)) - float(right_env.get(field, 0.0))), 6)


def main() -> int:
    args = build_parser().parse_args()
    output_root = Path(args.output_root).resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    scenario = resolve_scenario(
        source=args.scenario_source,
        crop=args.crop,
        seed=args.seed,
        scenario_index=args.scenario_index,
        sampling_mode=args.sampling_mode,
        scenario_json=args.scenario_json or None,
        subset_id=args.subset_id,
        treatment_no=args.treatment_no,
    )

    interactive_run_dir, replay_policy, interactive_trace = _run_interactive_fullseason(scenario)

    vanilla_config = DSSATRunConfig.from_env(runtime_role="vanilla")
    if args.vanilla_runtime_root:
        vanilla_config.runtime_root = Path(args.vanilla_runtime_root).resolve()
    vanilla_config.working_root = output_root / "vanilla_runs"
    vanilla_runner = DSSATRunner(config=vanilla_config)
    vanilla_context = vanilla_runner.prepare(scenario, replay_policy)
    vanilla_runner.run(vanilla_context)
    vanilla_run_dir = vanilla_context.run_dir

    parser = DSSATOutputParser()
    interactive_parsed = parser.parse(interactive_run_dir, scenario)
    vanilla_parsed = parser.parse(vanilla_run_dir, scenario)

    active_selector = infer_active_output_selector(interactive_run_dir)
    file_comparisons = [
        compare_output_file(
            interactive_run_dir / file_name,
            vanilla_run_dir / file_name,
            file_name=file_name,
            selector=active_selector,
        ).to_dict()
        for file_name in ("Summary.OUT", "PlantGro.OUT", "SoilWat.OUT", "SoilNi.OUT", "Evaluate.OUT")
    ]
    outcome_errors = {
        "yield_kg_ha": round(abs(interactive_parsed.outcome.yield_kg_ha - vanilla_parsed.outcome.yield_kg_ha), 6),
        "biomass_kg_ha": round(abs(interactive_parsed.outcome.biomass_kg_ha - vanilla_parsed.outcome.biomass_kg_ha), 6),
        "total_irrigation_mm": round(
            abs(interactive_parsed.outcome.total_irrigation_mm - vanilla_parsed.outcome.total_irrigation_mm),
            6,
        ),
        "total_nitrogen_kg_ha": round(
            abs(interactive_parsed.outcome.total_nitrogen_kg_ha - vanilla_parsed.outcome.total_nitrogen_kg_ha),
            6,
        ),
        "terminal_root_zone_water_mm": _compare_environmental_metric(
            interactive_parsed.outcome.to_dict(),
            vanilla_parsed.outcome.to_dict(),
            "terminal_root_zone_water_mm",
        ),
        "terminal_soil_nitrogen_kg_ha": _compare_environmental_metric(
            interactive_parsed.outcome.to_dict(),
            vanilla_parsed.outcome.to_dict(),
            "terminal_soil_nitrogen_kg_ha",
        ),
    }

    payload = {
        "status": "ok",
        "scenario_id": scenario.scenario_id,
        "scenario_source": args.scenario_source,
        "interactive_run_dir": str(interactive_run_dir),
        "vanilla_run_dir": str(vanilla_run_dir),
        "baseline_name": args.baseline_name,
        "active_output_selector": active_selector.to_dict() if active_selector is not None else None,
        "replayed_policy": replay_policy.to_dict(),
        "interactive_trace": interactive_trace,
        "interactive_outcome": interactive_parsed.outcome.to_dict(),
        "vanilla_outcome": vanilla_parsed.outcome.to_dict(),
        "outcome_errors": outcome_errors,
        "file_comparisons": file_comparisons,
        "checks": {
            "all_files_match": all(bool(item["match"]) for item in file_comparisons),
            "all_semantic_files_match": all(bool(item.get("semantic_match")) for item in file_comparisons),
            "all_outcome_fields_match": all(value <= 1e-3 for value in outcome_errors.values()),
        },
    }
    payload["status"] = (
        "ok"
        if payload["checks"]["all_semantic_files_match"] and payload["checks"]["all_outcome_fields_match"]
        else "failed"
    )

    rendered = json.dumps(payload, indent=2, ensure_ascii=False)
    report_path = output_root / args.report_name
    report_path.write_text(rendered, encoding="utf-8")
    print(rendered)
    return 0 if payload["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
