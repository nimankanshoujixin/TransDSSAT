from __future__ import annotations

from dataclasses import dataclass

from transdssat.domain import CropAction, Trajectory, TrajectoryStep
from transdssat.dssat import DSSATOutputParser, DSSATRunner
from transdssat.rewarding import (
    RewardWeights,
    anti_collapse_preferences,
    input_use_efficiency,
    objective_reward_weights,
    reward_from_outcome,
    resource_settlement_preferences,
    step_reward,
)
from transdssat.scenarios import SimulationScenario, scenario_yield_floor_reference
from transdssat.season import SeasonPolicy


@dataclass(slots=True)
class SeasonEvaluationResult:
    trajectory: Trajectory
    run_dir: str
    reward: float


class OfficialDSSATEnvironment:
    """
    Season-level official DSSAT backend.

    The flow is:
    1. materialize a per-run workspace from scenario + season policy,
    2. optionally run a preprocessor that renders DSSAT experiment files,
    3. run the DSSAT command,
    4. parse Summary.OUT / PlantGro.OUT / SoilWat.OUT / SoilNi.OUT,
    5. convert outputs into a reward-bearing trajectory.

    This matches DSSAT's natural whole-season workflow better than a daily step API.
    """

    def __init__(self) -> None:
        self.runner = DSSATRunner()
        self.parser = DSSATOutputParser()

    def evaluate_policy(
        self,
        scenario: SimulationScenario,
        policy: SeasonPolicy,
        weights: RewardWeights | None = None,
    ) -> SeasonEvaluationResult:
        context = self.runner.prepare(scenario, policy)
        self.runner.run(context)
        parsed = self.parser.parse(context.run_dir, scenario)
        if parsed.outcome.total_irrigation_mm <= 0.0:
            parsed.outcome.total_irrigation_mm = policy.total_irrigation_mm
        if parsed.outcome.total_nitrogen_kg_ha <= 0.0:
            parsed.outcome.total_nitrogen_kg_ha = policy.total_nitrogen_kg_ha
        parsed.outcome.water_use_efficiency = input_use_efficiency(
            parsed.outcome.yield_kg_ha,
            parsed.outcome.total_irrigation_mm,
        )
        parsed.outcome.nitrogen_use_efficiency = input_use_efficiency(
            parsed.outcome.yield_kg_ha,
            parsed.outcome.total_nitrogen_kg_ha,
        )
        trajectory = self._build_trajectory(scenario, policy, parsed, weights)
        reward = trajectory.outcome.cumulative_reward
        return SeasonEvaluationResult(
            trajectory=trajectory,
            run_dir=str(context.run_dir),
            reward=reward,
        )

    def _build_trajectory(
        self,
        scenario: SimulationScenario,
        policy: SeasonPolicy,
        parsed,
        weights: RewardWeights | None,
    ) -> Trajectory:
        weights = weights or objective_reward_weights(scenario.objective_context.to_dict())
        action_map = policy.action_map()
        steps: list[TrajectoryStep] = []
        states = parsed.daily_states
        if len(states) < 2:
            raise RuntimeError("Parsed DSSAT output did not contain enough daily states to build a trajectory.")

        total_reward = 0.0
        operation_count = 0
        for index in range(len(states) - 1):
            state = states[index]
            next_state = states[index + 1]
            action = action_map.get(state.day_index, CropAction())
            biomass_gain = max(0.0, next_state.biomass_kg_ha - state.biomass_kg_ha)
            step_operation_count = 1 if action.irrigation_mm > 0.0 or action.nitrogen_kg_ha > 0.0 else 0
            operation_count += step_operation_count
            reward = step_reward(
                biomass_gain=biomass_gain,
                irrigation_mm=action.irrigation_mm,
                nitrogen_kg_ha=action.nitrogen_kg_ha,
                water_stress=state.water_stress,
                nitrogen_stress=state.nitrogen_stress,
                operation_count=step_operation_count,
                weights=weights,
            )
            done = index == len(states) - 2
            if done:
                terminal_reward = reward_from_outcome(
                    yield_kg_ha=parsed.outcome.yield_kg_ha,
                    total_irrigation_mm=parsed.outcome.total_irrigation_mm,
                    total_nitrogen_kg_ha=parsed.outcome.total_nitrogen_kg_ha,
                    irrigation_budget_mm=scenario.irrigation_budget_mm,
                    nitrogen_budget_kg_ha=scenario.nitrogen_budget_kg_ha,
                    avg_water_stress=parsed.avg_water_stress,
                    avg_nitrogen_stress=parsed.avg_nitrogen_stress,
                    operation_count=operation_count,
                    environmental_metrics=dict(parsed.outcome.environmental_metrics),
                    weights=weights,
                    yield_floor_reference=scenario_yield_floor_reference(scenario),
                    anti_collapse_guardrail=anti_collapse_preferences(scenario.objective_context.to_dict()),
                    resource_settlement=resource_settlement_preferences(scenario.objective_context.to_dict()),
                )
                reward += terminal_reward
            total_reward += reward
            steps.append(
                TrajectoryStep(
                    state=state,
                    action=action,
                    reward=round(reward, 6),
                    next_state=next_state,
                    done=done,
                    info={
                        "engine_name": "dssat_official",
                        "policy_id": policy.policy_id,
                        "avg_water_stress": parsed.avg_water_stress,
                        "avg_nitrogen_stress": parsed.avg_nitrogen_stress,
                    },
                )
            )

        parsed.outcome.cumulative_reward = round(total_reward, 6)
        parsed.outcome.environmental_metrics = {
            **dict(parsed.outcome.environmental_metrics),
            "avg_water_stress": parsed.avg_water_stress,
            "avg_nitrogen_stress": parsed.avg_nitrogen_stress,
            "operation_count": float(operation_count),
        }

        return Trajectory(
            scenario_id=scenario.scenario_id,
            engine_name=scenario.engine_name,
            crop_name=scenario.crop_spec.crop_name,
            weather_regime=scenario.weather_regime,
            management_mode=scenario.management_mode,
            steps=steps,
            outcome=parsed.outcome,
            policy=policy.to_dict(),
        )
