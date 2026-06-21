# Step-wise PPO Transformer Rerun Contract `2026-06-10`

## Purpose

This document freezes the launch-facing contract for the first formal transformer-backed `step-wise PPO` rerun under the current objective-aware proxy semantics.

This rerun is a like-for-like backbone substitution on top of the already published `mlp` semantic-freeze baseline. It is not a tokenization redesign, not a legacy transformer revival, and not an official DSSAT full-fidelity result.

## Authoritative Training Path For This Run

### Included in the formal result

- entry script: `scripts/train_stepwise_ppo.py`
- environment interface: `transdssat.environments.stepwise.StepwiseDecisionEnvironment`
- rollout / PPO logic: `transdssat.stepwise_ppo`
- scenario pool generator: `transdssat.testset.generate_training_scenario_pool`
- reward backend: proxy-only `dssat_proxy`
- backbone: `transformer`

### Explicitly excluded from the formal result

- `scripts/train_rl_transformer.py`
- `scripts/train_transformer.py`
- any supervised transformer checkpoint or dataset produced before the current semantic freeze
- any historical PPO artifact that was not regenerated under the current objective-aware semantic contract

## Frozen Scenario-Pool Contract

- split sizes: `train=9000`, `val=500`, `test=500`
- engine set: `("dssat_proxy",)`
- comparison baseline: `docs/stepwise-ppo-10000-semantic-freeze-result-report-cn.md`
- baseline backbone: `mlp`
- baseline seed: `20260608`
- baseline pool seed: `20260608`
- authoritative policy for this rerun: keep the same `seed` and `pool_seed` as the published `mlp` baseline unless a launch-time blocker forces a documented change

Interpretation:

- pool membership should remain directly comparable to the published `mlp` run
- all derived transformer-stage artifacts must still be regenerated fresh for this rerun

## Frozen Model / Selection Contract

- hidden dimension: `128`
- attention heads: `4`
- transformer layers: `2`
- maximum sequence length: `64`
- baseline comparator inside evaluation: `heuristic`
- checkpoint selection metric: `reward_gain`
- authoritative checkpoint selector: `val`

## Active Sequence Semantics For This Rerun

The rerun must use the current `transdssat.stepwise_ppo` token contract exactly as implemented now:

- one decision step produces one token
- there is no separate static-context prefix-token stream yet
- token width remains `52`
- the token mixes:
  - current observation features
  - previous recommended / executed action feedback
  - previous reward
  - sinusoidal time encoding
  - objective weights
  - management-mode flags
  - decision interval / forecast horizon fields

Trust boundary:

- this rerun tests whether a causal transformer encoder helps under the current coarse token organization
- it does not answer whether a richer context-token layout would help more

## Freshness Rules

The following must be treated as stale for this rerun unless regenerated after launch:

- transformer-stage checkpoint
- transformer-stage `metrics.json`
- transformer-stage `run.log`
- any derived evaluation summary that claims to represent the current transformer rerun

Historical `mlp` artifacts stay valid only as the published comparison baseline, not as fresh transformer-stage outputs.

## Remote Launch Contract

- host: `10.10.252.11`
- repo: `/fs/fast/u2021201693/lym/TransDSSAT`
- tmux session: `transdssat`
- recommended window: `ppo10000-transformer-rerun`
- conda env: `transdssat`
- DSSAT env vars to export before launch:
  - `DSSAT_HOME=/fs/fast/u2021201693/lym/dssat-runtime`
  - `DSSAT_TEMPLATE_ROOT=/fs/fast/u2021201693/lym/dssat-templates`
  - `DSSAT_PREPROCESS_COMMAND="python scripts/render_dssat_inputs.py {manifest}"`
  - `DSSAT_RUN_COMMAND="/fs/fast/u2021201693/lym/dssat-runtime/dscsm048 A {experiment}"`

### Planned formal launch command

The formal rerun must use this path shape, with the selected free GPU mapped into logical `cuda:0` via `CUDA_VISIBLE_DEVICES`:

```bash
python -u scripts/train_stepwise_ppo.py \
  --device cuda:0 \
  --seed 20260608 \
  --pool-seed 20260608 \
  --train-count 9000 \
  --val-count 500 \
  --test-count 500 \
  --epochs 20 \
  --episodes-per-epoch 128 \
  --update-epochs 4 \
  --minibatch-size 256 \
  --hidden-dim 128 \
  --backbone transformer \
  --num-heads 4 \
  --num-layers 2 \
  --max-sequence-length 64 \
  --baseline-name heuristic \
  --selection-metric reward_gain \
  --output-dir /fs/fast/u2021201693/lym/TransDSSAT/artifacts/stepwise_ppo_10000_transformer_semantic_freeze_20260610_<timestamp>
```

## Live Verification Snapshot

### Verified on `2026-06-10 21:41 Asia/Shanghai`

- remote host reachable
- `tmux` session `transdssat` exists
- current remote key-file hashes match the local current-semantic worktree for:
  - `scripts/train_stepwise_ppo.py`
  - `transdssat/stepwise_ppo.py`
  - `transdssat/testset.py`
  - `transdssat/environments/stepwise.py`
- remote CPU-safe dry run passed:
  - `python scripts/train_stepwise_ppo.py --dry-run --backbone transformer --device cpu --train-count 8 --val-count 2 --test-count 2 --seed 20260610 --pool-seed 20260610`

### GPU gate result

The live `nvidia-smi` snapshot at the same check time showed no safely free GPU for a formal new training launch:

- GPU `0`: `75955 / 81920 MiB`
- GPU `1`: `46851 / 81920 MiB`
- GPU `2`: `62547 / 81920 MiB`
- GPU `3`: `80575 / 81920 MiB`
- GPU `4`: `55467 / 81920 MiB`, `66%` util
- GPU `5`: `57641 / 81920 MiB`
- GPU `6`: `76267 / 81920 MiB`
- GPU `7`: `81185 / 81920 MiB`

Decision:

- do not launch the formal transformer rerun in this wakeup
- re-check GPU availability in a later wakeup before creating the tmux training window

## Required Final Run Record

When the GPU gate eventually passes and the rerun is launched, the final result report must record:

- command
- remote host
- GPU info
- tmux session/window
- log path
- output dir
- checkpoint path
- metrics path
- backbone
- selection metric
- direct comparison against the published `mlp` baseline on the same scenario-pool contract
- whether transformer becomes the new authoritative proxy baseline
