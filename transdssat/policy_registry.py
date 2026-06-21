from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


IMPLEMENTATION_STATUSES = ("implemented", "conservative_approximation", "not_implemented")
BUDGET_HANDLING_MODES = ("original_absolute", "budget_normalized", "requires_reference_N")
TEST_SET_NAMES = ("general_random", "matched_slice")


def default_required_metadata() -> list[str]:
    return [
        "scenario_id",
        "crop_system",
        "crop_name",
        "season_name",
        "planting_date",
        "season_length_days",
        "weather_series",
        "soil_profile",
        "initial_root_zone_water_mm",
        "initial_nitrogen_kg_ha",
        "irrigation_budget_mm",
        "nitrogen_budget_kg_ha",
        "growth_stage_boundaries",
        "management_mode",
    ]


@dataclass(slots=True)
class GeneralizedRuleSpec:
    rule_id: str
    rule_name: str
    description: str
    trigger_conditions: list[str] = field(default_factory=list)
    required_metadata: list[str] = field(default_factory=default_required_metadata)
    budget_handling: str = "budget_normalized"
    outputs: list[str] = field(default_factory=lambda: ["season_policy"])
    applicable_crops: list[str] = field(default_factory=list)
    applicable_test_sets: list[str] = field(default_factory=lambda: list(TEST_SET_NAMES))
    implementation_status: str = "not_implemented"
    implementation_key: str = ""
    notes: str = ""
    missing_details: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class OriginalStrategySpec:
    strategy_id: str
    strategy_name: str
    description: str
    absolute_inputs: dict[str, Any] = field(default_factory=dict)
    required_metadata: list[str] = field(default_factory=default_required_metadata)
    required_scenario_slice: str = ""
    budget_handling: str = "original_absolute"
    applicable_crops: list[str] = field(default_factory=list)
    applicable_test_sets: list[str] = field(default_factory=lambda: ["matched_slice"])
    implementation_status: str = "not_implemented"
    implementation_key: str = ""
    policy_blueprint: dict[str, Any] = field(default_factory=dict)
    missing_details: list[str] = field(default_factory=list)
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class PolicyRegistryEntry:
    paper_id: str
    title: str
    source_url: str
    crop_system: str
    generalized_rules: list[GeneralizedRuleSpec] = field(default_factory=list)
    original_strategies: list[OriginalStrategySpec] = field(default_factory=list)
    required_metadata: list[str] = field(default_factory=default_required_metadata)
    applicable_test_sets: list[str] = field(default_factory=lambda: list(TEST_SET_NAMES))
    required_scenario_slice: str = ""
    budget_handling: str = "budget_normalized"
    notes: str = ""
    missing_details: list[str] = field(default_factory=list)
    implementation_status: str = "not_implemented"

    @property
    def original_strategy_available(self) -> bool:
        return any(item.implementation_status != "not_implemented" for item in self.original_strategies)

    @property
    def generalized_rule_available(self) -> bool:
        return any(item.implementation_status != "not_implemented" for item in self.generalized_rules)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["original_strategy_available"] = self.original_strategy_available
        payload["generalized_rule_available"] = self.generalized_rule_available
        return payload


@dataclass(slots=True)
class PolicyRegistry:
    entries: dict[str, PolicyRegistryEntry]

    def to_dict(self) -> dict[str, dict[str, Any]]:
        return {paper_id: entry.to_dict() for paper_id, entry in self.entries.items()}

    def generalized_rules(self) -> list[tuple[PolicyRegistryEntry, GeneralizedRuleSpec]]:
        items: list[tuple[PolicyRegistryEntry, GeneralizedRuleSpec]] = []
        for entry in self.entries.values():
            items.extend((entry, rule) for rule in entry.generalized_rules)
        return items

    def original_strategies(self) -> list[tuple[PolicyRegistryEntry, OriginalStrategySpec]]:
        items: list[tuple[PolicyRegistryEntry, OriginalStrategySpec]] = []
        for entry in self.entries.values():
            items.extend((entry, strategy) for strategy in entry.original_strategies)
        return items


def _placeholder_generalized_rule(paper_id: str, title: str, crop_system: str) -> GeneralizedRuleSpec:
    return GeneralizedRuleSpec(
        rule_id=f"{paper_id}_generalized_rule",
        rule_name=f"{title} generalized rule",
        description="Management docs require a generalized-rule entry, but current docs do not provide enough implementation detail.",
        applicable_crops=_applicable_crops_from_crop_system(crop_system),
        implementation_status="not_implemented",
        notes="Framework placeholder created strictly from policy-registry-spec-cn.md recommended-paper list.",
        missing_details=[
            "missing trigger conditions",
            "missing rule structure",
            "missing source_url",
        ],
    )


