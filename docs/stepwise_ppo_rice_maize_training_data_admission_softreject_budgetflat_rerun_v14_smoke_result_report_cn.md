# 基于 `training_update_admission` soft/hard split + budget-flat reward 的 Step-wise PPO/Transformer `v14` smoke 结果报告

## 运行概况
- 时间：2026-06-21 Asia/Shanghai
- 远端主机：`10.10.252.11`
- 训练入口：[scripts/train_stepwise_ppo.py](/G:/TransDSSAT/scripts/train_stepwise_ppo.py)
- 远端产物目录：
  - `/fs/fast/u2021201693/lym/TransDSSAT/artifacts/stepwise_ppo_rice_maize_training_data_admission_softreject_budgetflat_rerun_v14_smoke_20260621_20260621_181000`
- 本次合同变化：
  - 保留 budget-flat `reward_v2`
  - 保留 greedy/deterministic activity admission
  - 将 `training_update_admission` 改成两段式：
    - 小 shortfall 作为 soft penalty 保留梯度更新
    - 大 shortfall 才触发 hard rejection

## 正式产物
- checkpoint：
  - `/fs/fast/u2021201693/lym/TransDSSAT/artifacts/stepwise_ppo_rice_maize_training_data_admission_softreject_budgetflat_rerun_v14_smoke_20260621_20260621_181000/stepwise_ppo_policy.pt`
- metrics：
  - `/fs/fast/u2021201693/lym/TransDSSAT/artifacts/stepwise_ppo_rice_maize_training_data_admission_softreject_budgetflat_rerun_v14_smoke_20260621_20260621_181000/metrics.json`
- run log：
  - `/fs/fast/u2021201693/lym/TransDSSAT/artifacts/stepwise_ppo_rice_maize_training_data_admission_softreject_budgetflat_rerun_v14_smoke_20260621_20260621_181000/run.log`

## 核心结果
- 本次 smoke 正常完成并产出 checkpoint 与 metrics。
- 按 `selection_metric=yield_floor_gap` 选出的最佳 checkpoint 退回到 `epoch 1`。
- 最佳 checkpoint 指标：
  - `best_epoch = 1`
  - `val/test mean_reward_gain = -1.267923 / -1.150835`
  - `val/test mean_yield_floor_gap_ratio = 0.524330 / 0.524406`
  - `val/test mean_yield_floor_attainment_pct = 47.567 / 47.559`
  - `val/test irrigation_mm = 363.821 / 363.692`
  - `val/test nitrogen_kg_ha = 368.916 / 368.774`
- 末轮 `epoch 6` 指标：
  - `final val/test mean_reward_gain = -1.669132 / -1.566211`
  - `final val/test mean_yield_floor_gap_ratio = 0.524649 / 0.524743`
  - `final val/test mean_yield_floor_attainment_pct = 47.535 / 47.526`
  - `final val/test irrigation_mm = 364.057 / 363.882`
  - `final val/test nitrogen_kg_ha = 370.046 / 369.970`

## 训练合同信号
- `v14` 的正面结果有限：
  - `v13` 中后期的 `0 irrigation` collapse 没有回来
  - 软罚机制也确实让部分小 shortfall minibatch 保留了更新
- 但主问题仍然存在，而且更清晰：
  - 最优点重新退回到 `epoch 1`
  - `yield_floor_gap` 明显弱于 `v12/v13`
  - 后几轮仍重新触发 hard rejection
- 代表性信号：
  - `epoch 2`: `admitted_update_count = 1`, `rejected_update_count = 0`, `update_admission_penalty = 0.013392`
  - `epoch 5`: `admitted_update_count = 0`, `rejected_update_count = 1`, `mean_update_admission_shortfall = 0.046791`
  - `epoch 6`: `admitted_update_count = 0`, `rejected_update_count = 1`, `mean_update_admission_shortfall = 0.027246`
- 关键诊断：
  - `epoch 5/6` 的 greedy activity 其实仍健康，灌溉与氮肥执行活动都不低
  - 触发 hard reject 的主因反而是 `expected nitrogen activity` 相对 retention target 的小幅短缺
  - 这说明把 `expected activity` 和 `greedy activity` 一起放进 hard gate 仍然过严

## 与 `v13` / `v12` 的关键对比
- 相比 `v13`：
  - `v14` 去掉了“只要 shortfall > 0 就整步拒绝”的最硬冻结
  - 但还没有恢复 `v12` 那种更晚出现的较优 checkpoint
- 相比 `v12`：
  - `v14` 继续保住了“没有零灌溉坍塌”的收益
  - 但 `yield_floor_gap` 和最佳点时机都明显更差
- 结论不是“soft/hard split 无效”，而是：
  - hard gate 应继续保留对 `greedy semantic collapse` 的约束
  - `expected activity` 更适合留在 soft penalty 层，而不是直接参与 hard reject

## 结论
- `v14` 完成了必要诊断：两段式 soft/hard admission 本身是对的，但 hard gate 的信号分层还不对。
- 当前剩余缺口已经收敛为：
  - 继续用 hard reject 约束 rollout/greedy 这类真正会造成执行语义坍塌的信号
  - 把 `expected activity` 仅作为 soft penalty 保留训练压力
- 因此后续工作进入 `v15`：
  - 新合同保留 greedy hard gate
  - 将 expected shortfall 从 hard rejection 中剥离
  - 再做同配置 staged smoke 验证是否能同时保住“无零灌溉坍塌”和“更晚更好的 checkpoint”
