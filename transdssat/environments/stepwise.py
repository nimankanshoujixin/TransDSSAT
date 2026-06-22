from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
import os
from typing import Any

from transdssat.dssat import (
    InteractiveDSSATTransport,
    PatchedInteractiveDSSATSession,
)
from transdssat.discrete_actions import (
    ActionConstraintRules,
    ActionConstraintSnapshot,
    ContinuousAction,
    ContinuousActionSpace,
    DiscreteActionMask,
    DiscreteActionTable,
    action_mask_for_constraints,
    action_constraints_for_state,
    default_discrete_action_table,
    default_action_constraint_rules,
    default_continuous_action_space,
    validate_discrete_action,
    validate_continuous_action,
)
from transdssat.domain import CropOutcome, CropState
from transdssat.environments.proxy import make_environment as make_proxy_environment
from transdssat.environments.adapters import OfficialDSSATEnvironment
from transdssat.scenarios import SimulationScenario
from transdssat.season import SeasonPolicy, StageDecision


@dataclass(slots=True)
class DecisionObservation:
    scenario_id: str
    day_index: int
    decision_date: str
    state: CropState
    remaining_irrigation_mm: float
    remaining_nitrogen_kg_ha: float
    action_space: ContinuousActionSpace
    action_constraints: ActionConstraintSnapshot
    discrete_action_table: DiscreteActionTable
    discrete_action_mask: DiscreteActionMask
    crop_context: dict[str, Any]
    objective_context: dict[str, Any]
    decision_context: dict[str, Any]
    state_interface_contract: dict[str, Any]
    forecast_weather_window: list[dict[str, Any]]
    done: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "day_index": self.day_index,
            "decision_date": self.decision_date,
            "state": self.state.to_dict(),
            "remaining_irrigation_mm": round(self.remaining_irrigation_mm, 3),
            "remaining_nitrogen_kg_ha": round(self.remaining_nitrogen_kg_ha, 3),
            "action_space": self.action_space.to_dict(),
            "action_constraints": self.action_constraints.to_dict(),
            "discrete_action_table": self.discrete_action_table.to_dict(),
            "discrete_action_mask": self.discrete_action_mask.to_dict(),
            "crop_context": dict(self.crop_context),
            "objective_context": dict(self.objective_context),
            "decision_context": dict(self.decision_context),
            "state_interface_contract": dict(self.state_interface_contract),
            "forecast_weather_window": list(self.forecast_weather_window),
            "done": self.done,
        }


