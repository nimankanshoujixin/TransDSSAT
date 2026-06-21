from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from transdssat.real_subset_assets import RealSubsetAsset, RealSubsetTreatment, load_real_subset_asset
from transdssat.scenarios import build_cultivar_context, build_crop_specs
from transdssat.season import SeasonPolicy, StageDecision, apply_control_mode


@dataclass(slots=True)
class RealSubsetReplayCase:
    subset_id: str
    treatment: RealSubsetTreatment
    asset: RealSubsetAsset
    crop_name: str
    cultivar_id: str
    observed_yield_kg_ha: float
    source_root: str
    experiment_file: str
    observation_file: str
    genotype_append_file: str
    baseline_policy: SeasonPolicy
    management_anchor: str = "original_management_replay"
    compatibility_notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "subset_id": self.subset_id,
            "treatment": self.treatment.to_dict(),
            "crop_name": self.crop_name,
            "cultivar_id": self.cultivar_id,
            "observed_yield_kg_ha": self.observed_yield_kg_ha,
            "source_root": self.source_root,
            "experiment_file": self.experiment_file,
            "observation_file": self.observation_file,
            "genotype_append_file": self.genotype_append_file,
            "baseline_policy": self.baseline_policy.to_dict(),
            "management_anchor": self.management_anchor,
            "compatibility_notes": list(self.compatibility_notes),
        }


@dataclass(slots=True)
class RealSubsetReplacementPlan:
    subset_id: str
    treatment_no: int
    control_mode: str
    anchor_case: RealSubsetReplayCase
    reference_policy: SeasonPolicy
    candidate_policy: SeasonPolicy
    composed_policy: SeasonPolicy
    observed_phenology: dict[str, dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "subset_id": self.subset_id,
            "treatment_no": self.treatment_no,
            "control_mode": self.control_mode,
            "anchor_case": self.anchor_case.to_dict(),
            "reference_policy": self.reference_policy.to_dict(),
            "candidate_policy": self.candidate_policy.to_dict(),
            "composed_policy": self.composed_policy.to_dict(),
            "observed_phenology": dict(self.observed_phenology),
        }


def _normalize_phenology_token(raw_value: str) -> dict[str, Any]:
    token = str(raw_value or "").strip()
    normalized: dict[str, Any] = {
        "raw": token,
        "yyddd": "",
        "year": None,
        "doy": None,
        "iso_date": "",
    }
    if not token:
        return normalized

    year: int | None = None
    doy: int | None = None
    if len(token) == 5 and token.isdigit():
        prefix = int(token[:2])
        year = 2000 + prefix if prefix < 70 else 1900 + prefix
        doy = int(token[2:])
        normalized["yyddd"] = token
    elif len(token) == 3 and token.isdigit():
        doy = int(token)

    if doy is None or doy <= 0:
        return normalized
    if year is None:
        year = 2000
    try:
        iso_date = (date(year, 1, 1) + timedelta(days=doy - 1)).isoformat()
    except ValueError:
        return normalized
    normalized["year"] = year
    normalized["doy"] = doy
    normalized["iso_date"] = iso_date
    return normalized


def _default_placeholder_policy(subset_id: str, treatment_no: int) -> SeasonPolicy:
    # The first replay pass focuses on original-management reproduction.
    # We keep a no-op placeholder policy object so the same interface can later
    # host "replace only water/fertilizer strategy" candidates without changing callers.
    return SeasonPolicy(
        policy_id=f"{subset_id}-tr{treatment_no:02d}-baseline-placeholder",
        scenario_id=f"{subset_id}-tr{treatment_no:02d}",
        actions=[
            StageDecision(stage="emergence", day_index=0, date="1970-01-01", irrigation_mm=0.0, nitrogen_kg_ha=0.0),
        ],
    )


def _yyddd_to_date(value: str) -> date:
    token = str(value).strip()
    year = int(token[:2])
    doy = int(token[2:])
    full_year = 1900 + year if year >= 50 else 2000 + year
    return date(full_year, 1, 1) + timedelta(days=doy - 1)


