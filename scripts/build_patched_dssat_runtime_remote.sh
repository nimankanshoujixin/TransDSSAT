#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat >&2 <<'EOF'
Usage:
  bash scripts/build_patched_dssat_runtime_remote.sh \
    --overlay-root <overlay-root> \
    [--source-root <dssat-source-root>] \
    [--build-root <build-root>] \
    [--runtime-root <patched-runtime-root>] \
    [--build-type <Release|Debug>] \
    [--report-json <path>] \
    [--clean]

Purpose:
  Copy a small Fortran overlay onto a temporary patched DSSAT source tree,
  rebuild dscsm048 with CMake, and refresh the patched runtime binary.

Overlay layout:
  <overlay-root>/CSM_Main/CSM.for
  <overlay-root>/CSM_Main/LAND.for
  <overlay-root>/Management/MgmtOps.for

Any file present under overlay-root will be copied over the source clone at
the same relative path.
EOF
}

OVERLAY_ROOT=""
SOURCE_ROOT="${SOURCE_ROOT:-/fs/fast/u2021201693/lym/dssat-csm-os-v4.8.5}"
BUILD_ROOT="${BUILD_ROOT:-/tmp/transdssat_dssat_build}"
RUNTIME_ROOT="${RUNTIME_ROOT:-/fs/fast/u2021201693/lym/dssat-runtime-patched}"
BUILD_TYPE="${BUILD_TYPE:-Release}"
REPORT_JSON=""
CLEAN=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --overlay-root)
      OVERLAY_ROOT="${2:-}"
      shift 2
      ;;
    --source-root)
      SOURCE_ROOT="${2:-}"
      shift 2
      ;;
    --build-root)
      BUILD_ROOT="${2:-}"
      shift 2
      ;;
    --runtime-root)
      RUNTIME_ROOT="${2:-}"
      shift 2
      ;;
    --build-type)
      BUILD_TYPE="${2:-}"
      shift 2
      ;;
    --report-json)
      REPORT_JSON="${2:-}"
      shift 2
      ;;
    --clean)
      CLEAN=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 2
      ;;
  esac
done

if [[ -z "$OVERLAY_ROOT" ]]; then
  echo "--overlay-root is required." >&2
  usage
  exit 2
fi

if [[ ! -d "$OVERLAY_ROOT" ]]; then
  echo "Overlay root does not exist: $OVERLAY_ROOT" >&2
  exit 1
fi

REQUIRED_OVERLAY_FILES=(
  "CSM_Main/CSM.for"
  "CSM_Main/LAND.for"
  "Management/MgmtOps.for"
)
MISSING_OVERLAY_FILES=()
for required_path in "${REQUIRED_OVERLAY_FILES[@]}"; do
  if [[ ! -f "$OVERLAY_ROOT/$required_path" ]]; then
    MISSING_OVERLAY_FILES+=("$required_path")
  fi