class StepwiseDecisionEnvironment:
    def __init__(
        self,
        scenario: SimulationScenario,
        action_space: ContinuousActionSpace | None = None,
        constraint_rules: ActionConstraintRules | None = None,
        official_backend_mode: str = "auto",
        official_interactive_transport: InteractiveDSSATTransport | None = None,
    ) -> None:
        self.scenario = scenario
        self.action_space = action_space or default_continuous_action_space(scenario)
        self.constraint_rules = constraint_rules or default_action_constraint_rules(scenario)
        self.discrete_action_table = default_discrete_action_table(scenario)
        self.official_backend_mode = resolve_official_backend_mode(official_backend_mode)
        self.official_interactive_transport = official_interactive_transport
        self.base_env = self._make_backend(scenario)
        self.current_state: CropState | None = None
        self.remaining_irrigation_mm = scenario.irrigation_budget_mm
        self.remaining_nitrogen_kg_ha = scenario.nitrogen_budget_kg_ha
        self.last_irrigation_day: int | None = None
        self.last_nitrogen_day: int | None = None
        self.done = False
        self._official_cumulative_reward = 0.0

    def _make_backend(self, scenario: SimulationScenario):
        if scenario.engine_name == "dssat_official":
            if self.official_backend_mode == "interactive_patched":
                return _InteractivePatchedOfficialBackend(
                    scenario,
                    transport=self.official_interactive_transport,
                )
            return _OfficialStepwiseBackend(scenario)
        return make_proxy_environment(scenario)

    def reset(self) -> DecisionObservation:
        self.current_state = self.base_env.reset()
        self.remaining_irrigation_mm = self.scenario.irrigation_budget_mm
        self.remaining_nitrogen_kg_ha = self.scenario.nitrogen_budget_kg_ha
        self.last_irrigation_day = None
        self.last_nitrogen_day = None
        self.done = False
        self._official_cumulative_reward = 0.0
        return self.observe()

    def observe(self) -> DecisionObservation:
        if self.current_state is None:
            raise RuntimeError("Environment has not been reset.")
        action_constraints = self.get_action_constraints()
        decision_context = self.scenario.decision_context.to_dict()
        decision_context["management_mode"] = self.scenario.management_mode
        return DecisionObservation(
            scenario_id=self.scenario.scenario_id,
            day_index=self.current_state.day_index,
            decision_date=self._decision_date(self.current_state.day_index),
            state=self.current_state,
            remaining_irrigation_mm=self.remaining_irrigation_mm,
            remaining_nitrogen_kg_ha=self.remaining_nitrogen_kg_ha,
            action_space=self.action_space,
            action_constraints=action_constraints,
            discrete_action_table=self.discrete_action_table,
            discrete_action_mask=action_mask_for_constraints(action_constraints, self.discrete_action_table),
            crop_context=self.scenario.crop_context.to_dict() if self.scenario.crop_context is not None else {},
            objective_context=self.scenario.objective_context.to_dict(),
            decision_context=decision_context,
            state_interface_contract=self.scenario.state_interface_contract_dict(),
            forecast_weather_window=self._forecast_weather_window(),
            done=self.done,
        )

    def get_action_constraints(self) -> ActionConstraintSnapshot:
        if self.current_state is None:
            raise RuntimeError("Environment has not been reset.")
        return action_constraints_for_state(
            scenario=self.scenario,
            state=self.current_state,
            remaining_irrigation_mm=self.remaining_irrigation_mm,
            remaining_nitrogen_kg_ha=self.remaining_nitrogen_kg_ha,
            last_irrigation_day=self.last_irrigation_day,
            last_nitrogen_day=self.last_nitrogen_day,
            done=self.done,
        )

    def step(self, action: ContinuousAction | dict[str, Any]) -> tuple[DecisionObservation, float, bool, dict[str, Any]]:
        if self.current_state is None:
            raise RuntimeError("Environment has not been reset.")
        if self.done:
            raise RuntimeError("Environment already finished. Call reset() before stepping again.")

        executed_action = validate_continuous_action(action, self.get_action_constraints())

        decision_day = self.current_state.day_index
        if executed_action.irrigation_mm > 0.0:
            self.remaining_irrigation_mm = max(0.0, self.remaining_irrigation_mm - executed_action.irrigation_mm)
            self.last_irrigation_day = decision_day
        if executed_action.nitrogen_kg_ha > 0.0:
            self.remaining_nitrogen_kg_ha = max(0.0, self.remaining_nitrogen_kg_ha - executed_action.nitrogen_kg_ha)
            self.last_nitrogen_day = decision_day

        if isinstance(self.base_env, (_OfficialStepwiseBackend, _InteractivePatchedOfficialBackend)):
            next_state, reward_total, done, backend_info = self.base_env.step(
                executed_action.to_crop_action(),
                decision_interval_days=self.constraint_rules.decision_interval_days,
            )
            self.current_state = next_state
            self.done = done
            self._official_cumulative_reward = self.base_env.cumulative_reward
            daily_trace = list(backend_info.get("daily_trace", []))
            days_executed = int(backend_info.get("days_executed", 0))
        else:
            reward_total = 0.0
            daily_trace: list[dict[str, Any]] = []
            days_executed = 0
            backend_info = {}
            for interval_index in range(self.constraint_rules.decision_interval_days):
                daily_action = executed_action.to_crop_action() if interval_index == 0 else ContinuousAction().to_crop_action()
                next_state, reward, done, info = self.base_env.step(daily_action)
                days_executed += 1
                reward_total += reward
                daily_trace.append(
                    {
                        "day_index": next_state.day_index,
                        "reward": reward,
                        "done": done,
                        "engine_info": info,
                    }
                )
                self.current_state = next_state
                self.done = done
                if done:
                    break

        observation = self.observe()
        info = {
            "executed_action": executed_action.to_dict(),
            "decision_day_index": decision_day,
            "days_executed": days_executed,
            "remaining_irrigation_mm": round(self.remaining_irrigation_mm, 3),
            "remaining_nitrogen_kg_ha": round(self.remaining_nitrogen_kg_ha, 3),
            "daily_trace": daily_trace,
            **backend_info,
        }
        return observation, round(reward_total, 6), self.done, info

    def step_discrete(self, action_id: int) -> tuple[DecisionObservation, float, bool, dict[str, Any]]:
        executed_action = validate_discrete_action(
            action_id=action_id,
            constraints=self.get_action_constraints(),
            action_table=self.discrete_action_table,
        )
        observation, reward, done, info = self.step(executed_action)
        info["discrete_action_id"] = action_id
        return observation, reward, done, info

    def final_outcome(self) -> CropOutcome:
        return self.base_env.final_outcome()

    def _decision_date(self, day_index: int) -> str:
        planting = date.fromisoformat(self.scenario.planting_date)
        return (planting + timedelta(days=day_index)).isoformat()

    def _forecast_weather_window(self) -> list[dict[str, Any]]:
        if self.current_state is None:
            return []
        horizon = self.scenario.decision_context.forecast_horizon_days
        planting = date.fromisoformat(self.scenario.planting_date)
        start_index = self.current_state.day_index
        window: list[dict[str, Any]] = []
        for day in self.scenario.weather[start_index : start_index + horizon]:
            window.append(
                {
                    "date": (planting + timedelta(days=day.day_index)).isoformat(),
                    "tmin_c": day.tmin_c,
                    "tmax_c": day.tmax_c,
                    "precipitation_mm": day.precipitation_mm,
                    "radiation_mj_m2": day.radiation_mj_m2,
                    "et0_mm": day.et0_mm,
                }
            )
        return window


