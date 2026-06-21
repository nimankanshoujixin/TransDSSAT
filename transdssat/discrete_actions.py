from __future__ import annotations

from dataclasses import asdict, dataclass, field
import math
from typing import Any, Mapping

from transdssat.domain import CropAction, CropState
from transdssat.scenarios import SimulationScenario


@dataclass(frozen=True, slots=True)
class ContinuousAction:
    irrigation_mm: float = 0.0
    nitrogen_kg_ha: float = 0.0

    def to_crop_action(self) -> CropAction:
        return CropAction(irrigation_mm=self.irrigation_mm, nitrogen_kg_ha=self.nitrogen_kg_ha)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class DiscreteAction:
    action_id: int
    irrigation_mm: float
    nitrogen_kg_ha: float
    label: str
    notes: list[str] = field(default_factory=list)

    def to_continuous_action(self) -> ContinuousAction:
        return ContinuousAction(
            irrigation_mm=self.irrigation_mm,
            nitrogen_kg_ha=self.nitrogen_kg_ha,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ActionSpaceDimension:
    name: str
    unit: str
    min_value: float = 0.0
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ContinuousActionSpace:
    action_space_id: str
    allow_joint_action: bool
    dimensions: list[ActionSpaceDimension]
    notes: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["dimensions"] = [dimension.to_dict() for dimension in self.dimensions]
        payload["notes"] = self.notes or []
        return payload


@dataclass(slots=True)
class DiscreteActionTable:
    action_table_id: str
    actions: list[DiscreteAction]
    notes: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_table_id": self.action_table_id,
            "actions": [action.to_dict() for action in self.actions],
            "notes": list(self.notes or []),
        }


@dataclass(slots=True)
class ActionConstraintRules:
    decision_interval_days: int
    irrigation_min_gap_days: int
    nitrogen_min_gap_days: int
    max_soil_moisture_for_irrigation: float
    allowed_irrigation_stages: list[str]
    allowed_nitrogen_stages: list[str]
    post_harvest_allows_only_noop: bool = True
    notes: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["notes"] = self.notes or []
        return payload


@dataclass(slots=True)
class ActionDimensionConstraints:
    name: str
    unit: str
    min_value: float
    max_value: float
    allowed: bool
    remaining_budget: float
    days_since_last_event: int | None
    min_gap_days: int
    gap_days_remaining: int
    blocked_reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ActionConstraintSnapshot:
    action_space_id: str
    decision_interval_days: int
    current_stage: str
    allow_joint_action: bool
    irrigation: ActionDimensionConstraints
    nitrogen: ActionDimensionConstraints
    notes: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["irrigation"] = self.irrigation.to_dict()
        payload["nitrogen"] = self.nitrogen.to_dict()
        payload["notes"] = self.notes or []
        return payload


@dataclass(slots=True)
class DiscreteActionMask:
    action_table_id: str
    mask: list[int]
    legal_action_ids: list[int]
    notes: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_table_id": self.action_table_id,
            "mask": list(self.mask),
            "legal_action_ids": list(self.legal_action_ids),
            "notes": list(self.notes or []),
        }


_CROP_STAGE_RULES = {
    "wheat": {
        "irrigation": ["vegetative", "reproductive"],
        "nitrogen": ["emergence", "vegetative", "reproductive"],
    },
    "maize": {
        "irrigation": ["emergence", "vegetative", "reproductive"],
        "nitrogen": ["emergence", "vegetative", "reproductive"],
    },
}

_ACTION_DIMENSIONS = (
    ActionSpaceDimension(
        name="irrigation_mm",
        unit="mm",
        min_value=0.0,
        description="Irrigation amount to apply on the current decision day.",
    ),
    ActionSpaceDimension(
        name="nitrogen_kg_ha",
        unit="kg/ha",
        min_value=0.0,
        description="Nitrogen amount to apply on the current decision day.",
    ),
)

_DEFAULT_DISCRETE_ACTIONS = (
    DiscreteAction(action_id=0, irrigation_mm=0.0, nitrogen_kg_ha=0.0, label="noop", notes=["always_legal_if_noop_allowed"]),
    DiscreteAction(action_id=1, irrigation_mm=10.0, nitrogen_kg_ha=0.0, label="irrigation_10mm"),
    DiscreteAction(action_id=2, irrigation_mm=20.0, nitrogen_kg_ha=0.0, label="irrigation_20mm"),
    DiscreteAction(action_id=3, irrigation_mm=30.0, nitrogen_kg_ha=0.0, label="irrigation_30mm"),
    DiscreteAction(action_id=4, irrigation_mm=0.0, nitrogen_kg_ha=20.0, label="nitrogen_20kg_ha"),
    DiscreteAction(action_id=5, irrigation_mm=0.0, nitrogen_kg_ha=40.0, label="nitrogen_40kg_ha"),
    DiscreteAction(
        action_id=6,
        irrigation_mm=10.0,
        nitrogen_kg_ha=20.0,
        label="irrigation_10mm_plus_nitrogen_20kg_ha",
        notes=["joint_action_example_from_foundation_plan"],
    ),
)


