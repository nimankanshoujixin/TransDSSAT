from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, timedelta
from pathlib import Path
import hashlib
import json
import math
from typing import Any

from transdssat.dssat.parser import DSSATOutputParser
from transdssat.scenarios import SimulationScenario
from transdssat.real_subset_runner import RealSubsetReplayResult
from transdssat.season import SeasonPolicy, StageDecision


@dataclass(slots=True)
class DSSATFileComparison:
    file_name: str
    exists_left: bool
    exists_right: bool
    left_sha256: str
    right_sha256: str
    match: bool
    semantic_match: bool
    left_row_count: int | None = None
    right_row_count: int | None = None
    first_difference: dict[str, Any] | None = None
    semantic_first_difference: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class DSSATRuntimeCaseComparison:
    subset_id: str
    treatment_no: int
    left_runtime_label: str
    right_runtime_label: str
    left_run_dir: str
    right_run_dir: str
    replay_match: bool
    yield_match: bool
    anthesis_match: bool
    maturity_match: bool
    summary_row_match: bool
    evaluate_row_match: bool
    file_comparisons: list[DSSATFileComparison]
    left_replay: dict[str, Any]
    right_replay: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["file_comparisons"] = [item.to_dict() for item in self.file_comparisons]
        return payload


@dataclass(slots=True)
class DSSATOutputRowSelector:
    selector_kind: str
    selector_value: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def compare_real_subset_replays(
    left: RealSubsetReplayResult,
    right: RealSubsetReplayResult,
    *,
    left_runtime_label: str,
    right_runtime_label: str,
) -> DSSATRuntimeCaseComparison:
    left_run_dir = Path(left.run_dir)
    right_run_dir = Path(right.run_dir)
    file_comparisons = [
        compare_output_file(left_run_dir / file_name, right_run_dir / file_name, file_name=file_name)
        for file_name in ("Summary.OUT", "PlantGro.OUT", "SoilWat.OUT", "SoilNi.OUT", "Evaluate.OUT")
    ]
    summary_row_match = normalize_row(left.summary_row) == normalize_row(right.summary_row)
    evaluate_row_match = normalize_row(left.evaluate_row) == normalize_row(right.evaluate_row)
    yield_match = _rounded_equal(left.simulated_yield_kg_ha, right.simulated_yield_kg_ha)
    anthesis_match = str(left.simulated_anthesis_yyddd or "") == str(right.simulated_anthesis_yyddd or "")
    maturity_match = str(left.simulated_maturity_yyddd or "") == str(right.simulated_maturity_yyddd or "")
    replay_match = (
        yield_match
        and anthesis_match
        and maturity_match
        and summary_row_match
        and evaluate_row_match
        and all(item.match for item in file_comparisons)
    )
    return DSSATRuntimeCaseComparison(
        subset_id=left.subset_id,
        treatment_no=left.treatment_no,
        left_runtime_label=left_runtime_label,
        right_runtime_label=right_runtime_label,
        left_run_dir=str(left_run_dir),
        right_run_dir=str(right_run_dir),
        replay_match=replay_match,
        yield_match=yield_match,
        anthesis_match=anthesis_match,
        maturity_match=maturity_match,
        summary_row_match=summary_row_match,
        evaluate_row_match=evaluate_row_match,
        file_comparisons=file_comparisons,
        left_replay=left.to_dict(),
        right_replay=right.to_dict(),
    )


def compare_output_file(
    left_path: Path,
    right_path: Path,
    *,
    file_name: str,
    selector: DSSATOutputRowSelector | None = None,
) -> DSSATFileComparison:
    left_exists = left_path.exists()
    right_exists = right_path.exists()
    left_sha = sha256_for_path(left_path) if left_exists else ""
    right_sha = sha256_for_path(right_path) if right_exists else ""
    if not left_exists or not right_exists:
        return DSSATFileComparison(
            file_name=file_name,
            exists_left=left_exists,
            exists_right=right_exists,
            left_sha256=left_sha,
            right_sha256=right_sha,
            match=False,
            semantic_match=False,
        )

    parser = DSSATOutputParser()
    fixed_width = file_name == "Summary.OUT"
    left_rows = parser.parse_table(left_path, fixed_width=fixed_width)
    right_rows = parser.parse_table(right_path, fixed_width=fixed_width)
    active_selector = selector or infer_active_output_selector_from_rows(left_rows)
    if active_selector is not None:
        left_rows = _reparse_rows_for_active_run(parser, left_path, file_name, active_selector)
        right_rows = _reparse_rows_for_active_run(parser, right_path, file_name, active_selector)
    if active_selector is not None:
        left_rows = filter_rows_for_selector(left_rows, active_selector)
        right_rows = filter_rows_for_selector(right_rows, active_selector)
    left_normalized = [normalize_row(row) for row in left_rows]
    right_normalized = [normalize_row(row) for row in right_rows]
    left_semantic = [normalize_row_for_semantic_comparison(file_name, row) for row in left_rows]
    right_semantic = [normalize_row_for_semantic_comparison(file_name, row) for row in right_rows]
    first_difference = first_row_difference(left_normalized, right_normalized)
    semantic_first_difference = first_row_difference(left_semantic, right_semantic)
    return DSSATFileComparison(
        file_name=file_name,
        exists_left=True,
        exists_right=True,
        left_sha256=left_sha,
        right_sha256=right_sha,
        match=left_normalized == right_normalized,
        semantic_match=left_semantic == right_semantic,
        left_row_count=len(left_normalized),
        right_row_count=len(right_normalized),
        first_difference=first_difference,
        semantic_first_difference=semantic_first_difference,
    )