@dataclass(slots=True)
class _OfficialEvaluationSnapshot:
    trajectory_states: list[CropState]
    outcome: CropOutcome
    cumulative_reward: float
    daily_trace: list[dict[str, Any]]
    run_dir: str


class _OfficialStepwiseBackend:
    """
    Transitional official-DSSAT step-wise wrapper.

    This is not yet a true gym-DSSAT-style interactive backend. It re-runs the
    whole-season official DSSAT simulation after each accumulated action prefix
    and then slices out the requested future state window.
    """

    def __init__(self, scenario: SimulationScenario) -> None:
        self.scenario = scenario
        self.official_env = OfficialDSSATEnvironment()
        self.executed_actions: list[StageDecision] = []
        self.current_snapshot = self._evaluate([])
        self.current_state = self.current_snapshot.trajectory_states[0]
        self.cumulative_reward = 0.0

    def reset(self) -> CropState:
        self.executed_actions = []
        self.current_snapshot = self._evaluate(self.executed_actions)
        self.current_state = self.current_snapshot.trajectory_states[0]
        self.cumulative_reward = 0.0
        return self.current_state

    def step(self, action: CropAction, *, decision_interval_days: int) -> tuple[CropState, float, bool, dict[str, Any]]:
        decision_day = self.current_state.day_index
        if action.irrigation_mm > 0.0 or action.nitrogen_kg_ha > 0.0:
            self.executed_actions.append(
                StageDecision(
                    stage=self.current_state.stage,
                    day_index=decision_day,
                    date=self._decision_date(decision_day),
                    irrigation_mm=round(action.irrigation_mm, 3),
                    nitrogen_kg_ha=round(action.nitrogen_kg_ha, 3),
                )
            )
        previous_reward = self.cumulative_reward
        self.current_snapshot = self._evaluate(self.executed_actions)
        current_index = self._state_index_for_day(decision_day + decision_interval_days)
        next_state = self.current_snapshot.trajectory_states[current_index]
        self.current_state = next_state
        self.cumulative_reward = self.current_snapshot.cumulative_reward
        reward = round(self.cumulative_reward - previous_reward, 6)
        done = current_index >= len(self.current_snapshot.trajectory_states) - 1
        info = {
            "engine_name": "dssat_official",
            "backend_mode": "season_replay_wrapper",
            "run_dir": self.current_snapshot.run_dir,
            "days_executed": min(
                decision_interval_days,
                self.scenario.crop_spec.season_length_days - decision_day,
            ),
            "daily_trace": self.current_snapshot.daily_trace[decision_day:current_index],
            "official_cumulative_reward": round(self.cumulative_reward, 6),
        }
        return next_state, reward, done, info

    def final_outcome(self) -> CropOutcome:
        return self.current_snapshot.outcome

    def _evaluate(self, actions: list[StageDecision]) -> _OfficialEvaluationSnapshot:
        policy = SeasonPolicy(
            policy_id=f"{self.scenario.scenario_id}-official-stepwise",
            scenario_id=self.scenario.scenario_id,
            actions=list(actions),
        )
        result = self.official_env.evaluate_policy(self.scenario, policy)
        trajectory_states = [result.trajectory.steps[0].state] + [step.next_state for step in result.trajectory.steps]
        daily_trace = [
            {
                "day_index": step.state.day_index,
                "reward": step.reward,
                "done": step.done,
                "engine_info": step.info,
            }
            for step in result.trajectory.steps
        ]
        return _OfficialEvaluationSnapshot(
            trajectory_states=trajectory_states,
            outcome=result.trajectory.outcome,
            cumulative_reward=result.reward,
            daily_trace=daily_trace,
            run_dir=result.run_dir,
        )

    def _state_index_for_day(self, day_index: int) -> int:
        return max(0, min(day_index, len(self.current_snapshot.trajectory_states) - 1))

    def _decision_date(self, day_index: int) -> str:
        planting = date.fromisoformat(self.scenario.planting_date)
        return (planting + timedelta(days=day_index)).isoformat()


