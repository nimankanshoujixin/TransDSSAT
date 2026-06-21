from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class RealSubsetTreatment:
    treatment_no: int
    treatment_name: str
    cultivar_code: str
    cultivar_name: str
    observed_yield_kg_ha: float
    observed_anthesis_yyddd: str = ""
    observed_maturity_yyddd: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class RealSubsetAsset:
    subset_id: str
    subset_name: str
    crop_name: str
    source_root: str
    experiment_file: str
    observation_file: str
    genotype_append_file: str
    treatments: list[RealSubsetTreatment] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "subset_id": self.subset_id,
            "subset_name": self.subset_name,
            "crop_name": self.crop_name,
            "source_root": self.source_root,
            "experiment_file": self.experiment_file,
            "observation_file": self.observation_file,
            "genotype_append_file": self.genotype_append_file,
            "treatments": [item.to_dict() for item in self.treatments],
            "notes": list(self.notes),
        }


def _parse_cultivar_map(lines: list[str]) -> dict[int, tuple[str, str]]:
    result: dict[int, tuple[str, str]] = {}
    in_block = False
    for raw in lines:
        line = raw.rstrip("\n")
        if line.startswith("*CULTIVARS"):
            in_block = True
            continue
        if in_block and line.startswith("*"):
            break
        if not in_block or not line.strip() or line.lstrip().startswith("@"):
            continue
        parts = line.split()
        if len(parts) >= 4 and parts[0].isdigit():
            result[int(parts[0])] = (parts[2], " ".join(parts[3:]))
    return result


def _parse_treatment_factor_cu(lines: list[str]) -> dict[int, tuple[str, int]]:
    result: dict[int, tuple[str, int]] = {}
    in_block = False
    for raw in lines:
        line = raw.rstrip("\n")
        if line.startswith("*TREATMENTS"):
            in_block = True
            continue
        if in_block and line.startswith("*") and not line.startswith("*TREATMENTS"):
            break
        if not in_block or not line.strip() or line.lstrip().startswith("@"):
            continue
        parts = line.split()
        if len(parts) >= 7 and parts[0].isdigit():
            trno = int(parts[0])
            factor_values = parts[-13:]
            if len(factor_values) != 13:
                continue
            cu_idx = int(factor_values[0])
            treatment_name = " ".join(parts[4:-13]).strip()
            result[trno] = (treatment_name, cu_idx)
    return result


def _parse_ria_records(lines: list[str]) -> dict[int, dict[str, str]]:
    header: list[str] | None = None
    result: dict[int, dict[str, str]] = {}
    for raw in lines:
        line = raw.rstrip("\n")
        if line.lstrip().startswith("@TRNO"):
            header = line.split()
            continue
        if header is None or not line.strip() or line.lstrip().startswith("*") or line.lstrip().startswith("!"):
            continue
        parts = line.split()
        if len(parts) != len(header):
            continue
        row = dict(zip(header, parts))
        if row.get("@TRNO", "").isdigit():
            result[int(row["@TRNO"])] = row
    return result


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def load_real_subset_asset(subset_id: str, root: str | Path | None = None) -> RealSubsetAsset:
    root_path = Path(root) if root is not None else _repo_root() / "作物模型_20260616"
    if subset_id == "mx475_migrated":
        source_root = root_path / "01_4.7.5迁移后模型_美香粘"
        experiment_file = source_root / "MX232107.RIX"
        observation_file = source_root / "MX232107.RIA"
        genotype_append_file = source_root / "RICER048_IB2002_APPEND.CUL"
        crop_name = "rice"
        subset_name = "美香粘4.7.5迁移后模型"
    elif subset_id == "wuhu_rice_calibrated":
        source_root = root_path / "02_自己校准模型_芜湖水稻" / "dssat_native"
        experiment_file = source_root / "Rice" / "WHRI2101.RIX"
        observation_file = source_root / "Rice" / "WHRI2101.RIA"
        genotype_append_file = source_root / "Genotype" / "RICER048_WHRI_APPEND.CUL"
        crop_name = "rice"
        subset_name = "芜湖水稻校准模型"
    else:
        raise ValueError(f"Unsupported real subset asset: {subset_id}")

    exp_lines = experiment_file.read_text(encoding="utf-8", errors="ignore").splitlines()
    obs_lines = observation_file.read_text(encoding="utf-8", errors="ignore").splitlines()
    cultivar_map = _parse_cultivar_map(exp_lines)
    treatment_map = _parse_treatment_factor_cu(exp_lines)
    ria_records = _parse_ria_records(obs_lines)

    _raw_treatments: list[RealSubsetTreatment] = []
    for trno, (treatment_name, cu_idx) in sorted(treatment_map.items()):
        cultivar_code, cultivar_name = cultivar_map.get(cu_idx, ("", ""))
        obs = ria_records.get(trno, {})
        observed_yield = float(obs.get("HWAM", "0") or 0.0)
        _raw_treatments.append(
            RealSubsetTreatment(
                treatment_no=trno,
                treatment_name=treatment_name,
                cultivar_code=cultivar_code,
                cultivar_name=cultivar_name,
                observed_yield_kg_ha=observed_yield,
                observed_anthesis_yyddd=obs.get("ADAT", ""),
                observed_maturity_yyddd=obs.get("MDAT", ""),
            )
        )

    _exclude_uncalibrated_cultivars: dict[str, set[str]] = {
        "mx475_migrated": set(),
        "wuhu_rice_calibrated": {"WHR001", "WHR002", "WHR003", "WHR004", "WHR005", "WHR007", "WHR008", "WHR009"},
    }
    if subset_id in _exclude_uncalibrated_cultivars:
        excluded = _exclude_uncalibrated_cultivars[subset_id]
        treatments = [item for item in _raw_treatments if item.cultivar_code not in excluded]
    else:
        treatments = list(_raw_treatments)

    return RealSubsetAsset(
        subset_id=subset_id,
        subset_name=subset_name,
        crop_name=crop_name,
        source_root=str(source_root),
        experiment_file=str(experiment_file),
        observation_file=str(observation_file),
        genotype_append_file=str(genotype_append_file),
        treatments=treatments,
        notes=[
            "This asset loader only extracts the minimum fields needed for replay/test-subset construction.",
            "Observed yield comes directly from the source .RIA file in kg/ha units.",
        ],
    )
