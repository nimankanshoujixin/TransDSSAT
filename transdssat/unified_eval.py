from __future__ import annotations

from dataclasses import asdict, dataclass, field
import statistics
from typing import Any

from transdssat.evaluation import PolicyScorecard, score_trajectory, summarize_scorecards
from transdssat.rl import evaluate_policy_for_scenario
from transdssat.season import SeasonPolicy
from transdssat.stepwise_adapter import project_policy_to_stepwise
from transdssat.stepwise_policy import StepwisePolicy, rollout_stepwise_policy
from transdssat.strategies import ExecutablePolicy, StrategyBuildContext, StrategyDefinition, strategy_applicability
from transdssat.testset import LiteratureMatchedSlice, TestScenarioRecord


@dataclass(slots=True)
class StrategyExecutionRecord:
    strategy_id: str
    scenario_id: str
    status: str
    scorecard: dict[str, Any] | None = None
    reasons: list[str] = field(default_factory=list)
    execution_interface: str = "season_policy"
    adapter_summary: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _stdev(values: list[float]) -> float:
    if len(values) <= 1:
        return 0.0
    return round(statistics.pstdev(values), 6)


def _summarize_scorecards(scorecards: list[PolicyScorecard]) -> dict[str, Any]:
    if not scorecards:
        summary = summarize_scorecards(scorecards)
        summary["std_yield_kg_ha"] = 0.0
        summary["std_reward"] = 0.0
        summary["std_total_score_100"] = 0.0
        return summary
    summary = summarize_scorecards(scorecards)
    summary["std_yield_kg_ha"] = _stdev([card.yield_kg_ha for card in scorecards])
    summary["std_reward"] = _stdev([card.reward for card in scorecards])
    summary["std_total_score_100"] = _stdev([card.total_score_100 for card in scorecards])
    return summary