def _parse_treatment_planting_dates(lines: list[str]) -> dict[int, str]:
    result: dict[int, str] = {}
    in_block = False
    for raw in lines:
        line = raw.rstrip("\n")
        if line.startswith("*PLANTING DETAILS"):
            in_block = True
            continue
        if in_block and line.startswith("*") and not line.startswith("*PLANTING DETAILS"):
            break
        if not in_block or not line.strip() or line.lstrip().startswith("@"):
            continue
        parts = line.split()
        if len(parts) >= 2 and parts[0].isdigit():
            result[int(parts[0])] = parts[1]
    return result


def _parse_irrigation_events(lines: list[str], treatment_no: int) -> list[tuple[str, float]]:
    events: list[tuple[str, float]] = []
    in_block = False
    for raw in lines:
        line = raw.rstrip("\n")
        if line.startswith("*IRRIGATION AND WATER MANAGEMENT"):
            in_block = True
            continue
        if in_block and line.startswith("*") and not line.startswith("*IRRIGATION AND WATER MANAGEMENT"):
            break
        if not in_block or not line.strip() or line.lstrip().startswith("@"):
            continue
        parts = line.split()
        if len(parts) >= 4 and parts[0].isdigit() and int(parts[0]) == treatment_no and parts[1].isdigit() and len(parts[1]) == 5:
            events.append((parts[1], float(parts[3])))
    return events


def _parse_fertilizer_events(lines: list[str], treatment_no: int) -> list[tuple[str, float]]:
    events: list[tuple[str, float]] = []
    in_block = False
    for raw in lines:
        line = raw.rstrip("\n")
        if line.startswith("*FERTILIZERS"):
            in_block = True
            continue
        if in_block and line.startswith("*") and not line.startswith("*FERTILIZERS"):
            break
        if not in_block or not line.strip() or line.lstrip().startswith("@"):
            continue
        parts = line.split()
        if len(parts) >= 6 and parts[0].isdigit() and int(parts[0]) == treatment_no and parts[1].isdigit() and len(parts[1]) == 5:
            events.append((parts[1], float(parts[5])))
    return events


def _source_management_policy(asset: RealSubsetAsset, treatment_no: int) -> SeasonPolicy:
    lines = Path(asset.experiment_file).read_text(encoding="utf-8", errors="ignore").splitlines()
    planting_dates = _parse_treatment_planting_dates(lines)
    planting_yyddd = planting_dates.get(treatment_no, "")
    if not planting_yyddd:
        return _default_placeholder_policy(asset.subset_id, treatment_no)
    planting_date = _yyddd_to_date(planting_yyddd)

    events_by_day: dict[int, dict[str, float | str]] = {}
    for yyddd, irrigation_mm in _parse_irrigation_events(lines, treatment_no):
        event_date = _yyddd_to_date(yyddd)
        day_index = (event_date - planting_date).days
        slot = events_by_day.setdefault(
            day_index,
            {"date": event_date.isoformat(), "irrigation_mm": 0.0, "nitrogen_kg_ha": 0.0},
        )
        slot["irrigation_mm"] = float(slot["irrigation_mm"]) + irrigation_mm
    for yyddd, nitrogen_kg_ha in _parse_fertilizer_events(lines, treatment_no):
        event_date = _yyddd_to_date(yyddd)
        day_index = (event_date - planting_date).days
        slot = events_by_day.setdefault(
            day_index,
            {"date": event_date.isoformat(), "irrigation_mm": 0.0, "nitrogen_kg_ha": 0.0},
        )
        slot["nitrogen_kg_ha"] = float(slot["nitrogen_kg_ha"]) + nitrogen_kg_ha

    actions = [
        StageDecision(
            stage=f"event_{index + 1:02d}",
            day_index=day_index,
            date=str(payload["date"]),
            irrigation_mm=round(float(payload["irrigation_mm"]), 3),
            nitrogen_kg_ha=round(float(payload["nitrogen_kg_ha"]), 3),
        )
        for index, (day_index, payload) in enumerate(sorted(events_by_day.items()))
    ]
    if not actions:
        return _default_placeholder_policy(asset.subset_id, treatment_no)
    return SeasonPolicy(
        policy_id=f"{asset.subset_id}-tr{treatment_no:02d}-source-management",
        scenario_id=f"{asset.subset_id}-tr{treatment_no:02d}",
        actions=actions,
    )


