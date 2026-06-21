from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from transdssat.real_subset_runner import run_real_subset_management_replacement
from transdssat.real_subset_runner import run_real_subset_original_management
from transdssat.real_subset_stepwise_eval import (
    build_real_subset_simulation_scenario,
    rollout_episode_to_season_policy,
    summarize_real_subset_replay_results,
)
from transdssat.stepwise_ppo import (
    StepwiseGatedContinuousActorCritic,
    StepwiseGatedContinuousTransformerActorCritic,
    StepwisePPOActorCritic,
    StepwiseTransformerActorCritic,
    TORCH_AVAILABLE,
    rollout_stepwise_episode,
    select_action_from_model,
)
from transdssat.testset import load_real_data_test_subsets


def _load_model(checkpoint_path: Path, device: str):
    import torch

    checkpoint = torch.load(checkpoint_path, map_location=device)
    config = dict(checkpoint.get("config", {}))
    backbone = str(checkpoint.get("backbone", "mlp"))
    action_mode = str(checkpoint.get("action_mode", "continuous"))
    control_mode = str(checkpoint.get("control_mode", "joint"))
    hidden_dim = int(config.get("hidden_dim", 128))
    num_heads = int(config.get("num_heads", 4))
    num_layers = int(config.get("num_layers", 2))
    max_sequence_length = int(config.get("max_sequence_length", 64))

    if backbone == "transformer":
        if action_mode != "discrete":
            model = StepwiseGatedContinuousTransformerActorCritic(
                hidden_dim=hidden_dim,
                control_mode=control_mode,
                num_heads=num_heads,
                num_layers=num_layers,
                max_sequence_length=max_sequence_length,
            ).to(device)
        else:
            model = StepwiseTransformerActorCritic(
                hidden_dim=hidden_dim,
                num_heads=num_heads,
                num_layers=num_layers,
                max_sequence_length=max_sequence_length,
            ).to(device)
    else:
        if action_mode != "discrete":
            model = StepwiseGatedContinuousActorCritic(
                hidden_dim=hidden_dim,
                control_mode=control_mode,
            ).to(device)
        else:
            model = StepwisePPOActorCritic(hidden_dim=hidden_dim).to(device)
    model.load_state_dict(checkpoint["model_state_dict"])
    model.eval()
    return checkpoint, model


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a best-checkpoint stepwise PPO model on the stable real-data DSSAT subsets after training."
    )
    parser.add_argument("--checkpoint", required=True, help="Path to stepwise_ppo_policy.pt")
    parser.add_argument("--runtime-root", required=True, help="DSSAT runtime root containing dscsm048")
    parser.add_argument("--output-root", required=True, help="Directory for replay outputs and JSON report")
    parser.add_argument("--subset-ids", nargs="+", default=["mx475_migrated", "wuhu_rice_calibrated"])
    parser.add_argument(
        "--case",
        action="append",
        default=[],
        help="Optional subset:treatment selector, for example mx475_migrated:1 . Repeatable.",
    )
    parser.add_argument("--control-mode", choices=("joint", "water_only", "nitrogen_only"), default="joint")
    parser.add_argument("--device", default="cpu", help="Torch device used for greedy PPO inference")
    parser.add_argument("--subset-root", help="Override root containing 作物模型_20260616")
    parser.add_argument("--report-name", default="real_subset_checkpoint_eval_report.json")
    return parser


