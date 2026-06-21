from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable

from transdssat.policy_registry import GeneralizedRuleSpec, OriginalStrategySpec, PolicyRegistry, PolicyRegistryEntry
from transdssat.rl import build_daily_policy_from_allocations, sample_policies, SeasonRLTransformer
from transdssat.scenarios import SimulationScenario
from transdssat.season import (
    CONTROL_MODES,
    SeasonPolicy,
    STAGES,
    apply_control_mode,
    build_baseline_policy,
    build_event_policy,
    build_stage_split_policy,
)
from transdssat.stepwise_policy import (
    StepwisePolicy,
    apply_stepwise_control_mode,
    build_equal_allocation_stepwise_policy,
    build_heuristic_legacy_stepwise_policy,
    build_heuristic_stepwise_policy,
    build_literature_stepwise_policy,
    build_stepwise_policy_from_season_policy,
)
from transdssat.testset import TestScenarioRecord, scenario_metadata_map


ExecutablePolicy = SeasonPolicy | StepwisePolicy
PolicyBuilder = Callable[[SimulationScenario, "StrategyBuildContext"], ExecutablePolicy]


@dataclass(slots=True)
class StrategyBuildContext:
    scenario_record: TestScenarioRecord
    decision_granularity: str
    test_set_name: str
    reference_policy: ExecutablePolicy | None = None
    slice_metadata: dict[str, Any] | None = None


@dataclass(slots=True)
class ApplicabilityResult:
    status: str
    reasons: list[str] = field(default_factory=list)

    @property
    def applicable(self) -> bool:
        return self.status == "applicable"


@dataclass(slots=True)
class StrategyDefinition:
    strategy_id: str
    display_name: str
    strategy_kind: str
    paper_id: str | None
    implementation_status: str
    applicable_test_sets: list[str]
    required_metadata: list[str]
    applicable_crops: list[str]
    required_scenario_slice: str = ""
    budget_handling: str = ""
    control_mode: str | None = None
    reference_strategy_id: str = ""
    notes: str = ""
    missing_details: list[str] = field(default_factory=list)
    builder: PolicyBuilder | None = None


