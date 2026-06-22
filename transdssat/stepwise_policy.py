from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from math import floor
from typing import Any

from transdssat.discrete_actions import ActionConstraintSnapshot, ContinuousAction
from transdssat.discrete_actions import default_action_constraint_rules
from transdssat.domain import CropAction, Trajectory, TrajectoryStep
from transdssat.environments import StepwiseDecisionEnvironment
from transdssat.scenarios import STAGES, SimulationScenario, stage_for_day
from transdssat.season import (
    HEURISTIC_STAGE_BUDGET_SPLITS,
    LITERATURE_EVENT_PLAN,
    SeasonPolicy,
)


@dataclass(slots=True)
class StepwisePolicySummary:
    policy_kind: str
    scheduled_decision_count: int
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "policy_kind": self.policy_kind,
            "scheduled_decision_count": self.scheduled_decision_count,
            "notes": list(self.notes),
        }


class StepwisePolicy(ABC):
    policy_id: str
    scenario_id: str

    def reset(self, scenario: SimulationScenario) -> None:
        return None

    @abstractmethod
    def decide(self, observation: Any) -> ContinuousAction:
        raise NotImplementedError

    @abstractmethod
    def summary(self) -> StepwisePolicySummary:
        raise NotImplementedError

    @abstractmethod
    def to_dict(self) -> dict[str, Any]:
        raise NotImplementedError


@dataclass(slots=True)
class ScheduledStepwisePolicy(StepwisePolicy):
    policy_id: str
    scenario_id: str
    action_schedule: dict[int, ContinuousAction]
    notes: list[str] = field(default_factory=list)

    def decide(self, observation: Any) -> ContinuousAction:
        scheduled = self.action_schedule.get(observation.day_index, ContinuousAction())
        return _clip_action_to_constraints(scheduled, observation.action_constraints)

    def summary(self) -> StepwisePolicySummary:
        return StepwisePolicySummary(
            policy_kind="scheduled_stepwise_policy",
            scheduled_decision_count=len(self.action_schedule),
            notes=list(self.notes),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "policy_id": self.policy_id,
            "scenario_id": self.scenario_id,
            "policy_kind": "scheduled_stepwise_policy",
            "action_schedule": {
                str(day_index): action.to_dict()
                for day_index, action in sorted(self.action_schedule.items())
            },
            "notes": list(self.notes),
        }


@dataclass(slots=True)
class ReactiveHeuristicStepwisePolicy(StepwisePolicy):
    policy_id: str
    scenario_id: str
    irrigation_schedule: dict[int, float]
    nitrogen_schedule: dict[int, float]
    notes: list[str] = field(default_factory=list)
    pending_irrigation_mm: float = 0.0
    pending_nitrogen_kg_ha: float = 0.0

    def reset(self, scenario: SimulationScenario) -> None:
        del scenario
        self.pending_irrigation_mm = 0.0
        self.pending_nitrogen_kg_ha = 0.0

    def decide(self, observation: Any) -> ContinuousAction:
        irrigation_target = self.pending_irrigation_mm + self.irrigation_schedule.get(observation.day_index, 0.0)
        nitrogen_target = self.pending_nitrogen_kg_ha + self.nitrogen_schedule.get(observation.day_index, 0.0)
        irrigation_mm = 0.0
        nitrogen_kg_ha = 0.0

        if observation.action_constraints.irrigation.allowed and irrigation_target > 0.0:
            irrigation_mm = min(irrigation_target, observation.action_constraints.irrigation.max_value)
        if observation.action_constraints.nitrogen.allowed and nitrogen_target > 0.0:
            nitrogen_kg_ha = min(nitrogen_target, observation.action_constraints.nitrogen.max_value)

        if not observation.action_constraints.allow_joint_action and irrigation_mm > 0.0 and nitrogen_kg_ha > 0.0:
            if irrigation_target >= nitrogen_target:
                nitrogen_kg_ha = 0.0
            else:
                irrigation_mm = 0.0

        self.pending_irrigation_mm = round(max(0.0, irrigation_target - irrigation_mm), 3)
        self.pending_nitrogen_kg_ha = round(max(0.0, nitrogen_target - nitrogen_kg_ha), 3)
        return ContinuousAction(
            irrigation_mm=round(irrigation_mm, 3),
            nitrogen_kg_ha=round(nitrogen_kg_ha, 3),
        )

    def summary(self) -> StepwisePolicySummary:
        scheduled_days = set(self.irrigation_schedule) | set(self.nitrogen_schedule)
        return StepwisePolicySummary(
            policy_kind="reactive_heuristic_stepwise_policy",
            scheduled_decision_count=len(scheduled_days),
            notes=list(self.notes),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "policy_id": self.policy_id,
            "scenario_id": self.scenario_id,
            "policy_kind": "reactive_heuristic_stepwise_policy",
            "irrigation_schedule": {str(day_index): amount for day_index, amount in sorted(self.irrigation_schedule.items())},
            "nitrogen_schedule": {str(day_index): amount for day_index, amount in sorted(self.nitrogen_schedule.items())},
            "notes": list(self.notes),
        }