def default_continuous_action_space(scenario: SimulationScenario | None = None) -> ContinuousActionSpace:
    decision_context = scenario.decision_context if scenario is not None else None
    return ContinuousActionSpace(
        action_space_id=decision_context.action_space_id if decision_context is not None else "v2_joint_continuous",
        allow_joint_action=decision_context.allow_combined_actions if decision_context is not None else True,
        dimensions=list(_ACTION_DIMENSIONS),
        notes=[
            "continuous_joint_action_space",
            "per-dimension maxima are determined by current constraints and remaining budget",
        ],
    )


def default_discrete_action_table(scenario: SimulationScenario | None = None) -> DiscreteActionTable:
    decision_context = scenario.decision_context if scenario is not None else None
    return DiscreteActionTable(
        action_table_id=decision_context.action_table_id if decision_context is not None else "v1_joint_discrete",
        actions=list(_DEFAULT_DISCRETE_ACTIONS),
        notes=[
            "canonical_discrete_action_table_for_stepwise_proxy_rollouts",
            "designed_to mirror the minimal irrigation/nitrogen examples in foundation-policy-implementation-plan-cn.md",
            "continuous constraints are still enforced on top of this table through action masks",
        ],
    )


def default_action_constraint_rules(scenario: SimulationScenario | None = None) -> ActionConstraintRules:
    crop_name = scenario.crop_spec.crop_name if scenario is not None else "maize"
    decision_context = scenario.decision_context if scenario is not None else None
    stage_rules = _CROP_STAGE_RULES.get(crop_name, _CROP_STAGE_RULES["maize"])
    return ActionConstraintRules(
        decision_interval_days=decision_context.decision_interval_days if decision_context is not None else 5,
        irrigation_min_gap_days=decision_context.irrigation_min_gap_days if decision_context is not None else 5,
        nitrogen_min_gap_days=decision_context.nitrogen_min_gap_days if decision_context is not None else 10,
        max_soil_moisture_for_irrigation=0.95,
        allowed_irrigation_stages=list(stage_rules["irrigation"]),
        allowed_nitrogen_stages=list(stage_rules["nitrogen"]),
        notes=[
            "budget_limit",
            "minimum_gap_between_same_input_events",
            "stage_restriction",
            "block_irrigation_when_soil_is_already_wet",
            "continuous_action_bounds_are_state_dependent",
            "no_operation_only_after_harvest",
        ],
    )


def _days_since_last_event(current_day: int, last_day: int | None) -> int | None:
    if last_day is None:
        return None
    return current_day - last_day


def _gap_days_remaining(current_day: int, last_day: int | None, min_gap_days: int) -> int:
    if last_day is None:
        return 0
    return max(0, min_gap_days - (current_day - last_day))


def _dimension_constraints(
    *,
    name: str,
    unit: str,
    remaining_budget: float,
    allowed: bool,
    days_since_last_event: int | None,
    min_gap_days: int,
    gap_days_remaining: int,
    blocked_reasons: list[str],
) -> ActionDimensionConstraints:
    max_value = max(0.0, remaining_budget) if allowed and not blocked_reasons else 0.0
    return ActionDimensionConstraints(
        name=name,
        unit=unit,
        min_value=0.0,
        max_value=round(max_value, 3),
        allowed=allowed and not blocked_reasons,
        remaining_budget=round(max(0.0, remaining_budget), 3),
        days_since_last_event=days_since_last_event,
        min_gap_days=min_gap_days,
        gap_days_remaining=gap_days_remaining,
        blocked_reasons=blocked_reasons,
    )


