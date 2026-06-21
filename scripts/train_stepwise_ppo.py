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

from transdssat.stepwise_ppo import (
    TORCH_AVAILABLE,
    StepwisePolicyDecision,
    build_stepwise_baseline_trajectory,
    build_checkpoint_guardrail_summary,
    rollout_stepwise_episode,
    select_highest_legal_action,
    summarize_rollout_episodes,
)
from transdssat.scenarios import clone_objective_context_with_reward_contract
from transdssat.testset import ScenarioPoolBundle, generate_training_scenario_pool
from transdssat.evaluation import score_trajectory, summarize_scorecards


def resolve_device(requested: str):
    import torch

    if requested == "auto":
        return torch.device("cuda" if torch.cuda.is_available() else "cpu")
    return torch.device(requested)


def split_bundle(bundle: ScenarioPoolBundle) -> dict[str, list]:
    return {
        "train": [record.scenario for record in bundle.records if record.split == "train"],
        "val": [record.scenario for record in bundle.records if record.split == "val"],
        "test": [record.scenario for record in bundle.records if record.split == "test"],
    }


def build_baseline_cache(scenarios: list, baseline_name: str) -> dict[str, object]:
    return {
        scenario.scenario_id: build_stepwise_baseline_trajectory(scenario, baseline_name=baseline_name)
        for scenario in scenarios
    }


def summarize_baseline_reference(scenarios: list, baseline_cache: dict[str, object]) -> dict[str, float]:
    scorecards = [
        score_trajectory(
            scenario,
            baseline_cache[scenario.scenario_id],
            baseline_cache[scenario.scenario_id],
        )
        for scenario in scenarios
    ]
    return summarize_scorecards(scorecards)


def resolve_pool_seed(requested_pool_seed: int | None, training_seed: int) -> int:
    return training_seed if requested_pool_seed is None else requested_pool_seed


def apply_reward_contract(scenarios: list, reward_contract: str) -> None:
    for scenario in scenarios:
        scenario.objective_context = clone_objective_context_with_reward_contract(
            scenario.objective_context,
            reward_contract,
        )


def apply_control_mode_guardrail_channels(scenarios: list, control_mode: str) -> None:
    channels = {
        "water_only": ["irrigation"],
        "nitrogen_only": ["nitrogen"],
        "joint": ["irrigation", "nitrogen"],
    }[control_mode]
    for scenario in scenarios:
        soft_preferences = scenario.objective_context.soft_preferences
        guardrail = dict(soft_preferences.get("anti_collapse_guardrail", {}))
        if not guardrail:
            continue
        guardrail["active_channels"] = list(channels)
        soft_preferences["anti_collapse_guardrail"] = guardrail


def _apply_enabled_override(config: dict[str, float], *, force_disable: bool, force_enable: bool) -> dict[str, float]:
    if force_disable:
        config["enabled"] = False
    elif force_enable:
        config["enabled"] = True
    return config


def resolve_training_activity_regularizer(
    scenarios: list,
    control_mode: str,
    *,
    force_disable: bool = False,
    force_enable: bool = False,
) -> dict[str, float]:
    if not scenarios:
        return {"enabled": False}
    soft_preferences = scenarios[0].objective_context.soft_preferences
    regularizer = dict(soft_preferences.get("training_activity_regularizer", {}))
    if not regularizer:
        return {"enabled": False}
    regularizer = _apply_enabled_override(regularizer, force_disable=force_disable, force_enable=force_enable)
    if control_mode == "water_only":
        regularizer["minimum_expected_nitrogen_ratio"] = 0.0
        regularizer["nitrogen_penalty_weight"] = 0.0
    elif control_mode == "nitrogen_only":
        regularizer["minimum_expected_irrigation_ratio"] = 0.0
        regularizer["irrigation_penalty_weight"] = 0.0
    return regularizer


def resolve_training_behavior_anchor(
    scenarios: list,
    control_mode: str,
    *,
    force_disable: bool = False,
    force_enable: bool = False,
) -> dict[str, float]:
    if not scenarios:
        return {"enabled": False}
    soft_preferences = scenarios[0].objective_context.soft_preferences
    anchor = dict(soft_preferences.get("training_behavior_anchor", {}))
    if not anchor:
        return {"enabled": False}
    anchor = _apply_enabled_override(anchor, force_disable=force_disable, force_enable=force_enable)
    if control_mode == "water_only":
        anchor["minimum_anchor_nitrogen_ratio"] = 0.0
        anchor["nitrogen_penalty_weight"] = 0.0
    elif control_mode == "nitrogen_only":
        anchor["minimum_anchor_irrigation_ratio"] = 0.0
        anchor["irrigation_penalty_weight"] = 0.0
    return anchor


