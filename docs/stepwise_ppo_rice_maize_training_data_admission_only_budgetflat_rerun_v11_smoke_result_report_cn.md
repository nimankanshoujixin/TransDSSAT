# 基于 `training_update_admission` 单独保留 + budget-flat reward 的 Step-wise PPO/Transformer `v11` smoke 结果报告

## 运行概况
- 时间：2026-06-21 Asia/Shanghai
- 远端主机：`10.10.252.11`
- 训练入口：[scripts/train_stepwise_ppo.py](/G:/TransDSSAT/scripts/train_stepwise_ppo.py)
- 远端产物目录：
  - `/fs/fast/u2021201693/lym/TransDSSAT/artifacts/stepwise_ppo_rice_maize_training_data_admission_only_budgetflat_rerun_v11_smoke_20260621_20260621_124200`
- 本次合同变化：
  - 保留 budget-flat `reward_v2`
  - 关闭 `training_activity_regularizer`
  - 关闭 `training_behavior_anchor`
  - 关闭 `training_policy_anchor`
  - 关闭 `training_advantage_activity_anchor`
  - 仅保留 `training_update_admission`

## 正式产物
- checkpoint：
  - `/fs/fast/u2021201693/lym/TransDSSAT/artifacts/stepwise_ppo_rice_maize_training_data_admission_only_budgetflat_rerun_v11_smoke_20260621_20260621_124200/stepwise_ppo_policy.pt`
- metrics：
  - `/fs/fast/u2021201693/lym/TransDSSAT/artifacts/stepwise_ppo_rice_maize_training_data_admission_only_budgetflat_rerun_v11_smoke_20260621_20260621_124200/metrics.json`
- run log：
  - `/fs/fast/u2021201693/lym/TransDSSAT/artifacts/stepwise_ppo_rice_maize_training_data_admission_only_budgetflat_rerun_v11_smoke_20260621_20260621_124200/run.log`

## 核心结果
- 本次 smoke 正常完成并产出 checkpoint 与 metrics。
- 按 `selection_metric=yield_floor_gap` 选出的最优 checkpoint 仍停在 `epoch 1`。
- 最优 checkpoint 指标：
  - `best_epoch = 1`
  - `val/test mean_reward_gain = -0.487219 / -0.657620`
  - `val/test mean_yield_floor_gap_ratio = 0.421825 / 0.415001`
  - `val/test mean_yield_floor_attainment_pct = 57.817 / 58.500`
  - `val/test irrigation_mm = 220.612 / 218.963`
  - `val/test nitrogen_kg_ha = 156.895 / 159.496`
  - `best val min_enabled_activity_ratio = 0.964558`
- 末轮 `epoch 6` 指标：
  - `final val/test mean_reward_gain = -4.885905 / -5.795804`
  - `final val/test mean_yield_floor_gap_ratio = 0.445752 / 0.443630`
  - `final val/test mean_yield_floor_attainment_pct = 55.425 / 55.637`
  - `final val/test irrigation_mm = 63.327 / 47.361`
  - `final val/test nitrogen_kg_ha = 133.430 / 135.025`
  - `final val min_enabled_activity_ratio = 0.283684`

## 训练合同信号
- `training_update_admission` 确实改变了最优点附近的表现：
  - `epoch 1 mean_update_min_enabled_activity_ratio = 0.238391`
  - `epoch 1` 的季末评估活动量仍接近 baseline，而不是立刻滑向旧的低活动吸引子
- 但 rollout-side admission 仍有明显缺口：
  - `epoch 2` 起评估端就出现 `irrigation_mm = 0.0` 的阶段性塌缩
  - `epoch 6` 虽不再是全零，但灌溉活跃度仍大幅跌到 baseline 的约 `28%`
  - 同期 `admitted_update_count` 仍全部通过，说明“只检查旧 rollout 动作活跃度”不足以阻止新策略在更新后继续向低活动漂移

## 与 `v10` / `v8` 的关键对比
- `v8` 最佳点：
  - `best_epoch = 1`
  - `val/test mean_reward_gain = -1.470415 / -1.669506`
  - `val/test mean_yield_floor_gap_ratio = 0.427850 / 0.421183`
  - `val/test mean_yield_floor_attainment_pct = 57.215 / 57.882`
- `v10` 最佳点：
  - `best_epoch = 1`
  - `val/test mean_reward_gain = -2.237468 / -2.428749`
  - `val/test mean_yield_floor_gap_ratio = 0.431483 / 0.424385`
  - `val/test mean_yield_floor_attainment_pct = 56.852 / 57.561`
- `v11` 相比 `v10` / `v8` 的结论：
  - `best_epoch` 仍然没有后移，问题没有根治
  - 但 `v11` 最优点的 `reward_gain` 明显优于 `v10` 和 `v8`
  - `v11` 最优点的 `yield_floor_gap_ratio` 也优于 `v10` 和 `v8`
  - 因而“轻栈 admission-only”方向在 winning checkpoint 上是有益的，只是后期稳定性不足

## 结论
- `v11` 证明了一个更轻的 anti-collapse 栈可以得到比 `v8/v10` 更好的 winning checkpoint。
- 但 `v11` 同时暴露出当前 `training_update_admission` 的设计缺口：
  - 它只基于 rollout 已发生的动作做准入
  - 它没有约束新策略在同一批状态上的预测活跃度
- 因此当前任务仍保持 `In Progress`，下一步应保留 `v11` 的轻栈方向，同时把 `training_update_admission` 升级为“预测端也必须满足活动保留目标”的更强过程约束，再做新的 staged smoke。
