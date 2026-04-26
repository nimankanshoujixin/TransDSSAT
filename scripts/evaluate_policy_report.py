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
from transdssat.season import build_baseline_policy


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate an agronomic evaluation report for baseline or RL policies.")
    parser.add_argument("--engine", default="dssat_proxy", help="wofost_proxy, dssat_proxy, dssat_official")
    parser.add_argument("--scenario-count", type=int, default=108, help="Number of scenarios to evaluate.")
    parser.add_argument("--crops", nargs="+", default=["wheat", "maize"], help="Crop subset.")
    parser.add_argument("--split", choices=("train", "test", "all"), default="test")
    parser.add_argument("--checkpoint", default=None, help="Optional RL checkpoint path. Omit for baseline-only report.")
    parser.add_argument("--output", default=None, help="Optional JSON report path.")
    args = parser.parse_args()

    scenarios = build_quzhou_scenarios(
        target_count=args.scenario_count,
        engines=(args.engine,),
        crops_filter=tuple(args.crops) if args.crops else None,
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
        baseline_policy = build_baseline_policy(scenario)
        baseline_trajectory = evaluate_policy_for_scenario(scenario, baseline_policy)
        if model is None:
            candidate_trajectory = baseline_trajectory
        else:
            sampled_policy = sample_policies(model, [scenario], greedy=True)[0].policy
            candidate_trajectory = evaluate_policy_for_scenario(scenario, sampled_policy)

        scorecards.append(score_trajectory(scenario, candidate_trajectory, baseline_trajectory))

    summary = summarize_scorecards(scorecards)
    report = {
        "engine": args.engine,
        "split": args.split,
        "scenario_count": len(scorecards),
        "mode": "rl" if model is not None else "baseline",
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
