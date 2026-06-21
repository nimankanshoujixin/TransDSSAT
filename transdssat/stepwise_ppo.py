from __future__ import annotations

from dataclasses import asdict, dataclass, field
import inspect
import math
import random
from typing import Any, Callable

from transdssat.discrete_actions import (
    ContinuousAction,
    default_discrete_action_table,
    discrete_action_by_id,
)
from transdssat.domain import CropAction, CropOutcome, CropState, Trajectory, TrajectoryStep
from transdssat.environments.stepwise import DecisionObservation, StepwiseDecisionEnvironment
from transdssat.evaluation import score_trajectory, summarize_scorecards
from transdssat.scenarios import SimulationScenario
from transdssat.stepwise_policy import (
    build_equal_allocation_stepwise_policy,
    build_heuristic_legacy_stepwise_policy,
    build_heuristic_stepwise_policy,
    build_literature_stepwise_policy,
    rollout_stepwise_policy,
)

STEPWISE_DISCRETE_ACTION_DIM = len(default_discrete_action_table().actions)
STEPWISE_OBSERVATION_DIM = 25
STEPWISE_SEQUENCE_FEATURE_DIM = 60
STEPWISE_CONTINUOUS_ACTION_DIM = 2
STEPWISE_BUDGET_SCALE = 500.0
STEPWISE_ACTION_MAX_SCALE = 250.0


def _mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def encode_stepwise_observation(observation: DecisionObservation) -> list[float]:
    forecast_precipitation = [float(day["precipitation_mm"]) for day in observation.forecast_weather_window]
    forecast_et0 = [float(day["et0_mm"]) for day in observation.forecast_weather_window]
    forecast_tmean = [
        (float(day["tmin_c"]) + float(day["tmax_c"])) / 2.0
        for day in observation.forecast_weather_window
    ]
    crop_name = str(observation.crop_context.get("crop_name", "")).lower()
    return [
        float(observation.state.day_index) / 200.0,
        float(observation.state.stage_index) / 3.0,
        float(observation.state.soil_moisture),
        float(observation.state.root_zone_water_mm) / 400.0,
        float(observation.state.soil_nitrogen_kg_ha) / 300.0,
        float(observation.state.canopy_cover),
        float(observation.state.biomass_kg_ha) / 30000.0,
        float(observation.state.water_stress),
        float(observation.state.nitrogen_stress),
        float(observation.state.tmean_c) / 40.0,
        float(observation.state.precipitation_mm) / 60.0,
        float(observation.state.et0_mm) / 12.0,
        float(observation.state.radiation_mj_m2) / 30.0,
        float(observation.remaining_irrigation_mm) / STEPWISE_BUDGET_SCALE,
        float(observation.remaining_nitrogen_kg_ha) / STEPWISE_BUDGET_SCALE,
        float(observation.action_constraints.irrigation.max_value) / STEPWISE_ACTION_MAX_SCALE,
        float(observation.action_constraints.nitrogen.max_value) / STEPWISE_ACTION_MAX_SCALE,
        float(observation.action_constraints.irrigation.gap_days_remaining) / 30.0,
        float(observation.action_constraints.nitrogen.gap_days_remaining) / 30.0,
        1.0 if observation.action_constraints.allow_joint_action else 0.0,
        _mean(forecast_precipitation) / 60.0,
        _mean(forecast_et0) / 12.0,
        _mean(forecast_tmean) / 40.0,
        1.0 if crop_name == "maize" else 0.0,
        1.0 if crop_name == "wheat" else 0.0,
    ]


@dataclass(slots=True)
class StepwiseHistoryFeedback:
    action_mode: str
    control_mode: str
    recommended_action_id: int | None
    recommended_irrigation_gate: int
    recommended_nitrogen_gate: int
    recommended_irrigation_max_mm: float
    recommended_nitrogen_max_kg_ha: float
    recommended_action: CropAction
    executed_action: CropAction
    reward: float


@dataclass(slots=True)
class ResolvedStepwiseAction:
    action_mode: str
    control_mode: str
    recommended_action: ContinuousAction
    recommended_action_id: int | None
    irrigation_gate: int
    nitrogen_gate: int
    irrigation_max_mm: float
    nitrogen_max_kg_ha: float
    action_family: str

    def to_crop_action(self) -> CropAction:
        return self.recommended_action.to_crop_action()


def _reward_weight(observation: DecisionObservation, name: str) -> float:
    reward_weights = observation.objective_context.get("reward_weights", {})
    return float(reward_weights.get(name, 0.0))


def _management_mode_features(observation: DecisionObservation) -> list[float]:
    management_mode = str(observation.decision_context.get("management_mode", "")).lower()
    crop_name = str(observation.crop_context.get("crop_name", "")).lower()
    if not management_mode:
        management_mode = "balanced" if crop_name == "wheat" else "reproductive_focus"
    return [
        1.0 if management_mode == "balanced" else 0.0,
        1.0 if management_mode == "reproductive_focus" else 0.0,
        1.0 if management_mode == "vegetative_focus" else 0.0,
    ]


def _canonicalize_action_mode(action_mode: str) -> str:
    normalized = str(action_mode).strip().lower() or "continuous"
    if normalized == "gated_continuous":
        normalized = "continuous"
    if normalized not in {"discrete", "continuous"}:
        raise ValueError(f"Unsupported stepwise action mode: {action_mode}")
    return normalized


def _canonicalize_control_mode(control_mode: str) -> str:
    normalized = str(control_mode).strip().lower() or "joint"
    if normalized not in {"water_only", "nitrogen_only", "joint"}:
        raise ValueError(f"Unsupported stepwise control mode: {control_mode}")
    return normalized


def _control_mode_flags(control_mode: str) -> tuple[int, int]:
    normalized = _canonicalize_control_mode(control_mode)
    if normalized == "water_only":
        return 1, 0
    if normalized == "nitrogen_only":
        return 0, 1
    return 1, 1


def _gate_from_amount(amount: float) -> int:
    return 1 if float(amount) > 1e-9 else 0


def _action_family(irrigation_gate: int, nitrogen_gate: int) -> str:
    if irrigation_gate and nitrogen_gate:
        return "joint"
    if irrigation_gate:
        return "water_only"
    if nitrogen_gate:
        return "nitrogen_only"
    return "noop"


def _continuous_ratio(amount: float, maximum: float) -> float:
    if maximum <= 1e-9:
        return 0.0
    return round(min(max(float(amount) / maximum, 0.0), 1.0), 6)


def encode_stepwise_sequence_token(
    observation: DecisionObservation,
    previous_feedback: StepwiseHistoryFeedback | None = None,
) -> list[float]:
    base = encode_stepwise_observation(observation)
    previous_recommended_irrigation_gate = 0.0
    previous_recommended_nitrogen_gate = 0.0
    previous_executed_irrigation_gate = 0.0
    previous_executed_nitrogen_gate = 0.0
    previous_recommended_irrigation_ratio = 0.0
    previous_recommended_nitrogen_ratio = 0.0
    previous_executed_irrigation_ratio = 0.0
    previous_executed_nitrogen_ratio = 0.0
    previous_recommended_irrigation = 0.0
    previous_recommended_nitrogen = 0.0
    previous_executed_irrigation = 0.0
    previous_executed_nitrogen = 0.0
    previous_reward = 0.0
    previous_action_exists = 0.0
    previous_control_mode = [0.0, 0.0, 0.0]
    previous_action_family = [0.0, 0.0, 0.0, 0.0]

    if previous_feedback is not None:
        previous_recommended_irrigation_gate = float(previous_feedback.recommended_irrigation_gate)
        previous_recommended_nitrogen_gate = float(previous_feedback.recommended_nitrogen_gate)
        previous_executed_irrigation_gate = float(_gate_from_amount(previous_feedback.executed_action.irrigation_mm))
        previous_executed_nitrogen_gate = float(_gate_from_amount(previous_feedback.executed_action.nitrogen_kg_ha))
        previous_recommended_irrigation = float(previous_feedback.recommended_action.irrigation_mm) / 100.0
        previous_recommended_nitrogen = float(previous_feedback.recommended_action.nitrogen_kg_ha) / 100.0
        previous_executed_irrigation = float(previous_feedback.executed_action.irrigation_mm) / 100.0
        previous_executed_nitrogen = float(previous_feedback.executed_action.nitrogen_kg_ha) / 100.0
        previous_recommended_irrigation_ratio = _continuous_ratio(
            previous_feedback.recommended_action.irrigation_mm,
            previous_feedback.recommended_irrigation_max_mm,
        )
        previous_recommended_nitrogen_ratio = _continuous_ratio(
            previous_feedback.recommended_action.nitrogen_kg_ha,
            previous_feedback.recommended_nitrogen_max_kg_ha,
        )
        previous_executed_irrigation_ratio = _continuous_ratio(
            previous_feedback.executed_action.irrigation_mm,
            previous_feedback.recommended_irrigation_max_mm,
        )
        previous_executed_nitrogen_ratio = _continuous_ratio(
            previous_feedback.executed_action.nitrogen_kg_ha,
            previous_feedback.recommended_nitrogen_max_kg_ha,
        )
        previous_reward = math.tanh(float(previous_feedback.reward) / 1000.0)
        previous_action_exists = 1.0
        if previous_feedback.control_mode == "water_only":
            previous_control_mode = [1.0, 0.0, 0.0]
        elif previous_feedback.control_mode == "nitrogen_only":
            previous_control_mode = [0.0, 1.0, 0.0]
        else:
            previous_control_mode = [0.0, 0.0, 1.0]
        family = _action_family(
            previous_feedback.recommended_irrigation_gate,
            previous_feedback.recommended_nitrogen_gate,
        )
        if family == "noop":
            previous_action_family = [1.0, 0.0, 0.0, 0.0]
        elif family == "water_only":
            previous_action_family = [0.0, 1.0, 0.0, 0.0]
        elif family == "nitrogen_only":
            previous_action_family = [0.0, 0.0, 1.0, 0.0]
        else:
            previous_action_family = [0.0, 0.0, 0.0, 1.0]

    normalized_day = float(observation.state.day_index) / max(1.0, 200.0)
    time_encoding = [
        math.sin(2.0 * math.pi * normalized_day),
        math.cos(2.0 * math.pi * normalized_day),
    ]
    objective_context = [
        _reward_weight(observation, "yield_revenue"),
        _reward_weight(observation, "irrigation_cost"),
        _reward_weight(observation, "nitrogen_cost"),
        _reward_weight(observation, "operation_cost"),
        _reward_weight(observation, "water_penalty"),
        _reward_weight(observation, "nitrogen_leaching_penalty"),
        _reward_weight(observation, "risk_penalty"),
    ]
    decision_context = [
        float(observation.decision_context.get("decision_interval_days", 5)) / 30.0,
        float(observation.decision_context.get("forecast_horizon_days", 7)) / 30.0,
    ]
    token = (
        base
        + [
            previous_recommended_irrigation_gate,
            previous_recommended_nitrogen_gate,
            previous_executed_irrigation_gate,
            previous_executed_nitrogen_gate,
            previous_recommended_irrigation_ratio,
            previous_recommended_nitrogen_ratio,
            previous_executed_irrigation_ratio,
            previous_executed_nitrogen_ratio,
            previous_recommended_irrigation,
            previous_recommended_nitrogen,
            previous_executed_irrigation,
            previous_executed_nitrogen,
            previous_reward,
            previous_action_exists,
        ]
        + previous_control_mode
        + previous_action_family
        + time_encoding
        + objective_context
        + _management_mode_features(observation)
        + decision_context
    )
    if len(token) != STEPWISE_SEQUENCE_FEATURE_DIM:
        raise RuntimeError(
            f"Unexpected history token length {len(token)}; expected {STEPWISE_SEQUENCE_FEATURE_DIM}."
        )
    return token


@dataclass(slots=True)
class StepwisePolicyDecision:
    action_mode: str = "continuous"
    control_mode: str = "joint"
    action_id: int | None = None
    irrigation_gate: int = 0
    nitrogen_gate: int = 0
    irrigation_amount_mm: float = 0.0
    nitrogen_amount_kg_ha: float = 0.0
    value_estimate: float = 0.0
    log_prob: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def compute_activity_ratio(candidate_value: float, baseline_value: float) -> float:
    baseline = float(baseline_value)
    candidate = float(candidate_value)
    if baseline <= 1e-9:
        return 1.0 if candidate <= 1e-9 else float("inf")
    return candidate / baseline


