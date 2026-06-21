from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Mapping


def input_use_efficiency(yield_kg_ha: float, applied_amount: float, min_input: float = 1.0) -> float:
    if applied_amount <= min_input:
        return 0.0
    return round(yield_kg_ha / applied_amount, 5)


@dataclass(slots=True)
class RewardWeights:
    contract_id: str = "reward_v2"
    yield_weight: float = 0.0080
    irrigation_cost: float = 0.0025
    nitrogen_cost: float = 0.0045
    operation_cost: float = 0.080
    water_stress_cost: float = 0.800
    nitrogen_stress_cost: float = 0.700
    biomass_gain_weight: float = 0.0012
    budget_deviation_cost: float = 10.000
    irrigation_overshoot_cost: float = 4.000
    nitrogen_overshoot_cost: float = 6.000
    irrigation_undershoot_cost: float = 0.000
    nitrogen_undershoot_cost: float = 0.000
    zero_irrigation_penalty: float = 0.000
    zero_nitrogen_penalty: float = 0.000
    soil_water_drainage_cost: float = 0.004
    nitrogen_leaching_cost: float = 0.050
    normalized_irrigation_cost: float = 0.150
    normalized_nitrogen_cost: float = 0.250
    yield_floor_penalty: float = 15.000


def default_reward_weights(contract_id: str = "reward_v2") -> RewardWeights:
    normalized = str(contract_id or "reward_v2").strip().lower()
    if normalized == "reward_v1":
        return RewardWeights(
            contract_id="reward_v1",
            yield_weight=0.003,
            irrigation_cost=0.010,
            nitrogen_cost=0.020,
            operation_cost=0.200,
            water_stress_cost=1.250,
            nitrogen_stress_cost=1.100,
            biomass_gain_weight=0.0025,
            budget_deviation_cost=9.000,
            irrigation_overshoot_cost=3.000,
            nitrogen_overshoot_cost=5.000,
            irrigation_undershoot_cost=2.500,
            nitrogen_undershoot_cost=1.500,
            zero_irrigation_penalty=2.000,
            zero_nitrogen_penalty=1.000,
            soil_water_drainage_cost=0.008,
            nitrogen_leaching_cost=0.120,
            normalized_irrigation_cost=0.0,
            normalized_nitrogen_cost=0.0,
            yield_floor_penalty=0.0,
        )
    if normalized != "reward_v2":
        raise ValueError(f"Unsupported reward contract: {contract_id}")
    return RewardWeights(contract_id="reward_v2")


def objective_reward_weights(objective_context: Mapping[str, Any] | None) -> RewardWeights:
    contract_id = reward_contract_id(objective_context)
    default = default_reward_weights(contract_id)
    if objective_context is None:
        return default
    reward_weights = objective_context.get("reward_weights", {})
    if not isinstance(reward_weights, Mapping):
        return default

    irrigation_factor = float(reward_weights.get("irrigation_cost", 1.0))
    nitrogen_factor = float(reward_weights.get("nitrogen_cost", 1.0))
    water_factor = float(reward_weights.get("water_penalty", 1.0))
    leaching_factor = float(reward_weights.get("nitrogen_leaching_penalty", 1.0))
    risk_factor = float(reward_weights.get("risk_penalty", 1.0))
    operation_factor = float(reward_weights.get("operation_cost", 1.0))

    return RewardWeights(
        contract_id=default.contract_id,
        yield_weight=default.yield_weight * float(reward_weights.get("yield_revenue", 1.0)),
        irrigation_cost=default.irrigation_cost * irrigation_factor,
        nitrogen_cost=default.nitrogen_cost * nitrogen_factor,
        operation_cost=default.operation_cost * operation_factor,
        water_stress_cost=default.water_stress_cost * risk_factor,
        nitrogen_stress_cost=default.nitrogen_stress_cost * risk_factor,
        biomass_gain_weight=default.biomass_gain_weight,
        budget_deviation_cost=default.budget_deviation_cost,
        irrigation_overshoot_cost=default.irrigation_overshoot_cost * water_factor,
        nitrogen_overshoot_cost=default.nitrogen_overshoot_cost * leaching_factor,
        irrigation_undershoot_cost=default.irrigation_undershoot_cost * water_factor,
        nitrogen_undershoot_cost=default.nitrogen_undershoot_cost * nitrogen_factor,
        zero_irrigation_penalty=default.zero_irrigation_penalty * risk_factor,
        zero_nitrogen_penalty=default.zero_nitrogen_penalty * risk_factor,
        soil_water_drainage_cost=default.soil_water_drainage_cost * water_factor,
        nitrogen_leaching_cost=default.nitrogen_leaching_cost * leaching_factor,
        normalized_irrigation_cost=default.normalized_irrigation_cost * irrigation_factor,
        normalized_nitrogen_cost=default.normalized_nitrogen_cost * nitrogen_factor,
        yield_floor_penalty=default.yield_floor_penalty * float(reward_weights.get("yield_floor_penalty", 1.0)),
    )


