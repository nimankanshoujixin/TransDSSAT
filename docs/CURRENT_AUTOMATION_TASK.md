# Current Automation Task

## Task Description
Completed

Current assignment: rerun the restored pre-collapse Transformer+PPO baseline and verify whether the codebase really reproduces the historical `2026-06-20` baseline regime with:

- `best checkpoint = epoch 5`
- full real-subset mean yield gap ratio around `+0.080018`
- no later anti-collapse training stack active in the default path

## Current Status
Completed

## Progress This Wakeup

1. Polled the formal baseline rerun to completion and confirmed the active tmux training window has exited.
2. Re-checked the finished artifact directory:
   - `/fs/fast/u2021201693/lym/TransDSSAT/artifacts/stepwise_ppo_rice_maize_training_data_precollapse_baseline_rerun_20260621_20260621_203650`
   - landed files:
     - `metrics.json`
     - `run.log`
     - `stepwise_ppo_policy.pt`
3. Verified that the rollback really restored the historical pre-collapse regime:
   - `best_epoch = 5`
   - all later anti-collapse controls remain disabled on the default baseline path
4. Confirmed the late-training collapse is also reproducible on the restored baseline:
   - by `epoch 20`, `val/test irrigation_mm = 0.0 / 0.0`
   - by `epoch 20`, `val/test nitrogen_kg_ha = 0.0 / 0.0`

## Expected Deliverables

1. A finished formal rerun from the restored pre-collapse baseline code path.
2. `metrics.json`, `stepwise_ppo_policy.pt`, and `run.log` under the new baseline artifact directory.
3. A direct comparison between the new rerun and the historical `2026-06-20` baseline on:
   - `best_epoch`
   - `reward_gain`
   - `yield_floor_gap_ratio`
   - collapse behavior at late epochs

## Final Result

1. The rerun finished successfully and reproduced the expected restored baseline contract.
2. Key best-checkpoint metrics matched the earlier healthy regime closely:
   - `best_epoch = 5`
   - `val/test mean_reward_gain = 1.594909 / 1.551148`
   - `val/test mean_yield_floor_gap_ratio = 0.412211 / 0.404294`
   - `val/test mean_yield_kg_ha = 2763.127 / 2803.386`
   - `val/test mean_irrigation_mm = 196.624 / 193.625`
   - `val/test mean_nitrogen_kg_ha = 67.435 / 65.601`
3. Late-training collapse was reproduced as well:
   - `epoch 20 val/test mean_reward_gain = -0.720261 / -0.876687`
   - `epoch 20 val/test mean_yield_floor_gap_ratio = 0.458747 / 0.451843`
   - `epoch 20 val/test irrigation_mm = 0.0 / 0.0`
   - `epoch 20 val/test nitrogen_kg_ha = 0.0 / 0.0`
4. This wakeup completes the rollback verification task. The next admissible development direction is root-cause analysis with at most `1-3` minimal interventions, per user preference.

## Constraints

- Do not re-enable the later anti-collapse training stack during this rerun.
- Do not mix this baseline validation run with any new corrective strategy.
- Keep the rerun on the restored default path marked by `training_baseline_mode = pre_collapse_epoch5_rerun`.
