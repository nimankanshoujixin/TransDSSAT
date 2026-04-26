from __future__ import annotations

from dataclasses import dataclass


def input_use_efficiency(yield_kg_ha: float, applied_amount: float, min_input: float = 1.0) -> float:
    if applied_amount <= min_input:
        return 0.0
    return round(yield_kg_ha / applied_amount, 5)


@dataclass(slots=True)
class RewardWeights:
    yield_weight: float = 0.003
    irrigation_cost: float = 0.010
    nitrogen_cost: float = 0.020
    water_stress_cost: float = 1.250
    nitrogen_stress_cost: float = 1.100
    biomass_gain_weight: float = 0.0025
    budget_deviation_cost: float = 9.000
    irrigation_overshoot_cost: float = 3.000
    nitrogen_overshoot_cost: float = 5.000
    irrigation_undershoot_cost: float = 2.500
    nitrogen_undershoot_cost: float = 1.500
    zero_irrigation_penalty: float = 2.000
    zero_nitrogen_penalty: float = 1.000


def budget_penalty(
    total_irrigation_mm: float,
    total_nitrogen_kg_ha: float,
    irrigation_budget_mm: float,
    nitrogen_budget_kg_ha: float,
    weights: RewardWeights,
) -> float:
    irrigation_budget = max(1.0, irrigation_budget_mm)
    nitrogen_budget = max(1.0, nitrogen_budget_kg_ha)
    irrigation_deviation = abs(total_irrigation_mm - irrigation_budget_mm) / irrigation_budget
    nitrogen_deviation = abs(total_nitrogen_kg_ha - nitrogen_budget_kg_ha) / nitrogen_budget
    irrigation_overshoot = max(0.0, total_irrigation_mm - irrigation_budget_mm) / irrigation_budget
    nitrogen_overshoot = max(0.0, total_nitrogen_kg_ha - nitrogen_budget_kg_ha) / nitrogen_budget
    irrigation_undershoot = max(0.0, irrigation_budget_mm - total_irrigation_mm) / irrigation_budget
    nitrogen_undershoot = max(0.0, nitrogen_budget_kg_ha - total_nitrogen_kg_ha) / nitrogen_budget

    penalty = (
        (irrigation_deviation + nitrogen_deviation) * weights.budget_deviation_cost
        + irrigation_overshoot * weights.irrigation_overshoot_cost
        + nitrogen_overshoot * weights.nitrogen_overshoot_cost
        + irrigation_undershoot * weights.irrigation_undershoot_cost
        + nitrogen_undershoot * weights.nitrogen_undershoot_cost
    )
    if irrigation_budget_mm >= 80.0 and total_irrigation_mm <= 1.0:
        penalty += weights.zero_irrigation_penalty
    if nitrogen_budget_kg_ha >= 80.0 and total_nitrogen_kg_ha <= 1.0:
        penalty += weights.zero_nitrogen_penalty
    return penalty


def reward_from_outcome(
    *,
    yield_kg_ha: float,
    total_irrigation_mm: float,
    total_nitrogen_kg_ha: float,
    irrigation_budget_mm: float,
    nitrogen_budget_kg_ha: float,
    avg_water_stress: float,
    avg_nitrogen_stress: float,
    weights: RewardWeights | None = None,
) -> float:
    weights = weights or RewardWeights()
    penalty = budget_penalty(
        total_irrigation_mm=total_irrigation_mm,
        total_nitrogen_kg_ha=total_nitrogen_kg_ha,
        irrigation_budget_mm=irrigation_budget_mm,
        nitrogen_budget_kg_ha=nitrogen_budget_kg_ha,
        weights=weights,
    )
    return round(
        yield_kg_ha * weights.yield_weight
        - total_irrigation_mm * weights.irrigation_cost
        - total_nitrogen_kg_ha * weights.nitrogen_cost
        - avg_water_stress * weights.water_stress_cost
        - avg_nitrogen_stress * weights.nitrogen_stress_cost
        - penalty,
        6,
    )
