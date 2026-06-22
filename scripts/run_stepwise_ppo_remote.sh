#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: bash scripts/run_stepwise_ppo_remote.sh <output-dir> [train_stepwise_ppo args...]" >&2
  exit 2
fi

OUTPUT_DIR="$1"
shift

for arg in "$@"; do
  if [[ "$arg" == "--output-dir" ]]; then
    echo "Do not pass --output-dir to run_stepwise_ppo_remote.sh; use the first positional argument instead." >&2
    exit 2
  fi
done

REPO_ROOT="${REPO_ROOT:-/fs/fast/u2021201693/lym/TransDSSAT}"
CONDA_ENV_NAME="${CONDA_ENV_NAME:-transdssat}"
export DSSAT_VANILLA_HOME="${DSSAT_VANILLA_HOME:-/fs/fast/u2021201693/lym/dssat-runtime}"
export DSSAT_PATCHED_HOME="${DSSAT_PATCHED_HOME:-/fs/fast/u2021201693/lym/dssat-runtime-patched}"
export DSSAT_HOME="${DSSAT_HOME:-$DSSAT_PATCHED_HOME}"
export DSSAT_TEMPLATE_ROOT="${DSSAT_TEMPLATE_ROOT:-/fs/fast/u2021201693/lym/dssat-templates}"
export DSSAT_PREPROCESS_COMMAND="${DSSAT_PREPROCESS_COMMAND:-python scripts/render_dssat_inputs.py {manifest}}"
export DSSAT_VANILLA_RUN_COMMAND="${DSSAT_VANILLA_RUN_COMMAND:-$DSSAT_VANILLA_HOME/dscsm048 A {experiment}}"
export DSSAT_PATCHED_RUN_COMMAND="${DSSAT_PATCHED_RUN_COMMAND:-$DSSAT_PATCHED_HOME/dscsm048 A {experiment}}"
export DSSAT_RUN_COMMAND="${DSSAT_RUN_COMMAND:-$DSSAT_PATCHED_RUN_COMMAND}"

mkdir -p "$OUTPUT_DIR"
RUN_LOG="${OUTPUT_DIR}/run.log"

cd "$REPO_ROOT"
exec > >(tee -a "$RUN_LOG") 2>&1

echo "[run_stepwise_ppo_remote] started_at=$(date --iso-8601=seconds)"
echo "[run_stepwise_ppo_remote] repo_root=$REPO_ROOT"
echo "[run_stepwise_ppo_remote] output_dir=$OUTPUT_DIR"
echo "[run_stepwise_ppo_remote] conda_env=$CONDA_ENV_NAME"
echo "[run_stepwise_ppo_remote] dssat_vanilla_home=$DSSAT_VANILLA_HOME"
echo "[run_stepwise_ppo_remote] dssat_patched_home=$DSSAT_PATCHED_HOME"

COMMAND=(
  python -u scripts/train_stepwise_ppo.py
  --output-dir "$OUTPUT_DIR"
  "$@"
)

printf '[run_stepwise_ppo_remote] command='
printf '%q ' "${COMMAND[@]}"
printf '\n'

conda run --no-capture-output -n "$CONDA_ENV_NAME" "${COMMAND[@]}"
STATUS=$?

echo "[run_stepwise_ppo_remote] finished_at=$(date --iso-8601=seconds) status=$STATUS"
exit "$STATUS"
