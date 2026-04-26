from __future__ import annotations

from dataclasses import asdict, dataclass

from transdssat.domain import Trajectory
from transdssat.scenarios import SimulationScenario


def _clip(value: float, lower: float = 0.0, upper: float = 100.0) -> float:
    return max(lower, min(upper, value))


def _safe_pct_gain(candidate: float, baseline: float) -> float:
    if abs(baseline) < 1e-6:
        return 0.0
    return (candidate / baseline - 1.0) * 100.0


def _centered_score(delta_pct: float, span_pct: float = 20.0) -> float:
    return round(_clip(50.0 + 50.0 * (delta_pct / span_pct)), 3)


def _stress_score(candidate: float, baseline: float, span: float = 0.30) -> float:
    delta = baseline - candidate
    return round(_clip(50.0 + 50.0 * (delta / span)), 3)


def average_water_stress(trajectory: Trajectory) -> float:
    if not trajectory.steps:
        return 0.0
    return round(sum(step.state.water_stress for step in trajectory.steps) / len(trajectory.steps), 6)


def average_nitrogen_stress(trajectory: Trajectory) -> float:
    if not trajectory.steps:
        return 0.0
    return round(sum(step.state.nitrogen_stress for step in trajectory.steps) / len(trajectory.steps), 6)


@dataclass(slots=True)
class PolicyScorecard:
    scenario_id: str
    crop_name: str
    weather_regime: str
    yield_kg_ha: float
    yield_gain_pct: float
    irrigation_mm: float
    nitrogen_kg_ha: float
    water_use_efficiency: float
    water_efficiency_gain_pct: float
    nitrogen_use_efficiency: float
    nitrogen_efficiency_gain_pct: float
    avg_water_stress: float
    avg_nitrogen_stress: float
    reward: float
    reward_gain: float
    budget_adherence_score: float
    production_score: float
    efficiency_score: float
    stress_score: float
    reward_score: float
    total_score_100: float

    def to_dict(self) -> dict:
        return asdict(self)


def score_trajectory(
    scenario: SimulationScenario,
    candidate: Trajectory,
    baseline: Trajectory,
) -> PolicyScorecard:
    baseline_outcome = baseline.outcome
    candidate_outcome = candidate.outcome
    candidate_water_stress = average_water_stress(candidate)
    candidate_n_stress = average_nitrogen_stress(candidate)
    baseline_water_stress = average_water_stress(baseline)
    baseline_n_stress = average_nitrogen_stress(baseline)

    yield_gain_pct = _safe_pct_gain(candidate_outcome.yield_kg_ha, baseline_outcome.yield_kg_ha)
    water_efficiency_gain_pct = _safe_pct_gain(
        candidate_outcome.water_use_efficiency,
        baseline_outcome.water_use_efficiency,
    )
    nitrogen_efficiency_gain_pct = _safe_pct_gain(
        candidate_outcome.nitrogen_use_efficiency,
        baseline_outcome.nitrogen_use_efficiency,
    )
    reward_gain = candidate_outcome.cumulative_reward - baseline_outcome.cumulative_reward

    irrigation_error = abs(candidate_outcome.total_irrigation_mm - scenario.irrigation_budget_mm) / max(
        1.0, scenario.irrigation_budget_mm
    )
    nitrogen_error = abs(candidate_outcome.total_nitrogen_kg_ha - scenario.nitrogen_budget_kg_ha) / max(
        1.0, scenario.nitrogen_budget_kg_ha
    )
    budget_adherence_score = round(
        _clip(100.0 - 50.0 * (irrigation_error + nitrogen_error)),
        3,
    )

    production_score = _centered_score(yield_gain_pct)
    efficiency_score = round(
        (
            _centered_score(water_efficiency_gain_pct, span_pct=25.0)
            + _centered_score(nitrogen_efficiency_gain_pct, span_pct=25.0)
        )
        / 2.0,
        3,
    )
    stress_score = round(
        (
            _stress_score(candidate_water_stress, baseline_water_stress)
            + _stress_score(candidate_n_stress, baseline_n_stress)
        )
        / 2.0,
        3,
    )
    reward_score = round(_clip(50.0 + 10.0 * reward_gain), 3)
    total_score = round(
        production_score * 0.35
        + efficiency_score * 0.25
        + stress_score * 0.15
        + reward_score * 0.15
        + budget_adherence_score * 0.10,
        3,
    )

    return PolicyScorecard(
        scenario_id=scenario.scenario_id,
        crop_name=scenario.crop_spec.crop_name,
        weather_regime=scenario.weather_regime,
        yield_kg_ha=round(candidate_outcome.yield_kg_ha, 3),
        yield_gain_pct=round(yield_gain_pct, 3),
        irrigation_mm=round(candidate_outcome.total_irrigation_mm, 3),
        nitrogen_kg_ha=round(candidate_outcome.total_nitrogen_kg_ha, 3),
        water_use_efficiency=round(candidate_outcome.water_use_efficiency, 5),
        water_efficiency_gain_pct=round(water_efficiency_gain_pct, 3),
        nitrogen_use_efficiency=round(candidate_outcome.nitrogen_use_efficiency, 5),
        nitrogen_efficiency_gain_pct=round(nitrogen_efficiency_gain_pct, 3),
        avg_water_stress=candidate_water_stress,
        avg_nitrogen_stress=candidate_n_stress,
        reward=round(candidate_outcome.cumulative_reward, 6),
        reward_gain=round(reward_gain, 6),
        budget_adherence_score=budget_adherence_score,
        production_score=production_score,
        efficiency_score=efficiency_score,
        stress_score=stress_score,
        reward_score=reward_score,
        total_score_100=total_score,
    )


def summarize_scorecards(scorecards: list[PolicyScorecard]) -> dict:
    if not scorecards:
        return {
            "scenario_count": 0,
            "mean_total_score_100": 0.0,
            "mean_reward": 0.0,
            "mean_yield_kg_ha": 0.0,
            "mean_yield_gain_pct": 0.0,
            "mean_water_use_efficiency": 0.0,
            "mean_nitrogen_use_efficiency": 0.0,
        }

    count = len(scorecards)
    return {
        "scenario_count": count,
        "mean_total_score_100": round(sum(card.total_score_100 for card in scorecards) / count, 3),
        "mean_reward": round(sum(card.reward for card in scorecards) / count, 6),
        "mean_reward_gain": round(sum(card.reward_gain for card in scorecards) / count, 6),
        "mean_yield_kg_ha": round(sum(card.yield_kg_ha for card in scorecards) / count, 3),
        "mean_yield_gain_pct": round(sum(card.yield_gain_pct for card in scorecards) / count, 3),
        "mean_water_use_efficiency": round(sum(card.water_use_efficiency for card in scorecards) / count, 5),
        "mean_nitrogen_use_efficiency": round(sum(card.nitrogen_use_efficiency for card in scorecards) / count, 5),
    }