def resolve_training_policy_anchor(
    scenarios: list,
    control_mode: str,
    *,
    force_disable: bool = False,
    force_enable: bool = False,
) -> dict[str, float]:
    if not scenarios:
        return {"enabled": False}
    soft_preferences = scenarios[0].objective_context.soft_preferences
    anchor = dict(soft_preferences.get("training_policy_anchor", {}))
    if not anchor:
        return {"enabled": False}
    anchor = _apply_enabled_override(anchor, force_disable=force_disable, force_enable=force_enable)
    if control_mode == "water_only":
        anchor["nitrogen_amount_penalty_weight"] = 0.0
    elif control_mode == "nitrogen_only":
        anchor["irrigation_amount_penalty_weight"] = 0.0
    return anchor


def resolve_training_advantage_activity_anchor(
    scenarios: list,
    control_mode: str,
    *,
    force_disable: bool = False,
    force_enable: bool = False,
) -> dict[str, float]:
    if not scenarios:
        return {"enabled": False}
    soft_preferences = scenarios[0].objective_context.soft_preferences
    anchor = dict(soft_preferences.get("training_advantage_activity_anchor", {}))
    if not anchor:
        return {"enabled": False}
    anchor = _apply_enabled_override(anchor, force_disable=force_disable, force_enable=force_enable)
    if control_mode == "water_only":
        anchor["minimum_anchor_nitrogen_ratio"] = 0.0
        anchor["nitrogen_penalty_weight"] = 0.0
    elif control_mode == "nitrogen_only":
        anchor["minimum_anchor_irrigation_ratio"] = 0.0
        anchor["irrigation_penalty_weight"] = 0.0
    return anchor


def resolve_training_update_admission(
    scenarios: list,
    control_mode: str,
    *,
    force_disable: bool = False,
    force_enable: bool = False,
) -> dict[str, float]:
    if not scenarios:
        return {"enabled": False}
    soft_preferences = scenarios[0].objective_context.soft_preferences
    admission = dict(soft_preferences.get("training_update_admission", {}))
    if not admission:
        return {"enabled": False}
    admission = _apply_enabled_override(admission, force_disable=force_disable, force_enable=force_enable)
    if control_mode == "water_only":
        admission["minimum_nitrogen_ratio"] = 0.0
        admission["nitrogen_penalty_weight"] = 0.0
        admission["minimum_expected_nitrogen_ratio"] = 0.0
        admission["expected_nitrogen_penalty_weight"] = 0.0
        admission["minimum_greedy_nitrogen_ratio"] = 0.0
        admission["greedy_nitrogen_penalty_weight"] = 0.0
    elif control_mode == "nitrogen_only":
        admission["minimum_irrigation_ratio"] = 0.0
        admission["irrigation_penalty_weight"] = 0.0
        admission["minimum_expected_irrigation_ratio"] = 0.0
        admission["expected_irrigation_penalty_weight"] = 0.0
        admission["minimum_greedy_irrigation_ratio"] = 0.0
        admission["greedy_irrigation_penalty_weight"] = 0.0
    return admission


def resolve_training_auxiliary_penalty_budget(
    scenarios: list,
    *,
    force_disable: bool = False,
    force_enable: bool = False,
) -> dict[str, float]:
    if not scenarios:
        return {"enabled": False}
    soft_preferences = scenarios[0].objective_context.soft_preferences
    budget = dict(soft_preferences.get("training_auxiliary_penalty_budget", {}))
    if not budget:
        return {"enabled": False}
    return _apply_enabled_override(budget, force_disable=force_disable, force_enable=force_enable)