@dataclass(slots=True)
class ControlledStepwisePolicy(StepwisePolicy):
    policy_id: str
    scenario_id: str
    control_mode: str
    candidate_policy: StepwisePolicy
    reference_policy: StepwisePolicy

    def reset(self, scenario: SimulationScenario) -> None:
        self.candidate_policy.reset(scenario)
        self.reference_policy.reset(scenario)

    def decide(self, observation: Any) -> ContinuousAction:
        candidate = self.candidate_policy.decide(observation)
        reference = self.reference_policy.decide(observation)
        if self.control_mode == "joint":
            return candidate
        if self.control_mode == "water_only":
            return ContinuousAction(
                irrigation_mm=candidate.irrigation_mm,
                nitrogen_kg_ha=reference.nitrogen_kg_ha,
            )
        if self.control_mode == "nitrogen_only":
            return ContinuousAction(
                irrigation_mm=reference.irrigation_mm,
                nitrogen_kg_ha=candidate.nitrogen_kg_ha,
            )
        raise ValueError(f"Unsupported stepwise control mode: {self.control_mode}")

    def summary(self) -> StepwisePolicySummary:
        return StepwisePolicySummary(
            policy_kind="controlled_stepwise_policy",
            scheduled_decision_count=max(
                self.candidate_policy.summary().scheduled_decision_count,
                self.reference_policy.summary().scheduled_decision_count,
            ),
            notes=[f"control_mode={self.control_mode}"],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "policy_id": self.policy_id,
            "scenario_id": self.scenario_id,
            "policy_kind": "controlled_stepwise_policy",
            "control_mode": self.control_mode,
            "candidate_policy": self.candidate_policy.to_dict(),
            "reference_policy": self.reference_policy.to_dict(),
        }


def is_native_stepwise_policy(policy: object) -> bool:
    return isinstance(policy, StepwisePolicy)


def rollout_stepwise_policy(scenario: SimulationScenario, policy: StepwisePolicy) -> Trajectory:
    env = StepwiseDecisionEnvironment(scenario)
    observation = env.reset()
    policy.reset(scenario)
    steps: list[TrajectoryStep] = []

    while not observation.done:
        action = policy.decide(observation)
        next_observation, reward, done, info = env.step(action)
        step_info = dict(info)
        step_info["policy_id"] = policy.policy_id
        step_info["execution_interface"] = "native_stepwise_policy"
        steps.append(
            TrajectoryStep(
                state=observation.state,
                action=CropAction(
                    irrigation_mm=round(action.irrigation_mm, 3),
                    nitrogen_kg_ha=round(action.nitrogen_kg_ha, 3),
                ),
                reward=reward,
                next_state=next_observation.state,
                done=done,
                info=step_info,
            )
        )
        observation = next_observation
        if done:
            break

    outcome = env.final_outcome()
    return Trajectory(
        scenario_id=scenario.scenario_id,
        engine_name=scenario.engine_name,
        crop_name=scenario.crop_spec.crop_name,
        weather_regime=scenario.weather_regime,
        management_mode=scenario.management_mode,
        steps=steps,
        outcome=outcome,
        policy=policy.to_dict(),
    )


def decision_day_indices(scenario: SimulationScenario) -> list[int]:
    interval_days = max(1, scenario.decision_context.decision_interval_days)
    return list(range(0, scenario.crop_spec.season_length_days, interval_days))