def build_checkpoint_guardrail_summary(
    candidate_summary: dict[str, Any],
    baseline_summary: dict[str, Any],
    *,
    control_mode: str,
    min_activity_ratio: float,
    min_yield_floor_attainment_pct: float,
    primary_metric: str,
) -> dict[str, Any]:
    normalized_control_mode = _canonicalize_control_mode(control_mode)
    irrigation_enabled, nitrogen_enabled = _control_mode_flags(normalized_control_mode)
    irrigation_ratio = compute_activity_ratio(
        float(candidate_summary.get("mean_irrigation_mm", 0.0)),
        float(baseline_summary.get("mean_irrigation_mm", 0.0)),
    )
    nitrogen_ratio = compute_activity_ratio(
        float(candidate_summary.get("mean_nitrogen_kg_ha", 0.0)),
        float(baseline_summary.get("mean_nitrogen_kg_ha", 0.0)),
    )
    enabled_activity_ratios: list[float] = []
    if irrigation_enabled:
        enabled_activity_ratios.append(irrigation_ratio)
    if nitrogen_enabled:
        enabled_activity_ratios.append(nitrogen_ratio)
    min_enabled_activity_ratio = min(enabled_activity_ratios) if enabled_activity_ratios else 1.0
    yield_floor_attainment_pct = float(candidate_summary.get("mean_yield_floor_attainment_pct", 0.0))
    activity_shortfall = sum(
        max(0.0, float(min_activity_ratio) - ratio) for ratio in enabled_activity_ratios
    )
    yield_shortfall = max(0.0, float(min_yield_floor_attainment_pct) - yield_floor_attainment_pct) / 100.0
    guardrail_shortfall = activity_shortfall + yield_shortfall
    meets_activity_floor = min_enabled_activity_ratio >= float(min_activity_ratio)
    meets_yield_floor = yield_floor_attainment_pct >= float(min_yield_floor_attainment_pct)
    primary_value = (
        -float(candidate_summary.get("mean_yield_floor_gap_ratio", 0.0))
        if primary_metric == "yield_floor_gap"
        else (
            float(candidate_summary.get("mean_reward_gain", 0.0))
            if primary_metric == "reward_gain"
            else float(candidate_summary.get("mean_total_score_100", 0.0))
        )
    )
    eligible = meets_activity_floor and meets_yield_floor
    selection_tuple = (
        1 if eligible else 0,
        primary_value if eligible else -guardrail_shortfall,
        yield_floor_attainment_pct,
        min_enabled_activity_ratio,
        primary_value,
    )
    return {
        "control_mode": normalized_control_mode,
        "primary_metric": primary_metric,
        "primary_metric_value": round(primary_value, 6),
        "activity_reference": {
            "baseline_mean_irrigation_mm": round(float(baseline_summary.get("mean_irrigation_mm", 0.0)), 6),
            "baseline_mean_nitrogen_kg_ha": round(float(baseline_summary.get("mean_nitrogen_kg_ha", 0.0)), 6),
            "candidate_mean_irrigation_mm": round(float(candidate_summary.get("mean_irrigation_mm", 0.0)), 6),
            "candidate_mean_nitrogen_kg_ha": round(float(candidate_summary.get("mean_nitrogen_kg_ha", 0.0)), 6),
            "irrigation_activity_ratio": None if not irrigation_enabled else round(irrigation_ratio, 6),
            "nitrogen_activity_ratio": None if not nitrogen_enabled else round(nitrogen_ratio, 6),
            "min_enabled_activity_ratio": round(min_enabled_activity_ratio, 6),
            "min_activity_ratio": float(min_activity_ratio),
        },
        "yield_floor_reference": {
            "mean_yield_floor_attainment_pct": round(yield_floor_attainment_pct, 6),
            "min_yield_floor_attainment_pct": float(min_yield_floor_attainment_pct),
        },
        "guardrail_shortfall": round(guardrail_shortfall, 6),
        "meets_activity_floor": meets_activity_floor,
        "meets_yield_floor": meets_yield_floor,
        "eligible_for_best_checkpoint": eligible,
        "selection_tuple": list(selection_tuple),
    }


@dataclass(slots=True)
class StepwiseEpisodeTransition:
    decision_date: str
    state: CropState
    next_state: CropState
    action: CropAction
    reward: float
    done: bool
    action_mode: str
    control_mode: str
    action_id: int | None
    irrigation_gate: int
    nitrogen_gate: int
    irrigation_max_mm: float
    nitrogen_max_kg_ha: float
    action_family: str
    action_mask: list[int]
    legal_action_ids: list[int]
    observation_features: list[float]
    sequence_features: list[list[float]]
    sequence_length: int
    value_estimate: float = 0.0
    log_prob: float = 0.0
    info: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision_date": self.decision_date,
            "state": self.state.to_dict(),
            "next_state": self.next_state.to_dict(),
            "action": self.action.to_dict(),
            "reward": self.reward,
            "done": self.done,
            "action_mode": self.action_mode,
            "control_mode": self.control_mode,
            "action_id": self.action_id,
            "irrigation_gate": self.irrigation_gate,
            "nitrogen_gate": self.nitrogen_gate,
            "irrigation_max_mm": self.irrigation_max_mm,
            "nitrogen_max_kg_ha": self.nitrogen_max_kg_ha,
            "action_family": self.action_family,
            "action_mask": list(self.action_mask),
            "legal_action_ids": list(self.legal_action_ids),
            "observation_features": list(self.observation_features),
            "sequence_features": [list(token) for token in self.sequence_features],
            "sequence_length": self.sequence_length,
            "value_estimate": self.value_estimate,
            "log_prob": self.log_prob,
            "info": dict(self.info),
        }


@dataclass(slots=True)
class StepwiseRolloutEpisode:
    scenario_id: str
    engine_name: str
    crop_name: str
    weather_regime: str
    management_mode: str
    transitions: list[StepwiseEpisodeTransition]
    total_reward: float
    final_outcome: CropOutcome
    action_mode: str = "continuous"
    control_mode: str = "joint"
    policy_id: str = "stepwise_rollout"
    notes: list[str] = field(default_factory=list)

    @property
    def decision_count(self) -> int:
        return len(self.transitions)

    def to_policy_dict(self) -> dict[str, Any]:
        return {
            "policy_id": self.policy_id,
            "policy_kind": f"{self.action_mode}_stepwise_rollout",
            "action_mode": self.action_mode,
            "control_mode": self.control_mode,
            "actions": [
                {
                    "day_index": step.state.day_index,
                    "decision_date": step.decision_date,
                    "action_id": step.action_id,
                    "action_mode": step.action_mode,
                    "control_mode": step.control_mode,
                    "irrigation_gate": step.irrigation_gate,
                    "nitrogen_gate": step.nitrogen_gate,
                    "action_family": step.action_family,
                    "irrigation_mm": step.action.irrigation_mm,
                    "nitrogen_kg_ha": step.action.nitrogen_kg_ha,
                }
                for step in self.transitions
            ],
            "notes": list(self.notes),
        }

    def to_trajectory(self) -> Trajectory:
        return Trajectory(
            scenario_id=self.scenario_id,
            engine_name=self.engine_name,
            crop_name=self.crop_name,
            weather_regime=self.weather_regime,
            management_mode=self.management_mode,
            steps=[
                TrajectoryStep(
                    state=step.state,
                    action=step.action,
                    reward=step.reward,
                    next_state=step.next_state,
                    done=step.done,
                    info=dict(step.info),
                )
                for step in self.transitions
            ],
            outcome=self.final_outcome,
            policy=self.to_policy_dict(),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "engine_name": self.engine_name,
            "crop_name": self.crop_name,
            "weather_regime": self.weather_regime,
            "management_mode": self.management_mode,
            "decision_count": self.decision_count,
            "total_reward": self.total_reward,
            "action_mode": self.action_mode,
            "control_mode": self.control_mode,
            "final_outcome": self.final_outcome.to_dict(),
            "transitions": [step.to_dict() for step in self.transitions],
            "policy": self.to_policy_dict(),
            "notes": list(self.notes),
        }


def normalize_policy_decision(
    decision: StepwisePolicyDecision | int,
) -> StepwisePolicyDecision:
    if isinstance(decision, StepwisePolicyDecision):
        decision.action_mode = _canonicalize_action_mode(decision.action_mode)
        decision.control_mode = _canonicalize_control_mode(decision.control_mode)
        return decision
    return StepwisePolicyDecision(action_mode="discrete", control_mode="joint", action_id=int(decision))


def select_highest_legal_action(
    observation: DecisionObservation,
    _: list[float],
) -> StepwisePolicyDecision:
    return StepwisePolicyDecision(action_mode="discrete", control_mode="joint", action_id=observation.discrete_action_mask.legal_action_ids[-1])


def select_random_legal_action(
    observation: DecisionObservation,
    _: list[float],
    rng: random.Random | None = None,
) -> StepwisePolicyDecision:
    random_source = rng or random
    return StepwisePolicyDecision(
        action_mode="discrete",
        control_mode="joint",
        action_id=random_source.choice(observation.discrete_action_mask.legal_action_ids),
    )


def _resolve_policy_action(
    observation: DecisionObservation,
    decision: StepwisePolicyDecision,
) -> ResolvedStepwiseAction:
    action_mode = _canonicalize_action_mode(decision.action_mode)
    control_mode = _canonicalize_control_mode(decision.control_mode)
    irrigation_control_enabled, nitrogen_control_enabled = _control_mode_flags(control_mode)
    irrigation_max = float(observation.action_constraints.irrigation.max_value)
    nitrogen_max = float(observation.action_constraints.nitrogen.max_value)

    if action_mode == "discrete":
        if decision.action_id is None:
            raise ValueError("Discrete stepwise policy decisions must include action_id.")
        recommended_action = discrete_action_by_id(
            decision.action_id,
            observation.discrete_action_table,
        ).to_continuous_action()
        irrigation_gate = _gate_from_amount(recommended_action.irrigation_mm)
        nitrogen_gate = _gate_from_amount(recommended_action.nitrogen_kg_ha)
        return ResolvedStepwiseAction(
            action_mode=action_mode,
            control_mode=control_mode,
            recommended_action=recommended_action,
            recommended_action_id=decision.action_id,
            irrigation_gate=irrigation_gate,
            nitrogen_gate=nitrogen_gate,
            irrigation_max_mm=irrigation_max,
            nitrogen_max_kg_ha=nitrogen_max,
            action_family=_action_family(irrigation_gate, nitrogen_gate),
        )

    irrigation_gate = int(
        bool(
            irrigation_control_enabled
            and irrigation_max > 1e-9
            and (decision.irrigation_gate or float(decision.irrigation_amount_mm) > 1e-9)
        )
    )
    nitrogen_gate = int(
        bool(
            nitrogen_control_enabled
            and nitrogen_max > 1e-9
            and (decision.nitrogen_gate or float(decision.nitrogen_amount_kg_ha) > 1e-9)
        )
    )
    irrigation_amount_mm = 0.0
    nitrogen_amount_kg_ha = 0.0
    if irrigation_gate:
        irrigation_amount_mm = min(max(float(decision.irrigation_amount_mm), 0.0), irrigation_max)
    if nitrogen_gate:
        nitrogen_amount_kg_ha = min(max(float(decision.nitrogen_amount_kg_ha), 0.0), nitrogen_max)
    recommended_action = ContinuousAction(
        irrigation_mm=round(irrigation_amount_mm, 3),
        nitrogen_kg_ha=round(nitrogen_amount_kg_ha, 3),
    )
    return ResolvedStepwiseAction(
        action_mode=action_mode,
        control_mode=control_mode,
        recommended_action=recommended_action,
        recommended_action_id=None,
        irrigation_gate=irrigation_gate,
        nitrogen_gate=nitrogen_gate,
        irrigation_max_mm=irrigation_max,
        nitrogen_max_kg_ha=nitrogen_max,
        action_family=_action_family(irrigation_gate, nitrogen_gate),
    )


def _supports_sequence_argument(action_selector: Callable[..., StepwisePolicyDecision | int]) -> bool:
    signature = inspect.signature(action_selector)
    for parameter in signature.parameters.values():
        if parameter.kind == inspect.Parameter.VAR_POSITIONAL:
            return True
    positional = [
        parameter
        for parameter in signature.parameters.values()
        if parameter.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
    ]
    return len(positional) >= 3


def _invoke_action_selector(
    action_selector: Callable[..., StepwisePolicyDecision | int],
    observation: DecisionObservation,
    features: list[float],
    sequence_features: list[list[float]],
) -> StepwisePolicyDecision | int:
    if _supports_sequence_argument(action_selector):
        return action_selector(observation, features, sequence_features)
    return action_selector(observation, features)


def rollout_stepwise_episode(
    scenario: SimulationScenario,
    action_selector: Callable[..., StepwisePolicyDecision | int],
    *,
    policy_id: str = "stepwise_rollout",
    notes: list[str] | None = None,
) -> StepwiseRolloutEpisode:
    env = StepwiseDecisionEnvironment(scenario)
    observation = env.reset()
    transitions: list[StepwiseEpisodeTransition] = []
    total_reward = 0.0
    sequence_history: list[list[float]] = []
    previous_feedback: StepwiseHistoryFeedback | None = None
    episode_action_mode = "continuous"
    episode_control_mode = "joint"

    while not observation.done:
        features = encode_stepwise_observation(observation)
        current_token = encode_stepwise_sequence_token(observation, previous_feedback)
        current_sequence = [list(token) for token in sequence_history]
        current_sequence.append(current_token)
        decision = normalize_policy_decision(
            _invoke_action_selector(action_selector, observation, features, current_sequence)
        )
        resolved_action = _resolve_policy_action(observation, decision)
        episode_action_mode = resolved_action.action_mode
        episode_control_mode = resolved_action.control_mode
        if resolved_action.action_mode == "discrete":
            next_observation, reward, done, info = env.step_discrete(resolved_action.recommended_action_id)
        else:
            next_observation, reward, done, info = env.step(resolved_action.recommended_action)
        executed_action = info["executed_action"]
        executed_crop_action = CropAction(
            irrigation_mm=float(executed_action["irrigation_mm"]),
            nitrogen_kg_ha=float(executed_action["nitrogen_kg_ha"]),
        )
        transitions.append(
            StepwiseEpisodeTransition(
                decision_date=observation.decision_date,
                state=observation.state,
                next_state=next_observation.state,
                action=executed_crop_action,
                reward=float(reward),
                done=bool(done),
                action_mode=resolved_action.action_mode,
                control_mode=resolved_action.control_mode,
                action_id=resolved_action.recommended_action_id,
                irrigation_gate=resolved_action.irrigation_gate,
                nitrogen_gate=resolved_action.nitrogen_gate,
                irrigation_max_mm=resolved_action.irrigation_max_mm,
                nitrogen_max_kg_ha=resolved_action.nitrogen_max_kg_ha,
                action_family=resolved_action.action_family,
                action_mask=list(observation.discrete_action_mask.mask),
                legal_action_ids=list(observation.discrete_action_mask.legal_action_ids),
                observation_features=features,
                sequence_features=[list(token) for token in current_sequence],
                sequence_length=len(current_sequence),
                value_estimate=float(decision.value_estimate),
                log_prob=float(decision.log_prob),
                info={
                    **dict(info),
                    **dict(decision.metadata),
                    "recommended_action": resolved_action.recommended_action.to_dict(),
                    "recommended_action_mode": resolved_action.action_mode,
                    "recommended_control_mode": resolved_action.control_mode,
                    "recommended_action_family": resolved_action.action_family,
                },
            )
        )
        total_reward += float(reward)
        previous_feedback = StepwiseHistoryFeedback(
            action_mode=resolved_action.action_mode,
            control_mode=resolved_action.control_mode,
            recommended_action_id=resolved_action.recommended_action_id,
            recommended_irrigation_gate=resolved_action.irrigation_gate,
            recommended_nitrogen_gate=resolved_action.nitrogen_gate,
            recommended_irrigation_max_mm=resolved_action.irrigation_max_mm,
            recommended_nitrogen_max_kg_ha=resolved_action.nitrogen_max_kg_ha,
            recommended_action=resolved_action.to_crop_action(),
            executed_action=executed_crop_action,
            reward=float(reward),
        )
        sequence_history = current_sequence
        observation = next_observation

    return StepwiseRolloutEpisode(
        scenario_id=scenario.scenario_id,
        engine_name=scenario.engine_name,
        crop_name=scenario.crop_spec.crop_name,
        weather_regime=scenario.weather_regime,
        management_mode=scenario.management_mode,
        transitions=transitions,
        total_reward=round(total_reward, 6),
        final_outcome=env.final_outcome(),
        action_mode=episode_action_mode,
        control_mode=episode_control_mode,
        policy_id=policy_id,
        notes=list(notes or []),
    )


