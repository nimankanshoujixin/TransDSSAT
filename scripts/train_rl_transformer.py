from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import random
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from transdssat.dataset import split_name
from transdssat.evaluation import score_trajectory, summarize_scorecards
from transdssat.policy import training_readiness
from transdssat.rl import SeasonRLTransformer, evaluate_policy_for_scenario, model_eval_mode, sample_policies
from transdssat.scenarios import build_quzhou_scenarios
from transdssat.season import (
    BASELINE_BUDGET_SOURCES,
    BASELINE_NAMES,
    CONTROL_MODES,
    DECISION_GRANULARITIES,
    build_baseline_policy,
)


def batch_scenarios(items, batch_size: int):
    batch = []
    for item in items:
        batch.append(item)
        if len(batch) == batch_size:
            yield batch
            batch = []
    if batch:
        yield batch


def evaluate_greedy_policy(
    model,
    scenarios,
    baseline_cache,
    baseline_policy_cache,
    decision_granularity: str,
    control_mode: str,
):
    scorecards = []
    rewards = []
    with model_eval_mode(model):
        for scenario in scenarios:
            sampled_policy = sample_policies(
                model,
                [scenario],
                greedy=True,
                decision_granularity=decision_granularity,
                control_mode=control_mode,
                reference_policies=[baseline_policy_cache[scenario.scenario_id]],
            )[0].policy
            candidate = evaluate_policy_for_scenario(scenario, sampled_policy)
            baseline = baseline_cache[scenario.scenario_id]
            scorecards.append(score_trajectory(scenario, candidate, baseline))
            rewards.append(candidate.outcome.cumulative_reward)
    summary = summarize_scorecards(scorecards)
    summary["mean_reward"] = round(sum(rewards) / max(1, len(rewards)), 6)
    return summary, scorecards