def build_stepwise_policy_from_season_policy(
    scenario: SimulationScenario,
    policy: SeasonPolicy,
    suffix: str = "scheduled",
    notes: list[str] | None = None,
) -> ScheduledStepwisePolicy:
    interval_days = max(1, scenario.decision_context.decision_interval_days)
    schedule: dict[int, ContinuousAction] = {}
    for action in policy.actions:
        decision_day = interval_days * floor(action.day_index / interval_days)
        current = schedule.get(decision_day, ContinuousAction())
        schedule[decision_day] = ContinuousAction(
            irrigation_mm=round(current.irrigation_mm + action.irrigation_mm, 3),
            nitrogen_kg_ha=round(current.nitrogen_kg_ha + action.nitrogen_kg_ha, 3),
        )
    return ScheduledStepwisePolicy(
        policy_id=f"{scenario.scenario_id}-{suffix}",
        scenario_id=scenario.scenario_id,
        action_schedule=schedule,
        notes=list(notes or []) + ["built_from_season_policy_window_aggregation"],
    )


def build_equal_allocation_stepwise_policy(scenario: SimulationScenario) -> ScheduledStepwisePolicy:
    decision_days = decision_day_indices(scenario)
    irrigation_weights = {day: 1.0 for day in decision_days}
    nitrogen_weights = {day: 1.0 for day in decision_days}
    return build_weighted_stepwise_policy(
        scenario,
        irrigation_day_weights=irrigation_weights,
        nitrogen_day_weights=nitrogen_weights,
        suffix="stepwise-equal-allocation",
        notes=["uniform_decision_day_allocation"],
    )


def build_heuristic_v1_stepwise_policy(scenario: SimulationScenario) -> ScheduledStepwisePolicy:
    stage_weights = HEURISTIC_STAGE_BUDGET_SPLITS[scenario.management_mode]
    irrigation_weights = _stage_weights_to_day_weights(scenario, {stage: weight[0] for stage, weight in stage_weights.items()})
    nitrogen_weights = _stage_weights_to_day_weights(scenario, {stage: weight[1] for stage, weight in stage_weights.items()})
    return build_weighted_stepwise_policy(
        scenario,
        irrigation_day_weights=irrigation_weights,
        nitrogen_day_weights=nitrogen_weights,
        suffix="stepwise-heuristic-legacy",
        notes=[
            f"management_mode={scenario.management_mode}",
            "legacy_budget_planned_then_legality_clipped",
        ],
    )


def build_heuristic_v2_stepwise_policy(scenario: SimulationScenario) -> ReactiveHeuristicStepwisePolicy:
    stage_weights = HEURISTIC_STAGE_BUDGET_SPLITS[scenario.management_mode]
    irrigation_schedule, irrigation_notes = _build_native_heuristic_schedule(
        scenario,
        total_amount=scenario.irrigation_budget_mm,
        stage_weights={stage: weight[0] for stage, weight in stage_weights.items()},
        allowed_stages=_allowed_input_stages(scenario, input_name="irrigation"),
        min_gap_days=scenario.decision_context.irrigation_min_gap_days,
    )
    nitrogen_schedule, nitrogen_notes = _build_native_heuristic_schedule(
        scenario,
        total_amount=scenario.nitrogen_budget_kg_ha,
        stage_weights={stage: weight[1] for stage, weight in stage_weights.items()},
        allowed_stages=_allowed_input_stages(scenario, input_name="nitrogen"),
        min_gap_days=scenario.decision_context.nitrogen_min_gap_days,
    )
    return ReactiveHeuristicStepwisePolicy(
        policy_id=f"{scenario.scenario_id}-stepwise-heuristic-v2",
        scenario_id=scenario.scenario_id,
        irrigation_schedule=irrigation_schedule,
        nitrogen_schedule=nitrogen_schedule,
        notes=[
            f"management_mode={scenario.management_mode}",
            "native_stepwise_heuristic_v2",
            "generation_time_stage_and_min_gap_compliant",
            "runtime_wet_soil_and_joint_legality_respected_with_carryover",
            *irrigation_notes,
            *nitrogen_notes,
        ],
    )


def build_heuristic_stepwise_policy(scenario: SimulationScenario) -> StepwisePolicy:
    return build_heuristic_v2_stepwise_policy(scenario)


def build_heuristic_legacy_stepwise_policy(scenario: SimulationScenario) -> ScheduledStepwisePolicy:
    return build_heuristic_v1_stepwise_policy(scenario)


