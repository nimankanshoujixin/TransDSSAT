from __future__ import annotations

import argparse
from pathlib import Path


MINIMA_CODE = "999991"
MAXIMA_CODE = "999992"
RICE_CODES = tuple(f"WHR00{i}" for i in range(1, 10))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a traceable rice-compatible RICER048.CUL from the current runtime baseline and local calibration fragments."
    )
    parser.add_argument("--runtime-cultivar", required=True, help="Path to the current baseline RICER048.CUL")
    parser.add_argument("--append-fragment", required=True, help="Path to RICER048_WHRI_APPEND.CUL")
    parser.add_argument("--calibrated-fragment", required=True, help="Path to RICER048_WHR006_CALIBRATED.CUL")
    parser.add_argument("--output", required=True, help="Path to write the generated compatible RICER048.CUL")
    return parser.parse_args()


def _read_lines(path: str | Path) -> list[str]:
    return Path(path).read_text(encoding="utf-8", errors="ignore").splitlines()


def _format_runtime_like(raw_line: str) -> str:
    parts = raw_line.split()
    var_code = parts[0]
    expno = parts[-13]
    eco_code = parts[-12]
    numeric_fields = parts[-11:]
    cultivar_name = " ".join(parts[1:-13])
    return (
        f"{var_code:<6} "
        f"{cultivar_name:<21.21}"
        f"{expno}"
        " "
        f"{eco_code:<6}"
        f"{numeric_fields[0]:>6}"
        f"{numeric_fields[1]:>6}"
        f"{numeric_fields[2]:>6}"
        f"{numeric_fields[3]:>6}"
        f"{numeric_fields[4]:>6}"
        f"{numeric_fields[5]:>6}"
        f"{numeric_fields[6]:>6}"
        f"{numeric_fields[7]:>6}"
        f"{numeric_fields[8]:>6}"
        f"{numeric_fields[9]:>6}"
        f"{numeric_fields[10]:>6}"
    )


def _extract_fragment_rows(path: str | Path) -> dict[str, str]:
    rows: dict[str, str] = {}
    for line in _read_lines(path):
        stripped = line.strip()
        if not stripped or stripped.startswith(("!", "*", "@")):
            continue
        code = stripped.split()[0]
        if code.startswith("WHR"):
            rows[code] = _format_runtime_like(stripped)
    return rows


def _update_minmax(lines: list[str]) -> list[str]:
    updated: list[str] = []
    for line in lines:
        if line.startswith(f"{MINIMA_CODE} "):
            updated.append(
                "999991 MINIMA               . DFAULT 150.0   5.0 150.0  11.0  50.0 .0150  0.70  55.0  24.0  12.0  10.0"
            )
        elif line.startswith(f"{MAXIMA_CODE} "):
            updated.append(
                "999992 MAXIMA               . DFAULT 800.0 300.0 850.0  13.0  72.0 .0300  1.30  90.0  35.0  18.0  20.0"
            )
        else:
            updated.append(line)
    return updated


def build_rice_compat_baseline(
    runtime_cultivar: str | Path,
    append_fragment: str | Path,
    calibrated_fragment: str | Path,
    output: str | Path,
) -> Path:
    base_lines = _update_minmax(_read_lines(runtime_cultivar))
    fragment_rows = _extract_fragment_rows(append_fragment)
    calibrated_rows = _extract_fragment_rows(calibrated_fragment)
    fragment_rows.update(calibrated_rows)

    kept_lines: list[str] = []
    seen_codes: set[str] = set()
    for line in base_lines:
        stripped = line.strip()
        if not stripped:
            kept_lines.append(line)
            continue
        code = stripped.split()[0]
        if code in RICE_CODES:
            if code in fragment_rows:
                kept_lines.append(fragment_rows[code])
                seen_codes.add(code)
            continue
        kept_lines.append(line)

    if fragment_rows:
        insert_at = len(kept_lines)
        for index, line in enumerate(kept_lines):
            if line.startswith("IB0001 "):
                insert_at = index
                break
        missing_rows = [fragment_rows[code] for code in sorted(fragment_rows) if code not in seen_codes]
        kept_lines[insert_at:insert_at] = missing_rows

    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(kept_lines) + "\n", encoding="utf-8")
    return output_path


def main() -> None:
    args = parse_args()
    result = build_rice_compat_baseline(
        runtime_cultivar=args.runtime_cultivar,
        append_fragment=args.append_fragment,
        calibrated_fragment=args.calibrated_fragment,
        output=args.output,
    )
    print(result)


if __name__ == "__main__":
    main()
