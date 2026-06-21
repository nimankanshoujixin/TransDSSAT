from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from transdssat.data_generator import generate_training_data


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate real-data-driven TransDSSAT training scenario records.")
    parser.add_argument("--output-dir", required=True, help="Directory for generated JSONL + metadata outputs.")
    parser.add_argument("--count-per-crop", type=int, default=5000, help="Scenario count for each crop.")
    parser.add_argument("--crops", nargs="+", default=["rice", "maize"], help="Crops to generate.")
    parser.add_argument("--seed", type=int, default=0, help="Random seed.")
    parser.add_argument(
        "--disable-splicing",
        action="store_true",
        help="Disable temperature/precipitation year splicing.",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    bundle = generate_training_data(
        count_per_crop=args.count_per_crop,
        crops=tuple(args.crops),
        seed=args.seed,
        use_splicing=not args.disable_splicing,
    )

    records_path = output_dir / "records.jsonl"
    with records_path.open("w", encoding="utf-8") as handle:
        for record in bundle.records:
            handle.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")

    metadata = {
        "summary": bundle.summary,
        "validation_errors": bundle.validation_errors,
        "output_files": {
            "records": str(records_path),
        },
    }
    metadata_path = output_dir / "metadata.json"
    metadata_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")

    print(json.dumps(metadata, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