def reward_contract_id(objective_context: Mapping[str, Any] | None) -> str:
    if objective_context is None:
        return "reward_v2"
    contract_id = str(objective_context.get("reward_contract", "reward_v2")).strip().lower()
    return contract_id or "reward_v2"


def anti_collapse_preferences(objective_context: Mapping[str, Any] | None) -> dict[str, Any]:
    if objective_context is None:
        return {}
    soft_preferences = objective_context.get("soft_preferences", {})
    if not isinstance(soft_preferences, Mapping):
        return {}
    payload = soft_preferences.get("anti_collapse_guardrail", {})
    if not isinstance(payload, Mapping):
        return {}
    return dict(payload)


def resource_settlement_preferences(objective_context: Mapping[str, Any] | None) -> dict[str, Any]:
    if objective_context is None:
        return {}
    soft_preferences = objective_context.get("soft_preferences", {})
    if not isinstance(soft_preferences, Mapping):
        return {}
    payload = soft_preferences.get("resource_settlement", {})
    if not isinstance(payload, Mapping):
        return {}
    return dict(payload)


def _budget_satisficing_cost(
    *,
    total_use: float,
    budget: float,
    normalized_cost_weight: float,
    direct_unit_cost: float,
    exponent: float,
    direct_input_cost_scale: float,
    under_budget_cost_scale: float,
) -> float:
    normalized_budget = max(1.0, float(budget))
    normalized_use = float(total_use) / normalized_budget
    if normalized_use <= 1.0:
        shaped_cost = (normalized_use ** exponent) * float(normalized_cost_weight) * float(under_budget_cost_scale)
        direct_cost = float(total_use) * float(direct_unit_cost) * float(under_budget_cost_scale)
        return shaped_cost + direct_cost

    overshoot_ratio = normalized_use - 1.0
    shaped_cost = (overshoot_ratio ** exponent) * float(normalized_cost_weight)
    direct_cost = max(0.0, float(total_use) - normalized_budget) * float(direct_unit_cost) * float(direct_input_cost_scale)
    return shaped_cost + direct_cost


