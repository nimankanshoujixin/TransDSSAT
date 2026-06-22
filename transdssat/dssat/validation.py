from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import hashlib
import json
from typing import Any

from transdssat.dssat.parser import DSSATOutputParser
from transdssat.real_subset_runner import RealSubsetReplayResult


@dataclass(slots=True)
class DSSATFileComparison:
    file_name: str
    exists_left: bool
    exists_right: bool
    left_sha256: str
    right_sha256: str
    match: bool
    left_row_count: int | None = None
    right_row_count: int | None = None
    first_difference: dict[str, Any] | None = None

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


def compare_output_file(left_path: Path, right_path: Path, *, file_name: str) -> DSSATFileComparison:
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
        )

    parser = DSSATOutputParser()
    fixed_width = file_name == "Summary.OUT"
    left_rows = parser.parse_table(left_path, fixed_width=fixed_width)
    right_rows = parser.parse_table(right_path, fixed_width=fixed_width)
    left_normalized = [normalize_row(row) for row in left_rows]
    right_normalized = [normalize_row(row) for row in right_rows]
    first_difference = first_row_difference(left_normalized, right_normalized)
    return DSSATFileComparison(
        file_name=file_name,
        exists_left=True,
        exists_right=True,
        left_sha256=left_sha,
        right_sha256=right_sha,
        match=left_normalized == right_normalized,
        left_row_count=len(left_normalized),
        right_row_count=len(right_normalized),
        first_difference=first_difference,
    )


def normalize_row(row: dict[str, Any] | None) -> dict[str, str]:
    payload = dict(row or {})
    normalized: dict[str, str] = {}
    for key in sorted(payload):
        normalized[str(key)] = str(payload[key]).strip()
    return normalized


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
