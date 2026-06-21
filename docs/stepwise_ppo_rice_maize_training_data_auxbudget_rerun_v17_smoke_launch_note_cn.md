# v17 staged smoke 启动说明

## 背景

`v16` 已完成，但结果不满足推广条件：

- `best checkpoint` 仍停在 `epoch 1`
- `hard rejects` 维持在 `0`
- 零灌溉/零施氮硬坍塌没有回归
- 但后续 epoch 的 `yield_floor_gap` 持续劣化，且 `greedy / expected` 活动继续抬升

据此判断，剩余问题不再是 hard veto，也不只是 greedy soft-loss，而是多路 `activity/anchor/admission` 软损失的合力在单个 minibatch 上仍可能压过 PPO 主目标，导致策略被推向高投入但低质量的更新方向。

## 本轮修正

在 `transdssat.stepwise_ppo.run_ppo_update(...)` 中新增 `training_auxiliary_penalty_budget`：

- 汇总 `activity_regularizer`
- 汇总 `behavior_anchor`
- 汇总 `policy_anchor`
- 汇总 `advantage_activity_anchor`
- 汇总 `update_admission`

然后按 `max_auxiliary_to_core_ratio` 相对于 `|policy_loss| + value_coef * value_loss (+ entropy magnitude)` 的上限做统一缩放。

默认配置：

- `enabled = true`
- `max_auxiliary_to_core_ratio = 0.6`
- `minimum_core_loss = 0.25`
- `include_entropy_magnitude = true`

该设计保留现有 anti-collapse 约束，但阻止辅助损失在单个 PPO 更新中主导梯度方向。

## 验证

- 本地 `python -m compileall transdssat scripts tests` 通过
- 本地 `python -m unittest tests.test_stepwise_ppo tests.test_stepwise_env -v` 通过
- 远端 `/home/u2021201693/anaconda3/bin/python -m unittest tests.test_stepwise_ppo -v` 通过
- 远端 `scripts/train_stepwise_ppo.py --dry-run ...` 通过，并确认 authoritative payload 含：
  - `training_auxiliary_penalty_budget`

## 启动的 v17 smoke

- 时间：`2026-06-21 20:10 Asia/Shanghai`
- tmux window：`transdssat:ppo-ac-rerun-v17-smk`
- wrapper：`/tmp/transdssat_v17_smoke_20260621_201820.sh`
- artifact dir：`/fs/fast/u2021201693/lym/TransDSSAT/artifacts/stepwise_ppo_rice_maize_training_data_auxbudget_rerun_v17_smoke_20260621_20260621_201820`
- device gate：启动前 `nvidia-smi` 显示 `cuda:0` 与 `cuda:3` 近空闲，实际 run 绑定 `CUDA_VISIBLE_DEVICES=0`

## 下轮检查重点

1. `auxiliary_penalty_budget_applied_penalty` 是否显著低于 raw penalty
2. `mean_auxiliary_penalty_budget_scale` 是否在后期明显低于 `1.0`
3. `best checkpoint` 是否从 `epoch 1` 后移
4. `yield_floor_gap` 是否停止继续恶化
5. `hard rejects` 是否继续维持在 `0` 或接近 `0`
