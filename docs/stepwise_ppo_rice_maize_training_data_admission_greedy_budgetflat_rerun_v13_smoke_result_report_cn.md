# 基于 `training_update_admission` greedy-activity 约束 + budget-flat reward 的 Step-wise PPO/Transformer `v13` smoke 结果报告

## 运行概况
- 时间：2026-06-21 Asia/Shanghai
- 远端主机：`10.10.252.11`
- 训练入口：[scripts/train_stepwise_ppo.py](/G:/TransDSSAT/scripts/train_stepwise_ppo.py)
- 远端产物目录：
  - `/fs/fast/u2021201693/lym/TransDSSAT/artifacts/stepwise_ppo_rice_maize_training_data_admission_greedy_budgetflat_rerun_v13_smoke_20260621_20260621_181950`
- 本次合同变化：
  - 保留 budget-flat `reward_v2`
  - 保留轻栈 `training_update_admission`
  - 在 rollout-side 与 expected-activity 之外，再加入 greedy/deterministic activity admission

## 正式产物
- checkpoint：
  - `/fs/fast/u2021201693/lym/TransDSSAT/artifacts/stepwise_ppo_rice_maize_training_data_admission_greedy_budgetflat_rerun_v13_smoke_20260621_20260621_181950/stepwise_ppo_policy.pt`
- metrics：
  - `/fs/fast/u2021201693/lym/TransDSSAT/artifacts/stepwise_ppo_rice_maize_training_data_admission_greedy_budgetflat_rerun_v13_smoke_20260621_20260621_181950/metrics.json`
- run log：
  - `/fs/fast/u2021201693/lym/TransDSSAT/artifacts/stepwise_ppo_rice_maize_training_data_admission_greedy_budgetflat_rerun_v13_smoke_20260621_20260621_181950/run.log`

## 核心结果
- 本次 smoke 正常完成并产出 checkpoint 与 metrics。
- 按 `selection_metric=yield_floor_gap` 选出的最佳 checkpoint 为 `epoch 2`。
- 最佳 checkpoint 指标：
  - `best_epoch = 2`
  - `val/test mean_reward_gain = -1.265862 / -1.487970`
  - `val/test mean_yield_floor_gap_ratio = 0.424903 / 0.418591`
  - `val/test mean_yield_floor_attainment_pct = 57.510 / 58.141`
  - `val/test irrigation_mm = 224.786 / 222.920`
  - `val/test nitrogen_kg_ha = 162.069 / 164.780`
- 末轮 `epoch 6` 指标：
  - `final val/test mean_reward_gain = -2.584254 / -2.826294`
  - `final val/test mean_yield_floor_gap_ratio = 0.433871 / 0.427871`
  - `final val/test mean_yield_floor_attainment_pct = 56.613 / 57.213`
  - `final val/test irrigation_mm = 226.424 / 224.636`
  - `final val/test nitrogen_kg_ha = 162.440 / 165.137`

## 训练合同信号
- `v13` 的正面结果很明确：
  - `v12` 中后期的 `0 irrigation` 坍塌消失了
  - greedy semantic mismatch 已不再是主矛盾
  - 各 epoch 的评估 irrigation 始终维持在接近 baseline 的正常区间
- 但新的主问题也同样明确：
  - 最优点从 `v12` 的 `epoch 5` 回退到 `epoch 2`
  - 训练过程出现明显的 hard rejection 过量
  - 代表性信号：
    - `epoch 3`: `11 admitted / 45 rejected`
    - `epoch 5`: `0 admitted / 1 rejected`
    - `epoch 3 mean_update_admission_shortfall = 0.060890`
    - `epoch 5 mean_update_admission_shortfall = 0.017783`
- 这说明当前 greedy admission 虽然能防止执行语义坍塌，但“只要 shortfall > 0 就整步拒绝”的策略过于刚性，开始抑制正常学习更新。

## 与 `v12` 的关键对比
- `v12` 最优点：
  - `best_epoch = 5`
  - `val/test mean_reward_gain = -0.801074 / -0.930447`
  - `val/test mean_yield_floor_gap_ratio = 0.420487 / 0.413464`
  - 存在后期 `0 irrigation` 坍塌
- `v13` 相比 `v12` 的结论：
  - 成功去除了 `0 irrigation` 坍塌
  - 但最佳 checkpoint 质量和出现时机都退化
  - 因此不能直接晋级推广为下一阶段主合同

## 结论
- `v13` 不是失败样本，它完成了一个必要诊断：greedy semantic alignment 是必要的，但 hard reject 过于严格。
- 当前剩余缺口已收敛为“如何保留 greedy admission 的防坍塌收益，同时避免过量冻结训练步骤”。
- 因此后续不应回退到旧 penalty 栈，而应把 `training_update_admission` 改成两段式：
  - 小 shortfall 作为 soft penalty 继续训练
  - 大 shortfall 才触发 hard reject
- 当前任务继续保持 `In Progress`，并已据此进入 `v14` replacement smoke。