def summarize_rollout_episodes(episodes: list[StepwiseRolloutEpisode]) -> dict[str, Any]:
    if not episodes:
        return {
            "episode_count": 0,
            "scenario_count": 0,
            "transition_count": 0,
            "mean_total_reward": 0.0,
            "mean_decision_count": 0.0,
            "mean_sequence_length": 0.0,
            "max_sequence_length": 0,
        }
    sequence_lengths = [step.sequence_length for episode in episodes for step in episode.transitions]
    return {
        "episode_count": len(episodes),
        "scenario_count": len({episode.scenario_id for episode in episodes}),
        "transition_count": sum(len(episode.transitions) for episode in episodes),
        "mean_total_reward": round(sum(episode.total_reward for episode in episodes) / len(episodes), 6),
        "mean_decision_count": round(sum(episode.decision_count for episode in episodes) / len(episodes), 3),
        "mean_sequence_length": round(sum(sequence_lengths) / max(1, len(sequence_lengths)), 3),
        "max_sequence_length": max(sequence_lengths, default=0),
    }


def compute_discounted_returns(
    rewards: list[float],
    dones: list[bool],
    *,
    gamma: float = 0.99,
    bootstrap_value: float = 0.0,
) -> list[float]:
    returns = [0.0 for _ in rewards]
    running_return = bootstrap_value
    for index in range(len(rewards) - 1, -1, -1):
        mask = 0.0 if dones[index] else 1.0
        running_return = rewards[index] + gamma * running_return * mask
        returns[index] = running_return
    return returns


def compute_gae_advantages(
    rewards: list[float],
    values: list[float],
    dones: list[bool],
    *,
    gamma: float = 0.99,
    gae_lambda: float = 0.95,
    bootstrap_value: float = 0.0,
) -> tuple[list[float], list[float]]:
    if len(rewards) != len(values) or len(rewards) != len(dones):
        raise ValueError("rewards, values, and dones must have the same length.")
    advantages = [0.0 for _ in rewards]
    returns = [0.0 for _ in rewards]
    next_advantage = 0.0
    next_value = bootstrap_value
    for index in range(len(rewards) - 1, -1, -1):
        mask = 0.0 if dones[index] else 1.0
        delta = rewards[index] + gamma * next_value * mask - values[index]
        next_advantage = delta + gamma * gae_lambda * mask * next_advantage
        advantages[index] = next_advantage
        returns[index] = next_advantage + values[index]
        next_value = values[index]
    return advantages, returns


def build_stepwise_baseline_trajectory(
    scenario: SimulationScenario,
    baseline_name: str = "heuristic",
) -> Trajectory:
    if baseline_name == "heuristic":
        policy = build_heuristic_stepwise_policy(scenario)
    elif baseline_name == "heuristic_legacy":
        policy = build_heuristic_legacy_stepwise_policy(scenario)
    elif baseline_name == "literature":
        policy = build_literature_stepwise_policy(scenario)
    elif baseline_name == "equal":
        policy = build_equal_allocation_stepwise_policy(scenario)
    else:
        raise ValueError(f"Unsupported stepwise baseline: {baseline_name}")
    return rollout_stepwise_policy(scenario, policy)


