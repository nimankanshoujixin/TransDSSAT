from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from transdssat.policy_registry import build_policy_registry
from transdssat.strategies import CheckpointAIPolicyFamily, ReferenceAIPolicyFamily, build_default_strategies
from transdssat.testset import generate_general_random_test_set, generate_literature_matched_slices
from transdssat.unified_eval import UnifiedEvaluationRunner


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the phase-1 unified evaluation protocol.")
    parser.add_argument(
        "--engine",
        choices=("dssat_official",),
        default="dssat_official",
        help="Evaluation backend. Official DSSAT only.",
    )
    parser.add_argument("--train-count", type=int, default=12)
    parser.add_argument("--val-count", type=int, default=3)
    parser.add_argument("--test-count", type=int, default=5)
    parser.add_argument("--matched-count-per-slice", type=int, default=2)
    parser.add_argument("--decision-granularity", choices=("stage", "daily", "stepwise"), default="stage")
    parser.add_argument("--reference-strategy", default="equal_allocation")
    parser.add_argument("--ai-family", choices=("none", "reference", "checkpoint"), default="reference")
    parser.add_argument("--checkpoint-water", default="")
    parser.add_argument("--checkpoint-nitrogen", default="")
    parser.add_argument("--checkpoint-joint", default="")
    parser.add_argument("--seed", type=int, default=20260519)
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    registry = build_policy_registry()
    ai_family = None
    if args.ai_family == "reference":
        ai_family = ReferenceAIPolicyFamily()
    elif args.ai_family == "checkpoint":
        checkpoints = {
            key: value
            for key, value in {
                "water_only": args.checkpoint_water,
                "nitrogen_only": args.checkpoint_nitrogen,
                "joint": args.checkpoint_joint,
            }.items()
            if value
        }
        ai_family = CheckpointAIPolicyFamily(checkpoints)

    strategies = build_default_strategies(registry, ai_family=ai_family)
    general_random = generate_general_random_test_set(
        train_count=args.train_count,
        val_count=args.val_count,
        test_count=args.test_count,
        engines=(args.engine,),
        seed=args.seed,
    )
    matched_slices = generate_literature_matched_slices(
        registry,
        scenario_count_per_slice=args.matched_count_per_slice,
        engines=(args.engine,),
        seed=args.seed + 17,
    )
    runner = UnifiedEvaluationRunner(
        strategies,
        decision_granularity=args.decision_granularity,
        reference_strategy_id=args.reference_strategy,
    )
    report = {
        "registry": registry.to_dict(),
        "report": runner.evaluate(general_random, matched_slices),
    }

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
