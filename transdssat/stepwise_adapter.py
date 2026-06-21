from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
from typing import Any

from transdssat.discrete_actions import ActionConstraintSnapshot, ContinuousAction
from transdssat.environments import StepwiseDecisionEnvironment
from transdssat.scenarios import SimulationScenario
from transdssat.season import SeasonPolicy, StageDecision


@dataclass(slots=True)
class StepwiseProjectionSummary:
    decision_count: int
    projected_action_count: int
    decision_interval_days: int
    target_total_irrigation_mm: float
    target_total_nitrogen_kg_ha: float
    projected_total_irrigation_mm: float
    projected_total_nitrogen_kg_ha: float
    irrigation_projection_error_mm: float
    nitrogen_projection_error_kg_ha: float
    adapter_name: str = "season_policy_to_stepwise_projection"
    notes: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["notes"] = self.notes or []
        return payload


def _policy_window_targets(
    policy: SeasonPolicy,
    start_day_index: int,
    end_day_index: int,
) -> tuple[float, float]:
    irrigation_mm = 0.0
    nitrogen_kg_ha = 0.0
    for action in policy.actions:
        if start_day_index <= action.day_index < end_day_index:
            irrigation_mm += action.irrigation_mm
            nitrogen_kg_ha += action.nitrogen_kg_ha
    return irrigation_mm, nitrogen_kg_ha


def _clip_action_to_constraints(
    target_irrigation_mm: float,
    target_nitrogen_kg_ha: float,
    constraints: ActionConstraintSnapshot,
) -> ContinuousAction:
    irrigation_mm = min(max(0.0, target_irrigation_mm), constraints.irrigation.max_value)
    nitrogen_kg_ha = min(max(0.0, target_nitrogen_kg_ha), constraints.nitrogen.max_value)
    if not constraints.allow_joint_action and irrigation_mm > 0.0 and nitrogen_kg_ha > 0.0:
        if irrigation_mm >= nitrogen_kg_ha:
            nitrogen_kg_ha = 0.0
        else:
            irrigation_mm = 0.0
    return ContinuousAction(
        irrigation_mm=round(irrigation_mm, 3),
        nitrogen_kg_ha=round(nitrogen_kg_ha, 3),
    )


def _build_projected_policy(
    scenario: SimulationScenario,
    decisions: list[StageDecision],
    source_policy_id: str,
) -> SeasonPolicy:
    fingerprint = "|".join(
        f"{action.day_index}:{action.irrigation_mm}:{action.nitrogen_kg_ha}"
        for action in decisions
    )
    policy_hash = hashlib.sha256(f"{source_policy_id}|{fingerprint}".encode("utf-8")).hexdigest()[:10]
    return SeasonPolicy(
        policy_id=f"{scenario.scenario_id}-stepwise-{policy_hash}",
        scenario_id=scenario.scenario_id,
        actions=decisions,
    )


def project_policy_to_stepwise(
    scenario: SimulationScenario,
    policy: SeasonPolicy,
) -> tuple[SeasonPolicy, StepwiseProjectionSummary]:
    if scenario.engine_name == "dssat_official":
        raise ValueError("stepwise projection currently supports proxy scenarios only.")

    env = StepwiseDecisionEnvironment(scenario)
    observation = env.reset()
    projected_actions: list[StageDecision] = []
    decision_count = 0
    interval_days = env.constraint_rules.decision_interval_days

    while not observation.done:
        decision_count += 1
        window_end = min(
            scenario.crop_spec.season_length_days,
            observation.day_index + interval_days,
        )
        target_irrigation_mm, target_nitrogen_kg_ha = _policy_window_targets(
            policy,
            start_day_index=observation.day_index,
            end_day_index=window_end,
        )
        chosen_action = _clip_action_to_constraints(
            target_irrigation_mm,
            target_nitrogen_kg_ha,
            observation.action_constraints,
        )
        if chosen_action.irrigation_mm > 0.0 or chosen_action.nitrogen_kg_ha > 0.0:
            projected_actions.append(
                StageDecision(
                    stage=observation.state.stage,
                    day_index=observation.day_index,
                    date=observation.decision_date,
                    irrigation_mm=chosen_action.irrigation_mm,
                    nitrogen_kg_ha=chosen_action.nitrogen_kg_ha,
                )
            )
        observation, _, done, _ = env.step(chosen_action)
        if done:
            break

    projected_policy = _build_projected_policy(scenario, projected_actions, policy.policy_id)
    summary = StepwiseProjectionSummary(
        decision_count=decision_count,
        projected_action_count=len(projected_actions),
        decision_interval_days=interval_days,
        target_total_irrigation_mm=round(policy.total_irrigation_mm, 3),
        target_total_nitrogen_kg_ha=round(policy.total_nitrogen_kg_ha, 3),
        projected_total_irrigation_mm=round(projected_policy.total_irrigation_mm, 3),
        projected_total_nitrogen_kg_ha=round(projected_policy.total_nitrogen_kg_ha, 3),
        irrigation_projection_error_mm=round(abs(projected_policy.total_irrigation_mm - policy.total_irrigation_mm), 3),
        nitrogen_projection_error_kg_ha=round(abs(projected_policy.total_nitrogen_kg_ha - policy.total_nitrogen_kg_ha), 3),
        notes=[
            "projection_uses_window_totals_clipped_to_legal_continuous_bounds",
            "projection_is_based_on_proxy_stepwise_constraint_rules",
        ],
    )
    return projected_policy, summary
