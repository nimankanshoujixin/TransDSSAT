from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from transdssat.dssat import DSSATOutputParser, DSSATRunConfig, DSSATRunner, build_filesystem_interactive_transport_from_env
from transdssat.discrete_actions import ActionConstraintRules
from transdssat.dssat.validation import (
    compare_output_file,
    infer_active_output_selector,
    reconstruct_interactive_session_policy,
)
from transdssat.real_subset_replay import load_real_subset_replay_case
from transdssat.scenario_sources import resolve_scenario
from transdssat.season import SeasonPolicy
from transdssat.stepwise_policy import StepwisePolicy, build_stepwise_policy_from_season_policy
from transdssat.environments.stepwise import StepwiseDecisionEnvironment


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Replay observed real-subset management step-by-step on interactive patched DSSAT, "
            "then compare against vanilla DSSAT under the same observed management sequence."
        )
    )
    parser.add_argument("--subset-id", required=True, choices=("mx475_migrated", "wuhu_rice_calibrated"))
    parser.add_argument("--treatment-no", required=True, type=int)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--report-name", default="interactive_real_subset_observed_management_parity_report.json")
    parser.add_argument("--vanilla-runtime-root", default="")
    return parser


def _build_observed_management_scenario(subset_id: str, treatment_no: int):
    materialized = resolve_scenario(
        source="real_subset",
        crop="rice",
        subset_id=subset_id,
        treatment_no=treatment_no,
    )
    scenario = copy.deepcopy(materialized)
    scenario.decision_context.decision_interval_days = 1
    scenario.decision_context.irrigation_min_gap_days = 1
    scenario.decision_context.nitrogen_min_gap_days = 1
    scenario.decision_context.allow_combined_actions = True
    return scenario


def _scheduled_action_for_observation(policy: StepwisePolicy, observation) -> dict:
    schedule = getattr(policy, "action_schedule", None)
    if not isinstance(schedule, dict):
        return {}
    action = schedule.get(observation.day_index)
    return {} if action is None else action.to_dict()


def _observed_management_replay_constraint_rules(scenario) -> ActionConstraintRules:
    return ActionConstraintRules(
        decision_interval_days=scenario.decision_context.decision_interval_days,
        irrigation_min_gap_days=scenario.decision_context.irrigation_min_gap_days,
        nitrogen_min_gap_days=scenario.decision_context.nitrogen_min_gap_days,
        max_soil_moisture_for_irrigation=999.0,
        allowed_irrigation_stages=["preplant", "in_season", "emergence", "vegetative", "reproductive", "grain_fill"],
        allowed_nitrogen_stages=["preplant", "in_season", "emergence", "vegetative", "reproductive", "grain_fill"],
        ignore_wet_soil_irrigation_block=True,
        notes=[
            "observed_management_replay_override",
            "preserve_source_observed_management_sequence_on_real_subset_path",
            "budget_and_same_input_gap_rules_still_apply",
        ],
    )


