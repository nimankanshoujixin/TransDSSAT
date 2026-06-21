# 基于 advantage-weighted `training_policy_anchor` 的 Step-wise PPO/Transformer `v8` smoke 结果报告

## 运行概况
- 时间：2026-06-21 Asia/Shanghai
- 远端主机：`10.10.252.11`
- 训练入口：[scripts/train_stepwise_ppo.py](/G:/TransDSSAT/scripts/train_stepwise_ppo.py)
- 远端产物目录：
  - `/fs/fast/u2021201693/lym/TransDSSAT/artifacts/stepwise_ppo_rice_maize_training_data_policy_anchor_advantage_rerun_v8_smoke_20260621_20260621_100958`
- 本次训练合同变化：
  - 将平坦 `training_policy_anchor` 替换为 advantage-weighted 版本
  - 正 advantage 样本保留完整 anchor 权重
  - 负 advantage 样本降权到 `0.07`

## 正式产物
- checkpoint：
  - `/fs/fast/u2021201693/lym/TransDSSAT/artifacts/stepwise_ppo_rice_maize_training_data_policy_anchor_advantage_rerun_v8_smoke_20260621_20260621_100958/stepwise_ppo_policy.pt`
- metrics：
  - `/fs/fast/u2021201693/lym/TransDSSAT/artifacts/stepwise_ppo_rice_maize_training_data_policy_anchor_advantage_rerun_v8_smoke_20260621_20260621_100958/metrics.json`
- run log：
  - `/fs/fast/u2021201693/lym/TransDSSAT/artifacts/stepwise_ppo_rice_maize_training_data_policy_anchor_advantage_rerun_v8_smoke_20260621_20260621_100958/run.log`

## 核心结果
- 本次 smoke 正常执行完 `6` 个 epoch，`run.log` 结束于 `finished_at=2026-06-21T10:20:14+08:00 status=0`。
- 按 `selection_metric=yield_floor_gap` 选出的最佳 checkpoint 仍停在 `epoch 1`。
- 最佳 checkpoint 指标：
  - `best_epoch = 1`
  - `val mean_reward_gain = -1.470415`
  - `test mean_reward_gain = -1.669506`
  - `val mean_yield_floor_gap_ratio = 0.427850`
  - `test mean_yield_floor_gap_ratio = 0.421183`
  - `val mean_yield_floor_attainment_pct = 57.215`
  - `test mean_yield_floor_attainment_pct = 57.882`
  - `val mean_irrigation_mm = 225.741`
  - `test mean_irrigation_mm = 223.877`
  - `val mean_nitrogen_kg_ha = 158.036`
  - `test mean_nitrogen_kg_ha = 160.656`
- 末轮 `epoch 6` 指标：
  - `final val mean_reward_gain = -2.737957`
  - `final test mean_reward_gain = -2.951789`
  - `final val mean_yield_floor_gap_ratio = 0.435602`
  - `final test mean_yield_floor_gap_ratio = 0.429183`
  - `final val mean_yield_floor_attainment_pct = 56.440`
  - `final test mean_yield_floor_attainment_pct = 57.082`
  - `final val/test irrigation_mm = 226.482 / 224.683`
  - `final val/test nitrogen_kg_ha = 162.656 / 165.356`

## 训练合同信号
- advantage 权重路径确实生效：
  - `mean_policy_anchor_positive_advantage_fraction` 在已记录 epoch 上约为 `0.44-0.53`
  - `mean_policy_anchor_positive_advantage_weight = 1.0`
  - `mean_policy_anchor_negative_advantage_weight = 0.07`
- 但它没有把“最佳点过早出现”问题推迟：
  - `best_epoch` 仍然是 `1`
  - `epoch 3` 与 `epoch 6` 都再次出现 `early_stopped_on_kl = true`
- 活动量没有塌到旧的 `0/0` 退化，但最优点的氮投入反而比 `v7` 更低：
  - `v8` 最优 `val/test nitrogen_kg_ha = 158.036 / 160.656`
  - `v7` 最优 `val/test nitrogen_kg_ha = 161.799 / 164.467`

## 与 `v7` 的关键对比
- `v8` 相比 `v7` 的最好点：
  - `mean_reward_gain` 略好
    - `val`: `-1.470415` vs `-1.524520`
    - `test`: `-1.669506` vs `-1.692527`
  - 但 `yield_floor_gap_ratio` 并未改善，略差
    - `val`: `0.427850` vs `0.427616`
    - `test`: `0.421183` vs `0.420278`
  - `yield_floor_attainment_pct` 也未改善
    - `val`: `57.215` vs `57.238`
    - `test`: `57.882` vs `57.972`
  - 最优点氮投入更低，说明新权重更像是在“更温和地保留活动”，而不是把 PPO 牵引到更优的高产行为。
- `v8` 相比 `v7` 的末轮：
  - 末轮 `reward_gain` 退化程度略轻
  - 但最关键的最优 checkpoint 时机和产量/`yield_floor_gap` 质量没有实质改善

## 结论
- advantage-weighted `training_policy_anchor` 已完成第一轮 GPU smoke 验证。
- 当前证据不支持直接把该合同升级为更大 rerun：
  - 它没有把最佳 checkpoint 从 `epoch 1` 向后推移
  - 它也没有把最佳 `yield_floor_gap` 或 `yield_floor_attainment` 做到优于 `v7`
- 因此当前更合理的结论是：
  - 保持任务 `In Progress`
  - 不直接提升到更大 GPU rerun
  - 启动下一轮 CPU-safe 纠偏设计，重点不再只是“按 advantage 降权模仿”，而是要把训练过程显式牵引到“更优于 baseline 的高价值活动片段”