def compose_real_subset_management_policy(
    reference_policy: SeasonPolicy,
    candidate_policy: SeasonPolicy,
    *,
    control_mode: str = "joint",
) -> SeasonPolicy:
    # Real-data subset experiments should preserve all non-water/non-nitrogen
    # management from the validated replay clone and only swap the intended
    # action channel when running controlled interventions.
    return apply_control_mode(candidate_policy, reference_policy, control_mode=control_mode)


def build_real_subset_replacement_plan(
    case: RealSubsetReplayCase,
    candidate_policy: SeasonPolicy,
    *,
    control_mode: str = "joint",
    reference_policy: SeasonPolicy | None = None,
) -> RealSubsetReplacementPlan:
    reference = reference_policy or case.baseline_policy
    composed = compose_real_subset_management_policy(reference, candidate_policy, control_mode=control_mode)
    observed_phenology = {
        "anthesis": _normalize_phenology_token(case.treatment.observed_anthesis_yyddd),
        "maturity": _normalize_phenology_token(case.treatment.observed_maturity_yyddd),
    }
    return RealSubsetReplacementPlan(
        subset_id=case.subset_id,
        treatment_no=case.treatment.treatment_no,
        control_mode=control_mode,
        anchor_case=case,
        reference_policy=reference,
        candidate_policy=candidate_policy,
        composed_policy=composed,
        observed_phenology=observed_phenology,
    )


def write_real_subset_policy_tsv(policy: SeasonPolicy, output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["stage\tdate\tday_index\tirrigation_mm\tnitrogen_kg_ha"]
    for action in policy.actions:
        lines.append(
            f"{action.stage}\t{action.date}\t{action.day_index}\t"
            f"{action.irrigation_mm}\t{action.nitrogen_kg_ha}"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def load_real_subset_replay_case(
    subset_id: str,
    treatment_no: int,
    root: str | Path | None = None,
) -> RealSubsetReplayCase:
    asset = load_real_subset_asset(subset_id, root=root)
    treatment = next((item for item in asset.treatments if item.treatment_no == treatment_no), None)
    if treatment is None:
        raise ValueError(f"Treatment {treatment_no} not found in subset {subset_id}")

    if subset_id == "mx475_migrated":
        cultivar_context = build_cultivar_context("rice", "IB2002", site_name="wuhu")
        compatibility_notes = [
            "Validated replay target is treatment 1 under batch-mode single-treatment execution.",
            "Native replay currently depends on mirrored root-level Genotype and StandardData files inside the clone.",
        ]
    elif subset_id == "wuhu_rice_calibrated":
        cultivar_context = build_cultivar_context("rice", "IB2002", site_name="wuhu")
        compatibility_notes = [
            "Validated replay target is treatment 11 under batch-mode single-treatment execution.",
            "Current replay result is a bridge result that depends on replay-only accepted-code remap plus EXPNO='.' normalization.",
        ]
    else:
        raise ValueError(f"Unsupported subset id: {subset_id}")

    return RealSubsetReplayCase(
        subset_id=subset_id,
        treatment=treatment,
        asset=asset,
        crop_name="rice",
        cultivar_id=cultivar_context.cultivar.cultivar_id,
        observed_yield_kg_ha=treatment.observed_yield_kg_ha,
        source_root=asset.source_root,
        experiment_file=asset.experiment_file,
        observation_file=asset.observation_file,
        genotype_append_file=asset.genotype_append_file,
        baseline_policy=_source_management_policy(asset, treatment_no),
        compatibility_notes=compatibility_notes,
    )
