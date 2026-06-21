from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from transdssat.evaluation import average_nitrogen_stress, average_water_stress
from transdssat.rewarding import default_reward_weights
from transdssat.scenarios import build_quzhou_scenarios, clone_objective_context_with_reward_contract
from transdssat.stepwise_ppo import build_stepwise_baseline_trajectory


COMBINATIONS: tuple[tuple[str, str], ...] = (
    ("heuristic_legacy", "reward_v1"),
    ("heuristic_legacy", "reward_v2"),
    ("heuristic", "reward_v1"),
    ("heuristic", "reward_v2"),
)


def _mean(values: list[float], digits: int = 6) -> float:
    if not values:
        return 0.0
    return round(sum(values) / len(values), digits)


def _combination_id(baseline_name: str, reward_contract: str) -> str:
    return f"{baseline_name}__{reward_contract}"


def _yield_floor_reference(irrigation_budget_mm: float, nitrogen_budget_kg_ha: float) -> float:
    return max(2500.0, irrigation_budget_mm * 12.0 + nitrogen_budget_kg_ha * 12.0)


def _summarize_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "scenario_count": len(records),
        "mean_yield_kg_ha": _mean([record["yield_kg_ha"] for record in records], digits=3),
        "mean_cumulative_reward": _mean([record["cumulative_reward"] for record in records]),
        "mean_irrigation_mm": _mean([record["total_irrigation_mm"] for record in records], digits=3),
        "mean_nitrogen_kg_ha": _mean([record["total_nitrogen_kg_ha"] for record in records], digits=3),
        "mean_water_use_efficiency": _mean([record["water_use_efficiency"] for record in records], digits=5),
        "mean_nitrogen_use_efficiency": _mean([record["nitrogen_use_efficiency"] for record in records], digits=5),
        "mean_decision_count": _mean([record["decision_count"] for record in records], digits=3),
        "mean_avg_water_stress": _mean([record["avg_water_stress"] for record in records]),
        "mean_avg_nitrogen_stress": _mean([record["avg_nitrogen_stress"] for record in records]),
        "mean_total_drainage_mm": _mean([record["total_drainage_mm"] for record in records]),
        "mean_total_nitrogen_leached_kg_ha": _mean([record["total_nitrogen_leached_kg_ha"] for record in records]),
        "yield_floor_trigger_rate": _mean([record["yield_floor_triggered"] for record in records]),
        "mean_yield_floor_gap_ratio": _mean([record["yield_floor_gap_ratio"] for record in records]),
    }


def _diff_metric(current: dict[str, Any], baseline: dict[str, Any], metric: str, digits: int = 6) -> float:
    return round(float(current.get(metric, 0.0)) - float(baseline.get(metric, 0.0)), digits)


