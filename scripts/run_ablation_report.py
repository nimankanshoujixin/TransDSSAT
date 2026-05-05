from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from transdssat.dataset import split_name
from transdssat.evaluation import score_trajectory, summarize_scorecards
from transdssat.rl import SeasonRLTransformer, evaluate_policy_for_scenario, sample_policies
from transdssat.scenarios import build_quzhou_scenarios
from transdssat.season import (
    BASELINE_BUDGET_SOURCES,
    BASELINE_NAMES,
    build_baseline_policy,
)


def load_model(checkpoint_path: str):
    import torch

    checkpoint = torch.load(checkpoint_path, map_location="cpu")
    model = SeasonRLTransformer()
    model.load_state_dict(checkpoint["model_state_dict"])
    model.eval()
    return model


def evaluate_mode(model, scenarios, baseline_name: str, baseline_budget_source: str, decision_granularity: str, control_mode: str):
    scorecards = []
    for scenario in scenarios:
        baseline_policy = build_baseline_policy(
            scenario,
            baseline_name=baseline_name,
            decision_granularity=decision_granularity,
            budget_source=baseline_budget_source,
        )
        baseline_trajectory = evaluate_policy_for_scenario(scenario, baseline_policy)
        candidate_policy = sample_policies(
            model,
            [scenario],
            greedy=True,
            decision_granularity=decision_granularity,
            control_mode=control_mode,
            reference_policies=[baseline_policy],
        )[0].policy
        candidate_trajectory = evaluate_policy_for_scenario(scenario, candidate_policy)
        scorecards.append(score_trajectory(scenario, candidate_trajectory, baseline_trajectory))
    return {
        "control_mode": control_mode,
        "summary": summarize_scorecards(scorecards),
        "scorecards": [card.to_dict() for card in scorecards],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run water-only / nitrogen-only / joint ablation summaries.")
    parser.add_argument("--engine", default="dssat_proxy")
    parser.add_argument("--scenario-count", type=int, default=120)
    parser.add_argument("--sampling-mode", choices=("grid", "random"), default="random")
    parser.add_argument("--crops", nargs="+", default=["wheat", "maize"])
    parser.add_argument("--split", choices=("train", "test", "all"), default="test")
    parser.add_argument("--seed", type=int, default=20260426)
    parser.add_argument("--baseline-name", choices=BASELINE_NAMES, default="literature_ncp")
    parser.add_argument("--baseline-budget-source", choices=BASELINE_BUDGET_SOURCES, default="scenario")
    parser.add_argument("--decision-granularity", choices=("stage", "daily"), default="stage")
    parser.add_argument("--checkpoint-water", required=True)
    parser.add_argument("--checkpoint-nitrogen", required=True)
    parser.add_argument("--checkpoint-joint", required=True)
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    scenarios = build_quzhou_scenarios(
        target_count=args.scenario_count,
        engines=(args.engine,),
        crops_filter=tuple(args.crops) if args.crops else None,
        sampling_mode=args.sampling_mode,
        seed=args.seed,
    )
    if args.split != "all":
        scenarios = [scenario for scenario in scenarios if split_name(scenario.scenario_id) == args.split]

    water_model = load_model(args.checkpoint_water)
    nitrogen_model = load_model(args.checkpoint_nitrogen)
    joint_model = load_model(args.checkpoint_joint)

    report = {
        "engine": args.engine,
        "split": args.split,
        "scenario_count": len(scenarios),
        "baseline_name": args.baseline_name,
        "baseline_budget_source": args.baseline_budget_source,
        "decision_granularity": args.decision_granularity,
        "ablations": [
            evaluate_mode(
                water_model,
                scenarios,
                baseline_name=args.baseline_name,
                baseline_budget_source=args.baseline_budget_source,
                decision_granularity=args.decision_granularity,
                control_mode="water_only",
            ),
            evaluate_mode(
                nitrogen_model,
                scenarios,
                baseline_name=args.baseline_name,
                baseline_budget_source=args.baseline_budget_source,
                decision_granularity=args.decision_granularity,
                control_mode="nitrogen_only",
            ),
            evaluate_mode(
                joint_model,
                scenarios,
                baseline_name=args.baseline_name,
                baseline_budget_source=args.baseline_budget_source,
                decision_granularity=args.decision_granularity,
                control_mode="joint",
            ),
        ],
    }

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