try:
    import torch
    from torch import nn
    from torch.distributions import Bernoulli, Beta, Categorical
    from torch.nn import functional as F

    TORCH_AVAILABLE = True

    def collate_sequence_features(
        sequence_features: list[list[list[float]]],
        *,
        device: torch.device | str,
    ) -> tuple[torch.Tensor, torch.Tensor]:
        if not sequence_features:
            raise ValueError("At least one sequence is required.")
        max_length = max(len(sequence) for sequence in sequence_features)
        sequences = torch.zeros(
            (len(sequence_features), max_length, STEPWISE_SEQUENCE_FEATURE_DIM),
            dtype=torch.float32,
            device=device,
        )
        padding_mask = torch.ones((len(sequence_features), max_length), dtype=torch.bool, device=device)
        for row_index, sequence in enumerate(sequence_features):
            length = len(sequence)
            sequences[row_index, :length, :] = torch.tensor(sequence, dtype=torch.float32, device=device)
            padding_mask[row_index, :length] = False
        return sequences, padding_mask


    def _last_valid_hidden(hidden: torch.Tensor, padding_mask: torch.Tensor | None) -> torch.Tensor:
        if padding_mask is None:
            return hidden[:, -1, :]
        valid_lengths = (~padding_mask).sum(dim=1).clamp(min=1)
        gather_index = (valid_lengths - 1).view(-1, 1, 1).expand(-1, 1, hidden.size(-1))
        return torch.gather(hidden, 1, gather_index).squeeze(1)


    class StepwisePPOActorCritic(nn.Module):
        action_mode = "discrete"
        control_mode = "joint"

        def __init__(
            self,
            input_dim: int = STEPWISE_SEQUENCE_FEATURE_DIM,
            hidden_dim: int = 128,
            action_dim: int = STEPWISE_DISCRETE_ACTION_DIM,
        ) -> None:
            super().__init__()
            self.backbone = nn.Sequential(
                nn.Linear(input_dim, hidden_dim),
                nn.Tanh(),
                nn.Linear(hidden_dim, hidden_dim),
                nn.Tanh(),
            )
            self.policy_head = nn.Linear(hidden_dim, action_dim)
            self.value_head = nn.Linear(hidden_dim, 1)

        def forward(
            self,
            sequences: torch.Tensor,
            padding_mask: torch.Tensor | None = None,
        ) -> tuple[torch.Tensor, torch.Tensor]:
            last_hidden = _last_valid_hidden(sequences, padding_mask)
            hidden = self.backbone(last_hidden)
            return self.policy_head(hidden), self.value_head(hidden).squeeze(-1)


    class StepwiseTransformerActorCritic(nn.Module):
        action_mode = "discrete"
        control_mode = "joint"

        def __init__(
            self,
            input_dim: int = STEPWISE_SEQUENCE_FEATURE_DIM,
            hidden_dim: int = 128,
            action_dim: int = STEPWISE_DISCRETE_ACTION_DIM,
            num_heads: int = 4,
            num_layers: int = 2,
            dropout: float = 0.1,
            max_sequence_length: int = 64,
        ) -> None:
            super().__init__()
            self.max_sequence_length = max_sequence_length
            self.input_projection = nn.Linear(input_dim, hidden_dim)
            self.position_embedding = nn.Embedding(max_sequence_length, hidden_dim)
            encoder_layer = nn.TransformerEncoderLayer(
                d_model=hidden_dim,
                nhead=num_heads,
                batch_first=True,
                dim_feedforward=hidden_dim * 4,
                dropout=dropout,
                activation="gelu",
            )
            self.encoder = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)
            self.norm = nn.LayerNorm(hidden_dim)
            self.policy_head = nn.Linear(hidden_dim, action_dim)
            self.value_head = nn.Linear(hidden_dim, 1)

        def forward(
            self,
            sequences: torch.Tensor,
            padding_mask: torch.Tensor | None = None,
        ) -> tuple[torch.Tensor, torch.Tensor]:
            sequence_length = sequences.size(1)
            if sequence_length > self.max_sequence_length:
                raise RuntimeError(
                    f"Sequence length {sequence_length} exceeds transformer max_sequence_length "
                    f"{self.max_sequence_length}."
                )
            positions = torch.arange(sequence_length, device=sequences.device).unsqueeze(0)
            hidden = self.input_projection(sequences) + self.position_embedding(positions)
            causal_mask = torch.triu(
                torch.ones((sequence_length, sequence_length), device=sequences.device, dtype=torch.bool),
                diagonal=1,
            )
            encoded = self.encoder(hidden, mask=causal_mask, src_key_padding_mask=padding_mask)
            last_hidden = self.norm(_last_valid_hidden(encoded, padding_mask))
            return self.policy_head(last_hidden), self.value_head(last_hidden).squeeze(-1)


    class StepwiseGatedContinuousActorCritic(nn.Module):
        action_mode = "continuous"

        def __init__(
            self,
            input_dim: int = STEPWISE_SEQUENCE_FEATURE_DIM,
            hidden_dim: int = 128,
            control_mode: str = "joint",
        ) -> None:
            super().__init__()
            self.control_mode = _canonicalize_control_mode(control_mode)
            self.backbone = nn.Sequential(
                nn.Linear(input_dim, hidden_dim),
                nn.Tanh(),
                nn.Linear(hidden_dim, hidden_dim),
                nn.Tanh(),
            )
            self.gate_head = nn.Linear(hidden_dim, STEPWISE_CONTINUOUS_ACTION_DIM)
            self.amount_alpha_head = nn.Linear(hidden_dim, STEPWISE_CONTINUOUS_ACTION_DIM)
            self.amount_beta_head = nn.Linear(hidden_dim, STEPWISE_CONTINUOUS_ACTION_DIM)
            self.value_head = nn.Linear(hidden_dim, 1)

        def forward(
            self,
            sequences: torch.Tensor,
            padding_mask: torch.Tensor | None = None,
        ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
            last_hidden = _last_valid_hidden(sequences, padding_mask)
            hidden = self.backbone(last_hidden)
            gate_logits = self.gate_head(hidden)
            amount_alpha = F.softplus(self.amount_alpha_head(hidden)) + 1.0
            amount_beta = F.softplus(self.amount_beta_head(hidden)) + 1.0
            values = self.value_head(hidden).squeeze(-1)
            return gate_logits, amount_alpha, amount_beta, values


    class StepwiseGatedContinuousTransformerActorCritic(nn.Module):
        action_mode = "continuous"

        def __init__(
            self,
            input_dim: int = STEPWISE_SEQUENCE_FEATURE_DIM,
            hidden_dim: int = 128,
            control_mode: str = "joint",
            num_heads: int = 4,
            num_layers: int = 2,
            dropout: float = 0.1,
            max_sequence_length: int = 64,
        ) -> None:
            super().__init__()
            self.control_mode = _canonicalize_control_mode(control_mode)
            self.max_sequence_length = max_sequence_length
            self.input_projection = nn.Linear(input_dim, hidden_dim)
            self.position_embedding = nn.Embedding(max_sequence_length, hidden_dim)
            encoder_layer = nn.TransformerEncoderLayer(
                d_model=hidden_dim,
                nhead=num_heads,
                batch_first=True,
                dim_feedforward=hidden_dim * 4,
                dropout=dropout,
                activation="gelu",
            )
            self.encoder = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)
            self.norm = nn.LayerNorm(hidden_dim)
            self.gate_head = nn.Linear(hidden_dim, STEPWISE_CONTINUOUS_ACTION_DIM)
            self.amount_alpha_head = nn.Linear(hidden_dim, STEPWISE_CONTINUOUS_ACTION_DIM)
            self.amount_beta_head = nn.Linear(hidden_dim, STEPWISE_CONTINUOUS_ACTION_DIM)
            self.value_head = nn.Linear(hidden_dim, 1)

        def forward(
            self,
            sequences: torch.Tensor,
            padding_mask: torch.Tensor | None = None,
        ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
            sequence_length = sequences.size(1)
            if sequence_length > self.max_sequence_length:
                raise RuntimeError(
                    f"Sequence length {sequence_length} exceeds transformer max_sequence_length "
                    f"{self.max_sequence_length}."
                )
            positions = torch.arange(sequence_length, device=sequences.device).unsqueeze(0)
            hidden = self.input_projection(sequences) + self.position_embedding(positions)
            causal_mask = torch.triu(
                torch.ones((sequence_length, sequence_length), device=sequences.device, dtype=torch.bool),
                diagonal=1,
            )
            encoded = self.encoder(hidden, mask=causal_mask, src_key_padding_mask=padding_mask)
            last_hidden = self.norm(_last_valid_hidden(encoded, padding_mask))
            gate_logits = self.gate_head(last_hidden)
            amount_alpha = F.softplus(self.amount_alpha_head(last_hidden)) + 1.0
            amount_beta = F.softplus(self.amount_beta_head(last_hidden)) + 1.0
            values = self.value_head(last_hidden).squeeze(-1)
            return gate_logits, amount_alpha, amount_beta, values


    @dataclass(slots=True)
    class PPORolloutBatch:
        action_mode: str
        control_mode: str
        sequences: torch.Tensor
        padding_mask: torch.Tensor
        old_log_probs: torch.Tensor
        old_values: torch.Tensor
        advantages: torch.Tensor
        returns: torch.Tensor
        action_masks: torch.Tensor | None = None
        actions: torch.Tensor | None = None
        gate_actions: torch.Tensor | None = None
        amount_actions: torch.Tensor | None = None
        amount_maxima: torch.Tensor | None = None

        @property
        def size(self) -> int:
            if self.actions is not None:
                return int(self.actions.size(0))
            if self.gate_actions is not None:
                return int(self.gate_actions.size(0))
            return 0


    def _mean_realized_activity_ratio(
        gate_actions: torch.Tensor,
        amount_actions: torch.Tensor,
        amount_maxima: torch.Tensor,
        *,
        control_mode: str,
    ) -> torch.Tensor:
        control_mask = _control_mode_tensor(
            control_mode,
            device=gate_actions.device,
            batch_size=gate_actions.size(0),
        )
        legal_mask = (amount_maxima > 1e-9).to(dtype=torch.float32)
        active_mask = control_mask * legal_mask
        normalized_amounts = torch.where(
            amount_maxima > 1e-9,
            amount_actions / amount_maxima.clamp(min=1e-6),
            torch.zeros_like(amount_actions),
        )
        realized_activity = gate_actions.to(dtype=torch.float32) * normalized_amounts * active_mask
        active_counts = active_mask.sum(dim=0).clamp(min=1.0)
        return realized_activity.sum(dim=0) / active_counts


    def _mean_expected_activity_ratio(
        gate_logits: torch.Tensor,
        amount_alpha: torch.Tensor,
        amount_beta: torch.Tensor,
        amount_maxima: torch.Tensor,
        *,
        control_mode: str,
    ) -> torch.Tensor:
        control_mask = _control_mode_tensor(
            control_mode,
            device=gate_logits.device,
            batch_size=gate_logits.size(0),
        )
        legal_mask = (amount_maxima > 1e-9).to(dtype=torch.float32)
        active_mask = control_mask * legal_mask
        expected_gate_open = torch.sigmoid(gate_logits) * active_mask
        expected_amount_ratio = (amount_alpha / (amount_alpha + amount_beta)).clamp(min=1e-6, max=1.0 - 1.0e-6)
        expected_activity = expected_gate_open * expected_amount_ratio
        active_counts = active_mask.sum(dim=0).clamp(min=1.0)
        return expected_activity.sum(dim=0) / active_counts


    def _mean_greedy_activity_ratio(
        gate_logits: torch.Tensor,
        amount_alpha: torch.Tensor,
        amount_beta: torch.Tensor,
        amount_maxima: torch.Tensor,
        *,
        control_mode: str,
    ) -> torch.Tensor:
        control_mask = _control_mode_tensor(
            control_mode,
            device=gate_logits.device,
            batch_size=gate_logits.size(0),
        )
        legal_mask = (amount_maxima > 1e-9).to(dtype=torch.float32)
        active_mask = control_mask * legal_mask
        greedy_gate_open = (torch.sigmoid(gate_logits) >= 0.5).to(dtype=torch.float32) * active_mask
        greedy_amount_ratio = (amount_alpha / (amount_alpha + amount_beta)).clamp(min=1e-6, max=1.0 - 1.0e-6)
        greedy_activity = greedy_gate_open * greedy_amount_ratio
        active_counts = active_mask.sum(dim=0).clamp(min=1.0)
        return greedy_activity.sum(dim=0) / active_counts


    def _mean_activity_shortfall_penalty(
        gate_logits: torch.Tensor,
        amount_alpha: torch.Tensor,
        amount_beta: torch.Tensor,
        amount_maxima: torch.Tensor,
        *,
        control_mode: str,
        regularizer: dict[str, float] | None,
    ) -> tuple[torch.Tensor, dict[str, float]]:
        device = gate_logits.device
        zero = torch.zeros((), dtype=torch.float32, device=device)
        config = regularizer or {}
        if not bool(config.get("enabled", False)):
            return zero, {
                "enabled": False,
                "penalty": 0.0,
            }

        control_mask = _control_mode_tensor(control_mode, device=device, batch_size=gate_logits.size(0))
        legal_mask = (amount_maxima > 1e-9).to(dtype=torch.float32)
        active_mask = control_mask * legal_mask
        mean_expected_activity_ratio = _mean_expected_activity_ratio(
            gate_logits,
            amount_alpha,
            amount_beta,
            amount_maxima,
            control_mode=control_mode,
        )

        minimum_irrigation_ratio = float(config.get("minimum_expected_irrigation_ratio", 0.0))
        minimum_nitrogen_ratio = float(config.get("minimum_expected_nitrogen_ratio", 0.0))
        irrigation_penalty_weight = float(config.get("irrigation_penalty_weight", 0.0))
        nitrogen_penalty_weight = float(config.get("nitrogen_penalty_weight", 0.0))

        channel_targets = (
            minimum_irrigation_ratio,
            minimum_nitrogen_ratio,
        )
        channel_weights = (
            irrigation_penalty_weight,
            nitrogen_penalty_weight,
        )
        channel_names = ("irrigation", "nitrogen")
        penalty = zero
        metrics: dict[str, float] = {
            "enabled": True,
            "penalty": 0.0,
        }

        for index, (name, target_ratio, penalty_weight) in enumerate(zip(channel_names, channel_targets, channel_weights)):
            active_count = active_mask[:, index].sum()
            if float(active_count.item()) <= 1e-9:
                metrics[f"{name}_expected_activity_ratio"] = 0.0
                metrics[f"{name}_activity_shortfall"] = 0.0
                continue
            mean_expected_ratio = mean_expected_activity_ratio[index]
            shortfall = torch.clamp(torch.tensor(target_ratio, dtype=torch.float32, device=device) - mean_expected_ratio, min=0.0)
            penalty = penalty + shortfall * float(penalty_weight)
            metrics[f"{name}_expected_activity_ratio"] = round(float(mean_expected_ratio.item()), 6)
            metrics[f"{name}_activity_shortfall"] = round(float(shortfall.item()), 6)

        metrics["penalty"] = round(float(penalty.item()), 6)
        return penalty, metrics


    def _mean_behavior_anchor_penalty(
        gate_logits: torch.Tensor,
        amount_alpha: torch.Tensor,
        amount_beta: torch.Tensor,
        gate_actions: torch.Tensor,
        amount_actions: torch.Tensor,
        amount_maxima: torch.Tensor,
        *,
        control_mode: str,
        anchor: dict[str, float] | None,
    ) -> tuple[torch.Tensor, dict[str, float]]:
        device = gate_logits.device
        zero = torch.zeros((), dtype=torch.float32, device=device)
        config = anchor or {}
        if not bool(config.get("enabled", False)):
            return zero, {
                "enabled": False,
                "penalty": 0.0,
            }

        control_mask = _control_mode_tensor(
            control_mode,
            device=device,
            batch_size=gate_logits.size(0),
        )
        legal_mask = (amount_maxima > 1e-9).to(dtype=torch.float32)
        active_mask = control_mask * legal_mask
        expected_gate_open = torch.sigmoid(gate_logits) * active_mask
        expected_amount_ratio = (amount_alpha / (amount_alpha + amount_beta)).clamp(min=1e-6, max=1.0 - 1e-6)
        expected_normalized_activity = expected_gate_open * expected_amount_ratio
        active_counts = active_mask.sum(dim=0).clamp(min=1.0)
        mean_expected_ratio = expected_normalized_activity.sum(dim=0) / active_counts
        mean_rollout_ratio = _mean_realized_activity_ratio(
            gate_actions,
            amount_actions,
            amount_maxima,
            control_mode=control_mode,
        )

        retention_ratio = float(config.get("retention_ratio", 1.0))
        minimum_irrigation_ratio = float(config.get("minimum_anchor_irrigation_ratio", 0.0))
        minimum_nitrogen_ratio = float(config.get("minimum_anchor_nitrogen_ratio", 0.0))
        irrigation_penalty_weight = float(config.get("irrigation_penalty_weight", 0.0))
        nitrogen_penalty_weight = float(config.get("nitrogen_penalty_weight", 0.0))

        channel_names = ("irrigation", "nitrogen")
        minimum_targets = (
            minimum_irrigation_ratio,
            minimum_nitrogen_ratio,
        )
        penalty_weights = (
            irrigation_penalty_weight,
            nitrogen_penalty_weight,
        )
        penalty = zero
        metrics: dict[str, float] = {
            "enabled": True,
            "penalty": 0.0,
            "retention_ratio": retention_ratio,
        }

        for index, (name, minimum_target, penalty_weight) in enumerate(
            zip(channel_names, minimum_targets, penalty_weights)
        ):
            if float(active_mask[:, index].sum().item()) <= 1e-9:
                metrics[f"{name}_anchor_target_ratio"] = 0.0
                metrics[f"{name}_rollout_activity_ratio"] = 0.0
                metrics[f"{name}_expected_activity_ratio"] = 0.0
                metrics[f"{name}_anchor_shortfall"] = 0.0
                continue
            rollout_target = float(mean_rollout_ratio[index].item()) * retention_ratio
            anchor_target = max(minimum_target, rollout_target)
            shortfall = torch.clamp(
                torch.tensor(anchor_target, dtype=torch.float32, device=device) - mean_expected_ratio[index],
                min=0.0,
            )
            penalty = penalty + shortfall * penalty_weight
            metrics[f"{name}_anchor_target_ratio"] = round(anchor_target, 6)
            metrics[f"{name}_rollout_activity_ratio"] = round(float(mean_rollout_ratio[index].item()), 6)
            metrics[f"{name}_expected_activity_ratio"] = round(float(mean_expected_ratio[index].item()), 6)
            metrics[f"{name}_anchor_shortfall"] = round(float(shortfall.item()), 6)

        metrics["penalty"] = round(float(penalty.item()), 6)
        return penalty, metrics


    def _mean_policy_anchor_penalty(
        gate_logits: torch.Tensor,
        amount_alpha: torch.Tensor,
        amount_beta: torch.Tensor,
        gate_actions: torch.Tensor,
        amount_actions: torch.Tensor,
        amount_maxima: torch.Tensor,
        *,
        control_mode: str,
        anchor: dict[str, float] | None,
        advantages: torch.Tensor | None = None,
    ) -> tuple[torch.Tensor, dict[str, float]]:
        device = gate_logits.device
        zero = torch.zeros((), dtype=torch.float32, device=device)
        config = anchor or {}
        if not bool(config.get("enabled", False)):
            return zero, {
                "enabled": False,
                "penalty": 0.0,
            }

        control_mask = _control_mode_tensor(
            control_mode,
            device=device,
            batch_size=gate_logits.size(0),
        )
        legal_mask = (amount_maxima > 1e-9).to(dtype=torch.float32)
        active_mask = control_mask * legal_mask
        gate_targets = gate_actions.to(dtype=torch.float32) * active_mask
        expected_gate_open = torch.sigmoid(gate_logits) * active_mask
        expected_amount_ratio = (amount_alpha / (amount_alpha + amount_beta)).clamp(min=1e-6, max=1.0 - 1e-6)
        rollout_amount_ratio = torch.where(
            amount_maxima > 1e-9,
            amount_actions / amount_maxima.clamp(min=1e-6),
            torch.zeros_like(amount_actions),
        ).clamp(min=0.0, max=1.0)

        gate_weight = float(config.get("gate_penalty_weight", 0.0))
        irrigation_amount_weight = float(config.get("irrigation_amount_penalty_weight", 0.0))
        nitrogen_amount_weight = float(config.get("nitrogen_amount_penalty_weight", 0.0))
        positive_advantage_scale = float(config.get("positive_advantage_scale", 0.0))
        negative_advantage_scale = float(config.get("negative_advantage_scale", 1.0))
        minimum_sample_weight = float(config.get("minimum_sample_weight", 1.0))

        sample_weights = torch.ones(gate_logits.size(0), dtype=torch.float32, device=device)
        positive_advantage_fraction = 0.0
        mean_positive_advantage_weight = 0.0
        mean_negative_advantage_weight = 0.0
        if advantages is not None:
            normalized_advantages = advantages.to(dtype=torch.float32, device=device)
            positive_mask = normalized_advantages > 0.0
            negative_mask = ~positive_mask
            positive_advantage_fraction = float(positive_mask.to(dtype=torch.float32).mean().item())
            sample_weights = torch.full_like(normalized_advantages, minimum_sample_weight)
            if bool(positive_mask.any()):
                positive_advantages = normalized_advantages[positive_mask]
                positive_scale_denominator = positive_advantages.mean().clamp(min=1e-6)
                sample_weights[positive_mask] = minimum_sample_weight + (
                    positive_advantages / positive_scale_denominator
                ) * positive_advantage_scale
                mean_positive_advantage_weight = float(sample_weights[positive_mask].mean().item())
            if bool(negative_mask.any()):
                sample_weights[negative_mask] = minimum_sample_weight * negative_advantage_scale
                mean_negative_advantage_weight = float(sample_weights[negative_mask].mean().item())
        weighted_active_mask = active_mask * sample_weights.unsqueeze(1)

        gate_denominator = weighted_active_mask.sum().clamp(min=1.0)
        gate_bce = (
            F.binary_cross_entropy_with_logits(gate_logits, gate_targets, reduction="none") * weighted_active_mask
        ).sum() / gate_denominator
        gate_match = (
            (1.0 - torch.abs(expected_gate_open - gate_targets)) * weighted_active_mask
        ).sum() / gate_denominator

        channel_amount_weights = (
            irrigation_amount_weight,
            nitrogen_amount_weight,
        )
        channel_names = ("irrigation", "nitrogen")
        penalty = gate_bce * gate_weight
        metrics: dict[str, float] = {
            "enabled": True,
            "penalty": 0.0,
            "gate_penalty": round(float((gate_bce * gate_weight).item()), 6),
            "gate_match_ratio": round(float(gate_match.item()), 6),
            "positive_advantage_fraction": round(positive_advantage_fraction, 6),
            "mean_positive_advantage_anchor_weight": round(mean_positive_advantage_weight, 6),
            "mean_negative_advantage_anchor_weight": round(mean_negative_advantage_weight, 6),
        }

        for index, (name, amount_weight) in enumerate(zip(channel_names, channel_amount_weights)):
            channel_mask = gate_targets[:, index] * sample_weights
            active_count = channel_mask.sum()
            if float(active_count.item()) <= 1e-9:
                metrics[f"{name}_expected_amount_ratio"] = 0.0
                metrics[f"{name}_rollout_amount_ratio"] = 0.0
                metrics[f"{name}_amount_abs_error"] = 0.0
                metrics[f"{name}_amount_penalty"] = 0.0
                continue
            abs_error = torch.abs(expected_amount_ratio[:, index] - rollout_amount_ratio[:, index])
            mean_abs_error = (abs_error * channel_mask).sum() / active_count
            channel_penalty = mean_abs_error * amount_weight
            penalty = penalty + channel_penalty
            metrics[f"{name}_expected_amount_ratio"] = round(
                float((expected_amount_ratio[:, index] * channel_mask).sum().div(active_count).item()),
                6,
            )
            metrics[f"{name}_rollout_amount_ratio"] = round(
                float((rollout_amount_ratio[:, index] * channel_mask).sum().div(active_count).item()),
                6,
            )
            metrics[f"{name}_amount_abs_error"] = round(float(mean_abs_error.item()), 6)
            metrics[f"{name}_amount_penalty"] = round(float(channel_penalty.item()), 6)

        metrics["penalty"] = round(float(penalty.item()), 6)
        return penalty, metrics


    def _mean_advantage_activity_anchor_penalty(
        gate_logits: torch.Tensor,
        amount_alpha: torch.Tensor,
        amount_beta: torch.Tensor,
        gate_actions: torch.Tensor,
        amount_actions: torch.Tensor,
        amount_maxima: torch.Tensor,
        *,
        control_mode: str,
        anchor: dict[str, float] | None,
        advantages: torch.Tensor | None = None,
    ) -> tuple[torch.Tensor, dict[str, float]]:
        device = gate_logits.device
        zero = torch.zeros((), dtype=torch.float32, device=device)
        config = anchor or {}
        if not bool(config.get("enabled", False)) or advantages is None:
            return zero, {
                "enabled": False,
                "penalty": 0.0,
            }

        normalized_advantages = advantages.to(dtype=torch.float32, device=device)
        positive_threshold = float(config.get("positive_advantage_threshold", 0.0))
        positive_mask = normalized_advantages > positive_threshold
        positive_fraction = float(positive_mask.to(dtype=torch.float32).mean().item())
        if not bool(positive_mask.any()):
            return zero, {
                "enabled": True,
                "penalty": 0.0,
                "positive_advantage_fraction": round(positive_fraction, 6),
            }

        control_mask = _control_mode_tensor(
            control_mode,
            device=device,
            batch_size=gate_logits.size(0),
        )
        legal_mask = (amount_maxima > 1e-9).to(dtype=torch.float32)
        active_mask = control_mask * legal_mask
        positive_active_mask = active_mask * positive_mask.to(dtype=torch.float32).unsqueeze(1)
        expected_gate_open = torch.sigmoid(gate_logits) * active_mask
        expected_amount_ratio = (amount_alpha / (amount_alpha + amount_beta)).clamp(min=1e-6, max=1.0 - 1e-6)
        expected_normalized_activity = expected_gate_open * expected_amount_ratio
        rollout_amount_ratio = torch.where(
            amount_maxima > 1e-9,
            amount_actions / amount_maxima.clamp(min=1e-6),
            torch.zeros_like(amount_actions),
        ).clamp(min=0.0, max=1.0)
        rollout_normalized_activity = gate_actions.to(dtype=torch.float32) * rollout_amount_ratio * active_mask

        retention_ratio = float(config.get("retention_ratio", 1.0))
        minimum_irrigation_ratio = float(config.get("minimum_anchor_irrigation_ratio", 0.0))
        minimum_nitrogen_ratio = float(config.get("minimum_anchor_nitrogen_ratio", 0.0))
        irrigation_penalty_weight = float(config.get("irrigation_penalty_weight", 0.0))
        nitrogen_penalty_weight = float(config.get("nitrogen_penalty_weight", 0.0))

        channel_names = ("irrigation", "nitrogen")
        minimum_targets = (
            minimum_irrigation_ratio,
            minimum_nitrogen_ratio,
        )
        penalty_weights = (
            irrigation_penalty_weight,
            nitrogen_penalty_weight,
        )
        penalty = zero
        metrics: dict[str, float] = {
            "enabled": True,
            "penalty": 0.0,
            "retention_ratio": retention_ratio,
            "positive_advantage_fraction": round(positive_fraction, 6),
        }

        for index, (name, minimum_target, penalty_weight) in enumerate(
            zip(channel_names, minimum_targets, penalty_weights)
        ):
            active_count = positive_active_mask[:, index].sum()
            if float(active_count.item()) <= 1e-9:
                metrics[f"{name}_positive_anchor_target_ratio"] = 0.0
                metrics[f"{name}_positive_rollout_activity_ratio"] = 0.0
                metrics[f"{name}_positive_expected_activity_ratio"] = 0.0
                metrics[f"{name}_positive_anchor_shortfall"] = 0.0
                continue
            mean_expected_ratio = (
                expected_normalized_activity[:, index] * positive_active_mask[:, index]
            ).sum() / active_count
            mean_rollout_ratio = (
                rollout_normalized_activity[:, index] * positive_active_mask[:, index]
            ).sum() / active_count
            rollout_target = float(mean_rollout_ratio.item()) * retention_ratio
            anchor_target = max(minimum_target, rollout_target)
            shortfall = torch.clamp(
                torch.tensor(anchor_target, dtype=torch.float32, device=device) - mean_expected_ratio,
                min=0.0,
            )
            penalty = penalty + shortfall * penalty_weight
            metrics[f"{name}_positive_anchor_target_ratio"] = round(anchor_target, 6)
            metrics[f"{name}_positive_rollout_activity_ratio"] = round(float(mean_rollout_ratio.item()), 6)
            metrics[f"{name}_positive_expected_activity_ratio"] = round(float(mean_expected_ratio.item()), 6)
            metrics[f"{name}_positive_anchor_shortfall"] = round(float(shortfall.item()), 6)

        metrics["penalty"] = round(float(penalty.item()), 6)
        return penalty, metrics


    def _apply_auxiliary_penalty_budget(
        policy_loss: torch.Tensor,
        value_loss: torch.Tensor,
        entropy: torch.Tensor,
        auxiliary_penalties: dict[str, torch.Tensor],
        *,
        value_coef: float,
        entropy_coef: float,
        budget: dict[str, float] | None,
    ) -> tuple[dict[str, torch.Tensor], dict[str, float | bool]]:
        device = policy_loss.device
        zero = torch.zeros((), dtype=torch.float32, device=device)
        config = budget or {}
        total_penalty = zero
        for penalty in auxiliary_penalties.values():
            total_penalty = total_penalty + penalty
        if not bool(config.get("enabled", False)):
            return auxiliary_penalties, {
                "enabled": False,
                "raw_penalty": round(float(total_penalty.item()), 6),
                "applied_penalty": round(float(total_penalty.item()), 6),
                "penalty_scale": 1.0,
                "max_allowed_penalty": 0.0,
                "core_loss_magnitude": 0.0,
            }

        minimum_core_loss = float(config.get("minimum_core_loss", 0.0))
        max_auxiliary_to_core_ratio = float(config.get("max_auxiliary_to_core_ratio", 1.0))
        include_entropy_magnitude = bool(config.get("include_entropy_magnitude", True))
        core_loss_magnitude = torch.abs(policy_loss) + value_loss * float(value_coef)
        if include_entropy_magnitude:
            core_loss_magnitude = core_loss_magnitude + torch.abs(entropy) * float(entropy_coef)
        core_loss_magnitude = torch.clamp(
            core_loss_magnitude,
            min=torch.tensor(minimum_core_loss, dtype=torch.float32, device=device),
        )
        max_allowed_penalty = core_loss_magnitude * max_auxiliary_to_core_ratio
        scale = torch.ones((), dtype=torch.float32, device=device)
        if float(total_penalty.item()) > 1e-9 and float(max_allowed_penalty.item()) < float(total_penalty.item()):
            scale = max_allowed_penalty / total_penalty
        scaled_penalties = {name: penalty * scale for name, penalty in auxiliary_penalties.items()}
        applied_penalty = total_penalty * scale
        return scaled_penalties, {
            "enabled": True,
            "raw_penalty": round(float(total_penalty.item()), 6),
            "applied_penalty": round(float(applied_penalty.item()), 6),
            "penalty_scale": round(float(scale.item()), 6),
            "max_allowed_penalty": round(float(max_allowed_penalty.item()), 6),
            "core_loss_magnitude": round(float(core_loss_magnitude.item()), 6),
        }


    def _evaluate_rollout_activity_admission(
        gate_actions: torch.Tensor,
        amount_actions: torch.Tensor,
        amount_maxima: torch.Tensor,
        *,
        control_mode: str,
        admission: dict[str, float] | None,
        gate_logits: torch.Tensor | None = None,
        amount_alpha: torch.Tensor | None = None,
        amount_beta: torch.Tensor | None = None,
    ) -> dict[str, float | bool]:
        config = admission or {}
        if not bool(config.get("enabled", False)):
            return {
                "enabled": False,
                "admitted": True,
                "penalty": 0.0,
                "shortfall": 0.0,
                "minimum_enabled_activity_ratio": 0.0,
            }

        mean_rollout_ratio = _mean_realized_activity_ratio(
            gate_actions,
            amount_actions,
            amount_maxima,
            control_mode=control_mode,
        )
        irrigation_enabled, nitrogen_enabled = _control_mode_flags(control_mode)
        minimum_irrigation_ratio = float(config.get("minimum_irrigation_ratio", 0.0))
        minimum_nitrogen_ratio = float(config.get("minimum_nitrogen_ratio", 0.0))
        irrigation_penalty_weight = float(config.get("irrigation_penalty_weight", 0.0))
        nitrogen_penalty_weight = float(config.get("nitrogen_penalty_weight", 0.0))
        enforce_expected_activity = bool(config.get("enforce_expected_activity", False))
        expected_activity_retention_ratio = float(config.get("expected_activity_retention_ratio", 1.0))
        minimum_expected_irrigation_ratio = float(config.get("minimum_expected_irrigation_ratio", minimum_irrigation_ratio))
        minimum_expected_nitrogen_ratio = float(config.get("minimum_expected_nitrogen_ratio", minimum_nitrogen_ratio))
        expected_irrigation_penalty_weight = float(
            config.get("expected_irrigation_penalty_weight", irrigation_penalty_weight)
        )
        expected_nitrogen_penalty_weight = float(
            config.get("expected_nitrogen_penalty_weight", nitrogen_penalty_weight)
        )
        enforce_greedy_activity = bool(config.get("enforce_greedy_activity", False))
        greedy_activity_retention_ratio = float(
            config.get("greedy_activity_retention_ratio", expected_activity_retention_ratio)
        )
        minimum_greedy_irrigation_ratio = float(
            config.get("minimum_greedy_irrigation_ratio", minimum_expected_irrigation_ratio)
        )
        minimum_greedy_nitrogen_ratio = float(
            config.get("minimum_greedy_nitrogen_ratio", minimum_expected_nitrogen_ratio)
        )
        greedy_irrigation_penalty_weight = float(
            config.get("greedy_irrigation_penalty_weight", expected_irrigation_penalty_weight)
        )
        greedy_nitrogen_penalty_weight = float(
            config.get("greedy_nitrogen_penalty_weight", expected_nitrogen_penalty_weight)
        )
        hard_rejection_threshold = float(config.get("hard_rejection_threshold", 0.0))
        soft_penalty_weight = float(config.get("soft_penalty_weight", 0.0))
        soft_rollout_penalty_weight_scale = float(config.get("soft_rollout_penalty_weight_scale", 1.0))
        soft_expected_penalty_weight_scale = float(config.get("soft_expected_penalty_weight_scale", 1.0))
        soft_greedy_penalty_weight_scale = float(config.get("soft_greedy_penalty_weight_scale", 1.0))
        hard_rollout_penalty_weight_scale = float(config.get("hard_rollout_penalty_weight_scale", 1.0))
        hard_expected_penalty_weight_scale = float(config.get("hard_expected_penalty_weight_scale", 1.0))
        hard_greedy_penalty_weight_scale = float(config.get("hard_greedy_penalty_weight_scale", 1.0))
        mean_expected_ratio = None
        mean_greedy_ratio = None
        if (
            gate_logits is not None
            and amount_alpha is not None
            and amount_beta is not None
        ):
            mean_expected_ratio = _mean_expected_activity_ratio(
                gate_logits,
                amount_alpha,
                amount_beta,
                amount_maxima,
                control_mode=control_mode,
            )
            mean_greedy_ratio = _mean_greedy_activity_ratio(
                gate_logits,
                amount_alpha,
                amount_beta,
                amount_maxima,
                control_mode=control_mode,
            )
        shortfall = 0.0
        hard_shortfall = 0.0
        enabled_ratios: list[float] = []
        metrics: dict[str, float | bool] = {
            "enabled": True,
            "admitted": True,
            "penalty": 0.0,
            "shortfall": 0.0,
            "hard_shortfall": 0.0,
            "hard_rejection_threshold": round(hard_rejection_threshold, 6),
            "soft_penalty_weight": round(soft_penalty_weight, 6),
            "soft_rollout_penalty_weight_scale": round(soft_rollout_penalty_weight_scale, 6),
            "soft_expected_penalty_weight_scale": round(soft_expected_penalty_weight_scale, 6),
            "soft_greedy_penalty_weight_scale": round(soft_greedy_penalty_weight_scale, 6),
            "hard_rollout_penalty_weight_scale": round(hard_rollout_penalty_weight_scale, 6),
            "hard_expected_penalty_weight_scale": round(hard_expected_penalty_weight_scale, 6),
            "hard_greedy_penalty_weight_scale": round(hard_greedy_penalty_weight_scale, 6),
            "minimum_enabled_activity_ratio": 0.0,
            "expected_activity_enforced": enforce_expected_activity and mean_expected_ratio is not None,
            "greedy_activity_enforced": enforce_greedy_activity and mean_greedy_ratio is not None,
            "expected_activity_retention_ratio": round(expected_activity_retention_ratio, 6),
            "greedy_activity_retention_ratio": round(greedy_activity_retention_ratio, 6),
        }

        channel_specs = (
            (
                "irrigation",
                irrigation_enabled,
                minimum_irrigation_ratio,
                irrigation_penalty_weight,
                minimum_expected_irrigation_ratio,
                expected_irrigation_penalty_weight,
                minimum_greedy_irrigation_ratio,
                greedy_irrigation_penalty_weight,
            ),
            (
                "nitrogen",
                nitrogen_enabled,
                minimum_nitrogen_ratio,
                nitrogen_penalty_weight,
                minimum_expected_nitrogen_ratio,
                expected_nitrogen_penalty_weight,
                minimum_greedy_nitrogen_ratio,
                greedy_nitrogen_penalty_weight,
            ),
        )
        for index, (
            name,
            enabled,
            minimum_ratio,
            penalty_weight,
            minimum_expected_ratio,
            expected_penalty_weight,
            minimum_greedy_ratio,
            greedy_penalty_weight,
        ) in enumerate(channel_specs):
            rollout_ratio = float(mean_rollout_ratio[index].item())
            metrics[f"{name}_rollout_activity_ratio"] = round(rollout_ratio, 6)
            metrics[f"{name}_minimum_activity_ratio"] = round(minimum_ratio, 6)
            if not enabled:
                metrics[f"{name}_activity_shortfall"] = 0.0
                metrics[f"{name}_expected_activity_ratio"] = 0.0
                metrics[f"{name}_expected_activity_target_ratio"] = 0.0
                metrics[f"{name}_expected_activity_shortfall"] = 0.0
                metrics[f"{name}_greedy_activity_ratio"] = 0.0
                metrics[f"{name}_greedy_activity_target_ratio"] = 0.0
                metrics[f"{name}_greedy_activity_shortfall"] = 0.0
                continue
            enabled_ratios.append(rollout_ratio)
            channel_shortfall = max(0.0, minimum_ratio - rollout_ratio)
            shortfall += channel_shortfall * penalty_weight * soft_rollout_penalty_weight_scale
            hard_shortfall += channel_shortfall * penalty_weight * hard_rollout_penalty_weight_scale
            metrics[f"{name}_activity_shortfall"] = round(channel_shortfall, 6)
            if mean_expected_ratio is None:
                metrics[f"{name}_expected_activity_ratio"] = 0.0
                metrics[f"{name}_expected_activity_target_ratio"] = 0.0
                metrics[f"{name}_expected_activity_shortfall"] = 0.0
            else:
                expected_ratio = float(mean_expected_ratio[index].item())
                expected_target_ratio = max(
                    minimum_expected_ratio,
                    rollout_ratio * expected_activity_retention_ratio,
                )
                expected_shortfall = (
                    max(0.0, expected_target_ratio - expected_ratio)
                    if enforce_expected_activity
                    else 0.0
                )
                shortfall += (
                    expected_shortfall * expected_penalty_weight * soft_expected_penalty_weight_scale
                )
                hard_shortfall += (
                    expected_shortfall * expected_penalty_weight * hard_expected_penalty_weight_scale
                )
                metrics[f"{name}_expected_activity_ratio"] = round(expected_ratio, 6)
                metrics[f"{name}_expected_activity_target_ratio"] = round(expected_target_ratio, 6)
                metrics[f"{name}_expected_activity_shortfall"] = round(expected_shortfall, 6)
            if mean_greedy_ratio is None:
                metrics[f"{name}_greedy_activity_ratio"] = 0.0
                metrics[f"{name}_greedy_activity_target_ratio"] = 0.0
                metrics[f"{name}_greedy_activity_shortfall"] = 0.0
                continue
            greedy_ratio = float(mean_greedy_ratio[index].item())
            greedy_target_ratio = max(
                minimum_greedy_ratio,
                rollout_ratio * greedy_activity_retention_ratio,
            )
            greedy_shortfall = (
                max(0.0, greedy_target_ratio - greedy_ratio)
                if enforce_greedy_activity
                else 0.0
            )
            shortfall += greedy_shortfall * greedy_penalty_weight * soft_greedy_penalty_weight_scale
            hard_shortfall += greedy_shortfall * greedy_penalty_weight * hard_greedy_penalty_weight_scale
            metrics[f"{name}_greedy_activity_ratio"] = round(greedy_ratio, 6)
            metrics[f"{name}_greedy_activity_target_ratio"] = round(greedy_target_ratio, 6)
            metrics[f"{name}_greedy_activity_shortfall"] = round(greedy_shortfall, 6)

        min_enabled_activity_ratio = min(enabled_ratios) if enabled_ratios else 0.0
        admitted = hard_shortfall <= hard_rejection_threshold + 1e-9
        metrics["admitted"] = admitted
        metrics["penalty"] = round(shortfall, 6)
        metrics["shortfall"] = round(shortfall, 6)
        metrics["hard_shortfall"] = round(hard_shortfall, 6)
        metrics["minimum_enabled_activity_ratio"] = round(min_enabled_activity_ratio, 6)
        return metrics


    def masked_categorical_distribution(
        logits: torch.Tensor,
        action_masks: torch.Tensor,
    ) -> Categorical:
        if torch.any(action_masks.sum(dim=-1) <= 0):
            raise RuntimeError("Encountered an action mask without any legal action.")
        invalid_logits = torch.full_like(logits, torch.finfo(logits.dtype).min)
        masked_logits = torch.where(action_masks > 0, logits, invalid_logits)
        return Categorical(logits=masked_logits)


    def _control_mode_tensor(
        control_mode: str,
        *,
        device: torch.device | str,
        batch_size: int,
    ) -> torch.Tensor:
        irrigation_enabled, nitrogen_enabled = _control_mode_flags(control_mode)
        base = torch.tensor(
            [float(irrigation_enabled), float(nitrogen_enabled)],
            dtype=torch.float32,
            device=device,
        )
        return base.unsqueeze(0).expand(batch_size, -1)


    def _sample_gated_continuous_decision(
        gate_logits: torch.Tensor,
        amount_alpha: torch.Tensor,
        amount_beta: torch.Tensor,
        amount_maxima: torch.Tensor,
        *,
        control_mode: str,
        greedy: bool,
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        control_mask = _control_mode_tensor(
            control_mode,
            device=gate_logits.device,
            batch_size=gate_logits.size(0),
        )
        legal_mask = (amount_maxima > 1e-9).to(dtype=torch.float32)
        active_mask = control_mask * legal_mask
        gate_distribution = Bernoulli(logits=gate_logits)
        if greedy:
            gate_actions = (torch.sigmoid(gate_logits) >= 0.5).to(dtype=torch.float32)
        else:
            gate_actions = gate_distribution.sample().to(dtype=torch.float32)
        gate_actions = gate_actions * active_mask
        amount_distribution = Beta(amount_alpha, amount_beta)
        if greedy:
            normalized_amounts = amount_alpha / (amount_alpha + amount_beta)
        else:
            normalized_amounts = amount_distribution.sample()
        normalized_amounts = torch.clamp(normalized_amounts, min=1e-6, max=1.0 - 1e-6)
        amount_actions = normalized_amounts * amount_maxima * gate_actions
        gate_log_prob = (gate_distribution.log_prob(gate_actions) * active_mask).sum(dim=-1)
        amount_log_prob = (amount_distribution.log_prob(normalized_amounts) * gate_actions).sum(dim=-1)
        return gate_actions, amount_actions, gate_log_prob + amount_log_prob


    def _gated_continuous_log_prob_and_entropy(
        gate_logits: torch.Tensor,
        amount_alpha: torch.Tensor,
        amount_beta: torch.Tensor,
        gate_actions: torch.Tensor,
        amount_actions: torch.Tensor,
        amount_maxima: torch.Tensor,
        *,
        control_mode: str,
    ) -> tuple[torch.Tensor, torch.Tensor]:
        control_mask = _control_mode_tensor(
            control_mode,
            device=gate_logits.device,
            batch_size=gate_logits.size(0),
        )
        legal_mask = (amount_maxima > 1e-9).to(dtype=torch.float32)
        active_mask = control_mask * legal_mask
        gate_actions = gate_actions.to(dtype=torch.float32) * active_mask
        gate_distribution = Bernoulli(logits=gate_logits)
        amount_distribution = Beta(amount_alpha, amount_beta)
        normalized_amounts = torch.where(
            amount_maxima > 1e-9,
            amount_actions / amount_maxima.clamp(min=1e-6),
            torch.full_like(amount_actions, 0.5),
        )
        normalized_amounts = torch.clamp(normalized_amounts, min=1e-6, max=1.0 - 1e-6)
        log_prob = (
            (gate_distribution.log_prob(gate_actions) * active_mask).sum(dim=-1)
            + (amount_distribution.log_prob(normalized_amounts) * gate_actions).sum(dim=-1)
        )
        entropy = (
            (gate_distribution.entropy() * active_mask).sum(dim=-1)
            + (amount_distribution.entropy() * gate_actions).sum(dim=-1)
        )
        return log_prob, entropy


    def select_action_from_model(
        model: nn.Module,
        observation: DecisionObservation,
        sequence_features: list[list[float]],
        *,
        device: torch.device | str,
        greedy: bool = False,
    ) -> StepwisePolicyDecision:
        sequences, padding_mask = collate_sequence_features([sequence_features], device=device)
        with torch.no_grad():
            if _canonicalize_action_mode(getattr(model, "action_mode", "continuous")) == "continuous":
                gate_logits, amount_alpha, amount_beta, values = model(sequences, padding_mask=padding_mask)
                amount_maxima = torch.tensor(
                    [
                        [
                            observation.action_constraints.irrigation.max_value,
                            observation.action_constraints.nitrogen.max_value,
                        ]
                    ],
                    dtype=torch.float32,
                    device=device,
                )
                gate_actions, amount_actions, log_prob = _sample_gated_continuous_decision(
                    gate_logits,
                    amount_alpha,
                    amount_beta,
                    amount_maxima,
                    control_mode=getattr(model, "control_mode", "joint"),
                    greedy=greedy,
                )
                return StepwisePolicyDecision(
                    action_mode="continuous",
                    control_mode=getattr(model, "control_mode", "joint"),
                    irrigation_gate=int(gate_actions[0, 0].item()),
                    nitrogen_gate=int(gate_actions[0, 1].item()),
                    irrigation_amount_mm=float(amount_actions[0, 0].item()),
                    nitrogen_amount_kg_ha=float(amount_actions[0, 1].item()),
                    value_estimate=float(values.item()),
                    log_prob=float(log_prob.item()),
                )

            action_mask = torch.tensor(
                [observation.discrete_action_mask.mask],
                dtype=torch.float32,
                device=device,
            )
            logits, values = model(sequences, padding_mask=padding_mask)
            distribution = masked_categorical_distribution(logits, action_mask)
            if greedy:
                action = torch.argmax(distribution.logits, dim=-1)
            else:
                action = distribution.sample()
            log_prob = distribution.log_prob(action)
            return StepwisePolicyDecision(
                action_mode="discrete",
                control_mode=getattr(model, "control_mode", "joint"),
                action_id=int(action.item()),
                value_estimate=float(values.item()),
                log_prob=float(log_prob.item()),
            )


    def collect_ppo_rollout_batch(
        model: nn.Module,
        scenarios: list[SimulationScenario],
        *,
        device: torch.device | str,
        episode_count: int,
        gamma: float = 0.99,
        gae_lambda: float = 0.95,
        seed: int | None = None,
    ) -> tuple[PPORolloutBatch, dict[str, Any], list[StepwiseRolloutEpisode]]:
        if not scenarios:
            raise ValueError("At least one scenario is required for rollout collection.")
        rng = random.Random(seed)
        episodes: list[StepwiseRolloutEpisode] = []
        flat_sequences: list[list[list[float]]] = []
        flat_log_probs: list[float] = []
        flat_values: list[float] = []
        flat_advantages: list[float] = []
        flat_returns: list[float] = []
        action_mode = _canonicalize_action_mode(getattr(model, "action_mode", "continuous"))
        control_mode = _canonicalize_control_mode(getattr(model, "control_mode", "joint"))
        flat_masks: list[list[int]] = []
        flat_actions: list[int] = []
        flat_gate_actions: list[list[float]] = []
        flat_amount_actions: list[list[float]] = []
        flat_amount_maxima: list[list[float]] = []

        was_training = model.training
        model.eval()
        try:
            for _ in range(episode_count):
                scenario = rng.choice(scenarios)
                episode = rollout_stepwise_episode(
                    scenario,
                    lambda obs, _, sequence: select_action_from_model(
                        model,
                        obs,
                        sequence,
                        device=device,
                        greedy=False,
                    ),
                    policy_id="stepwise_ppo_sample",
                    notes=["stochastic_rollout", "history_conditioned_sequence_prefix"],
                )
                episodes.append(episode)
                rewards = [step.reward for step in episode.transitions]
                values = [step.value_estimate for step in episode.transitions]
                dones = [step.done for step in episode.transitions]
                advantages, returns = compute_gae_advantages(
                    rewards,
                    values,
                    dones,
                    gamma=gamma,
                    gae_lambda=gae_lambda,
                )
                for step, advantage, discounted_return in zip(episode.transitions, advantages, returns):
                    flat_sequences.append([list(token) for token in step.sequence_features])
                    flat_log_probs.append(step.log_prob)
                    flat_values.append(step.value_estimate)
                    flat_advantages.append(advantage)
                    flat_returns.append(discounted_return)
                    if action_mode == "continuous":
                        flat_gate_actions.append([float(step.irrigation_gate), float(step.nitrogen_gate)])
                        flat_amount_actions.append(
                            [float(step.action.irrigation_mm), float(step.action.nitrogen_kg_ha)]
                        )
                        flat_amount_maxima.append(
                            [float(step.irrigation_max_mm), float(step.nitrogen_max_kg_ha)]
                        )
                    else:
                        flat_masks.append(step.action_mask)
                        flat_actions.append(int(step.action_id))
        finally:
            if was_training:
                model.train()

        sequences, padding_mask = collate_sequence_features(flat_sequences, device=device)
        old_log_probs = torch.tensor(flat_log_probs, dtype=torch.float32, device=device)
        old_values = torch.tensor(flat_values, dtype=torch.float32, device=device)
        advantages = torch.tensor(flat_advantages, dtype=torch.float32, device=device)
        returns = torch.tensor(flat_returns, dtype=torch.float32, device=device)
        if advantages.numel() > 1:
            advantages = (advantages - advantages.mean()) / (advantages.std(unbiased=False) + 1e-6)

        summary = summarize_rollout_episodes(episodes)
        summary["mean_value_estimate"] = round(sum(flat_values) / max(1, len(flat_values)), 6)
        summary["action_mode"] = action_mode
        summary["control_mode"] = control_mode
        if action_mode == "continuous":
            gate_actions = torch.tensor(flat_gate_actions, dtype=torch.float32, device=device)
            amount_actions = torch.tensor(flat_amount_actions, dtype=torch.float32, device=device)
            amount_maxima = torch.tensor(flat_amount_maxima, dtype=torch.float32, device=device)
            rollout_batch = PPORolloutBatch(
                action_mode=action_mode,
                control_mode=control_mode,
                sequences=sequences,
                padding_mask=padding_mask,
                old_log_probs=old_log_probs,
                old_values=old_values,
                advantages=advantages,
                returns=returns,
                gate_actions=gate_actions,
                amount_actions=amount_actions,
                amount_maxima=amount_maxima,
            )
        else:
            action_masks = torch.tensor(flat_masks, dtype=torch.float32, device=device)
            actions = torch.tensor(flat_actions, dtype=torch.long, device=device)
            rollout_batch = PPORolloutBatch(
                action_mode=action_mode,
                control_mode=control_mode,
                sequences=sequences,
                padding_mask=padding_mask,
                old_log_probs=old_log_probs,
                old_values=old_values,
                advantages=advantages,
                returns=returns,
                action_masks=action_masks,
                actions=actions,
            )
        return (
            rollout_batch,
            summary,
            episodes,
        )


    def _explained_variance(
        predictions: torch.Tensor,
        targets: torch.Tensor,
    ) -> float:
        target_variance = torch.var(targets, unbiased=False)
        if float(target_variance.item()) <= 1e-9:
            return 0.0
        residual_variance = torch.var(targets - predictions, unbiased=False)
        return float((1.0 - residual_variance / target_variance).item())


    def run_ppo_update(
        model: nn.Module,
        optimizer: torch.optim.Optimizer,
        batch: PPORolloutBatch,
        *,
        clip_epsilon: float = 0.2,
        value_coef: float = 0.5,
        entropy_coef: float = 0.01,
        minibatch_size: int = 64,
        update_epochs: int = 4,
        max_grad_norm: float = 0.5,
        target_kl: float | None = None,
        activity_regularizer: dict[str, float] | None = None,
        behavior_anchor: dict[str, float] | None = None,
        policy_anchor: dict[str, float] | None = None,
        advantage_activity_anchor: dict[str, float] | None = None,
        update_admission: dict[str, float] | None = None,
        auxiliary_penalty_budget: dict[str, float] | None = None,
    ) -> dict[str, Any]:
        model.train()
        update_count = 0
        admitted_update_count = 0
        rejected_update_count = 0
        policy_loss_total = 0.0
        value_loss_total = 0.0
        entropy_total = 0.0
        clip_fraction_total = 0.0
        approx_kl_total = 0.0
        activity_penalty_total = 0.0
        irrigation_expected_activity_total = 0.0
        nitrogen_expected_activity_total = 0.0
        irrigation_shortfall_total = 0.0
        nitrogen_shortfall_total = 0.0
        anchor_penalty_total = 0.0
        irrigation_anchor_target_total = 0.0
        nitrogen_anchor_target_total = 0.0
        irrigation_rollout_activity_total = 0.0
        nitrogen_rollout_activity_total = 0.0
        irrigation_anchor_shortfall_total = 0.0
        nitrogen_anchor_shortfall_total = 0.0
        policy_anchor_penalty_total = 0.0
        policy_anchor_gate_penalty_total = 0.0
        policy_anchor_gate_match_total = 0.0
        irrigation_policy_anchor_error_total = 0.0
        nitrogen_policy_anchor_error_total = 0.0
        policy_anchor_positive_fraction_total = 0.0
        policy_anchor_positive_weight_total = 0.0
        policy_anchor_negative_weight_total = 0.0
        advantage_activity_anchor_penalty_total = 0.0
        advantage_activity_positive_fraction_total = 0.0
        irrigation_advantage_anchor_target_total = 0.0
        nitrogen_advantage_anchor_target_total = 0.0
        irrigation_advantage_rollout_total = 0.0
        nitrogen_advantage_rollout_total = 0.0
        irrigation_advantage_expected_total = 0.0
        nitrogen_advantage_expected_total = 0.0
        irrigation_advantage_shortfall_total = 0.0
        nitrogen_advantage_shortfall_total = 0.0
        admission_penalty_total = 0.0
        admission_shortfall_total = 0.0
        admission_min_activity_total = 0.0
        admission_expected_irrigation_total = 0.0
        admission_expected_nitrogen_total = 0.0
        admission_expected_irrigation_target_total = 0.0
        admission_expected_nitrogen_target_total = 0.0
        admission_greedy_irrigation_total = 0.0
        admission_greedy_nitrogen_total = 0.0
        admission_greedy_irrigation_target_total = 0.0
        admission_greedy_nitrogen_target_total = 0.0
        auxiliary_budget_raw_penalty_total = 0.0
        auxiliary_budget_applied_penalty_total = 0.0
        auxiliary_budget_scale_total = 0.0
        auxiliary_budget_max_allowed_total = 0.0
        auxiliary_budget_core_magnitude_total = 0.0
        early_stopped = False

        def _mean_or_zero(total: float) -> float:
            return total / max(1, update_count)

        for _ in range(update_epochs):
            permutation_device = (
                batch.actions.device
                if batch.actions is not None
                else batch.gate_actions.device
            )
            permutation = torch.randperm(batch.size, device=permutation_device)
            for start in range(0, batch.size, minibatch_size):
                indices = permutation[start : start + minibatch_size]
                if batch.action_mode == "continuous":
                    gate_logits, amount_alpha, amount_beta, predicted_values = model(
                        batch.sequences[indices],
                        padding_mask=batch.padding_mask[indices],
                    )
                    new_log_probs, entropy_vector = _gated_continuous_log_prob_and_entropy(
                        gate_logits,
                        amount_alpha,
                        amount_beta,
                        batch.gate_actions[indices],
                        batch.amount_actions[indices],
                        batch.amount_maxima[indices],
                        control_mode=batch.control_mode,
                    )
                    entropy = entropy_vector.mean()
                    activity_penalty, activity_metrics = _mean_activity_shortfall_penalty(
                        gate_logits,
                        amount_alpha,
                        amount_beta,
                        batch.amount_maxima[indices],
                        control_mode=batch.control_mode,
                        regularizer=activity_regularizer,
                    )
                    anchor_penalty, anchor_metrics = _mean_behavior_anchor_penalty(
                        gate_logits,
                        amount_alpha,
                        amount_beta,
                        batch.gate_actions[indices],
                        batch.amount_actions[indices],
                        batch.amount_maxima[indices],
                        control_mode=batch.control_mode,
                        anchor=behavior_anchor,
                    )
                    policy_anchor_penalty, policy_anchor_metrics = _mean_policy_anchor_penalty(
                        gate_logits,
                        amount_alpha,
                        amount_beta,
                        batch.gate_actions[indices],
                        batch.amount_actions[indices],
                        batch.amount_maxima[indices],
                        control_mode=batch.control_mode,
                        anchor=policy_anchor,
                        advantages=batch.advantages[indices],
                    )
                    advantage_activity_anchor_penalty, advantage_activity_anchor_metrics = _mean_advantage_activity_anchor_penalty(
                        gate_logits,
                        amount_alpha,
                        amount_beta,
                        batch.gate_actions[indices],
                        batch.amount_actions[indices],
                        batch.amount_maxima[indices],
                        control_mode=batch.control_mode,
                        anchor=advantage_activity_anchor,
                        advantages=batch.advantages[indices],
                    )
                    admission_metrics = _evaluate_rollout_activity_admission(
                        batch.gate_actions[indices],
                        batch.amount_actions[indices],
                        batch.amount_maxima[indices],
                        control_mode=batch.control_mode,
                        admission=update_admission,
                        gate_logits=gate_logits,
                        amount_alpha=amount_alpha,
                        amount_beta=amount_beta,
                    )
                else:
                    logits, predicted_values = model(
                        batch.sequences[indices],
                        padding_mask=batch.padding_mask[indices],
                    )
                    distribution = masked_categorical_distribution(logits, batch.action_masks[indices])
                    new_log_probs = distribution.log_prob(batch.actions[indices])
                    entropy = distribution.entropy().mean()
                    activity_penalty = torch.zeros((), dtype=torch.float32, device=predicted_values.device)
                    activity_metrics = {
                        "enabled": False,
                        "penalty": 0.0,
                    }
                    anchor_penalty = torch.zeros((), dtype=torch.float32, device=predicted_values.device)
                    anchor_metrics = {
                        "enabled": False,
                        "penalty": 0.0,
                    }
                    policy_anchor_penalty = torch.zeros((), dtype=torch.float32, device=predicted_values.device)
                    policy_anchor_metrics = {
                        "enabled": False,
                        "penalty": 0.0,
                    }
                    advantage_activity_anchor_penalty = torch.zeros((), dtype=torch.float32, device=predicted_values.device)
                    advantage_activity_anchor_metrics = {
                        "enabled": False,
                        "penalty": 0.0,
                    }
                    admission_metrics = {
                        "enabled": False,
                        "admitted": True,
                        "penalty": 0.0,
                        "shortfall": 0.0,
                        "hard_rejection_threshold": 0.0,
                        "soft_penalty_weight": 0.0,
                        "minimum_enabled_activity_ratio": 0.0,
                        "irrigation_expected_activity_ratio": 0.0,
                        "nitrogen_expected_activity_ratio": 0.0,
                        "irrigation_expected_activity_target_ratio": 0.0,
                        "nitrogen_expected_activity_target_ratio": 0.0,
                        "irrigation_greedy_activity_ratio": 0.0,
                        "nitrogen_greedy_activity_ratio": 0.0,
                        "irrigation_greedy_activity_target_ratio": 0.0,
                        "nitrogen_greedy_activity_target_ratio": 0.0,
                    }
                ratios = torch.exp(new_log_probs - batch.old_log_probs[indices])
                unclipped = ratios * batch.advantages[indices]
                clipped = torch.clamp(ratios, 1.0 - clip_epsilon, 1.0 + clip_epsilon) * batch.advantages[indices]
                policy_loss = -torch.min(unclipped, clipped).mean()
                value_loss = 0.5 * torch.mean((batch.returns[indices] - predicted_values) ** 2)
                admission_penalty = torch.zeros((), dtype=torch.float32, device=predicted_values.device)
                if bool(admission_metrics.get("enabled", False)):
                    admission_penalty = torch.tensor(
                        float(admission_metrics.get("penalty", 0.0))
                        * float(admission_metrics.get("soft_penalty_weight", 0.0)),
                        dtype=torch.float32,
                        device=predicted_values.device,
                    )
                scaled_auxiliary_penalties, auxiliary_budget_metrics = _apply_auxiliary_penalty_budget(
                    policy_loss,
                    value_loss,
                    entropy,
                    {
                        "activity_regularizer": activity_penalty,
                        "behavior_anchor": anchor_penalty,
                        "policy_anchor": policy_anchor_penalty,
                        "advantage_activity_anchor": advantage_activity_anchor_penalty,
                        "update_admission": admission_penalty,
                    },
                    value_coef=value_coef,
                    entropy_coef=entropy_coef,
                    budget=auxiliary_penalty_budget,
                )
                loss = (
                    policy_loss
                    + value_coef * value_loss
                    - entropy_coef * entropy
                    + scaled_auxiliary_penalties["activity_regularizer"]
                    + scaled_auxiliary_penalties["behavior_anchor"]
                    + scaled_auxiliary_penalties["policy_anchor"]
                    + scaled_auxiliary_penalties["advantage_activity_anchor"]
                    + scaled_auxiliary_penalties["update_admission"]
                )

                update_count += 1
                if bool(admission_metrics.get("admitted", True)):
                    optimizer.zero_grad()
                    loss.backward()
                    if max_grad_norm > 0.0:
                        torch.nn.utils.clip_grad_norm_(model.parameters(), max_grad_norm)
                    optimizer.step()
                    admitted_update_count += 1
                else:
                    rejected_update_count += 1
                policy_loss_total += float(policy_loss.item())
                value_loss_total += float(value_loss.item())
                entropy_total += float(entropy.item())
                clip_fraction_total += float(((ratios - 1.0).abs() > clip_epsilon).float().mean().item())
                approx_kl_total += float((batch.old_log_probs[indices] - new_log_probs).mean().item())
                activity_penalty_total += float(activity_metrics.get("penalty", 0.0))
                irrigation_expected_activity_total += float(activity_metrics.get("irrigation_expected_activity_ratio", 0.0))
                nitrogen_expected_activity_total += float(activity_metrics.get("nitrogen_expected_activity_ratio", 0.0))
                irrigation_shortfall_total += float(activity_metrics.get("irrigation_activity_shortfall", 0.0))
                nitrogen_shortfall_total += float(activity_metrics.get("nitrogen_activity_shortfall", 0.0))
                anchor_penalty_total += float(anchor_metrics.get("penalty", 0.0))
                irrigation_anchor_target_total += float(anchor_metrics.get("irrigation_anchor_target_ratio", 0.0))
                nitrogen_anchor_target_total += float(anchor_metrics.get("nitrogen_anchor_target_ratio", 0.0))
                irrigation_rollout_activity_total += float(anchor_metrics.get("irrigation_rollout_activity_ratio", 0.0))
                nitrogen_rollout_activity_total += float(anchor_metrics.get("nitrogen_rollout_activity_ratio", 0.0))
                irrigation_anchor_shortfall_total += float(anchor_metrics.get("irrigation_anchor_shortfall", 0.0))
                nitrogen_anchor_shortfall_total += float(anchor_metrics.get("nitrogen_anchor_shortfall", 0.0))
                policy_anchor_penalty_total += float(policy_anchor_metrics.get("penalty", 0.0))
                policy_anchor_gate_penalty_total += float(policy_anchor_metrics.get("gate_penalty", 0.0))
                policy_anchor_gate_match_total += float(policy_anchor_metrics.get("gate_match_ratio", 0.0))
                irrigation_policy_anchor_error_total += float(policy_anchor_metrics.get("irrigation_amount_abs_error", 0.0))
                nitrogen_policy_anchor_error_total += float(policy_anchor_metrics.get("nitrogen_amount_abs_error", 0.0))
                policy_anchor_positive_fraction_total += float(policy_anchor_metrics.get("positive_advantage_fraction", 0.0))
                policy_anchor_positive_weight_total += float(policy_anchor_metrics.get("mean_positive_advantage_anchor_weight", 0.0))
                policy_anchor_negative_weight_total += float(policy_anchor_metrics.get("mean_negative_advantage_anchor_weight", 0.0))
                advantage_activity_anchor_penalty_total += float(advantage_activity_anchor_metrics.get("penalty", 0.0))
                advantage_activity_positive_fraction_total += float(advantage_activity_anchor_metrics.get("positive_advantage_fraction", 0.0))
                irrigation_advantage_anchor_target_total += float(advantage_activity_anchor_metrics.get("irrigation_positive_anchor_target_ratio", 0.0))
                nitrogen_advantage_anchor_target_total += float(advantage_activity_anchor_metrics.get("nitrogen_positive_anchor_target_ratio", 0.0))
                irrigation_advantage_rollout_total += float(advantage_activity_anchor_metrics.get("irrigation_positive_rollout_activity_ratio", 0.0))
                nitrogen_advantage_rollout_total += float(advantage_activity_anchor_metrics.get("nitrogen_positive_rollout_activity_ratio", 0.0))
                irrigation_advantage_expected_total += float(advantage_activity_anchor_metrics.get("irrigation_positive_expected_activity_ratio", 0.0))
                nitrogen_advantage_expected_total += float(advantage_activity_anchor_metrics.get("nitrogen_positive_expected_activity_ratio", 0.0))
                irrigation_advantage_shortfall_total += float(advantage_activity_anchor_metrics.get("irrigation_positive_anchor_shortfall", 0.0))
                nitrogen_advantage_shortfall_total += float(advantage_activity_anchor_metrics.get("nitrogen_positive_anchor_shortfall", 0.0))
                admission_penalty_total += float(admission_metrics.get("penalty", 0.0))
                admission_shortfall_total += float(admission_metrics.get("shortfall", 0.0))
                admission_min_activity_total += float(admission_metrics.get("minimum_enabled_activity_ratio", 0.0))
                admission_expected_irrigation_total += float(admission_metrics.get("irrigation_expected_activity_ratio", 0.0))
                admission_expected_nitrogen_total += float(admission_metrics.get("nitrogen_expected_activity_ratio", 0.0))
                admission_expected_irrigation_target_total += float(
                    admission_metrics.get("irrigation_expected_activity_target_ratio", 0.0)
                )
                admission_expected_nitrogen_target_total += float(
                    admission_metrics.get("nitrogen_expected_activity_target_ratio", 0.0)
                )
                admission_greedy_irrigation_total += float(admission_metrics.get("irrigation_greedy_activity_ratio", 0.0))
                admission_greedy_nitrogen_total += float(admission_metrics.get("nitrogen_greedy_activity_ratio", 0.0))
                admission_greedy_irrigation_target_total += float(
                    admission_metrics.get("irrigation_greedy_activity_target_ratio", 0.0)
                )
                admission_greedy_nitrogen_target_total += float(
                    admission_metrics.get("nitrogen_greedy_activity_target_ratio", 0.0)
                )
                auxiliary_budget_raw_penalty_total += float(auxiliary_budget_metrics.get("raw_penalty", 0.0))
                auxiliary_budget_applied_penalty_total += float(auxiliary_budget_metrics.get("applied_penalty", 0.0))
                auxiliary_budget_scale_total += float(auxiliary_budget_metrics.get("penalty_scale", 1.0))
                auxiliary_budget_max_allowed_total += float(auxiliary_budget_metrics.get("max_allowed_penalty", 0.0))
                auxiliary_budget_core_magnitude_total += float(auxiliary_budget_metrics.get("core_loss_magnitude", 0.0))
                if target_kl is not None and _mean_or_zero(approx_kl_total) > target_kl:
                    early_stopped = True
                    break
            if early_stopped:
                break

        with torch.no_grad():
            if batch.action_mode == "continuous":
                _, _, _, value_predictions = model(batch.sequences, padding_mask=batch.padding_mask)
            else:
                _, value_predictions = model(batch.sequences, padding_mask=batch.padding_mask)
        return {
            "update_count": update_count,
            "policy_loss": round(policy_loss_total / max(1, update_count), 6),
            "value_loss": round(value_loss_total / max(1, update_count), 6),
            "entropy": round(entropy_total / max(1, update_count), 6),
            "clip_fraction": round(clip_fraction_total / max(1, update_count), 6),
            "approx_kl": round(approx_kl_total / max(1, update_count), 6),
            "activity_regularizer_penalty": round(activity_penalty_total / max(1, update_count), 6),
            "mean_expected_irrigation_activity_ratio": round(irrigation_expected_activity_total / max(1, update_count), 6),
            "mean_expected_nitrogen_activity_ratio": round(nitrogen_expected_activity_total / max(1, update_count), 6),
            "mean_irrigation_activity_shortfall": round(irrigation_shortfall_total / max(1, update_count), 6),
            "mean_nitrogen_activity_shortfall": round(nitrogen_shortfall_total / max(1, update_count), 6),
            "behavior_anchor_penalty": round(anchor_penalty_total / max(1, update_count), 6),
            "mean_irrigation_anchor_target_ratio": round(irrigation_anchor_target_total / max(1, update_count), 6),
            "mean_nitrogen_anchor_target_ratio": round(nitrogen_anchor_target_total / max(1, update_count), 6),
            "mean_rollout_irrigation_activity_ratio": round(irrigation_rollout_activity_total / max(1, update_count), 6),
            "mean_rollout_nitrogen_activity_ratio": round(nitrogen_rollout_activity_total / max(1, update_count), 6),
            "mean_irrigation_anchor_shortfall": round(irrigation_anchor_shortfall_total / max(1, update_count), 6),
            "mean_nitrogen_anchor_shortfall": round(nitrogen_anchor_shortfall_total / max(1, update_count), 6),
            "policy_anchor_penalty": round(policy_anchor_penalty_total / max(1, update_count), 6),
            "mean_policy_anchor_gate_penalty": round(policy_anchor_gate_penalty_total / max(1, update_count), 6),
            "mean_policy_anchor_gate_match_ratio": round(policy_anchor_gate_match_total / max(1, update_count), 6),
            "mean_irrigation_policy_anchor_amount_abs_error": round(irrigation_policy_anchor_error_total / max(1, update_count), 6),
            "mean_nitrogen_policy_anchor_amount_abs_error": round(nitrogen_policy_anchor_error_total / max(1, update_count), 6),
            "mean_policy_anchor_positive_advantage_fraction": round(policy_anchor_positive_fraction_total / max(1, update_count), 6),
            "mean_policy_anchor_positive_advantage_weight": round(policy_anchor_positive_weight_total / max(1, update_count), 6),
            "mean_policy_anchor_negative_advantage_weight": round(policy_anchor_negative_weight_total / max(1, update_count), 6),
            "advantage_activity_anchor_penalty": round(advantage_activity_anchor_penalty_total / max(1, update_count), 6),
            "mean_advantage_activity_positive_fraction": round(advantage_activity_positive_fraction_total / max(1, update_count), 6),
            "mean_irrigation_positive_anchor_target_ratio": round(irrigation_advantage_anchor_target_total / max(1, update_count), 6),
            "mean_nitrogen_positive_anchor_target_ratio": round(nitrogen_advantage_anchor_target_total / max(1, update_count), 6),
            "mean_irrigation_positive_rollout_activity_ratio": round(irrigation_advantage_rollout_total / max(1, update_count), 6),
            "mean_nitrogen_positive_rollout_activity_ratio": round(nitrogen_advantage_rollout_total / max(1, update_count), 6),
            "mean_irrigation_positive_expected_activity_ratio": round(irrigation_advantage_expected_total / max(1, update_count), 6),
            "mean_nitrogen_positive_expected_activity_ratio": round(nitrogen_advantage_expected_total / max(1, update_count), 6),
            "mean_irrigation_positive_anchor_shortfall": round(irrigation_advantage_shortfall_total / max(1, update_count), 6),
            "mean_nitrogen_positive_anchor_shortfall": round(nitrogen_advantage_shortfall_total / max(1, update_count), 6),
            "admitted_update_count": admitted_update_count,
            "rejected_update_count": rejected_update_count,
            "update_admission_penalty": round(admission_penalty_total / max(1, update_count), 6),
            "mean_update_admission_shortfall": round(admission_shortfall_total / max(1, update_count), 6),
            "mean_update_min_enabled_activity_ratio": round(admission_min_activity_total / max(1, update_count), 6),
            "mean_update_expected_irrigation_activity_ratio": round(admission_expected_irrigation_total / max(1, update_count), 6),
            "mean_update_expected_nitrogen_activity_ratio": round(admission_expected_nitrogen_total / max(1, update_count), 6),
            "mean_update_expected_irrigation_target_ratio": round(admission_expected_irrigation_target_total / max(1, update_count), 6),
            "mean_update_expected_nitrogen_target_ratio": round(admission_expected_nitrogen_target_total / max(1, update_count), 6),
            "mean_update_greedy_irrigation_activity_ratio": round(admission_greedy_irrigation_total / max(1, update_count), 6),
            "mean_update_greedy_nitrogen_activity_ratio": round(admission_greedy_nitrogen_total / max(1, update_count), 6),
            "mean_update_greedy_irrigation_target_ratio": round(admission_greedy_irrigation_target_total / max(1, update_count), 6),
            "mean_update_greedy_nitrogen_target_ratio": round(admission_greedy_nitrogen_target_total / max(1, update_count), 6),
            "auxiliary_penalty_budget_raw_penalty": round(auxiliary_budget_raw_penalty_total / max(1, update_count), 6),
            "auxiliary_penalty_budget_applied_penalty": round(auxiliary_budget_applied_penalty_total / max(1, update_count), 6),
            "mean_auxiliary_penalty_budget_scale": round(auxiliary_budget_scale_total / max(1, update_count), 6),
            "mean_auxiliary_penalty_budget_max_allowed": round(auxiliary_budget_max_allowed_total / max(1, update_count), 6),
            "mean_auxiliary_penalty_budget_core_loss_magnitude": round(auxiliary_budget_core_magnitude_total / max(1, update_count), 6),
            "explained_variance": round(_explained_variance(value_predictions, batch.returns), 6),
            "early_stopped_on_kl": early_stopped,
            "target_kl": None if target_kl is None else float(target_kl),
            "activity_regularizer_enabled": bool(activity_regularizer and activity_regularizer.get("enabled", False)),
            "behavior_anchor_enabled": bool(behavior_anchor and behavior_anchor.get("enabled", False)),
            "policy_anchor_enabled": bool(policy_anchor and policy_anchor.get("enabled", False)),
            "advantage_activity_anchor_enabled": bool(advantage_activity_anchor and advantage_activity_anchor.get("enabled", False)),
            "update_admission_enabled": bool(update_admission and update_admission.get("enabled", False)),
            "auxiliary_penalty_budget_enabled": bool(auxiliary_penalty_budget and auxiliary_penalty_budget.get("enabled", False)),
        }


    def evaluate_stepwise_actor_critic(
        model: nn.Module,
        scenarios: list[SimulationScenario],
        *,
        baseline_trajectories: dict[str, Trajectory],
        device: torch.device | str,
    ) -> tuple[dict[str, Any], list[StepwiseRolloutEpisode]]:
        scorecards = []
        episodes: list[StepwiseRolloutEpisode] = []
        was_training = model.training
        model.eval()
        try:
            for scenario in scenarios:
                episode = rollout_stepwise_episode(
                    scenario,
                    lambda obs, _, sequence: select_action_from_model(
                        model,
                        obs,
                        sequence,
                        device=device,
                        greedy=True,
                    ),
                    policy_id="stepwise_ppo_greedy",
                    notes=["greedy_eval", "history_conditioned_sequence_prefix"],
                )
                episodes.append(episode)
                scorecards.append(
                    score_trajectory(
                        scenario,
                        episode.to_trajectory(),
                        baseline_trajectories[scenario.scenario_id],
                    )
                )
        finally:
            if was_training:
                model.train()
        summary = summarize_scorecards(scorecards)
        summary.update(summarize_rollout_episodes(episodes))
        return summary, episodes


except ImportError:  # pragma: no cover - depends on optional torch install
    TORCH_AVAILABLE = False
    collate_sequence_features = None
    collect_ppo_rollout_batch = None
    evaluate_stepwise_actor_critic = None
    masked_categorical_distribution = None
    _mean_behavior_anchor_penalty = None
    _mean_policy_anchor_penalty = None
    _mean_advantage_activity_anchor_penalty = None
    _mean_activity_shortfall_penalty = None
    _apply_auxiliary_penalty_budget = None
    _evaluate_rollout_activity_admission = None
    run_ppo_update = None
    select_action_from_model = None
    StepwisePPOActorCritic = None
    StepwiseTransformerActorCritic = None
    StepwiseGatedContinuousActorCritic = None
    StepwiseGatedContinuousTransformerActorCritic = None
    PPORolloutBatch = None