def _build_delta_summary(current: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    return {
        "delta_mean_yield_kg_ha": _diff_metric(current, baseline, "mean_yield_kg_ha", digits=3),
        "delta_mean_cumulative_reward": _diff_metric(current, baseline, "mean_cumulative_reward"),
        "delta_mean_irrigation_mm": _diff_metric(current, baseline, "mean_irrigation_mm", digits=3),
        "delta_mean_nitrogen_kg_ha": _diff_metric(current, baseline, "mean_nitrogen_kg_ha", digits=3),
        "delta_mean_decision_count": _diff_metric(current, baseline, "mean_decision_count", digits=3),
        "delta_mean_avg_water_stress": _diff_metric(current, baseline, "mean_avg_water_stress"),
        "delta_mean_avg_nitrogen_stress": _diff_metric(current, baseline, "mean_avg_nitrogen_stress"),
        "delta_mean_total_drainage_mm": _diff_metric(current, baseline, "mean_total_drainage_mm"),
        "delta_mean_total_nitrogen_leached_kg_ha": _diff_metric(
            current,
            baseline,
            "mean_total_nitrogen_leached_kg_ha",
        ),
        "delta_yield_floor_trigger_rate": _diff_metric(current, baseline, "yield_floor_trigger_rate"),
        "delta_mean_yield_floor_gap_ratio": _diff_metric(current, baseline, "mean_yield_floor_gap_ratio"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare legacy and revised step-wise heuristic/reward semantics.")
    parser.add_argument("--scenario-count", type=int, default=24)
    parser.add_argument("--seed", type=int, default=20260612)
    parser.add_argument("--engine", default="dssat_proxy")
    parser.add_argument("--crop", choices=("all", "maize", "wheat"), default="all")
    parser.add_argument("--sampling-mode", choices=("random", "grid"), default="random")
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    crops_filter = None if args.crop == "all" else (args.crop,)
    scenarios = build_quzhou_scenarios(
        target_count=args.scenario_count,
        engines=(args.engine,),
        crops_filter=crops_filter,
        sampling_mode=args.sampling_mode,
        seed=args.seed,
    )
    reward_v2_weights = default_reward_weights("reward_v2")

    combination_records: dict[str, list[dict[str, Any]]] = {}
    for baseline_name, reward_contract in COMBINATIONS:
        combo_id = _combination_id(baseline_name, reward_contract)
        records: list[dict[str, Any]] = []
        for scenario in scenarios:
            variant = copy.deepcopy(scenario)
            variant.objective_context = clone_objective_context_with_reward_contract(
                variant.objective_context,
                reward_contract,
            )
            trajectory = build_stepwise_baseline_trajectory(variant, baseline_name=baseline_name)
            outcome = trajectory.outcome
            yield_floor_reference = _yield_floor_reference(
                variant.irrigation_budget_mm,
                variant.nitrogen_budget_kg_ha,
            )
            yield_floor_gap_ratio = max(0.0, yield_floor_reference - outcome.yield_kg_ha) / max(1.0, yield_floor_reference)
            records.append(
                {
                    "scenario_id": variant.scenario_id,
                    "policy_kind": str(trajectory.policy.get("policy_kind", "")) if trajectory.policy else "",
                    "crop_name": variant.crop_spec.crop_name,
                    "objective_id": variant.objective_context.objective_id,
                    "weather_regime": variant.weather_regime,
                    "yield_kg_ha": round(outcome.yield_kg_ha, 6),
                    "cumulative_reward": round(outcome.cumulative_reward, 6),
                    "total_irrigation_mm": round(outcome.total_irrigation_mm, 6),
                    "total_nitrogen_kg_ha": round(outcome.total_nitrogen_kg_ha, 6),
                    "water_use_efficiency": round(outcome.water_use_efficiency, 6),
                    "nitrogen_use_efficiency": round(outcome.nitrogen_use_efficiency, 6),
                    "decision_count": len(trajectory.steps),
                    "avg_water_stress": average_water_stress(trajectory),
                    "avg_nitrogen_stress": average_nitrogen_stress(trajectory),
                    "total_drainage_mm": round(
                        float(outcome.environmental_metrics.get("total_drainage_mm", 0.0)),
                        6,
                    ),
                    "total_nitrogen_leached_kg_ha": round(
                        float(outcome.environmental_metrics.get("total_nitrogen_leached_kg_ha", 0.0)),
                        6,
                    ),
                    "yield_floor_reference_kg_ha": round(yield_floor_reference, 6),
                    "yield_floor_gap_ratio": round(yield_floor_gap_ratio, 6),
                    "yield_floor_triggered": 1 if yield_floor_gap_ratio > 0.0 else 0,
                    "reward_v2_yield_floor_penalty_weight": reward_v2_weights.yield_floor_penalty,
                }
            )
        combination_records[combo_id] = records

    summaries = {
        combo_id: _summarize_records(records)
        for combo_id, records in combination_records.items()
    }
    baseline_summary = summaries[_combination_id("heuristic_legacy", "reward_v1")]
    deltas_vs_legacy_v1 = {
        combo_id: _build_delta_summary(summary, baseline_summary)
        for combo_id, summary in summaries.items()
        if combo_id != _combination_id("heuristic_legacy", "reward_v1")
    }
    payload = {
        "metadata": {
            "scenario_count": len(scenarios),
            "seed": args.seed,
            "engine": args.engine,
            "crop": args.crop,
            "sampling_mode": args.sampling_mode,
            "combinations": [
                {
                    "baseline_name": baseline_name,
                    "reward_contract": reward_contract,
                    "combination_id": _combination_id(baseline_name, reward_contract),
                }
                for baseline_name, reward_contract in COMBINATIONS
            ],
        },
        "summaries": summaries,
        "deltas_vs_legacy_v1": deltas_vs_legacy_v1,
        "scenario_ids": [scenario.scenario_id for scenario in scenarios],
    }

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