def _placeholder_original_strategy(paper_id: str, title: str, crop_system: str) -> OriginalStrategySpec:
    return OriginalStrategySpec(
        strategy_id=f"{paper_id}_original_strategy",
        strategy_name=f"{title} original strategy",
        description="Management docs require an original-strategy entry, but current docs do not provide exact treatment inputs.",
        applicable_crops=_applicable_crops_from_crop_system(crop_system),
        implementation_status="not_implemented",
        notes="Framework placeholder created strictly from policy-registry-spec-cn.md recommended-paper list.",
        missing_details=[
            "missing absolute treatment inputs",
            "missing required_scenario_slice details",
            "missing source_url",
        ],
    )


def _applicable_crops_from_crop_system(crop_system: str) -> list[str]:
    normalized = crop_system.lower()
    crops: list[str] = []
    if "wheat" in normalized:
        crops.append("wheat")
    if "maize" in normalized:
        crops.append("maize")
    return crops


def build_policy_registry() -> PolicyRegistry:
    entries: dict[str, PolicyRegistryEntry] = {}

    implemented_paper_id = "international_agrophysics_dssat_derived"
    implemented_title = "International Agrophysics DSSAT 推导方案"
    entries[implemented_paper_id] = PolicyRegistryEntry(
        paper_id=implemented_paper_id,
        title=implemented_title,
        source_url="",
        crop_system="wheat-maize rotation",
        generalized_rules=[
            GeneralizedRuleSpec(
                rule_id="literature_ncp_generalized_rule",
                rule_name="literature_ncp generalized rule",
                description=(
                    "Current project literature-informed derived rule. It preserves literature-inspired timing and "
                    "allocation structure while normalizing totals to the scenario budget."
                ),
                trigger_conditions=[
                    "legal season-level scenario",
                    "crop in {wheat, maize}",
                    "stage or daily season-level policy generation",
                ],
                applicable_crops=["wheat", "maize"],
                implementation_status="conservative_approximation",
                implementation_key="season_literature_ncp",
                notes=(
                    "Per testset-eval-protocol-cn.md, current literature_ncp must be treated as "
                    "generalized_rule / derived_rule, not original_strategy."
                ),
                missing_details=[
                    "management docs do not provide an exact paper URL for the current derived rule lineage",
                ],
            )
        ],
        original_strategies=[],
        budget_handling="budget_normalized",
        notes="This entry maps the already implemented literature_ncp baseline into the new policy_registry schema.",
        missing_details=[
            "source_url missing in current management docs",
            "paper-exact original strategy intentionally not claimed",
        ],
        implementation_status="conservative_approximation",
    )

    placeholder_entries = [
        ("awm_2023_water_fertilizer_practice", "AWM 2023 水肥节约管理实践", "wheat-maize rotation"),
        ("icarda_dripfert_n_management", "ICARDA 滴灌施肥氮管理", "winter wheat only"),
        ("awm_2024_rainfall_irrigation_optimization", "AWM 2024 基于降雨的灌溉优化", "wheat-maize rotation"),
        ("awm_2023_water_productivity_gap", "AWM 2023 缩小水分生产力差距", "wheat-maize rotation"),
        ("jafr_2024_interseason_n_allocation", "JAFR 2024 季间氮肥分配", "wheat-maize rotation"),
        ("agriculture_2023_surface_fertigation", "Agriculture 2023 地面灌溉随水施肥", "wheat-maize rotation"),
        ("awm_2020_winter_wheat_dripfert", "AWM 2020 冬小麦滴灌施肥", "winter wheat only"),
        ("sci_rep_2020_split_n_winter_wheat", "Sci Rep 2020 冬小麦分次施氮", "winter wheat only"),
        ("awm_2024_summer_maize_dripfert", "AWM 2024 夏玉米滴灌施肥", "summer maize only"),
    ]
    for paper_id, title, crop_system in placeholder_entries:
        entries[paper_id] = PolicyRegistryEntry(
            paper_id=paper_id,
            title=title,
            source_url="",
            crop_system=crop_system,
            generalized_rules=[_placeholder_generalized_rule(paper_id, title, crop_system)],
            original_strategies=[_placeholder_original_strategy(paper_id, title, crop_system)],
            budget_handling="original_absolute",
            notes="Registered as a placeholder because the listed management docs do not provide paper-exact inputs.",
            missing_details=[
                "source_url missing in current management docs",
                "exact absolute treatment inputs missing in current management docs",
                "matched-slice condition details missing in current management docs",
            ],
            implementation_status="not_implemented",
        )

    return PolicyRegistry(entries=entries)