def build_literature_stepwise_policy(scenario: SimulationScenario) -> ScheduledStepwisePolicy:
    event_plan = LITERATURE_EVENT_PLAN[scenario.crop_spec.crop_name]
    irrigation_weights, nitrogen_weights = _event_plan_to_day_weights(scenario, event_plan)
    return build_weighted_stepwise_policy(
        scenario,
        irrigation_day_weights=irrigation_weights,
        nitrogen_day_weights=nitrogen_weights,
        suffix="stepwise-literature",
        notes=["native_event_weighted_stepwise_policy"],
    )


def build_weighted_stepwise_policy(
    scenario: SimulationScenario,
    irrigation_day_weights: dict[int, float],
    nitrogen_day_weights: dict[int, float],
    suffix: str,
    notes: list[str] | None = None,
) -> ScheduledStepwisePolicy:
    irrigation_schedule = _allocate_day_budget(scenario.irrigation_budget_mm, irrigation_day_weights)
    nitrogen_schedule = _allocate_day_budget(scenario.nitrogen_budget_kg_ha, nitrogen_day_weights)
    schedule: dict[int, ContinuousAction] = {}
    for day_index in sorted(set(irrigation_schedule) | set(nitrogen_schedule)):
        irrigation_mm = round(irrigation_schedule.get(day_index, 0.0), 3)
        nitrogen_kg_ha = round(nitrogen_schedule.get(day_index, 0.0), 3)
        if irrigation_mm <= 0.0 and nitrogen_kg_ha <= 0.0:
            continue
        schedule[day_index] = ContinuousAction(
            irrigation_mm=max(0.0, irrigation_mm),
            nitrogen_kg_ha=max(0.0, nitrogen_kg_ha),
        )
    return ScheduledStepwisePolicy(
        policy_id=f"{scenario.scenario_id}-{suffix}",
        scenario_id=scenario.scenario_id,
        action_schedule=schedule,
        notes=list(notes or []),
    )


def apply_stepwise_control_mode(
    candidate_policy: StepwisePolicy,
    reference_policy: StepwisePolicy,
    control_mode: str,
    scenario: SimulationScenario,
) -> StepwisePolicy:
    if control_mode == "joint":
        return candidate_policy
    return ControlledStepwisePolicy(
        policy_id=f"{scenario.scenario_id}-stepwise-{control_mode}",
        scenario_id=scenario.scenario_id,
        control_mode=control_mode,
        candidate_policy=candidate_policy,
        reference_policy=reference_policy,
    )


def _allocate_day_budget(total: float, weights: dict[int, float]) -> dict[int, float]:
    positive_items = [(day_index, weight) for day_index, weight in sorted(weights.items()) if weight > 0.0]
    if total <= 0.0 or not positive_items:
        return {}
    weight_sum = sum(weight for _, weight in positive_items)
    allocated: dict[int, float] = {}
    used = 0.0
    for index, (day_index, weight) in enumerate(positive_items):
        if index == len(positive_items) - 1:
            value = round(total - used, 3)
        else:
            value = round(total * weight / weight_sum, 3)
            used += value
        allocated[day_index] = max(0.0, value)
    return allocated


def _stage_weights_to_day_weights(scenario: SimulationScenario, stage_weights: dict[str, float]) -> dict[int, float]:
    weights: dict[int, float] = {}
    for day_index in decision_day_indices(scenario):
        stage_name, _ = stage_for_day(day_index, scenario.crop_spec.season_length_days)
        weights[day_index] = max(0.0, stage_weights.get(stage_name, 0.0))
    return weights


def _event_plan_to_day_weights(
    scenario: SimulationScenario,
    event_plan: tuple[tuple[str, float, float, float], ...],
) -> tuple[dict[int, float], dict[int, float]]:
    interval_days = max(1, scenario.decision_context.decision_interval_days)
    irrigation_weights: dict[int, float] = {}
    nitrogen_weights: dict[int, float] = {}
    max_day = scenario.crop_spec.season_length_days - 1
    for _, progress, irrigation_share, nitrogen_share in event_plan:
        raw_day = max(0, min(max_day, round(max_day * progress)))
        decision_day = interval_days * floor(raw_day / interval_days)
        irrigation_weights[decision_day] = irrigation_weights.get(decision_day, 0.0) + max(0.0, irrigation_share)
        nitrogen_weights[decision_day] = nitrogen_weights.get(decision_day, 0.0) + max(0.0, nitrogen_share)
    return irrigation_weights, nitrogen_weights


