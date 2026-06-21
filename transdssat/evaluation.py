from __future__ import annotations

from dataclasses import asdict, dataclass

from transdssat.domain import Trajectory
from transdssat.scenarios import SimulationScenario, scenario_yield_floor_reference


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


def _mean(values: list[float], digits: int = 6) -> float:
    if not values:
        return 0.0
    return round(sum(values) / len(values), digits)


def _environmental_metric(trajectory: Trajectory, metric_id: str) -> float:
    return float(trajectory.outcome.environmental_metrics.get(metric_id, 0.0))


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
    yield_floor_reference_kg_ha: float
    yield_floor_gap_ratio: float
    yield_floor_attainment_pct: float
    irrigation_budget_violation_ratio: float
    nitrogen_budget_violation_ratio: float
    budget_adherence_score: float
    total_drainage_mm: float
    total_nitrogen_leached_kg_ha: float
    terminal_root_zone_water_mm: float
    terminal_soil_nitrogen_kg_ha: float
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
    yield_floor_reference = scenario_yield_floor_reference(scenario)
    yield_floor_gap_ratio = max(0.0, yield_floor_reference - candidate_outcome.yield_kg_ha) / max(1.0, yield_floor_reference)
    yield_floor_attainment_pct = min(candidate_outcome.yield_kg_ha / max(1.0, yield_floor_reference), 1.0) * 100.0

    irrigation_violation_ratio = max(0.0, candidate_outcome.total_irrigation_mm - scenario.irrigation_budget_mm) / max(
        1.0, scenario.irrigation_budget_mm
    )
    nitrogen_violation_ratio = max(0.0, candidate_outcome.total_nitrogen_kg_ha - scenario.nitrogen_budget_kg_ha) / max(
        1.0, scenario.nitrogen_budget_kg_ha
    )
    budget_adherence_score = round(
        _clip(100.0 - 50.0 * (irrigation_violation_ratio + nitrogen_violation_ratio)),
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
        yield_floor_reference_kg_ha=round(yield_floor_reference, 3),
        yield_floor_gap_ratio=round(yield_floor_gap_ratio, 6),
        yield_floor_attainment_pct=round(yield_floor_attainment_pct, 3),
        irrigation_budget_violation_ratio=round(irrigation_violation_ratio, 6),
        nitrogen_budget_violation_ratio=round(nitrogen_violation_ratio, 6),
        budget_adherence_score=budget_adherence_score,
        total_drainage_mm=round(_environmental_metric(candidate, "total_drainage_mm"), 6),
        total_nitrogen_leached_kg_ha=round(_environmental_metric(candidate, "total_nitrogen_leached_kg_ha"), 6),
        terminal_root_zone_water_mm=round(_environmental_metric(candidate, "terminal_root_zone_water_mm"), 6),
        terminal_soil_nitrogen_kg_ha=round(_environmental_metric(candidate, "terminal_soil_nitrogen_kg_ha"), 6),
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
            "mean_reward_gain": 0.0,
            "mean_yield_kg_ha": 0.0,
            "mean_yield_gain_pct": 0.0,
            "mean_yield_floor_reference_kg_ha": 0.0,
            "mean_yield_floor_gap_ratio": 0.0,
            "mean_yield_floor_attainment_pct": 0.0,
            "mean_irrigation_mm": 0.0,
            "mean_nitrogen_kg_ha": 0.0,
            "mean_irrigation_budget_violation_ratio": 0.0,
            "mean_nitrogen_budget_violation_ratio": 0.0,
            "mean_water_use_efficiency": 0.0,
            "mean_nitrogen_use_efficiency": 0.0,
            "mean_budget_adherence_score": 0.0,
            "mean_avg_water_stress": 0.0,
            "mean_avg_nitrogen_stress": 0.0,
            "mean_total_drainage_mm": 0.0,
            "mean_total_nitrogen_leached_kg_ha": 0.0,
            "mean_terminal_root_zone_water_mm": 0.0,
            "mean_terminal_soil_nitrogen_kg_ha": 0.0,
        }

    count = len(scorecards)
    return {
        "scenario_count": count,
        "mean_total_score_100": _mean([card.total_score_100 for card in scorecards], digits=3),
        "mean_reward": _mean([card.reward for card in scorecards], digits=6),
        "mean_reward_gain": _mean([card.reward_gain for card in scorecards], digits=6),
        "mean_yield_kg_ha": _mean([card.yield_kg_ha for card in scorecards], digits=3),
        "mean_yield_gain_pct": _mean([card.yield_gain_pct for card in scorecards], digits=3),
        "mean_yield_floor_reference_kg_ha": _mean([card.yield_floor_reference_kg_ha for card in scorecards], digits=3),
        "mean_yield_floor_gap_ratio": _mean([card.yield_floor_gap_ratio for card in scorecards], digits=6),
        "mean_yield_floor_attainment_pct": _mean([card.yield_floor_attainment_pct for card in scorecards], digits=3),
        "mean_irrigation_mm": _mean([card.irrigation_mm for card in scorecards], digits=3),
        "mean_nitrogen_kg_ha": _mean([card.nitrogen_kg_ha for card in scorecards], digits=3),
        "mean_irrigation_budget_violation_ratio": _mean(
            [card.irrigation_budget_violation_ratio for card in scorecards],
            digits=6,
        ),
        "mean_nitrogen_budget_violation_ratio": _mean(
            [card.nitrogen_budget_violation_ratio for card in scorecards],
            digits=6,
        ),
        "mean_water_use_efficiency": _mean([card.water_use_efficiency for card in scorecards], digits=5),
        "mean_nitrogen_use_efficiency": _mean([card.nitrogen_use_efficiency for card in scorecards], digits=5),
        "mean_budget_adherence_score": _mean([card.budget_adherence_score for card in scorecards], digits=3),
        "mean_avg_water_stress": _mean([card.avg_water_stress for card in scorecards], digits=6),
        "mean_avg_nitrogen_stress": _mean([card.avg_nitrogen_stress for card in scorecards], digits=6),
        "mean_total_drainage_mm": _mean([card.total_drainage_mm for card in scorecards], digits=6),
        "mean_total_nitrogen_leached_kg_ha": _mean(
            [card.total_nitrogen_leached_kg_ha for card in scorecards],
            digits=6,
        ),
        "mean_terminal_root_zone_water_mm": _mean(
            [card.terminal_root_zone_water_mm for card in scorecards],
            digits=6,
        ),
        "mean_terminal_soil_nitrogen_kg_ha": _mean(
            [card.terminal_soil_nitrogen_kg_ha for card in scorecards],
            digits=6,
        ),
    }
