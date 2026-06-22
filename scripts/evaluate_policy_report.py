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
    CONTROL_MODES,
    DECISION_GRANULARITIES,
    build_baseline_policy,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate an agronomic evaluation report for baseline or RL policies.")
    parser.add_argument(
        "--engine",
        choices=("dssat_official",),
        default="dssat_official",
        help="Evaluation backend. Official DSSAT only.",
    )
    parser.add_argument("--scenario-count", type=int, default=108, help="Number of scenarios to evaluate.")
    parser.add_argument("--sampling-mode", choices=("grid", "random"), default="random")
    parser.add_argument("--crops", nargs="+", default=["wheat", "maize"], help="Crop subset.")
    parser.add_argument("--split", choices=("train", "test", "all"), default="test")
    parser.add_argument("--checkpoint", default=None, help="Optional RL checkpoint path. Omit for baseline-only report.")
    parser.add_argument("--output", default=None, help="Optional JSON report path.")
    parser.add_argument("--seed", type=int, default=20260426)
    parser.add_argument("--baseline-name", choices=BASELINE_NAMES, default="literature_ncp")
    parser.add_argument("--baseline-budget-source", choices=BASELINE_BUDGET_SOURCES, default="scenario")
    parser.add_argument("--decision-granularity", choices=DECISION_GRANULARITIES, default="stage")
    parser.add_argument("--control-mode", choices=CONTROL_MODES, default="joint")
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

    model = None
    if args.checkpoint:
        import torch

        checkpoint = torch.load(args.checkpoint, map_location="cpu")
        model = SeasonRLTransformer()
        model.load_state_dict(checkpoint["model_state_dict"])
        model.eval()

    scorecards = []
    for scenario in scenarios:
        baseline_policy = build_baseline_policy(
            scenario,
            baseline_name=args.baseline_name,
            decision_granularity=args.decision_granularity,
            budget_source=args.baseline_budget_source,
        )
        baseline_trajectory = evaluate_policy_for_scenario(scenario, baseline_policy)
        if model is None:
            candidate_trajectory = baseline_trajectory
        else:
            sampled_policy = sample_policies(
                model,
                [scenario],
                greedy=True,
                decision_granularity=args.decision_granularity,
                control_mode=args.control_mode,
                reference_policies=[baseline_policy],
            )[0].policy
            candidate_trajectory = evaluate_policy_for_scenario(scenario, sampled_policy)

        scorecards.append(score_trajectory(scenario, candidate_trajectory, baseline_trajectory))

    summary = summarize_scorecards(scorecards)
    report = {
        "engine": args.engine,
        "split": args.split,
        "scenario_count": len(scorecards),
        "mode": "rl" if model is not None else "baseline",
        "baseline_name": args.baseline_name,
        "baseline_budget_source": args.baseline_budget_source,
        "decision_granularity": args.decision_granularity,
        "control_mode": args.control_mode,
        "summary": summary,
        "scorecards": [card.to_dict() for card in scorecards],
    }

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