class AIPolicyFamily(ABC):
    family_id: str
    display_name: str

    @abstractmethod
    def supports_mode(self, control_mode: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def build_policy(
        self,
        scenario: SimulationScenario,
        control_mode: str,
        decision_granularity: str,
        reference_policy: ExecutablePolicy | None,
    ) -> ExecutablePolicy:
        raise NotImplementedError


class ReferenceAIPolicyFamily(AIPolicyFamily):
    family_id = "reference_ai"
    display_name = "Reference-backed AI interface"

    def supports_mode(self, control_mode: str) -> bool:
        return control_mode in CONTROL_MODES

    def build_policy(
        self,
        scenario: SimulationScenario,
        control_mode: str,
        decision_granularity: str,
        reference_policy: ExecutablePolicy | None,
    ) -> ExecutablePolicy:
        if decision_granularity == "stepwise":
            candidate_policy = build_heuristic_stepwise_policy(scenario)
            if reference_policy is not None:
                if not isinstance(reference_policy, StepwisePolicy):
                    reference_policy = build_stepwise_policy_from_season_policy(
                        scenario,
                        reference_policy,
                        suffix="reference-stepwise",
                        notes=["reference_policy_converted_for_stepwise_control_mode"],
                    )
                return apply_stepwise_control_mode(
                    candidate_policy,
                    reference_policy,
                    control_mode=control_mode,
                    scenario=scenario,
                )
            return candidate_policy
        if reference_policy is not None:
            return apply_control_mode(reference_policy, reference_policy, control_mode=control_mode)
        return build_baseline_policy(
            scenario,
            baseline_name="heuristic",
            decision_granularity=_season_policy_granularity(decision_granularity),
            budget_source="scenario",
        )


class CheckpointAIPolicyFamily(AIPolicyFamily):
    family_id = "checkpoint_ai"
    display_name = "RL checkpoint AI family"

    def __init__(self, checkpoints: dict[str, str]) -> None:
        import torch

        self.models: dict[str, SeasonRLTransformer] = {}
        for control_mode, checkpoint_path in checkpoints.items():
            checkpoint = torch.load(checkpoint_path, map_location="cpu")
            model = SeasonRLTransformer()
            model.load_state_dict(checkpoint["model_state_dict"])
            model.eval()
            self.models[control_mode] = model

    def supports_mode(self, control_mode: str) -> bool:
        return control_mode in self.models

    def build_policy(
        self,
        scenario: SimulationScenario,
        control_mode: str,
        decision_granularity: str,
        reference_policy: ExecutablePolicy | None,
    ) -> ExecutablePolicy:
        season_policy_granularity = _season_policy_granularity(decision_granularity)
        if control_mode not in self.models:
            raise RuntimeError(f"Checkpoint for control mode {control_mode} is not available.")
        if control_mode != "joint" and reference_policy is None:
            raise RuntimeError(f"{control_mode} requires a reference policy.")
        season_reference_policies: list[SeasonPolicy] | None = None
        if reference_policy is not None:
            if isinstance(reference_policy, StepwisePolicy):
                raise RuntimeError("Checkpoint AI stepwise mode requires a season-policy reference.")
            season_reference_policies = [reference_policy]
        sampled = sample_policies(
            self.models[control_mode],
            [scenario],
            greedy=True,
            decision_granularity=season_policy_granularity,
            control_mode=control_mode,
            reference_policies=season_reference_policies,
        )
        sampled_policy = sampled[0].policy
        if decision_granularity == "stepwise":
            return build_stepwise_policy_from_season_policy(
                scenario,
                sampled_policy,
                suffix=f"checkpoint-{control_mode}",
                notes=["checkpoint_daily_policy_aggregated_to_decision_windows"],
            )
        return sampled_policy


def _season_policy_granularity(decision_granularity: str) -> str:
    return "daily" if decision_granularity == "stepwise" else decision_granularity


def _build_equal_allocation_policy(scenario: SimulationScenario, context: StrategyBuildContext) -> ExecutablePolicy:
    if context.decision_granularity == "stepwise":
        return build_equal_allocation_stepwise_policy(scenario)
    season_policy_granularity = _season_policy_granularity(context.decision_granularity)
    if season_policy_granularity == "daily":
        season_days = scenario.crop_spec.season_length_days
        uniform_shares = [1.0 for _ in range(season_days)]
        return build_daily_policy_from_allocations(scenario, uniform_shares, uniform_shares)
    equal_split = {stage: 1.0 / len(STAGES) for stage in STAGES}
    return build_stage_split_policy(
        scenario,
        irrigation_splits=equal_split,
        nitrogen_splits=equal_split,
        total_irrigation_mm=scenario.irrigation_budget_mm,
        total_nitrogen_kg_ha=scenario.nitrogen_budget_kg_ha,
        suffix="equal-allocation",
    )


def _build_heuristic_policy(scenario: SimulationScenario, context: StrategyBuildContext) -> ExecutablePolicy:
    if context.decision_granularity == "stepwise":
        return build_heuristic_stepwise_policy(scenario)
    return build_baseline_policy(
        scenario,
        baseline_name="heuristic",
        decision_granularity=_season_policy_granularity(context.decision_granularity),
        budget_source="scenario",
    )


def _build_heuristic_legacy_policy(scenario: SimulationScenario, context: StrategyBuildContext) -> ExecutablePolicy:
    if context.decision_granularity == "stepwise":
        return build_heuristic_legacy_stepwise_policy(scenario)
    return build_baseline_policy(
        scenario,
        baseline_name="heuristic",
        decision_granularity=_season_policy_granularity(context.decision_granularity),
        budget_source="scenario",
    )


def _build_literature_ncp_policy(scenario: SimulationScenario, context: StrategyBuildContext) -> ExecutablePolicy:
    if context.decision_granularity == "stepwise":
        return build_literature_stepwise_policy(scenario)
    return build_baseline_policy(
        scenario,
        baseline_name="literature_ncp",
        decision_granularity=_season_policy_granularity(context.decision_granularity),
        budget_source="scenario",
    )


def _build_original_strategy_from_blueprint(
    scenario: SimulationScenario,
    context: StrategyBuildContext,
    strategy_spec: OriginalStrategySpec,
) -> SeasonPolicy:
    blueprint = strategy_spec.policy_blueprint
    mode = blueprint.get("mode")
    if mode == "stage_split":
        return build_stage_split_policy(
            scenario,
            irrigation_splits=blueprint["irrigation_splits"],
            nitrogen_splits=blueprint["nitrogen_splits"],
            total_irrigation_mm=float(strategy_spec.absolute_inputs["irrigation_mm"]),
            total_nitrogen_kg_ha=float(strategy_spec.absolute_inputs["nitrogen_kg_ha"]),
            suffix=strategy_spec.strategy_id,
        )
    if mode == "event_plan":
        return build_event_policy(
            scenario,
            event_plan=tuple(blueprint["event_plan"]),
            total_irrigation_mm=float(strategy_spec.absolute_inputs["irrigation_mm"]),
            total_nitrogen_kg_ha=float(strategy_spec.absolute_inputs["nitrogen_kg_ha"]),
            suffix=strategy_spec.strategy_id,
        )
    raise RuntimeError(f"Original strategy {strategy_spec.strategy_id} does not have an executable blueprint.")


def _make_original_strategy_builder(strategy_spec: OriginalStrategySpec) -> PolicyBuilder | None:
    if strategy_spec.implementation_key != "policy_blueprint":
        return None

    def _builder(scenario: SimulationScenario, context: StrategyBuildContext) -> ExecutablePolicy:
        return _build_original_strategy_from_blueprint(scenario, context, strategy_spec)

    return _builder


def strategy_applicability(
    strategy: StrategyDefinition,
    record: TestScenarioRecord,
    test_set_name: str,
    reference_policy_available: bool = True,
) -> ApplicabilityResult:
    reasons: list[str] = []
    if test_set_name not in strategy.applicable_test_sets:
        reasons.append(f"test_set_not_supported:{test_set_name}")
    if strategy.applicable_crops and record.scenario.crop_spec.crop_name not in strategy.applicable_crops:
        reasons.append(f"crop_not_supported:{record.scenario.crop_spec.crop_name}")
    if strategy.required_scenario_slice:
        actual_slice_id = record.slice_metadata.slice_id if record.slice_metadata is not None else ""
        if actual_slice_id != strategy.required_scenario_slice:
            reasons.append(f"slice_mismatch:{actual_slice_id or 'missing'}")
    metadata = scenario_metadata_map(record)
    for field_name in strategy.required_metadata:
        if field_name not in metadata or metadata[field_name] in ("", None):
            reasons.append(f"missing_metadata:{field_name}")
    if strategy.implementation_status == "not_implemented":
        reasons.append("implementation_status:not_implemented")
    if strategy.builder is None:
        reasons.append("builder_unavailable")
    if strategy.reference_strategy_id and not reference_policy_available:
        reasons.append(f"missing_reference_policy:{strategy.reference_strategy_id}")
    return ApplicabilityResult(status="applicable" if not reasons else "not_applicable", reasons=reasons)


def _generalized_rule_builder(rule: GeneralizedRuleSpec) -> PolicyBuilder | None:
    if rule.implementation_key == "season_literature_ncp":
        return _build_literature_ncp_policy
    return None


def _simple_baselines() -> list[StrategyDefinition]:
    required = [
        "scenario_id",
        "crop_name",
        "planting_date",
        "season_length_days",
        "irrigation_budget_mm",
        "nitrogen_budget_kg_ha",
        "growth_stage_boundaries",
    ]
    return [
        StrategyDefinition(
            strategy_id="equal_allocation",
            display_name="equal_allocation",
            strategy_kind="simple_baseline",
            paper_id=None,
            implementation_status="implemented",
            applicable_test_sets=["general_random", "matched_slice"],
            required_metadata=required,
            applicable_crops=["wheat", "maize"],
            budget_handling="budget_normalized",
            notes="Uniformly allocates seasonal irrigation and nitrogen totals over the current decision grid.",
            builder=_build_equal_allocation_policy,
        ),
        StrategyDefinition(
            strategy_id="heuristic",
            display_name="heuristic",
            strategy_kind="simple_baseline",
            paper_id=None,
            implementation_status="implemented",
            applicable_test_sets=["general_random", "matched_slice"],
            required_metadata=required,
            applicable_crops=["wheat", "maize"],
            budget_handling="budget_normalized",
            notes="Existing project heuristic baseline kept as a simple project baseline.",
            builder=_build_heuristic_policy,
        ),
        StrategyDefinition(
            strategy_id="heuristic_legacy",
            display_name="heuristic_legacy",
            strategy_kind="simple_baseline",
            paper_id=None,
            implementation_status="implemented",
            applicable_test_sets=["general_random", "matched_slice"],
            required_metadata=required,
            applicable_crops=["wheat", "maize"],
            budget_handling="budget_normalized",
            notes="Legacy plan-first-clip-later stepwise heuristic kept for side-by-side validation.",
            builder=_build_heuristic_legacy_policy,
        ),
    ]


def build_default_strategies(
    registry: PolicyRegistry,
    ai_family: AIPolicyFamily | None = None,
    ai_reference_strategy_id: str = "literature_ncp_generalized_rule",
) -> list[StrategyDefinition]:
    strategies = _simple_baselines()
    for entry, rule in registry.generalized_rules():
        strategies.append(
            StrategyDefinition(
                strategy_id=rule.rule_id,
                display_name=rule.rule_name,
                strategy_kind="generalized_rule",
                paper_id=entry.paper_id,
                implementation_status=rule.implementation_status,
                applicable_test_sets=rule.applicable_test_sets,
                required_metadata=rule.required_metadata,
                applicable_crops=rule.applicable_crops,
                budget_handling=rule.budget_handling,
                notes=rule.notes,
                missing_details=list(rule.missing_details),
                builder=_generalized_rule_builder(rule),
            )
        )
    for entry, original in registry.original_strategies():
        strategies.append(
            StrategyDefinition(
                strategy_id=original.strategy_id,
                display_name=original.strategy_name,
                strategy_kind="original_strategy",
                paper_id=entry.paper_id,
                implementation_status=original.implementation_status,
                applicable_test_sets=original.applicable_test_sets,
                required_metadata=original.required_metadata,
                applicable_crops=original.applicable_crops,
                required_scenario_slice=original.required_scenario_slice,
                budget_handling=original.budget_handling,
                notes=original.notes,
                missing_details=list(original.missing_details),
                builder=_make_original_strategy_builder(original),
            )
        )
    if ai_family is not None:
        for control_mode in CONTROL_MODES:
            if not ai_family.supports_mode(control_mode):
                continue
            strategies.append(
                StrategyDefinition(
                    strategy_id=f"AI-{control_mode}",
                    display_name=f"AI-{control_mode}",
                    strategy_kind="ai_policy_family",
                    paper_id=None,
                    implementation_status="implemented",
                    applicable_test_sets=["general_random", "matched_slice"],
                    required_metadata=[
                        "scenario_id",
                        "crop_name",
                        "planting_date",
                        "season_length_days",
                        "weather_series",
                        "soil_profile",
                        "irrigation_budget_mm",
                        "nitrogen_budget_kg_ha",
                    ],
                    applicable_crops=["wheat", "maize"],
                    control_mode=control_mode,
                    reference_strategy_id="" if control_mode == "joint" else ai_reference_strategy_id,
                    notes=f"AI policy family interface for {control_mode}.",
                    builder=lambda scenario, context, mode=control_mode, family=ai_family: family.build_policy(
                        scenario,
                        control_mode=mode,
                        decision_granularity=context.decision_granularity,
                        reference_policy=context.reference_policy,
                    ),
                )
            )
    return strategies
