#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: bash scripts/run_interactive_dssat_action_validation_remote.sh <output-dir> [crop]" >&2
  exit 2
fi

OUTPUT_DIR="$1"
CROP="${2:-maize}"

REPO_ROOT="${REPO_ROOT:-/fs/fast/u2021201693/lym/TransDSSAT}"
SCRIPT_ROOT="${SCRIPT_ROOT:-$REPO_ROOT}"
export SMOKE_SCRIPT_ROOT="${SMOKE_SCRIPT_ROOT:-$SCRIPT_ROOT}"

mkdir -p "$OUTPUT_DIR"
BASELINE_DIR="$OUTPUT_DIR/baseline_zero_action"
ACTION_DIR="$OUTPUT_DIR/action_applied"
VALIDATION_JSON="$OUTPUT_DIR/action_effect_validation.json"
RUN_LOG="$OUTPUT_DIR/run.log"

cd "$REPO_ROOT"
exec > >(tee -a "$RUN_LOG") 2>&1

echo "[run_interactive_dssat_action_validation_remote] started_at=$(date --iso-8601=seconds)"
echo "[run_interactive_dssat_action_validation_remote] output_dir=$OUTPUT_DIR crop=$CROP"
echo "[run_interactive_dssat_action_validation_remote] repo_root=$REPO_ROOT script_root=$SCRIPT_ROOT"

bash "$SCRIPT_ROOT/scripts/run_interactive_dssat_smoke_remote.sh" "$BASELINE_DIR" \
  --crop "$CROP" \
  --seed 20260622 \
  --decision-interval-days 5 \
  --irrigation-mm 0 \
  --nitrogen-kg-ha 0 \
  --archive-run-dir "$BASELINE_DIR/run_snapshot"

bash "$SCRIPT_ROOT/scripts/run_interactive_dssat_smoke_remote.sh" "$ACTION_DIR" \
  --crop "$CROP" \
  --seed 20260622 \
  --decision-interval-days 5 \
  --irrigation-mm 12 \
  --nitrogen-kg-ha 18 \
  --archive-run-dir "$ACTION_DIR/run_snapshot"

if [[ -n "${PYTHONPATH_PREFIX:-}" ]]; then
  export PYTHONPATH="$PYTHONPATH_PREFIX${PYTHONPATH:+:$PYTHONPATH}"
fi

conda run --no-capture-output -n "${CONDA_ENV_NAME:-transdssat}" \
  python "$SCRIPT_ROOT/scripts/validate_interactive_dssat_action_effect.py" \
  --baseline-report "$BASELINE_DIR/smoke_report.json" \
  --action-report "$ACTION_DIR/smoke_report.json" \
  --output-json "$VALIDATION_JSON"

echo "[run_interactive_dssat_action_validation_remote] finished_at=$(date --iso-8601=seconds)"