done
if [[ ${#MISSING_OVERLAY_FILES[@]} -gt 0 ]]; then
  printf 'Overlay root must contain the full interactive patch set. Missing:%s\n' \
    " ${MISSING_OVERLAY_FILES[*]}" >&2
  exit 1
fi

if [[ ! -d "$SOURCE_ROOT" ]]; then
  echo "Source root does not exist: $SOURCE_ROOT" >&2
  exit 1
fi

if [[ ! -d "$RUNTIME_ROOT" ]]; then
  echo "Runtime root does not exist: $RUNTIME_ROOT" >&2
  exit 1
fi

if ! command -v cmake >/dev/null 2>&1; then
  echo "cmake is required but not found on PATH." >&2
  exit 1
fi

if [[ -z "${FC:-}" ]]; then
  EXISTING_COMPILER_FILE="$(find "$SOURCE_ROOT"/build/CMakeFiles -path '*/CMakeFortranCompiler.cmake' 2>/dev/null | head -n 1 || true)"
  if [[ -n "$EXISTING_COMPILER_FILE" ]]; then
    FC="$(sed -n 's/^set(CMAKE_Fortran_COMPILER "\(.*\)")/\1/p' "$EXISTING_COMPILER_FILE" | head -n 1)"
    if [[ -n "$FC" ]]; then
      export FC
    fi
  fi
fi

if [[ $CLEAN -eq 1 ]]; then
  rm -rf "$BUILD_ROOT"
fi

PATCHED_SOURCE_ROOT="${BUILD_ROOT}/source"
PATCHED_BUILD_ROOT="${BUILD_ROOT}/build"
mkdir -p "$PATCHED_SOURCE_ROOT" "$PATCHED_BUILD_ROOT"

echo "[build_patched_dssat_runtime_remote] overlay_root=$OVERLAY_ROOT"
echo "[build_patched_dssat_runtime_remote] source_root=$SOURCE_ROOT"
echo "[build_patched_dssat_runtime_remote] patched_source_root=$PATCHED_SOURCE_ROOT"
echo "[build_patched_dssat_runtime_remote] patched_build_root=$PATCHED_BUILD_ROOT"
echo "[build_patched_dssat_runtime_remote] runtime_root=$RUNTIME_ROOT"
echo "[build_patched_dssat_runtime_remote] build_type=$BUILD_TYPE"
echo "[build_patched_dssat_runtime_remote] fortran_compiler=${FC:-<auto-not-found>}"

rsync -a --delete "$SOURCE_ROOT"/ "$PATCHED_SOURCE_ROOT"/
rsync -a "$OVERLAY_ROOT"/ "$PATCHED_SOURCE_ROOT"/

if [[ -n "${FC:-}" ]]; then
  cmake -S "$PATCHED_SOURCE_ROOT" -B "$PATCHED_BUILD_ROOT" -DCMAKE_BUILD_TYPE="$BUILD_TYPE" -DCMAKE_Fortran_COMPILER="$FC"
else
  cmake -S "$PATCHED_SOURCE_ROOT" -B "$PATCHED_BUILD_ROOT" -DCMAKE_BUILD_TYPE="$BUILD_TYPE"
fi
cmake --build "$PATCHED_BUILD_ROOT" --target dscsm048 -j "${CMAKE_BUILD_PARALLEL_LEVEL:-4}"

BUILT_BINARY="$PATCHED_BUILD_ROOT/bin/dscsm048"
if [[ ! -f "$BUILT_BINARY" ]]; then
  echo "Expected built binary not found: $BUILT_BINARY" >&2
  exit 1
fi

cp "$BUILT_BINARY" "$RUNTIME_ROOT/dscsm048"

if [[ -n "$REPORT_JSON" ]]; then
  mkdir -p "$(dirname "$REPORT_JSON")"
  python - "$REPORT_JSON" "$OVERLAY_ROOT" "$SOURCE_ROOT" "$PATCHED_SOURCE_ROOT" "$PATCHED_BUILD_ROOT" "$RUNTIME_ROOT" "$BUILT_BINARY" "$BUILD_TYPE" <<'PY'
import json
import os
import sys
from pathlib import Path

report_path = Path(sys.argv[1])
overlay_root = Path(sys.argv[2])
source_root = Path(sys.argv[3])
patched_source_root = Path(sys.argv[4])
patched_build_root = Path(sys.argv[5])
runtime_root = Path(sys.argv[6])
built_binary = Path(sys.argv[7])
build_type = sys.argv[8]

overlay_files = []
for path in sorted(overlay_root.rglob("*")):
    if path.is_file():
        overlay_files.append(str(path.relative_to(overlay_root)).replace("\\", "/"))

payload = {
    "status": "ok",
    "overlay_root": str(overlay_root),
    "overlay_files": overlay_files,
    "source_root": str(source_root),
    "patched_source_root": str(patched_source_root),
    "patched_build_root": str(patched_build_root),
    "runtime_root": str(runtime_root),
    "built_binary": str(built_binary),
    "build_type": build_type,
    "built_binary_size_bytes": built_binary.stat().st_size,
}
report_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
PY
fi

echo "[build_patched_dssat_runtime_remote] refreshed $RUNTIME_ROOT/dscsm048"