def budget_penalty(
    total_irrigation_mm: float,
    total_nitrogen_kg_ha: float,
    irrigation_budget_mm: float,
    nitrogen_budget_kg_ha: float,
    weights: RewardWeights,
) -> float:
    irrigation_budget = max(1.0, irrigation_budget_mm)
    nitrogen_budget = max(1.0, nitrogen_budget_kg_ha)
    irrigation_overshoot = max(0.0, total_irrigation_mm - irrigation_budget_mm) / irrigation_budget
    nitrogen_overshoot = max(0.0, total_nitrogen_kg_ha - nitrogen_budget_kg_ha) / nitrogen_budget

    penalty = (
        (irrigation_overshoot + nitrogen_overshoot) * weights.budget_deviation_cost
        + irrigation_overshoot * weights.irrigation_overshoot_cost
        + nitrogen_overshoot * weights.nitrogen_overshoot_cost
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
    operation_count: int = 0,
    environmental_metrics: Mapping[str, float] | None = None,
    weights: RewardWeights | None = None,
    yield_floor_reference: float | None = None,
    anti_collapse_guardrail: Mapping[str, Any] | None = None,
    resource_settlement: Mapping[str, Any] | None = None,
) -> float:
    weights = weights or default_reward_weights()
    environmental_metrics = environmental_metrics or {}
    penalty = budget_penalty(
        total_irrigation_mm=total_irrigation_mm,
        total_nitrogen_kg_ha=total_nitrogen_kg_ha,
        irrigation_budget_mm=irrigation_budget_mm,
        nitrogen_budget_kg_ha=nitrogen_budget_kg_ha,
        weights=weights,
    )
    total_drainage_mm = float(environmental_metrics.get("total_drainage_mm", 0.0))
    total_nitrogen_leached_kg_ha = float(environmental_metrics.get("total_nitrogen_leached_kg_ha", 0.0))
    if weights.contract_id == "reward_v1":
        return round(
            yield_kg_ha * weights.yield_weight
            - total_irrigation_mm * weights.irrigation_cost
            - total_nitrogen_kg_ha * weights.nitrogen_cost
            - operation_count * weights.operation_cost
            - avg_water_stress * weights.water_stress_cost
            - avg_nitrogen_stress * weights.nitrogen_stress_cost
            - total_drainage_mm * weights.soil_water_drainage_cost
            - total_nitrogen_leached_kg_ha * weights.nitrogen_leaching_cost
            - penalty,
            6,
        )
    irrigation_budget = max(1.0, irrigation_budget_mm)
    nitrogen_budget = max(1.0, nitrogen_budget_kg_ha)
    normalized_irrigation_use = total_irrigation_mm / irrigation_budget
    normalized_nitrogen_use = total_nitrogen_kg_ha / nitrogen_budget
    settlement = resource_settlement if isinstance(resource_settlement, Mapping) else {}
    settlement_enabled = bool(settlement.get("enabled", False))
    irrigation_cost_exponent = float(settlement.get("irrigation_cost_exponent", 1.0))
    nitrogen_cost_exponent = float(settlement.get("nitrogen_cost_exponent", 1.0))
    direct_input_cost_scale = float(settlement.get("direct_input_cost_scale", 1.0))
    under_budget_cost_scale = float(settlement.get("under_budget_cost_scale", 0.0))
    if settlement_enabled:
        shaped_irrigation_cost = _budget_satisficing_cost(
            total_use=total_irrigation_mm,
            budget=irrigation_budget_mm,
            normalized_cost_weight=weights.normalized_irrigation_cost,
            direct_unit_cost=weights.irrigation_cost,
            exponent=irrigation_cost_exponent,
            direct_input_cost_scale=direct_input_cost_scale,
            under_budget_cost_scale=under_budget_cost_scale,
        )
        shaped_nitrogen_cost = _budget_satisficing_cost(
            total_use=total_nitrogen_kg_ha,
            budget=nitrogen_budget_kg_ha,
            normalized_cost_weight=weights.normalized_nitrogen_cost,
            direct_unit_cost=weights.nitrogen_cost,
            exponent=nitrogen_cost_exponent,
            direct_input_cost_scale=direct_input_cost_scale,
            under_budget_cost_scale=under_budget_cost_scale,
        )
        direct_irrigation_cost = 0.0
        direct_nitrogen_cost = 0.0
    else:
        shaped_irrigation_cost = (normalized_irrigation_use ** irrigation_cost_exponent) * weights.normalized_irrigation_cost
        shaped_nitrogen_cost = (normalized_nitrogen_use ** nitrogen_cost_exponent) * weights.normalized_nitrogen_cost
        direct_irrigation_cost = total_irrigation_mm * weights.irrigation_cost * direct_input_cost_scale
        direct_nitrogen_cost = total_nitrogen_kg_ha * weights.nitrogen_cost * direct_input_cost_scale
    if yield_floor_reference is None:
        yield_floor_reference = max(2500.0, irrigation_budget_mm * 12.0 + nitrogen_budget_kg_ha * 12.0)
    yield_floor_gap = max(0.0, float(yield_floor_reference) - yield_kg_ha) / max(1.0, float(yield_floor_reference))
    collapse_penalty = 0.0
    guardrail = anti_collapse_guardrail if isinstance(anti_collapse_guardrail, Mapping) else {}
    guardrail_enabled = bool(guardrail.get("enabled", False))
    apply_when_below_floor = bool(guardrail.get("apply_when_yield_below_floor", True))
    if guardrail_enabled and (yield_floor_gap > 0.0 or not apply_when_below_floor):
        active_channels = guardrail.get("active_channels", ("irrigation", "nitrogen"))
        if not isinstance(active_channels, (list, tuple, set)):
            active_channels = ("irrigation", "nitrogen")
        active_channel_set = {str(item).strip().lower() for item in active_channels}
        minimum_budget_for_guardrail = float(guardrail.get("minimum_budget_for_guardrail", 80.0))
        minimum_irrigation_ratio = float(guardrail.get("minimum_irrigation_ratio", 0.12))
        minimum_nitrogen_ratio = float(guardrail.get("minimum_nitrogen_ratio", 0.15))
        shortfall_penalty_weight = float(guardrail.get("shortfall_penalty_weight", 24.0))
        irrigation_shortfall_penalty_weight = float(
            guardrail.get("irrigation_shortfall_penalty_weight", shortfall_penalty_weight)
        )
        nitrogen_shortfall_penalty_weight = float(
            guardrail.get("nitrogen_shortfall_penalty_weight", shortfall_penalty_weight * 1.5)
        )
        yield_gap_multiplier = float(guardrail.get("yield_gap_multiplier", 2.0))
        zero_irrigation_extra_penalty = float(guardrail.get("zero_irrigation_extra_penalty", 0.0))
        zero_nitrogen_extra_penalty = float(guardrail.get("zero_nitrogen_extra_penalty", 3.0))
        shortfall_penalty_scale = 1.0 + yield_floor_gap * yield_gap_multiplier
        collapse_penalty = 0.0
        if "irrigation" in active_channel_set and irrigation_budget_mm >= minimum_budget_for_guardrail:
            irrigation_shortfall = max(0.0, minimum_irrigation_ratio - normalized_irrigation_use)
            collapse_penalty += irrigation_shortfall * irrigation_shortfall_penalty_weight * shortfall_penalty_scale
            if total_irrigation_mm <= 1.0:
                collapse_penalty += zero_irrigation_extra_penalty * shortfall_penalty_scale
        if "nitrogen" in active_channel_set and nitrogen_budget_kg_ha >= minimum_budget_for_guardrail:
            nitrogen_shortfall = max(0.0, minimum_nitrogen_ratio - normalized_nitrogen_use)
            collapse_penalty += nitrogen_shortfall * nitrogen_shortfall_penalty_weight * shortfall_penalty_scale
            if total_nitrogen_kg_ha <= 1.0:
                collapse_penalty += zero_nitrogen_extra_penalty * shortfall_penalty_scale
    return round(
        yield_kg_ha * weights.yield_weight
        - shaped_irrigation_cost
        - shaped_nitrogen_cost
        - direct_irrigation_cost
        - direct_nitrogen_cost
        - operation_count * weights.operation_cost
        - avg_water_stress * weights.water_stress_cost
        - avg_nitrogen_stress * weights.nitrogen_stress_cost
        - total_drainage_mm * weights.soil_water_drainage_cost
        - total_nitrogen_leached_kg_ha * weights.nitrogen_leaching_cost
        - yield_floor_gap * weights.yield_floor_penalty
        - collapse_penalty
        - penalty,
        6,
    )


def step_reward(
    *,
    biomass_gain: float,
    irrigation_mm: float,
    nitrogen_kg_ha: float,
    water_stress: float,
    nitrogen_stress: float,
    operation_count: int,
    weights: RewardWeights | None = None,
) -> float:
    weights = weights or default_reward_weights()
    if weights.contract_id == "reward_v1":
        return round(
            biomass_gain * weights.biomass_gain_weight
            - irrigation_mm * weights.irrigation_cost
            - nitrogen_kg_ha * weights.nitrogen_cost
            - operation_count * weights.operation_cost
            - water_stress * weights.water_stress_cost
            - nitrogen_stress * weights.nitrogen_stress_cost,
            6,
        )
    return round(
        biomass_gain * weights.biomass_gain_weight
        - operation_count * weights.operation_cost * 0.25
        - water_stress * weights.water_stress_cost * 0.35
        - nitrogen_stress * weights.nitrogen_stress_cost * 0.35,
        6,
    )