def _run_interactive_fullseason(scenario, policy: StepwisePolicy) -> tuple[Path, Path, dict]:
    transport = build_filesystem_interactive_transport_from_env(scenario, runtime_role="patched")
    env = StepwiseDecisionEnvironment(
        scenario,
        constraint_rules=_observed_management_replay_constraint_rules(scenario),
        official_backend_mode="interactive_patched",
        official_interactive_transport=transport,
    )
    observation = env.reset()
    policy.reset(scenario)

    transition_log: list[dict] = []
    last_run_dir = Path(transport.run_dir)
    termination = {"mode": "normal", "message": ""}

    while not observation.done:
        scheduled_action = _scheduled_action_for_observation(policy, observation)
        action_constraints = observation.action_constraints.to_dict()
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
        run_dir = str(info.get("run_dir", "")).strip()
        if run_dir:
            last_run_dir = Path(run_dir)
        transition_log.append(
            {
                "decision_date": str(observation.decision_date),
                "day_index": int(observation.state.day_index),
                "reward": float(reward),
                "done": bool(done),
                "scheduled_action": scheduled_action,
                "policy_action": action.to_dict(),
                "action_constraints": action_constraints,
                "executed_action": dict(info.get("executed_action", {})),
                "run_dir": str(last_run_dir),
                "backend_mode": str(info.get("backend_mode", "")),
            }
        )
        observation = next_observation

    return (
        last_run_dir,
        transport.protocol.root_dir,
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


def _policies_match(left: SeasonPolicy, right: SeasonPolicy) -> bool:
    def _semantic_actions(policy: SeasonPolicy) -> list[tuple[int, str, float, float]]:
        return [
            (
                int(action.day_index),
                str(action.date),
                round(float(action.irrigation_mm), 3),
                round(float(action.nitrogen_kg_ha), 3),
            )
            for action in policy.actions
        ]

    return _semantic_actions(left) == _semantic_actions(right)


def main() -> int:
    args = build_parser().parse_args()
    output_root = Path(args.output_root).resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    case = load_real_subset_replay_case(args.subset_id, args.treatment_no)
    scenario = _build_observed_management_scenario(args.subset_id, args.treatment_no)
    source_policy = case.baseline_policy
    interactive_policy = build_stepwise_policy_from_season_policy(
        scenario,
        source_policy,
        suffix="observed-management-stepwise",
        notes=["real_subset_observed_management_daily_replay"],
    )

    interactive_run_dir, protocol_dir, interactive_trace = _run_interactive_fullseason(scenario, interactive_policy)
    reconstructed_policy = reconstruct_interactive_session_policy(protocol_dir)

    vanilla_config = DSSATRunConfig.from_env(runtime_role="vanilla")
    if args.vanilla_runtime_root:
        vanilla_config.runtime_root = Path(args.vanilla_runtime_root).resolve()
    vanilla_config.working_root = output_root / "vanilla_runs"
    vanilla_runner = DSSATRunner(config=vanilla_config)
    vanilla_context = vanilla_runner.prepare(scenario, source_policy)
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
        "subset_id": args.subset_id,
        "treatment_no": args.treatment_no,
        "scenario_id": scenario.scenario_id,
        "interactive_run_dir": str(interactive_run_dir),
        "interactive_protocol_dir": str(protocol_dir),
        "vanilla_run_dir": str(vanilla_run_dir),
        "active_output_selector": active_selector.to_dict() if active_selector is not None else None,
        "source_management_policy": source_policy.to_dict(),
        "interactive_stepwise_policy": interactive_policy.to_dict(),
        "reconstructed_interactive_policy": reconstructed_policy.to_dict(),
        "interactive_trace": interactive_trace,
        "interactive_outcome": interactive_parsed.outcome.to_dict(),
        "vanilla_outcome": vanilla_parsed.outcome.to_dict(),
        "outcome_errors": outcome_errors,
        "file_comparisons": file_comparisons,
        "checks": {
            "source_policy_matches_reconstructed_interactive_policy": _policies_match(source_policy, reconstructed_policy),
            "all_files_match": all(bool(item["match"]) for item in file_comparisons),
            "all_semantic_files_match": all(bool(item.get("semantic_match")) for item in file_comparisons),
            "all_outcome_fields_match": all(value <= 1e-3 for value in outcome_errors.values()),
        },
    }
    payload["status"] = (
        "ok"
        if payload["checks"]["source_policy_matches_reconstructed_interactive_policy"]
        and payload["checks"]["all_semantic_files_match"]
        and payload["checks"]["all_outcome_fields_match"]
        else "failed"
    )

    rendered = json.dumps(payload, indent=2, ensure_ascii=False)
    report_path = output_root / args.report_name
    report_path.write_text(rendered, encoding="utf-8")
    print(rendered)
    return 0 if payload["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