def main() -> int:
    parser = argparse.ArgumentParser(description="Train a step-wise masked PPO policy on the TransDSSAT scenario pool.")
    parser.add_argument("--train-count", type=int, default=9000, help="Training split size from generate_training_scenario_pool().")
    parser.add_argument("--val-count", type=int, default=500, help="Validation split size from generate_training_scenario_pool().")
    parser.add_argument("--test-count", type=int, default=500, help="Test split size from generate_training_scenario_pool().")
    parser.add_argument("--epochs", type=int, default=20, help="Number of PPO epochs.")
    parser.add_argument("--episodes-per-epoch", type=int, default=128, help="Number of rollout episodes collected each PPO epoch.")
    parser.add_argument("--update-epochs", type=int, default=4, help="Number of PPO minibatch passes per rollout batch.")
    parser.add_argument("--minibatch-size", type=int, default=256, help="Minibatch size for PPO updates.")
    parser.add_argument("--hidden-dim", type=int, default=128, help="Actor-critic hidden size.")
    parser.add_argument(
        "--backbone",
        choices=("mlp", "transformer"),
        default="mlp",
        help="Actor-critic backbone for PPO updates.",
    )
    parser.add_argument(
        "--action-mode",
        choices=("continuous", "discrete", "gated_continuous"),
        default="continuous",
        help="Policy action parameterization used by the PPO actor.",
    )
    parser.add_argument(
        "--control-mode",
        choices=("water_only", "nitrogen_only", "joint"),
        default="joint",
        help="Control family exposed to the PPO actor.",
    )
    parser.add_argument("--num-heads", type=int, default=4, help="Transformer attention head count.")
    parser.add_argument("--num-layers", type=int, default=2, help="Transformer encoder layer count.")
    parser.add_argument(
        "--max-sequence-length",
        type=int,
        default=64,
        help="Maximum supported sequence length for the Transformer backbone.",
    )
    parser.add_argument("--lr", type=float, default=3e-4, help="Adam learning rate.")
    parser.add_argument("--gamma", type=float, default=0.99, help="Reward discount factor.")
    parser.add_argument("--gae-lambda", type=float, default=0.95, help="GAE lambda.")
    parser.add_argument("--clip-epsilon", type=float, default=0.2, help="PPO clipping epsilon.")
    parser.add_argument("--value-coef", type=float, default=0.5, help="Value-loss coefficient.")
    parser.add_argument("--entropy-coef", type=float, default=0.01, help="Entropy bonus coefficient.")
    parser.add_argument("--max-grad-norm", type=float, default=0.5, help="Gradient clipping norm.")
    parser.add_argument(
        "--target-kl",
        type=float,
        default=0.03,
        help="Optional PPO early-stop threshold on mean approximate KL per update pass.",
    )
    parser.add_argument("--device", default="auto", help="Device selection: auto, cpu, cuda, cuda:0, ...")
    parser.add_argument("--seed", type=int, default=20260608, help="Random seed.")
    parser.add_argument(
        "--pool-seed",
        type=int,
        default=None,
        help="Optional scenario-pool seed. Defaults to --seed so existing runs stay reproducible.",
    )
    parser.add_argument(
        "--baseline-name",
        choices=("heuristic", "heuristic_legacy", "literature", "equal"),
        default="heuristic",
        help="Step-wise baseline used for validation/test scorecards.",
    )
    parser.add_argument(
        "--sampling-mode",
        choices=("random", "realistic", "training_data"),
        default="random",
        help="Scenario-pool source used for PPO training and validation.",
    )
    parser.add_argument(
        "--crops",
        nargs="+",
        default=["maize", "wheat"],
        help="Crop subset used when generating the scenario pool.",
    )
    parser.add_argument(
        "--engine",
        choices=("dssat_official", "dssat_proxy", "wofost_proxy"),
        default="dssat_official",
        help="Scenario engine for rollout, reward, and model selection.",
    )
    parser.add_argument(
        "--reward-contract",
        choices=("reward_v1", "reward_v2"),
        default="reward_v2",
        help="Reward contract injected into generated objective contexts for rollout and training.",
    )
    parser.add_argument(
        "--selection-metric",
        choices=("reward_gain", "score", "yield_floor_gap"),
        default="yield_floor_gap",
        help="Metric used to keep the best checkpoint.",
    )
    parser.add_argument(
        "--selection-min-activity-ratio",
        type=float,
        default=0.05,
        help="Minimum enabled-channel activity ratio versus the baseline replay for a checkpoint to stay eligible.",
    )
    parser.add_argument(
        "--selection-min-yield-floor-attainment-pct",
        type=float,
        default=55.0,
        help="Minimum mean yield-floor attainment percentage required for best-checkpoint eligibility.",
    )
    parser.add_argument("--disable-training-activity-regularizer", action="store_true", help="Disable the PPO expected-activity regularizer.")
    parser.add_argument("--disable-training-behavior-anchor", action="store_true", help="Disable the rollout-activity behavior anchor.")
    parser.add_argument("--disable-training-policy-anchor", action="store_true", help="Disable the rollout-action policy anchor.")
    parser.add_argument("--disable-training-advantage-activity-anchor", action="store_true", help="Disable the positive-advantage activity anchor.")
    parser.add_argument("--disable-training-update-admission", action="store_true", help="Disable the rollout-minibatch activity admission rule.")
    parser.add_argument("--admission-only-screen", action="store_true", help="Convenience ablation: disable every training-time anti-collapse term except update admission.")
    parser.add_argument("--output-dir", default="artifacts/stepwise_ppo", help="Directory for PPO checkpoints and metrics.")
    parser.add_argument("--dry-run", action="store_true", help="Validate scenario pool + rollout wiring without torch training.")
    args = parser.parse_args()

    if args.admission_only_screen:
        args.disable_training_activity_regularizer = True
        args.disable_training_behavior_anchor = True
        args.disable_training_policy_anchor = True
        args.disable_training_advantage_activity_anchor = True
        args.disable_training_update_admission = False

    pool_seed = resolve_pool_seed(args.pool_seed, args.seed)
    bundle = generate_training_scenario_pool(
        train_count=args.train_count,
        val_count=args.val_count,
        test_count=args.test_count,
        engines=(args.engine,),
        crops_filter=tuple(args.crops) if args.crops else None,
        sampling_mode=args.sampling_mode,
        seed=pool_seed,
    )
    splits = split_bundle(bundle)
    for split_scenarios in splits.values():
        apply_reward_contract(split_scenarios, args.reward_contract)
        apply_control_mode_guardrail_channels(split_scenarios, args.control_mode)
    payload = {
        "scenario_pool_summary": bundle.summary.to_dict(),
        "validation_errors": list(bundle.validation_errors),
        "split_sizes": {name: len(items) for name, items in splits.items()},
        "baseline_name": args.baseline_name,
        "backbone": args.backbone,
        "action_mode": args.action_mode,
        "control_mode": args.control_mode,
        "seed": args.seed,
        "pool_seed": pool_seed,
        "reward_contract": args.reward_contract,
        "engine": args.engine,
    }
    training_activity_regularizer = None
    training_behavior_anchor = None
    training_policy_anchor = None
    training_advantage_activity_anchor = None
    training_update_admission = None
    training_auxiliary_penalty_budget = None
    payload["training_baseline_mode"] = "pre_collapse_epoch5_rerun"
    payload["training_activity_regularizer"] = {"enabled": False}
    payload["training_behavior_anchor"] = {"enabled": False}
    payload["training_policy_anchor"] = {"enabled": False}
    payload["training_advantage_activity_anchor"] = {"enabled": False}
    payload["training_update_admission"] = {"enabled": False}
    payload["training_auxiliary_penalty_budget"] = {"enabled": False}
    payload["admission_only_screen"] = False

    if args.dry_run:
        if args.action_mode != "discrete":
            def dry_run_selector(observation, _, sequence):  # noqa: ANN001
                del sequence
                return StepwisePolicyDecision(
                    action_mode="continuous",
                    control_mode=args.control_mode,
                    irrigation_amount_mm=min(10.0, observation.action_constraints.irrigation.max_value),
                    nitrogen_amount_kg_ha=min(20.0, observation.action_constraints.nitrogen.max_value),
                )
        else:
            dry_run_selector = select_highest_legal_action
        sample_episode = rollout_stepwise_episode(
            splits["train"][0],
            dry_run_selector,
            policy_id="stepwise_ppo_dry_run",
            notes=["cpu_safe_rollout_validation", f"action_mode={args.action_mode}", f"control_mode={args.control_mode}"],
        )
        payload["dry_run_episode"] = {
            "scenario_id": sample_episode.scenario_id,
            "rollout_summary": summarize_rollout_episodes([sample_episode]),
            "final_outcome": sample_episode.final_outcome.to_dict(),
            "first_transition_sequence_length": sample_episode.transitions[0].sequence_length,
            "action_mode": sample_episode.action_mode,
            "control_mode": sample_episode.control_mode,
            "reward_contract": args.reward_contract,
            "engine": args.engine,
        }
        print(json.dumps(payload, ensure_ascii=False))
        return 0

    if not TORCH_AVAILABLE:
        payload["blocked_reason"] = "PyTorch is not installed in the current environment."
        payload["next_action"] = "Install torch or rerun on the remote GPU host before starting PPO training."
        print(json.dumps(payload, ensure_ascii=False))
        return 0

    from transdssat.stepwise_ppo import (
        StepwiseGatedContinuousActorCritic,
        StepwiseGatedContinuousTransformerActorCritic,
        StepwisePPOActorCritic,
        StepwiseTransformerActorCritic,
        collect_ppo_rollout_batch,
        evaluate_stepwise_actor_critic,
        run_ppo_update,
    )

    import torch

    random.seed(args.seed)
    torch.manual_seed(args.seed)
    device = resolve_device(args.device)
    if args.backbone == "transformer":
        if args.action_mode != "discrete":
            model = StepwiseGatedContinuousTransformerActorCritic(
                hidden_dim=args.hidden_dim,
                control_mode=args.control_mode,
                num_heads=args.num_heads,
                num_layers=args.num_layers,
                max_sequence_length=args.max_sequence_length,
            ).to(device)
        else:
            model = StepwiseTransformerActorCritic(
                hidden_dim=args.hidden_dim,
                num_heads=args.num_heads,
                num_layers=args.num_layers,
                max_sequence_length=args.max_sequence_length,
            ).to(device)
    else:
        if args.action_mode != "discrete":
            model = StepwiseGatedContinuousActorCritic(
                hidden_dim=args.hidden_dim,
                control_mode=args.control_mode,
            ).to(device)
        else:
            model = StepwisePPOActorCritic(hidden_dim=args.hidden_dim).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr)

    baseline_cache = build_baseline_cache(splits["val"] + splits["test"], args.baseline_name)
    val_baseline_summary = summarize_baseline_reference(splits["val"], baseline_cache)
    test_baseline_summary = summarize_baseline_reference(splits["test"], baseline_cache)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    history = []
    best_checkpoint = None
    best_score = None

    for epoch in range(1, args.epochs + 1):
        rollout_batch, rollout_summary, _ = collect_ppo_rollout_batch(
            model,
            splits["train"],
            device=device,
            episode_count=args.episodes_per_epoch,
            gamma=args.gamma,
            gae_lambda=args.gae_lambda,
            seed=args.seed + epoch,
        )
        update_summary = run_ppo_update(
            model,
            optimizer,
            rollout_batch,
            clip_epsilon=args.clip_epsilon,
            value_coef=args.value_coef,
            entropy_coef=args.entropy_coef,
            minibatch_size=args.minibatch_size,
            update_epochs=args.update_epochs,
            max_grad_norm=args.max_grad_norm,
            target_kl=args.target_kl,
            activity_regularizer=training_activity_regularizer,
            behavior_anchor=training_behavior_anchor,
            policy_anchor=training_policy_anchor,
            advantage_activity_anchor=training_advantage_activity_anchor,
            update_admission=training_update_admission,
            auxiliary_penalty_budget=training_auxiliary_penalty_budget,
        )
        val_summary, _ = evaluate_stepwise_actor_critic(
            model,
            splits["val"],
            baseline_trajectories={k: v for k, v in baseline_cache.items() if k in {scenario.scenario_id for scenario in splits["val"]}},
            device=device,
        )
        test_summary, _ = evaluate_stepwise_actor_critic(
            model,
            splits["test"],
            baseline_trajectories={k: v for k, v in baseline_cache.items() if k in {scenario.scenario_id for scenario in splits["test"]}},
            device=device,
        )

        epoch_record = {
            "epoch": epoch,
            "rollout": rollout_summary,
            "update": update_summary,
            "val": val_summary,
            "test": test_summary,
            "val_baseline": val_baseline_summary,
            "test_baseline": test_baseline_summary,
            "device": str(device),
            "backbone": args.backbone,
            "action_mode": args.action_mode,
            "control_mode": args.control_mode,
            "engine": args.engine,
            "seed": args.seed,
            "pool_seed": pool_seed,
        }
        selection_guardrail = build_checkpoint_guardrail_summary(
            val_summary,
            val_baseline_summary,
            control_mode=args.control_mode,
            min_activity_ratio=args.selection_min_activity_ratio,
            min_yield_floor_attainment_pct=args.selection_min_yield_floor_attainment_pct,
            primary_metric=args.selection_metric,
        )
        epoch_record["selection_guardrail"] = selection_guardrail
        history.append(epoch_record)

        selection_score = tuple(selection_guardrail["selection_tuple"])
        if best_score is None or selection_score > best_score:
            best_score = selection_score
            best_checkpoint = {
                "model_state_dict": copy.deepcopy(model.state_dict()),
                "epoch": epoch,
                "rollout": rollout_summary,
                "update": update_summary,
                "val": val_summary,
                "test": test_summary,
                "val_baseline": val_baseline_summary,
                "test_baseline": test_baseline_summary,
                "selection_guardrail": selection_guardrail,
                "pool_summary": bundle.summary.to_dict(),
                "selection_metric": args.selection_metric,
                "baseline_name": args.baseline_name,
                "device": str(device),
                "backbone": args.backbone,
                "action_mode": args.action_mode,
                "control_mode": args.control_mode,
                "engine": args.engine,
                "config": {
                    "train_count": args.train_count,
                    "val_count": args.val_count,
                    "test_count": args.test_count,
                    "episodes_per_epoch": args.episodes_per_epoch,
                    "update_epochs": args.update_epochs,
                    "minibatch_size": args.minibatch_size,
                    "hidden_dim": args.hidden_dim,
                    "num_heads": args.num_heads,
                    "num_layers": args.num_layers,
                    "max_sequence_length": args.max_sequence_length,
                    "lr": args.lr,
                    "gamma": args.gamma,
                    "gae_lambda": args.gae_lambda,
                    "clip_epsilon": args.clip_epsilon,
                    "value_coef": args.value_coef,
                    "entropy_coef": args.entropy_coef,
                    "max_grad_norm": args.max_grad_norm,
                    "target_kl": args.target_kl,
                    "action_mode": args.action_mode,
                    "control_mode": args.control_mode,
                    "engine": args.engine,
                    "seed": args.seed,
                    "pool_seed": pool_seed,
                    "selection_min_activity_ratio": args.selection_min_activity_ratio,
                    "selection_min_yield_floor_attainment_pct": args.selection_min_yield_floor_attainment_pct,
                    "training_activity_regularizer": training_activity_regularizer,
                    "training_behavior_anchor": training_behavior_anchor,
                    "training_policy_anchor": training_policy_anchor,
                    "training_advantage_activity_anchor": training_advantage_activity_anchor,
                    "training_update_admission": training_update_admission,
                    "training_auxiliary_penalty_budget": training_auxiliary_penalty_budget,
                },
            }

        print(json.dumps(epoch_record, ensure_ascii=False))

    assert best_checkpoint is not None
    checkpoint_path = output_dir / "stepwise_ppo_policy.pt"
    metrics_path = output_dir / "metrics.json"
    torch.save(best_checkpoint, checkpoint_path)
    metrics_path.write_text(
        json.dumps(
            {
                "history": history,
                "best_epoch": best_checkpoint["epoch"],
                "best_selection_value": list(best_score),
                "selection_metric": args.selection_metric,
                "selection_guardrail": best_checkpoint["selection_guardrail"],
                "val_baseline": val_baseline_summary,
                "test_baseline": test_baseline_summary,
                "pool_summary": bundle.summary.to_dict(),
                "validation_errors": list(bundle.validation_errors),
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "checkpoint": str(checkpoint_path),
                "metrics": str(metrics_path),
                "best_epoch": best_checkpoint["epoch"],
                "best_selection_value": list(best_score),
                "selection_metric": args.selection_metric,
                "selection_guardrail": best_checkpoint["selection_guardrail"],
                "device": str(device),
                "backbone": args.backbone,
                "action_mode": args.action_mode,
                "control_mode": args.control_mode,
                "engine": args.engine,
                "seed": args.seed,
                "pool_seed": pool_seed,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