def normalize_row(row: dict[str, Any] | None) -> dict[str, str]:
    payload = dict(row or {})
    normalized: dict[str, str] = {}
    for key in sorted(payload):
        normalized[str(key)] = str(payload[key]).strip()
    return normalized


TREATMENT_SELECTOR_KEYS: tuple[str, ...] = ("TRNO", "TRTNO", "TN")
RUN_SELECTOR_KEYS: tuple[str, ...] = ("RUNNO",)


def infer_active_output_selector(run_dir: Path) -> DSSATOutputRowSelector | None:
    parser = DSSATOutputParser()
    for file_name, fixed_width in (("Summary.OUT", True), ("Evaluate.OUT", False), ("PlantGro.OUT", False)):
        path = run_dir / file_name
        if not path.exists():
            continue
        selector = infer_active_output_selector_from_rows(parser.parse_table(path, fixed_width=fixed_width))
        if selector is not None:
            return selector
    return None


def infer_active_output_selector_from_rows(rows: list[dict[str, str]]) -> DSSATOutputRowSelector | None:
    if not rows:
        return None
    first_row = rows[0]
    treatment_value = _extract_selector_value(first_row, TREATMENT_SELECTOR_KEYS)
    if treatment_value is not None:
        return DSSATOutputRowSelector(selector_kind="treatment", selector_value=treatment_value)
    run_value = _extract_selector_value(first_row, RUN_SELECTOR_KEYS)
    if run_value is not None:
        return DSSATOutputRowSelector(selector_kind="run", selector_value=run_value)
    return None


def filter_rows_for_selector(
    rows: list[dict[str, str]],
    selector: DSSATOutputRowSelector | None,
) -> list[dict[str, str]]:
    if selector is None or not rows:
        return rows
    keys = TREATMENT_SELECTOR_KEYS if selector.selector_kind == "treatment" else RUN_SELECTOR_KEYS
    filtered = [row for row in rows if _extract_selector_value(row, keys) == selector.selector_value]
    return filtered or rows


def _extract_selector_value(row: dict[str, Any], keys: tuple[str, ...]) -> int | None:
    for key in keys:
        value = str(row.get(key, "")).strip()
        if value.isdigit():
            return int(value)
    return None


def _reparse_rows_for_active_run(
    parser: DSSATOutputParser,
    path: Path,
    file_name: str,
    selector: DSSATOutputRowSelector,
) -> list[dict[str, str]]:
    fixed_width = file_name == "Summary.OUT"
    run_number = selector.selector_value if selector.selector_kind in {"treatment", "run"} else None
    return parser.parse_table(path, run_number=run_number, fixed_width=fixed_width)


SEMANTICALLY_IGNORED_FIELDS_BY_FILE: dict[str, set[str]] = {
    "Summary.OUT": {"NI#M", "OPAM", "OPTAM"},
    "SoilWat.OUT": {"DTWTM"},
    "SoilNi.OUT": {"NI#M"},
}

SEMANTIC_NUMERIC_PRECISION_BY_FILE_AND_FIELD: dict[str, dict[str, int]] = {
    "Summary.OUT": {
        # Rice parity can differ here only by text rounding (e.g. 120.9 vs 121.).
        "CH4EM": 0,
    },
}


def normalize_row_for_semantic_comparison(file_name: str, row: dict[str, Any] | None) -> dict[str, str]:
    payload = dict(row or {})
    ignored_fields = SEMANTICALLY_IGNORED_FIELDS_BY_FILE.get(file_name, set())
    precision_overrides = SEMANTIC_NUMERIC_PRECISION_BY_FILE_AND_FIELD.get(file_name, {})
    normalized: dict[str, str] = {}
    for key in sorted(payload):
        key_str = str(key)
        if key_str in ignored_fields:
            continue
        normalized[key_str] = normalize_scalar(payload[key], digits=precision_overrides.get(key_str, 6))
    return normalized


def normalize_scalar(value: Any, *, digits: int = 6) -> str:
    rendered = str(value).strip()
    if not rendered:
        return ""
    try:
        numeric = float(rendered)
    except ValueError:
        return rendered
    if not math.isfinite(numeric):
        return rendered
    if numeric == 0.0:
        return "0"
    normalized = f"{numeric:.{digits}f}".rstrip("0").rstrip(".")
    return normalized or "0"