def action_constraints_for_state(
    scenario: SimulationScenario,
    state: CropState,
    remaining_irrigation_mm: float,
    remaining_nitrogen_kg_ha: float,
    last_irrigation_day: int | None,
    last_nitrogen_day: int | None,
    done: bool,
) -> ActionConstraintSnapshot:
    rules = default_action_constraint_rules(scenario)
    action_space = default_continuous_action_space(scenario)

    current_day = state.day_index
    soil_capacity = scenario.soil_profile.field_capacity_mm
    too_wet = (
        state.soil_moisture >= rules.max_soil_moisture_for_irrigation
        or state.root_zone_water_mm >= soil_capacity
    )

    irrigation_reasons: list[str] = []
    nitrogen_reasons: list[str] = []
    irrigation_gap_remaining = _gap_days_remaining(current_day, last_irrigation_day, rules.irrigation_min_gap_days)
    nitrogen_gap_remaining = _gap_days_remaining(current_day, last_nitrogen_day, rules.nitrogen_min_gap_days)

    if done:
        irrigation_reasons.append("environment_done")
        nitrogen_reasons.append("environment_done")
    if remaining_irrigation_mm <= 1e-9:
        irrigation_reasons.append("budget_exhausted")
    if remaining_nitrogen_kg_ha <= 1e-9:
        nitrogen_reasons.append("budget_exhausted")
    if state.stage not in rules.allowed_irrigation_stages:
        irrigation_reasons.append("stage_blocked")
    if state.stage not in rules.allowed_nitrogen_stages:
        nitrogen_reasons.append("stage_blocked")
    if irrigation_gap_remaining > 0:
        irrigation_reasons.append("minimum_gap_active")
    if nitrogen_gap_remaining > 0:
        nitrogen_reasons.append("minimum_gap_active")
    if too_wet:
        irrigation_reasons.append("soil_too_wet")

    irrigation = _dimension_constraints(
        name="irrigation_mm",
        unit="mm",
        remaining_budget=remaining_irrigation_mm,
        allowed=True,
        days_since_last_event=_days_since_last_event(current_day, last_irrigation_day),
        min_gap_days=rules.irrigation_min_gap_days,
        gap_days_remaining=irrigation_gap_remaining,
        blocked_reasons=irrigation_reasons,
    )
    nitrogen = _dimension_constraints(
        name="nitrogen_kg_ha",
        unit="kg/ha",
        remaining_budget=remaining_nitrogen_kg_ha,
        allowed=True,
        days_since_last_event=_days_since_last_event(current_day, last_nitrogen_day),
        min_gap_days=rules.nitrogen_min_gap_days,
        gap_days_remaining=nitrogen_gap_remaining,
        blocked_reasons=nitrogen_reasons,
    )
    return ActionConstraintSnapshot(
        action_space_id=action_space.action_space_id,
        decision_interval_days=rules.decision_interval_days,
        current_stage=state.stage,
        allow_joint_action=action_space.allow_joint_action,
        irrigation=irrigation,
        nitrogen=nitrogen,
        notes=rules.notes,
    )


def normalize_continuous_action(payload: ContinuousAction | Mapping[str, Any]) -> ContinuousAction:
    if isinstance(payload, ContinuousAction):
        return payload
    if not isinstance(payload, Mapping):
        raise TypeError("Continuous action payload must be a ContinuousAction or mapping.")
    return ContinuousAction(
        irrigation_mm=float(payload.get("irrigation_mm", 0.0)),
        nitrogen_kg_ha=float(payload.get("nitrogen_kg_ha", 0.0)),
    )


def validate_continuous_action(
    action: ContinuousAction | Mapping[str, Any],
    constraints: ActionConstraintSnapshot,
) -> ContinuousAction:
    normalized = normalize_continuous_action(action)

    def _validate_dimension(value: float, dimension: ActionDimensionConstraints) -> float:
        if not math.isfinite(value):
            raise ValueError(f"{dimension.name} must be finite.")
        if value < dimension.min_value - 1e-9:
            raise ValueError(f"{dimension.name} must be >= {dimension.min_value}.")
        if value > dimension.max_value + 1e-9:
            raise ValueError(
                f"{dimension.name}={value} exceeds legal maximum {dimension.max_value} "
                f"for stage {constraints.current_stage}."
            )
        return round(max(0.0, value), 3)

    irrigation_mm = _validate_dimension(normalized.irrigation_mm, constraints.irrigation)
    nitrogen_kg_ha = _validate_dimension(normalized.nitrogen_kg_ha, constraints.nitrogen)
    if not constraints.allow_joint_action and irrigation_mm > 0.0 and nitrogen_kg_ha > 0.0:
        raise ValueError("Joint irrigation and nitrogen actions are disabled for this action space.")
    return ContinuousAction(irrigation_mm=irrigation_mm, nitrogen_kg_ha=nitrogen_kg_ha)


def discrete_action_by_id(
    action_id: int,
    action_table: DiscreteActionTable,
) -> DiscreteAction:
    for action in action_table.actions:
        if action.action_id == action_id:
            return action
    raise KeyError(f"Unknown discrete action id: {action_id}")


def action_mask_for_constraints(
    constraints: ActionConstraintSnapshot,
    action_table: DiscreteActionTable,
) -> DiscreteActionMask:
    mask: list[int] = []
    legal_action_ids: list[int] = []
    for action in action_table.actions:
        try:
            validate_continuous_action(action.to_continuous_action(), constraints)
        except ValueError:
            mask.append(0)
            continue
        mask.append(1)
        legal_action_ids.append(action.action_id)
    return DiscreteActionMask(
        action_table_id=action_table.action_table_id,
        mask=mask,
        legal_action_ids=legal_action_ids,
        notes=[
            "mask value 1 means the discrete action is currently legal under budget, stage, gap, and wet-soil rules",
            "mask is aligned with action ordering emitted in discrete_action_table.actions",
        ],
    )


def validate_discrete_action(
    action_id: int,
    constraints: ActionConstraintSnapshot,
    action_table: DiscreteActionTable,
) -> ContinuousAction:
    action = discrete_action_by_id(action_id, action_table)
    return validate_continuous_action(action.to_continuous_action(), constraints)
