# Current Automation State

## Last updated
2026-06-21 20:58 Asia/Shanghai

## Mode
Completed

## Task status
The rollback verification is complete. The restored default code path reproduces the historical pre-collapse Transformer+PPO baseline regime, including `best_epoch = 5` and the same late-epoch zero-input collapse.

## What was verified this wakeup

- the formal rerun artifact directory is complete:
  - `/fs/fast/u2021201693/lym/TransDSSAT/artifacts/stepwise_ppo_rice_maize_training_data_precollapse_baseline_rerun_20260621_20260621_203650`
  - files present:
    - `metrics.json`
    - `run.log`
    - `stepwise_ppo_policy.pt`
- `metrics.json` confirms:
  - `best_epoch = 5`
  - `selection_metric = yield_floor_gap`
  - best `val/test mean_reward_gain = 1.594909 / 1.551148`
  - best `val/test mean_yield_floor_gap_ratio = 0.412211 / 0.404294`
- late-training collapse is also reproduced on the restored baseline:
  - `epoch 20 val/test irrigation_mm = 0.0 / 0.0`
  - `epoch 20 val/test nitrogen_kg_ha = 0.0 / 0.0`
  - `epoch 20 val/test mean_reward_gain = -0.720261 / -0.876687`

## Current active runs

- no active training run remains for this rollback verification task
- the earlier tmux training window `transdssat:ppo-baseline-rerun` has exited after successful completion

## Next immediate action

1. Do not start a new run unless explicitly requested.
2. If work continues, switch to root-cause analysis for why `epoch 5` is healthy but late epochs collapse to zero input.
3. Keep any future corrective design within `1-3` minimal strategies, per user preference.