def first_row_difference(left_rows: list[dict[str, str]], right_rows: list[dict[str, str]]) -> dict[str, Any] | None:
    max_len = max(len(left_rows), len(right_rows))
    for index in range(max_len):
        left_row = left_rows[index] if index < len(left_rows) else None
        right_row = right_rows[index] if index < len(right_rows) else None
        if left_row != right_row:
            return {
                "row_index": index,
                "left": left_row,
                "right": right_row,
            }
    return None


def summarize_runtime_comparisons(items: list[DSSATRuntimeCaseComparison]) -> dict[str, Any]:
    total_cases = len(items)
    matched_cases = sum(1 for item in items if item.replay_match)
    failing_cases = [
        {
            "subset_id": item.subset_id,
            "treatment_no": item.treatment_no,
            "yield_match": item.yield_match,
            "anthesis_match": item.anthesis_match,
            "maturity_match": item.maturity_match,
            "summary_row_match": item.summary_row_match,
            "evaluate_row_match": item.evaluate_row_match,
            "mismatched_files": [file.file_name for file in item.file_comparisons if not file.match],
        }
        for item in items
        if not item.replay_match
    ]
    return {
        "case_count": total_cases,
        "matched_case_count": matched_cases,
        "all_cases_match": matched_cases == total_cases,
        "failing_cases": failing_cases,
    }


def sha256_for_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_runtime_comparison_report(
    output_path: Path,
    *,
    left_runtime_root: str,
    right_runtime_root: str,
    left_runtime_label: str,
    right_runtime_label: str,
    case_comparisons: list[DSSATRuntimeCaseComparison],
) -> dict[str, Any]:
    report = {
        "left_runtime_label": left_runtime_label,
        "right_runtime_label": right_runtime_label,
        "left_runtime_root": left_runtime_root,
        "right_runtime_root": right_runtime_root,
        "summary": summarize_runtime_comparisons(case_comparisons),
        "cases": [item.to_dict() for item in case_comparisons],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report


def _rounded_equal(left: float, right: float, *, digits: int = 6) -> bool:
    return round(float(left), digits) == round(float(right), digits)


def load_interactive_session_manifest(protocol_dir: Path) -> dict[str, Any]:
    manifest_path = protocol_dir / "session_manifest.json"
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def load_interactive_session_scenario(protocol_dir: Path) -> SimulationScenario:
    manifest = load_interactive_session_manifest(protocol_dir)
    scenario_payload = manifest.get("scenario")
    if not isinstance(scenario_payload, dict):
        raise RuntimeError(f"Interactive session manifest did not contain a scenario payload: {protocol_dir}")
    return SimulationScenario.from_dict(scenario_payload)


def reconstruct_interactive_session_policy(protocol_dir: Path) -> SeasonPolicy:
    manifest = load_interactive_session_manifest(protocol_dir)
    scenario_payload = manifest.get("scenario")
    if not isinstance(scenario_payload, dict):
        raise RuntimeError(f"Interactive session manifest did not contain a scenario payload: {protocol_dir}")
    scenario = SimulationScenario.from_dict(scenario_payload)
    ready_path = protocol_dir / "session_ready.json"
    ready_payload = json.loads(ready_path.read_text(encoding="utf-8"))
    current_day_index = int(dict(ready_payload.get("state", {})).get("day_index", 0))
    planting_date = date.fromisoformat(scenario.planting_date)

    actions: list[StageDecision] = []
    request_paths = sorted(protocol_dir.glob("step_request_*.json"))
    for request_path in request_paths:
        request_payload = json.loads(request_path.read_text(encoding="utf-8"))
        action_payload = dict(request_payload.get("action", {}))
        irrigation_mm = round(float(action_payload.get("irrigation_mm", 0.0)), 3)
        nitrogen_kg_ha = round(float(action_payload.get("nitrogen_kg_ha", 0.0)), 3)
        if irrigation_mm > 0.0 or nitrogen_kg_ha > 0.0:
            actions.append(
                StageDecision(
                    stage=f"interactive_step_{len(actions) + 1:02d}",
                    day_index=current_day_index,
                    date=(planting_date + timedelta(days=current_day_index)).isoformat(),
                    irrigation_mm=irrigation_mm,
                    nitrogen_kg_ha=nitrogen_kg_ha,
                )
            )
        response_path = protocol_dir / request_path.name.replace("step_request_", "step_response_")
        if response_path.exists():
            response_payload = json.loads(response_path.read_text(encoding="utf-8"))
            current_day_index = int(dict(response_payload.get("next_state", {})).get("day_index", current_day_index))
        else:
            current_day_index += int(request_payload.get("decision_interval_days", scenario.decision_context.decision_interval_days))

    return SeasonPolicy(
        policy_id=f"{scenario.scenario_id}-interactive-session-reconstructed",
        scenario_id=scenario.scenario_id,
        actions=actions,
    )