class UnifiedEvaluationRunner:
    def __init__(
        self,
        strategies: list[StrategyDefinition],
        decision_granularity: str = "stage",
        reference_strategy_id: str = "equal_allocation",
    ) -> None:
        self.decision_granularity = decision_granularity
        self.reference_strategy_id = reference_strategy_id
        self.strategies = {strategy.strategy_id: strategy for strategy in strategies}
        if reference_strategy_id not in self.strategies:
            raise ValueError(f"Reference strategy {reference_strategy_id} is not registered.")

    def evaluate(
        self,
        general_random_records: list[TestScenarioRecord],
        matched_slices: list[LiteratureMatchedSlice],
    ) -> dict[str, Any]:
        policy_cache: dict[tuple[str, str], ExecutablePolicy] = {}
        general_random_summary = self._evaluate_collection(
            records=general_random_records,
            test_set_name="general_random",
            policy_cache=policy_cache,
        )
        matched_slice_summary = [
            self._evaluate_slice(item, policy_cache=policy_cache)
            for item in matched_slices
        ]
        applicability_summary = self._aggregate_applicability(general_random_summary, matched_slice_summary)
        return {
            "decision_granularity": self.decision_granularity,
            "general_random_summary": general_random_summary,
            "matched_slice_summary": matched_slice_summary,
            "strategy_applicability_summary": applicability_summary,
        }

    def _aggregate_applicability(
        self,
        general_random_summary: dict[str, Any],
        matched_slice_summary: list[dict[str, Any]],
    ) -> dict[str, Any]:
        aggregate: dict[str, dict[str, Any]] = {}
        all_sections = [general_random_summary["strategies"]]
        all_sections.extend(slice_summary["strategies"] for slice_summary in matched_slice_summary)
        for section in all_sections:
            for row in section:
                bucket = aggregate.setdefault(
                    row["strategy_id"],
                    {
                        "strategy_id": row["strategy_id"],
                        "strategy_kind": row["strategy_kind"],
                        "applicable_count": 0,
                        "not_applicable_count": 0,
                        "failed_count": 0,
                        "not_applicable_reasons": {},
                    },
                )
                bucket["applicable_count"] += row["applicable_count"]
                bucket["not_applicable_count"] += row["not_applicable_count"]
                bucket["failed_count"] += row["failed_count"]
                for reason, count in row["not_applicable_reasons"].items():
                    bucket["not_applicable_reasons"][reason] = bucket["not_applicable_reasons"].get(reason, 0) + count
        return aggregate

    def _evaluate_slice(
        self,
        item: LiteratureMatchedSlice,
        policy_cache: dict[tuple[str, str], ExecutablePolicy],
    ) -> dict[str, Any]:
        section = self._evaluate_collection(
            records=item.scenarios,
            test_set_name="matched_slice",
            policy_cache=policy_cache,
        )
        applicable_strategies = [row["strategy_id"] for row in section["strategies"] if row["applicable_count"] > 0]
        not_applicable_strategies = [
            row["strategy_id"] for row in section["strategies"] if row["not_applicable_count"] > 0 and row["applicable_count"] == 0
        ]
        return {
            "paper_id": item.metadata.paper_id,
            "slice_id": item.metadata.slice_id,
            "matched_scenario_count": len(item.scenarios),
            "approximated_conditions": item.metadata.approximated_conditions,
            "missing_conditions": item.metadata.missing_conditions,
            "applicable_strategies": applicable_strategies,
            "not_applicable_strategies": not_applicable_strategies,
            "strategies": section["strategies"],
            "executions": section["executions"],
        }

    def _evaluate_collection(
        self,
        records: list[TestScenarioRecord],
        test_set_name: str,
        policy_cache: dict[tuple[str, str], ExecutablePolicy],
    ) -> dict[str, Any]:
        strategy_rows: list[dict[str, Any]] = []
        executions: list[dict[str, Any]] = []
        for strategy in self.strategies.values():
            scorecards: list[PolicyScorecard] = []
            applicable_count = 0
            not_applicable_count = 0
            failed_count = 0
            reason_counter: dict[str, int] = {}
            for record in records:
                execution = self._evaluate_strategy_on_record(
                    strategy=strategy,
                    record=record,
                    test_set_name=test_set_name,
                    policy_cache=policy_cache,
                )
                executions.append(execution.to_dict())
                if execution.status == "applicable" and execution.scorecard is not None:
                    applicable_count += 1
                    scorecards.append(PolicyScorecard(**execution.scorecard))
                elif execution.status == "not_applicable":
                    not_applicable_count += 1
                    for reason in execution.reasons:
                        reason_counter[reason] = reason_counter.get(reason, 0) + 1
                else:
                    failed_count += 1
                    for reason in execution.reasons:
                        reason_counter[reason] = reason_counter.get(reason, 0) + 1
            strategy_rows.append(
                {
                    "strategy_id": strategy.strategy_id,
                    "strategy_kind": strategy.strategy_kind,
                    "paper_id": strategy.paper_id,
                    "implementation_status": strategy.implementation_status,
                    "applicable_count": applicable_count,
                    "not_applicable_count": not_applicable_count,
                    "failed_count": failed_count,
                    "not_applicable_reasons": reason_counter,
                    "summary": _summarize_scorecards(scorecards),
                }
            )
        return {
            "test_set_name": test_set_name,
            "reference_strategy_id": self.reference_strategy_id,
            "scenario_count": len(records),
            "strategies": strategy_rows,
            "executions": executions,
        }

    def _evaluate_strategy_on_record(
        self,
        strategy: StrategyDefinition,
        record: TestScenarioRecord,
        test_set_name: str,
        policy_cache: dict[tuple[str, str], ExecutablePolicy],
    ) -> StrategyExecutionRecord:
        try:
            reference_policy = self._build_reference_policy(record, strategy, test_set_name, policy_cache)
            applicability = strategy_applicability(
                strategy,
                record,
                test_set_name=test_set_name,
                reference_policy_available=(strategy.reference_strategy_id == "" or reference_policy is not None),
            )
            if not applicability.applicable:
                return StrategyExecutionRecord(
                    strategy_id=strategy.strategy_id,
                    scenario_id=record.scenario.scenario_id,
                    status="not_applicable",
                    reasons=applicability.reasons + list(strategy.missing_details),
                )
            assert strategy.builder is not None
            build_context = StrategyBuildContext(
                scenario_record=record,
                decision_granularity=self.decision_granularity,
                test_set_name=test_set_name,
                reference_policy=reference_policy,
                slice_metadata=record.slice_metadata.to_dict() if record.slice_metadata is not None else None,
            )
            candidate_policy = strategy.builder(record.scenario, build_context)
            policy_cache[(record.scenario.scenario_id, strategy.strategy_id)] = candidate_policy

            baseline_strategy = self.strategies[self.reference_strategy_id]
            baseline_context = StrategyBuildContext(
                scenario_record=record,
                decision_granularity=self.decision_granularity,
                test_set_name=test_set_name,
            )
            assert baseline_strategy.builder is not None
            baseline_policy = policy_cache.get((record.scenario.scenario_id, self.reference_strategy_id))
            if baseline_policy is None:
                baseline_policy = baseline_strategy.builder(record.scenario, baseline_context)
                policy_cache[(record.scenario.scenario_id, self.reference_strategy_id)] = baseline_policy

            candidate_execution_interface = "season_policy"
            candidate_adapter_summary = None
            if self.decision_granularity == "stepwise":
                candidate_trajectory, candidate_execution_interface, candidate_adapter_summary = self._execute_stepwise_policy(
                    record.scenario,
                    candidate_policy,
                )
                baseline_trajectory, _, _ = self._execute_stepwise_policy(record.scenario, baseline_policy)
            else:
                assert isinstance(candidate_policy, SeasonPolicy)
                assert isinstance(baseline_policy, SeasonPolicy)
                candidate_trajectory = evaluate_policy_for_scenario(record.scenario, candidate_policy)
                baseline_trajectory = evaluate_policy_for_scenario(record.scenario, baseline_policy)
            scorecard = score_trajectory(record.scenario, candidate_trajectory, baseline_trajectory)
            return StrategyExecutionRecord(
                strategy_id=strategy.strategy_id,
                scenario_id=record.scenario.scenario_id,
                status="applicable",
                scorecard=scorecard.to_dict(),
                execution_interface=candidate_execution_interface,
                adapter_summary=candidate_adapter_summary,
            )
        except Exception as exc:  # pragma: no cover - smoke-tested via CLI
            return StrategyExecutionRecord(
                strategy_id=strategy.strategy_id,
                scenario_id=record.scenario.scenario_id,
                status="failed",
                reasons=[f"{type(exc).__name__}:{exc}"],
            )

    def _build_reference_policy(
        self,
        record: TestScenarioRecord,
        strategy: StrategyDefinition,
        test_set_name: str,
        policy_cache: dict[tuple[str, str], ExecutablePolicy],
    ) -> ExecutablePolicy | None:
        if not strategy.reference_strategy_id:
            return None
        cache_key = (record.scenario.scenario_id, strategy.reference_strategy_id)
        if cache_key in policy_cache:
            return policy_cache[cache_key]
        reference_strategy = self.strategies.get(strategy.reference_strategy_id)
        if reference_strategy is None or reference_strategy.builder is None:
            return None
        applicability = strategy_applicability(reference_strategy, record, test_set_name=test_set_name)
        if not applicability.applicable:
            return None
        reference_context = StrategyBuildContext(
            scenario_record=record,
            decision_granularity=self.decision_granularity,
            test_set_name=test_set_name,
        )
        policy = reference_strategy.builder(record.scenario, reference_context)
        policy_cache[cache_key] = policy
        return policy

    def _execute_stepwise_policy(
        self,
        scenario,
        policy: ExecutablePolicy,
    ) -> tuple[Any, str, dict[str, Any] | None]:
        if isinstance(policy, StepwisePolicy):
            trajectory = rollout_stepwise_policy(scenario, policy)
            return trajectory, "native_stepwise_policy", policy.summary().to_dict()
        projected_policy, projection = project_policy_to_stepwise(scenario, policy)
        trajectory = evaluate_policy_for_scenario(scenario, projected_policy)
        return trajectory, "stepwise_adapter", projection.to_dict()
