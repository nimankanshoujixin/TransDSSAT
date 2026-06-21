# 基于 `training_advantage_activity_anchor` + budget-flat reward 的 Step-wise PPO/Transformer `v10` smoke 结果报告

## 运行概况
- 时间：2026-06-21 Asia/Shanghai
- 远端主机：`10.10.252.11`
- 训练入口：[scripts/train_stepwise_ppo.py](/G:/TransDSSAT/scripts/train_stepwise_ppo.py)
- 远端产物目录：
  - `/fs/fast/u2021201693/lym/TransDSSAT/artifacts/stepwise_ppo_rice_maize_training_data_advantage_activity_anchor_budgetflat_rerun_v10_smoke_20260621_20260621_122640`
- 本次合同变化：
  - 训练期新增 `training_advantage_activity_anchor`
  - reward_v2 资源结算改为 budget-flat 语义：预算内平坦，超预算才增加额外成本

## 正式产物
- checkpoint：
  - `/fs/fast/u2021201693/lym/TransDSSAT/artifacts/stepwise_ppo_rice_maize_training_data_advantage_activity_anchor_budgetflat_rerun_v10_smoke_20260621_20260621_122640/stepwise_ppo_policy.pt`
- metrics：
  - `/fs/fast/u2021201693/lym/TransDSSAT/artifacts/stepwise_ppo_rice_maize_training_data_advantage_activity_anchor_budgetflat_rerun_v10_smoke_20260621_20260621_122640/metrics.json`
- run log：
  - `/fs/fast/u2021201693/lym/TransDSSAT/artifacts/stepwise_ppo_rice_maize_training_data_advantage_activity_anchor_budgetflat_rerun_v10_smoke_20260621_20260621_122640/run.log`

## 核心结果
- 本次 smoke 正常完成并产出 checkpoint 与 metrics。
- 按 `selection_metric=yield_floor_gap` 选出的最佳 checkpoint 仍然停在 `epoch 1`。
- 最佳 checkpoint 指标：
  - `best_epoch = 1`
  - `val mean_reward_gain = -2.237468`
  - `test mean_reward_gain = -2.428749`
  - `val mean_yield_floor_gap_ratio = 0.431483`
  - `test mean_yield_floor_gap_ratio = 0.424385`
  - `val mean_yield_floor_attainment_pct = 56.852`
  - `test mean_yield_floor_attainment_pct = 57.561`
  - `val mean_irrigation_mm = 226.374`
  - `test mean_irrigation_mm = 224.570`
  - `val mean_nitrogen_kg_ha = 162.538`
  - `test mean_nitrogen_kg_ha = 165.236`
- 末轮 `epoch 6` 指标：
  - `final val mean_reward_gain = -2.707458`
  - `final test mean_reward_gain = -2.932346`
  - `final val mean_yield_floor_gap_ratio = 0.435220`
  - `final test mean_yield_floor_gap_ratio = 0.428901`
  - `final val mean_yield_floor_attainment_pct = 56.478`
  - `final test mean_yield_floor_attainment_pct = 57.110`
  - `final val/test irrigation_mm = 226.483 / 224.686`
  - `final val/test nitrogen_kg_ha = 162.572 / 165.270`

## 训练合同信号
- `training_advantage_activity_anchor` 确实在训练中起作用：
  - `epoch 1 advantage_activity_anchor_penalty = 0.006372`
  - 后续 epoch 仍有非零锚定项，但整体量级不大
  - 正 advantage 子集比例在 `0.44-0.52` 附近
- `training_update_admission` 仍保持有效：
  - `mean_update_min_enabled_activity_ratio` 大体维持在 `0.24-0.30`
  - 没有回到旧的 `0/0` 全零吸引子
- 但这次组合合同没有把策略推向更好的最优点：
  - best checkpoint 没有晚于 `epoch 1`
  - 各 epoch 的 `yield_floor_gap_ratio` 几乎单调变差

## 与 `v8` 的关键对比
- `v8` 最佳点：
  - `best_epoch = 1`
  - `val/test mean_reward_gain = -1.470415 / -1.669506`
  - `val/test mean_yield_floor_gap_ratio = 0.427850 / 0.421183`
  - `val/test mean_yield_floor_attainment_pct = 57.215 / 57.882`
- `v10` 相比 `v8` 的结论：
  - `best_epoch` 没有后移，仍然是 `epoch 1`
  - `reward_gain` 明显更差
  - `yield_floor_gap_ratio` 更差
  - `yield_floor_attainment_pct` 更差
  - 活动量保持在 baseline 附近，但这并没有换来更好的产量地板表现

## 结论
- “预算内不再奖励额外节约”的 reward 方向在目标定义上是合理的，应该保留为长期语义方向。
- 但 `v10` 这版和 `training_advantage_activity_anchor` 的组合并没有改善最优 checkpoint，反而把最佳指标拉差了。
- 因此当前应保持任务 `In Progress`，并进入下一轮纠偏设计：
  - 保留 budget-flat reward 作为新的目标语义基线
  - 不把当前 `training_advantage_activity_anchor` 直接升级为更大 rerun
  - 后续应开始筛选哪些 anti-collapse 组件真正改善了 winning checkpoint，哪些只是稳定了活动量却拖累了最优解