def _parse_case_selectors(raw_values: list[str]) -> dict[str, set[int]]:
    selectors: dict[str, set[int]] = {}
    for raw in raw_values:
        subset_id, _, treatment_text = str(raw).partition(":")
        if not subset_id or not treatment_text or not treatment_text.isdigit():
            raise ValueError(f"Invalid --case value: {raw}. Expected subset_id:treatment_no")
        selectors.setdefault(subset_id, set()).add(int(treatment_text))
    return selectors


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if not TORCH_AVAILABLE:
        raise RuntimeError("PyTorch is required to evaluate a stepwise PPO checkpoint.")

    checkpoint_path = Path(args.checkpoint).resolve()
    output_root = Path(args.output_root).resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    report_path = output_root / args.report_name
    case_selectors = _parse_case_selectors(list(args.case))

    checkpoint, model = _load_model(checkpoint_path, args.device)
    bundles = load_real_data_test_subsets(tuple(args.subset_ids))
    case_reports: list[dict[str, object]] = []
    for bundle in bundles:
        allowed_treatments = case_selectors.get(bundle.asset.subset_id)
        for case in bundle.replay_cases:
            if allowed_treatments is not None and case.treatment.treatment_no not in allowed_treatments:
                continue
            materialization = build_real_subset_simulation_scenario(
                bundle.asset.subset_id,
                case.treatment.treatment_no,
                subset_root=Path(args.subset_root) if args.subset_root else None,
            )
            episode = rollout_stepwise_episode(
                materialization.scenario,
                lambda obs, _, sequence: select_action_from_model(
                    model,
                    obs,
                    sequence,
                    device=args.device,
                    greedy=True,
                ),
                policy_id=f"stepwise_ppo_best_{bundle.asset.subset_id}_tr{case.treatment.treatment_no:02d}",
                notes=["best_checkpoint_real_subset_eval", f"control_mode={args.control_mode}"],
            )
            candidate_policy = rollout_episode_to_season_policy(
                episode,
                scenario_id=f"{bundle.asset.subset_id}-tr{case.treatment.treatment_no:02d}",
            )
            replay_output_root = output_root / f"{bundle.asset.subset_id}_checkpoint_eval"
            baseline_replay = run_real_subset_original_management(
                bundle.asset.subset_id,
                case.treatment.treatment_no,
                runtime_root=Path(args.runtime_root),
                output_root=replay_output_root / "baseline",
                subset_root=Path(args.subset_root) if args.subset_root else None,
            )
            replay_result = run_real_subset_management_replacement(
                bundle.asset.subset_id,
                case.treatment.treatment_no,
                candidate_policy,
                control_mode=args.control_mode,
                runtime_root=Path(args.runtime_root),
                output_root=replay_output_root / "replacement",
                subset_root=Path(args.subset_root) if args.subset_root else None,
            )
            case_reports.append(
                {
                    "subset_id": bundle.asset.subset_id,
                    "treatment_no": case.treatment.treatment_no,
                    "cultivar_code": case.treatment.cultivar_code,
                    "materialization": materialization.to_dict(),
                    "proxy_policy": candidate_policy.to_dict(),
                    "proxy_rollout": {
                        "scenario_id": episode.scenario_id,
                        "total_reward": episode.total_reward,
                        "decision_count": episode.decision_count,
                        "final_outcome": episode.final_outcome.to_dict(),
                    },
                    "baseline_replay": baseline_replay.to_dict(),
                    "replacement_replay": replay_result.to_dict(),
                    "official_replay": replay_result.to_dict(),
                    "yield_gap_kg_ha": replay_result.yield_gap_kg_ha,
                    "yield_gap_ratio": replay_result.yield_gap_ratio,
                    "baseline_yield_gap_kg_ha": baseline_replay.yield_gap_kg_ha,
                    "baseline_yield_gap_ratio": baseline_replay.yield_gap_ratio,
                    "replacement_minus_baseline_kg_ha": round(
                        replay_result.simulated_yield_kg_ha - baseline_replay.simulated_yield_kg_ha,
                        3,
                    ),
                    "replacement_minus_baseline_ratio": round(
                        0.0
                        if abs(baseline_replay.simulated_yield_kg_ha) <= 1e-6
                        else (
                            (replay_result.simulated_yield_kg_ha - baseline_replay.simulated_yield_kg_ha)
                            / baseline_replay.simulated_yield_kg_ha
                        ),
                        6,
                    ),
                }
            )

    report = {
        "checkpoint": str(checkpoint_path),
        "checkpoint_epoch": int(checkpoint.get("epoch", checkpoint.get("best_epoch", 0)) or 0),
        "backbone": checkpoint.get("backbone", ""),
        "action_mode": checkpoint.get("action_mode", ""),
        "control_mode": args.control_mode,
        "runtime_root": str(Path(args.runtime_root).resolve()),
        "subset_ids": list(args.subset_ids),
        "summary": summarize_real_subset_replay_results(case_reports),
        "cases": case_reports,
    }
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
