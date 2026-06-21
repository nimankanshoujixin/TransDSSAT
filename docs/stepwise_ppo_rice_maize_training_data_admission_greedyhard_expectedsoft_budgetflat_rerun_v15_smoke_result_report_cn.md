# 基于 `training_update_admission` greedy-hard / expected-soft 分层 + budget-flat reward 的 Step-wise PPO/Transformer `v15` smoke 结果报告

## 运行概况
- 时间：2026-06-21 Asia/Shanghai
- 远端主机：`10.10.252.11`
- 训练入口：[scripts/train_stepwise_ppo.py](/G:/TransDSSAT/scripts/train_stepwise_ppo.py)
- 远端产物目录：
  - `/fs/fast/u2021201693/lym/TransDSSAT/artifacts/stepwise_ppo_rice_maize_training_data_admission_greedyhard_expectedsoft_budgetflat_rerun_v15_smoke_20260621_20260621_184419`
- 本次合同变化：
  - 保留 budget-flat `reward_v2`
  - 保留 rollout / greedy 通道参与 hard rejection
  - 将 expected-activity shortfall 从 hard rejection 中剥离，仅保留 soft penalty

## 正式产物
- checkpoint：
  - `/fs/fast/u2021201693/lym/TransDSSAT/artifacts/stepwise_ppo_rice_maize_training_data_admission_greedyhard_expectedsoft_budgetflat_rerun_v15_smoke_20260621_20260621_184419/stepwise_ppo_policy.pt`
- metrics：
  - `/fs/fast/u2021201693/lym/TransDSSAT/artifacts/stepwise_ppo_rice_maize_training_data_admission_greedyhard_expectedsoft_budgetflat_rerun_v15_smoke_20260621_20260621_184419/metrics.json`
- run log：
  - `/fs/fast/u2021201693/lym/TransDSSAT/artifacts/stepwise_ppo_rice_maize_training_data_admission_greedyhard_expectedsoft_budgetflat_rerun_v15_smoke_20260621_20260621_184419/run.log`

## 核心结果
- 本次 smoke 正常完成并产出 checkpoint 与 metrics。
- 按 `selection_metric=yield_floor_gap` 选出的最佳 checkpoint 仍停在 `epoch 1`。
- 最佳 checkpoint 指标：
  - `best_epoch = 1`
  - `val/test mean_reward_gain = -1.267923 / -1.150835`
  - `val/test mean_yield_floor_gap_ratio = 0.524330 / 0.524406`
  - `val/test mean_yield_floor_attainment_pct = 47.567 / 47.559`
  - `val/test irrigation_mm = 363.821 / 363.692`
  - `val/test nitrogen_kg_ha = 368.916 / 368.774`
- 末轮 `epoch 6` 指标：
  - `final val/test mean_reward_gain = -1.859498 / -1.772564`
  - `final val/test mean_yield_floor_gap_ratio = 0.525312 / 0.525464`
  - `final val/test mean_yield_floor_attainment_pct = 47.469 / 47.454`
  - `final val/test irrigation_mm = 364.104 / 363.986`
  - `final val/test nitrogen_kg_ha = 370.060 / 369.984`

## 训练合同信号
- `v15` 的直接正面结果是明确的：
  - `epoch 1-6` 的 `rejected_update_count` 全部变成 `0`
  - `admitted_update_count` 恢复为每轮 `1`
  - 说明 `expected activity` 从 hard gate 中剥离后，`v14` 那种后期小 shortfall 触发整步 veto 的问题被消除了
- 但关键目标没有达成：
  - 最佳 checkpoint 没有从 `epoch 1` 后移
  - `yield_floor_gap_ratio` 没有回到 `v12` 水平，反而比 `v14` 末轮略差
  - 高投入轨迹从一开始就维持在 `~364 mm` irrigation / `~370 kg/ha` nitrogen，说明当前保序压力本身仍把策略推在一条质量较差的轨道上
- 代表性信号：
  - `epoch_rejections = [0, 0, 0, 0, 0, 0]`
  - `epoch_shortfall = [0.000000, 0.013392, 0.000000, 0.000000, 0.046791, 0.019834]`
  - `epoch_val_gap = [0.524330, 0.524432, 0.524523, 0.524649, 0.524935, 0.525312]`

## 与 `v14` / `v13` / `v12` 的关键对比
- 相比 `v14`：
  - `v15` 成功消除了后期 hard reject
  - 但最优点仍是 `epoch 1`
  - 质量没有恢复，说明问题已从 “过度 veto” 转成 “soft pressure 本身仍把轨迹推偏”
- 相比 `v13`：
  - `v15` 不再出现 `v13` 那种大规模 hard rejection
  - 但 `yield_floor_gap` 仍明显差于 `v13`
- 相比 `v12`：
  - `v12` 仍然是目前唯一把 winning checkpoint 推到 `epoch 5` 的 admission 路线
  - `v15` 证明仅靠 expected-soft 分层还不足以恢复这一收益

## 结论
- `v15` 完成了必要诊断：
  - `expected activity` 不应该继续参与 hard reject
  - 但仅做 hard/soft 分层还不够，greedy/rollout admission 的 soft loss 仍然过强
- 下一步不应回到旧 penalty 组合，也不应直接开更大 GPU 训练。
- 后续进入 `v16`：
  - 保留 rollout / greedy 的 hard gate
  - 新增 soft-scale 分层
  - 默认将 greedy shortfall 从 soft admission loss 中拿掉，只保留 hard gate 约束
