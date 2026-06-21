# 基于 training_policy_anchor 合同的 Step-wise PPO/Transformer `v7` smoke 结果报告

## 运行概况
- 时间：2026-06-21 Asia/Shanghai
- 远端主机：`10.10.252.11`
- 训练入口：[scripts/train_stepwise_ppo.py](/G:/TransDSSAT/scripts/train_stepwise_ppo.py)
- 远端产物目录：
  - `/fs/fast/u2021201693/lym/TransDSSAT/artifacts/stepwise_ppo_rice_maize_training_data_policy_anchor_rerun_v7_smoke_20260621_1610`
- 本次新增训练合同：
  - `training_policy_anchor`
  - 在 PPO update 阶段同时约束 gate 匹配与 amount 偏移，目标是抑制策略相对 rollout/baseline 的后期漂移

## 正式产物
- checkpoint：
  - `/fs/fast/u2021201693/lym/TransDSSAT/artifacts/stepwise_ppo_rice_maize_training_data_policy_anchor_rerun_v7_smoke_20260621_1610/stepwise_ppo_policy.pt`
- metrics：
  - `/fs/fast/u2021201693/lym/TransDSSAT/artifacts/stepwise_ppo_rice_maize_training_data_policy_anchor_rerun_v7_smoke_20260621_1610/metrics.json`
- run log：
  - `/fs/fast/u2021201693/lym/TransDSSAT/artifacts/stepwise_ppo_rice_maize_training_data_policy_anchor_rerun_v7_smoke_20260621_1610/run.log`

## 核心结果
- 本次 smoke 正常执行完 `6` 个 epoch，`run.log` 结束于 `finished_at=2026-06-21T08:18:21+08:00 status=0`。
- 按 `selection_metric=yield_floor_gap` 选出的最佳 checkpoint 停在 `epoch 1`。
- 最佳 checkpoint 指标：
  - `best_epoch = 1`
  - `val mean_reward_gain = -1.524520`
  - `test mean_reward_gain = -1.692527`
  - `val mean_yield_floor_gap_ratio = 0.427616`
  - `test mean_yield_floor_gap_ratio = 0.420278`
  - `val mean_yield_floor_attainment_pct = 57.238`
  - `test mean_yield_floor_attainment_pct = 57.972`
  - `val mean_irrigation_mm = 225.472`
  - `test mean_irrigation_mm = 223.675`
  - `val mean_nitrogen_kg_ha = 161.799`
  - `test mean_nitrogen_kg_ha = 164.467`
- 末轮 `epoch 6` 指标：
  - `final val mean_reward_gain = -2.866059`
  - `final test mean_reward_gain = -3.069675`
  - `final val mean_yield_floor_gap_ratio = 0.437122`
  - `final test mean_yield_floor_gap_ratio = 0.430342`
  - `final val mean_yield_floor_attainment_pct = 56.288`
  - `final test mean_yield_floor_attainment_pct = 56.966`
  - `final val/test irrigation_mm = 226.527 / 224.728`
  - `final val/test nitrogen_kg_ha = 162.617 / 165.316`

## 训练合同信号
- `policy_anchor_penalty` 在首末轮分别为 `0.553739` 和 `0.573673`，说明新项在整个 smoke 中持续起作用。
- `mean_policy_anchor_gate_match_ratio` 从 `0.531412` 降到 `0.503354`，没有出现“越训越贴近目标 gate”的改善趋势。
- 水氮活动量始终接近 baseline：
  - `val/test irrigation_mm` 基本稳定在 `223-227 mm`
  - `val/test nitrogen_kg_ha` 基本稳定在 `162-165 kg/ha`
- 因此这次 `v7` 更像是把策略活动水平锁在 baseline 附近，而不是把 PPO 推向更优 checkpoint。

## 与 `v6` 的关键对比
- `v6` 最佳点：
  - `best_epoch = 4`
  - `val/test mean_reward_gain = -1.432904 / -1.647605`
  - `val/test mean_yield_floor_gap_ratio = 0.425392 / 0.418942`
- `v7` 相比 `v6` 的结论：
  - 没有改善最佳 checkpoint，反而把最佳点进一步提前到 `epoch 1`
  - 最佳 `yield_floor_gap_ratio` 与 `mean_reward_gain` 均略差于 `v6`
  - 末轮表现也未优于 `v6`
  - 但活动量保持稳定，说明 `training_policy_anchor` 的主要作用是“抑制偏离 baseline 的漂移”，不是“提升后期策略质量”

## 结论
- `v7` smoke 已完成对 `training_policy_anchor` 的首轮 GPU 级行为验证。
- 当前证据不支持直接把该合同升级为中型或正式 rerun：
  - 它没有修复“最佳 checkpoint 过早出现”的问题
  - 也没有给出优于 `v6` 的最优指标
- 下一阶段更合理的方向是：
  - 保持任务 `In Progress`
  - 不立即启动 `v8` GPU rerun
  - 先在 CPU-safe 路线上重新设计更强的组合约束，使 anchor 不只是锁住 baseline 活动量，还要对“更优而非更稳”的训练目标提供正向牵引
