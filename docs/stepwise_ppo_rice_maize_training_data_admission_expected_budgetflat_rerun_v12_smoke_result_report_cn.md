# 基于 `training_update_admission` 预测活跃度约束 + budget-flat reward 的 Step-wise PPO/Transformer `v12` smoke 结果报告

## 运行概况
- 时间：2026-06-21 Asia/Shanghai
- 远端主机：`10.10.252.11`
- 训练入口：[scripts/train_stepwise_ppo.py](/G:/TransDSSAT/scripts/train_stepwise_ppo.py)
- 远端产物目录：
  - `/fs/fast/u2021201693/lym/TransDSSAT/artifacts/stepwise_ppo_rice_maize_training_data_admission_expected_budgetflat_rerun_v12_smoke_20260621_20260621_165322`
- 本次合同变化：
  - 保留 budget-flat `reward_v2`
  - 保留轻栈 `training_update_admission`
  - 在 rollout-side activity floor 之外，新增 candidate policy 的 `expected activity` 保留约束

## 正式产物
- checkpoint：
  - `/fs/fast/u2021201693/lym/TransDSSAT/artifacts/stepwise_ppo_rice_maize_training_data_admission_expected_budgetflat_rerun_v12_smoke_20260621_20260621_165322/stepwise_ppo_policy.pt`
- metrics：
  - `/fs/fast/u2021201693/lym/TransDSSAT/artifacts/stepwise_ppo_rice_maize_training_data_admission_expected_budgetflat_rerun_v12_smoke_20260621_20260621_165322/metrics.json`
- run log：
  - `/fs/fast/u2021201693/lym/TransDSSAT/artifacts/stepwise_ppo_rice_maize_training_data_admission_expected_budgetflat_rerun_v12_smoke_20260621_20260621_165322/run.log`

## 核心结果
- 本次 smoke 正常完成并产出 checkpoint 与 metrics。
- 按 `selection_metric=yield_floor_gap` 选出的最佳 checkpoint 首次从 `epoch 1` 后移到 `epoch 5`。
- 最佳 checkpoint 指标：
  - `best_epoch = 5`
  - `val/test mean_reward_gain = -0.801074 / -0.930447`
  - `val/test mean_yield_floor_gap_ratio = 0.420487 / 0.413464`
  - `val/test mean_yield_floor_attainment_pct = 57.951 / 58.654`
  - `val/test irrigation_mm = 216.374 / 214.432`
  - `val/test nitrogen_kg_ha = 162.545 / 165.243`
  - `best val min_enabled_activity_ratio = 0.969283`
- 末轮 `epoch 6` 指标：
  - `final val/test mean_reward_gain = -8.639409 / -8.773465`
  - `final val/test mean_yield_floor_gap_ratio = 0.458747 / 0.451843`
  - `final val/test mean_yield_floor_attainment_pct = 54.125 / 54.816`
  - `final val/test irrigation_mm = 0.0 / 0.0`
  - `final val/test nitrogen_kg_ha = 162.623 / 165.323`
  - `final val min_enabled_activity_ratio = 0.0`

## 训练合同信号
- `v12` 证明“预测端 admission”有部分效果：
  - 最优点首次后移到 `epoch 5`
  - 最优点的 `yield_floor_gap_ratio` 优于 `v11`
  - `epoch 5` 的 irrigation 活动仍接近 baseline，未再像 `v11` 那样在最佳点前明显滑落
- 但 `expected activity` 仍不足以阻止后续坍塌：
  - `epoch 2/3/4/6` 的评估 irrigation 都直接掉到 `0.0`
  - 同期 `mean_update_expected_irrigation_activity_ratio` 仍约为 `0.232-0.239`
  - 同期 `mean_update_expected_irrigation_target_ratio` 也约为 `0.205-0.236`
  - 说明 minibatch 上的“期望活跃度”可以满足阈值，但贪心执行语义仍能退化成 `gate < 0.5 => irrigation = 0`
- 因而当前缺口已收敛到一个更具体的问题：
  - admission 约束使用的是 `sigmoid(gate) * E[amount]`
  - 评估/部署使用的是 `gate >= 0.5` 的贪心门控
  - 两者语义不一致，导致 `expected activity` 指标通过，但真实执行仍会坍塌

## 与 `v11` / `v10` / `v8` 的关键对比
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
- `v11` 最佳点：
  - `best_epoch = 1`
  - `val/test mean_reward_gain = -0.487219 / -0.657620`
  - `val/test mean_yield_floor_gap_ratio = 0.421825 / 0.415001`
  - `val/test mean_yield_floor_attainment_pct = 57.817 / 58.500`
- `v12` 相比前三者的结论：
  - 首次把最佳点后移到了 `epoch 5`
  - 最佳点 `yield_floor_gap_ratio` 优于 `v11/v10/v8`
  - 但最佳点 `reward_gain` 仍弱于 `v11`
  - 后期 `0 irrigation` 坍塌仍然存在，所以还不能直接推广

## 结论
- `v12` 不是失败样本，它证明了“更聪明的 admission”确实能把 winning checkpoint 从 `epoch 1` 推后。
- 但它同时也把剩余缺口明确缩小到了“expected admission 指标与 greedy 执行语义不一致”。
- 因此当前任务仍保持 `In Progress`，下一步应保留轻栈方向，并把 `training_update_admission` 再升级为显式约束 greedy/deterministic activity 的版本，再做替换 staged smoke。