def main() -> int:
    parser = argparse.ArgumentParser(description="Train a season-level RL Transformer against DSSAT rewards.")
    parser.add_argument("--engine", default="dssat_proxy", help="wofost_proxy, dssat_proxy, dssat_official")
    parser.add_argument("--scenario-count", type=int, default=108, help="Number of scenarios from the scenario grid.")
    parser.add_argument("--sampling-mode", choices=("grid", "random"), default="random", help="Scenario generation mode.")
    parser.add_argument("--crops", nargs="+", default=["wheat", "maize"], help="Crop subset.")
    parser.add_argument("--epochs", type=int, default=10, help="Number of RL epochs.")
    parser.add_argument("--batch-size", type=int, default=4, help="Scenario batch size per policy update.")
    parser.add_argument("--lr", type=float, default=5e-4, help="Adam learning rate.")
    parser.add_argument("--entropy-coef", type=float, default=0.01, help="Entropy bonus coefficient.")
    parser.add_argument("--seed", type=int, default=20260426, help="Random seed.")
    parser.add_argument(
        "--baseline-name",
        choices=BASELINE_NAMES,
        default="literature_ncp",
        help="Reference baseline used for reward-gain comparison.",
    )
    parser.add_argument(
        "--baseline-budget-source",
        choices=BASELINE_BUDGET_SOURCES,
        default="scenario",
        help="Use paper fixed totals or scale the literature policy to each scenario budget.",
    )
    parser.add_argument(
        "--decision-granularity",
        choices=DECISION_GRANULARITIES,
        default="stage",
        help="Policy output granularity for the RL controller.",
    )
    parser.add_argument(
        "--control-mode",
        choices=CONTROL_MODES,
        default="joint",
        help="Optimize irrigation only, nitrogen only, or both jointly.",
    )
    parser.add_argument(
        "--selection-metric",
        choices=("reward_gain", "score"),
        default="reward_gain",
        help="How to select the best checkpoint on the test split.",
    )
    parser.add_argument("--output-dir", default="artifacts/rl_transformer", help="Directory for RL checkpoints and metrics.")
    args = parser.parse_args()

    readiness = training_readiness()
    if not readiness.torch_available:
        print(readiness.message)
        return 0

    import torch

    random.seed(args.seed)
    torch.manual_seed(args.seed)

    scenarios = build_quzhou_scenarios(
        target_count=args.scenario_count,
        engines=(args.engine,),
        crops_filter=tuple(args.crops) if args.crops else None,
        sampling_mode=args.sampling_mode,
        seed=args.seed,
    )
    train_scenarios = [scenario for scenario in scenarios if split_name(scenario.scenario_id) == "train"]
    test_scenarios = [scenario for scenario in scenarios if split_name(scenario.scenario_id) == "test"]

    baseline_cache = {}
    baseline_policy_cache = {}
    for scenario in scenarios:
        baseline_policy = build_baseline_policy(
            scenario,
            baseline_name=args.baseline_name,
            decision_granularity=args.decision_granularity,
            budget_source=args.baseline_budget_source,
        )
        baseline_policy_cache[scenario.scenario_id] = baseline_policy
        baseline_cache[scenario.scenario_id] = evaluate_policy_for_scenario(scenario, baseline_policy)

    model = SeasonRLTransformer()
    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    history = []
    best_checkpoint = None
    best_score = None

    for epoch in range(1, args.epochs + 1):
        model.train()
        shuffled = train_scenarios[:]
        random.shuffle(shuffled)
        epoch_rewards = []
        epoch_gains = []

        for scenario_batch in batch_scenarios(shuffled, args.batch_size):
            optimizer.zero_grad()
            sampled = sample_policies(
                model,
                scenario_batch,
                greedy=False,
                decision_granularity=args.decision_granularity,
                control_mode=args.control_mode,
                reference_policies=[baseline_policy_cache[scenario.scenario_id] for scenario in scenario_batch],
            )

            rewards = []
            baselines = []
            log_probs = []
            entropies = []
            for scenario, sampled_policy in zip(scenario_batch, sampled):
                trajectory = evaluate_policy_for_scenario(scenario, sampled_policy.policy)
                reward = trajectory.outcome.cumulative_reward
                baseline_reward = baseline_cache[scenario.scenario_id].outcome.cumulative_reward
                rewards.append(reward)
                baselines.append(baseline_reward)
                log_probs.append(sampled_policy.log_prob)
                entropies.append(sampled_policy.entropy)
                epoch_rewards.append(reward)
                epoch_gains.append(reward - baseline_reward)

            rewards_tensor = torch.tensor(rewards, dtype=torch.float32)
            baselines_tensor = torch.tensor(baselines, dtype=torch.float32)
            advantages = rewards_tensor - baselines_tensor
            if advantages.numel() > 1:
                advantages = (advantages - advantages.mean()) / (advantages.std(unbiased=False) + 1e-6)
            log_prob_tensor = torch.stack(log_probs)
            entropy_tensor = torch.stack(entropies)
            loss = -(advantages * log_prob_tensor).mean() - args.entropy_coef * entropy_tensor.mean()
            loss.backward()
            optimizer.step()

        train_summary = {
            "mean_reward": round(sum(epoch_rewards) / max(1, len(epoch_rewards)), 6),
            "mean_reward_gain_vs_baseline": round(sum(epoch_gains) / max(1, len(epoch_gains)), 6),
            "scenario_count": len(epoch_rewards),
        }
        test_summary, _ = evaluate_greedy_policy(
            model,
            test_scenarios,
            baseline_cache,
            baseline_policy_cache,
            decision_granularity=args.decision_granularity,
            control_mode=args.control_mode,
        )
        history.append({"epoch": epoch, "train": train_summary, "test": test_summary})

        selection_score = (
            test_summary["mean_reward_gain"]
            if args.selection_metric == "reward_gain"
            else test_summary["mean_total_score_100"]
        )
        if best_score is None or selection_score > best_score:
            best_score = selection_score
            best_checkpoint = {
                "model_state_dict": copy.deepcopy(model.state_dict()),
                "epoch": epoch,
                "train_summary": train_summary,
                "test_summary": test_summary,
                "engine": args.engine,
                "scenario_count": args.scenario_count,
                "crops": args.crops,
                "sampling_mode": args.sampling_mode,
                "selection_metric": args.selection_metric,
                "baseline_name": args.baseline_name,
                "baseline_budget_source": args.baseline_budget_source,
                "decision_granularity": args.decision_granularity,
                "control_mode": args.control_mode,
            }

        print(
            json.dumps(
                {
                    "epoch": epoch,
                    "train": train_summary,
                    "test": test_summary,
                },
                ensure_ascii=False,
            )
        )

    assert best_checkpoint is not None
    checkpoint_path = output_dir / "rl_transformer_policy.pt"
    metrics_path = output_dir / "metrics.json"
    torch.save(best_checkpoint, checkpoint_path)
    metrics_path.write_text(
        json.dumps({"history": history, "best_epoch": best_checkpoint["epoch"]}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "checkpoint": str(checkpoint_path),
                "metrics": str(metrics_path),
                "best_epoch": best_checkpoint["epoch"],
                "best_selection_value": best_score,
                "selection_metric": args.selection_metric,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