def _allowed_input_stages(scenario: SimulationScenario, input_name: str) -> tuple[str, ...]:
    constraints = default_action_constraint_rules(scenario)
    if input_name == "irrigation":
        return tuple(constraints.allowed_irrigation_stages)
    if input_name == "nitrogen":
        return tuple(constraints.allowed_nitrogen_stages)
    raise ValueError(f"Unsupported heuristic input channel: {input_name}")


def _build_native_heuristic_schedule(
    scenario: SimulationScenario,
    *,
    total_amount: float,
    stage_weights: dict[str, float],
    allowed_stages: tuple[str, ...],
    min_gap_days: int,
) -> tuple[dict[int, float], list[str]]:
    decision_days = decision_day_indices(scenario)
    slot_days: dict[str, list[int]] = {stage: [] for stage in STAGES}
    last_slot_day: int | None = None
    for day_index in decision_days:
        stage_name, _ = stage_for_day(day_index, scenario.crop_spec.season_length_days)
        if stage_name not in allowed_stages:
            continue
        if last_slot_day is not None and day_index - last_slot_day < min_gap_days:
            continue
        slot_days[stage_name].append(day_index)
        last_slot_day = day_index

    effective_stage_weights = _redistribute_stage_weights_to_available_slots(stage_weights, slot_days)
    schedule: dict[int, float] = {}
    notes: list[str] = []
    for stage_name in STAGES:
        days = slot_days[stage_name]
        stage_weight = effective_stage_weights.get(stage_name, 0.0)
        if stage_weight <= 0.0 or not days:
            continue
        stage_total = round(total_amount * stage_weight, 3)
        stage_schedule = _allocate_day_budget(stage_total, {day_index: 1.0 for day_index in days})
        for day_index, amount in stage_schedule.items():
            schedule[day_index] = round(schedule.get(day_index, 0.0) + amount, 3)
    if total_amount > 0.0:
        allocated_total = round(sum(schedule.values()), 3)
        if abs(allocated_total - total_amount) > 1e-6:
            tail_day = max(schedule, default=None)
            if tail_day is not None:
                schedule[tail_day] = round(schedule[tail_day] + (total_amount - allocated_total), 3)
        notes.append(f"native_slot_count={sum(len(days) for days in slot_days.values())}")
        notes.append(f"allowed_stages={','.join(allowed_stages)}")
        notes.append(f"min_gap_days={min_gap_days}")
    return schedule, notes


def _redistribute_stage_weights_to_available_slots(
    stage_weights: dict[str, float],
    slot_days: dict[str, list[int]],
) -> dict[str, float]:
    effective = {stage: max(0.0, float(stage_weights.get(stage, 0.0))) for stage in STAGES}
    for index, stage_name in enumerate(STAGES):
        if slot_days[stage_name] or effective[stage_name] <= 0.0:
            continue
        carry = effective[stage_name]
        effective[stage_name] = 0.0
        target_stage: str | None = None
        for later_stage in STAGES[index + 1 :]:
            if slot_days[later_stage]:
                target_stage = later_stage
                break
        if target_stage is None:
            for earlier_stage in reversed(STAGES[:index]):
                if slot_days[earlier_stage]:
                    target_stage = earlier_stage
                    break
        if target_stage is not None:
            effective[target_stage] = round(effective[target_stage] + carry, 6)

    total_weight = sum(effective.values())
    if total_weight <= 0.0:
        return effective
    return {
        stage_name: round(stage_weight / total_weight, 6)
        for stage_name, stage_weight in effective.items()
    }


def _clip_action_to_constraints(
    action: ContinuousAction,
    constraints: ActionConstraintSnapshot,
) -> ContinuousAction:
    irrigation_mm = min(max(0.0, action.irrigation_mm), constraints.irrigation.max_value)
    nitrogen_kg_ha = min(max(0.0, action.nitrogen_kg_ha), constraints.nitrogen.max_value)
    if not constraints.allow_joint_action and irrigation_mm > 0.0 and nitrogen_kg_ha > 0.0:
        if irrigation_mm >= nitrogen_kg_ha:
            nitrogen_kg_ha = 0.0
        else:
            irrigation_mm = 0.0
    return ContinuousAction(
        irrigation_mm=round(irrigation_mm, 3),
        nitrogen_kg_ha=round(nitrogen_kg_ha, 3),
    )