class _InteractivePatchedOfficialBackend:
    def __init__(
        self,
        scenario: SimulationScenario,
        *,
        transport: InteractiveDSSATTransport | None,
    ) -> None:
        if transport is None:
            raise NotImplementedError(
                "Official DSSAT interactive_patched backend requires an interactive transport. "
                "The patched runtime control channel is not implemented yet."
            )
        self.scenario = scenario
        self.session = PatchedInteractiveDSSATSession(scenario, transport)
        self.current_state: CropState | None = None
        self.cumulative_reward = 0.0
        self._final_outcome: CropOutcome | None = None

    def reset(self) -> CropState:
        result = self.session.reset()
        self.current_state = result.state
        self.cumulative_reward = 0.0
        self._final_outcome = None
        return result.state

    def step(self, action: CropAction, *, decision_interval_days: int) -> tuple[CropState, float, bool, dict[str, Any]]:
        if self.current_state is None:
            raise RuntimeError("Interactive patched official backend has not been reset.")
        result = self.session.step(
            action,
            decision_interval_days=decision_interval_days,
        )
        self.current_state = result.next_state
        self.cumulative_reward = round(self.cumulative_reward + float(result.reward), 6)
        if result.final_outcome is not None:
            self._final_outcome = result.final_outcome
        info = {
            "engine_name": "dssat_official",
            "backend_mode": "interactive_patched",
            "run_dir": result.run_dir or self.session.last_run_dir,
            "days_executed": decision_interval_days,
            "daily_trace": list(result.daily_trace),
            "official_cumulative_reward": round(self.cumulative_reward, 6),
            **dict(result.info),
        }
        return result.next_state, round(float(result.reward), 6), bool(result.done), info

    def final_outcome(self) -> CropOutcome:
        if self._final_outcome is not None:
            return self._final_outcome
        self._final_outcome = self.session.final_outcome()
        return self._final_outcome


def resolve_official_backend_mode(requested_mode: str) -> str:
    normalized = str(requested_mode or "auto").strip().lower()
    if normalized == "auto":
        normalized = str(os.environ.get("TRANSDSSAT_OFFICIAL_BACKEND_MODE", "season_replay_wrapper")).strip().lower()
    if normalized not in {"season_replay_wrapper", "interactive_patched"}:
        raise ValueError(f"Unsupported official backend mode: {requested_mode}")
    return normalized
