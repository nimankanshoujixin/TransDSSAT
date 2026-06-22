#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: bash scripts/run_interactive_dssat_smoke_remote.sh <output-dir> [smoke args...]" >&2
  exit 2
fi

OUTPUT_DIR="$1"
shift

REPO_ROOT="${REPO_ROOT:-/fs/fast/u2021201693/lym/TransDSSAT}"
SMOKE_SCRIPT_ROOT="${SMOKE_SCRIPT_ROOT:-$REPO_ROOT}"
CONDA_ENV_NAME="${CONDA_ENV_NAME:-transdssat}"
PYTHONPATH_PREFIX="${PYTHONPATH_PREFIX:-}"
export DSSAT_VANILLA_HOME="${DSSAT_VANILLA_HOME:-/fs/fast/u2021201693/lym/dssat-runtime}"
export DSSAT_PATCHED_HOME="${DSSAT_PATCHED_HOME:-/fs/fast/u2021201693/lym/dssat-runtime-patched}"
export DSSAT_HOME="${DSSAT_HOME:-$DSSAT_PATCHED_HOME}"
export DSSAT_TEMPLATE_ROOT="${DSSAT_TEMPLATE_ROOT:-/fs/fast/u2021201693/lym/dssat-templates}"
if [[ -z "${DSSAT_PREPROCESS_COMMAND:-}" ]]; then
  export DSSAT_PREPROCESS_COMMAND="python scripts/render_dssat_inputs.py {manifest}"
fi
if [[ -z "${DSSAT_VANILLA_RUN_COMMAND:-}" ]]; then
  export DSSAT_VANILLA_RUN_COMMAND="$DSSAT_VANILLA_HOME/dscsm048 A {experiment}"
fi
if [[ -z "${DSSAT_PATCHED_RUN_COMMAND:-}" ]]; then
  export DSSAT_PATCHED_RUN_COMMAND="$DSSAT_PATCHED_HOME/dscsm048 A {experiment}"
fi
export DSSAT_RUN_COMMAND="${DSSAT_RUN_COMMAND:-$DSSAT_PATCHED_RUN_COMMAND}"
if [[ -z "${DSSAT_PATCHED_INTERACTIVE_LAUNCH_COMMAND:-}" ]]; then
  export DSSAT_PATCHED_INTERACTIVE_LAUNCH_COMMAND="python {controller_script} --driver-mode patched_runtime_subprocess {session_manifest}"
fi
export DSSAT_INTERACTIVE_PROTOCOL_DIRNAME="${DSSAT_INTERACTIVE_PROTOCOL_DIRNAME:-interactive_protocol}"
export DSSAT_INTERACTIVE_POLL_INTERVAL_SECONDS="${DSSAT_INTERACTIVE_POLL_INTERVAL_SECONDS:-0.2}"
export DSSAT_INTERACTIVE_READY_TIMEOUT_SECONDS="${DSSAT_INTERACTIVE_READY_TIMEOUT_SECONDS:-60}"
export DSSAT_INTERACTIVE_STEP_TIMEOUT_SECONDS="${DSSAT_INTERACTIVE_STEP_TIMEOUT_SECONDS:-60}"
export DSSAT_INTERACTIVE_CLOSE_TIMEOUT_SECONDS="${DSSAT_INTERACTIVE_CLOSE_TIMEOUT_SECONDS:-30}"

mkdir -p "$OUTPUT_DIR"
RUN_LOG="${OUTPUT_DIR}/run.log"
SMOKE_REPORT="${OUTPUT_DIR}/smoke_report.json"

cd "$REPO_ROOT"
exec > >(tee -a "$RUN_LOG") 2>&1

echo "[run_interactive_dssat_smoke_remote] started_at=$(date --iso-8601=seconds)"
echo "[run_interactive_dssat_smoke_remote] repo_root=$REPO_ROOT"
echo "[run_interactive_dssat_smoke_remote] smoke_script_root=$SMOKE_SCRIPT_ROOT"
echo "[run_interactive_dssat_smoke_remote] output_dir=$OUTPUT_DIR"
echo "[run_interactive_dssat_smoke_remote] conda_env=$CONDA_ENV_NAME"
echo "[run_interactive_dssat_smoke_remote] dssat_vanilla_home=$DSSAT_VANILLA_HOME"
echo "[run_interactive_dssat_smoke_remote] dssat_patched_home=$DSSAT_PATCHED_HOME"
echo "[run_interactive_dssat_smoke_remote] dssat_patched_run_command=$DSSAT_PATCHED_RUN_COMMAND"
echo "[run_interactive_dssat_smoke_remote] interactive_launch_command=$DSSAT_PATCHED_INTERACTIVE_LAUNCH_COMMAND"

COMMAND=(
  python -u scripts/smoke_interactive_dssat_session.py
  --output-json "$SMOKE_REPORT"
  "$@"
)

if [[ "$SMOKE_SCRIPT_ROOT" != "$REPO_ROOT" ]]; then
  COMMAND[2]="$SMOKE_SCRIPT_ROOT/scripts/smoke_interactive_dssat_session.py"
fi

if [[ -n "$PYTHONPATH_PREFIX" ]]; then
  export PYTHONPATH="$PYTHONPATH_PREFIX${PYTHONPATH:+:$PYTHONPATH}"
fi

printf '[run_interactive_dssat_smoke_remote] command='
printf '%q ' "${COMMAND[@]}"
printf '\n'

conda run --no-capture-output -n "$CONDA_ENV_NAME" "${COMMAND[@]}"
STATUS=$?

echo "[run_interactive_dssat_smoke_remote] finished_at=$(date --iso-8601=seconds) status=$STATUS"
exit "$STATUS"
