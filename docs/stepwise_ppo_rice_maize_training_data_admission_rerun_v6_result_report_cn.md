# 基于 training_update_admission 合同的 Step-wise PPO/Transformer `v6` 重跑结果报告

## 运行概况
- 时间：2026-06-21 Asia/Shanghai
- 远端主机：`10.10.252.11`
- 训练入口：[scripts/train_stepwise_ppo.py](/G:/TransDSSAT/scripts/train_stepwise_ppo.py)
- 远端产物目录：
  - `/fs/fast/u2021201693/lym/TransDSSAT/artifacts/stepwise_ppo_rice_maize_training_data_admission_rerun_v6_20260621_0509`
- 关键新增训练合同：
  - `training_update_admission`
  - 当 rollout minibatch 的已实现活动量低于配置下限时，拒绝该 minibatch 进入 PPO 参数更新

## 正式产物
- checkpoint：
  - `/fs/fast/u2021201693/lym/TransDSSAT/artifacts/stepwise_ppo_rice_maize_training_data_admission_rerun_v6_20260621_0509/stepwise_ppo_policy.pt`
- metrics：
  - `/fs/fast/u2021201693/lym/TransDSSAT/artifacts/stepwise_ppo_rice_maize_training_data_admission_rerun_v6_20260621_0509/metrics.json`
- run log：
  - `/fs/fast/u2021201693/lym/TransDSSAT/artifacts/stepwise_ppo_rice_maize_training_data_admission_rerun_v6_20260621_0509/run.log`

## 核心结果
- 本次重跑完整执行了 `20` 个 epoch，并正常结束，`finished_at = 2026-06-21T05:40:08+08:00`。
- 按 `selection_metric=yield_floor_gap` 选出的最优 checkpoint 在 `epoch 4`。
- 最优 checkpoint 指标：
  - `best_epoch = 4`
  - `val mean_reward_gain = -0.179426`
  - `test mean_reward_gain = -0.356199`
  - `val mean_yield_floor_gap_ratio = 0.425392`
  - `test mean_yield_floor_gap_ratio = 0.418502`
  - `val mean_yield_floor_attainment_pct = 57.461`
  - `test mean_yield_floor_attainment_pct = 58.15`
  - `val mean_irrigation_mm = 224.936`
  - `test mean_irrigation_mm = 223.126`
  - `val mean_nitrogen_kg_ha = 162.473`
  - `test mean_nitrogen_kg_ha = 165.17`
- 最终 `epoch 20` 指标：
  - `final val mean_reward_gain = -2.836817`
  - `final test mean_reward_gain = -3.049318`
  - `final val mean_yield_floor_gap_ratio = 0.436697`
  - `final test mean_yield_floor_gap_ratio = 0.430106`
  - `final val mean_yield_floor_attainment_pct = 56.33`
  - `final test mean_yield_floor_attainment_pct = 56.989`
  - `final val/test irrigation_mm = 226.519 / 224.721`
  - `final val/test nitrogen_kg_ha = 162.642 / 165.342`

## 与 `v4` 的关键对比
- `v4` 最优点：
  - `best_epoch = 5`
  - `val/test mean_yield_floor_gap_ratio = 0.412211 / 0.404294`
  - `val/test nitrogen_kg_ha = 67.435 / 65.601`
- `v4` 末期 collapse：
  - `epoch 18-20 val irrigation_mm` 接近或等于 `0`
  - `epoch 18-20 val nitrogen_kg_ha = 0`
- `v6` 相比 `v4` 的明确改善：
  - 晚期不再掉回 `0` irrigation / `0` nitrogen
  - 最终 epoch 仍维持接近 baseline 的资源活动量
  - selection guardrail 始终满足，未再出现“靠 guardrail 把 0/0 checkpoint 挡掉”的末期极端形态
- `v6` 相比 `v4` 的不足：
  - 最优 checkpoint 没有后移，反而回到 `epoch 4`
  - 最优 `yield_floor_gap_ratio` 明显差于 `v4`
  - 整体 reward 与产量地板差距没有收敛到更优区间

## 对 admission 合同的判断
- 可以确认 `training_update_admission` 改变了后期训练轨迹：
  - 本次正式重跑不再收缩到 `0` 灌溉 / `0` 施氮吸引子
  - 晚期 `mean_update_min_enabled_activity_ratio` 保持在约 `0.33` 附近，而不是掉到接近 `0`
- 但当前证据不足以把问题判定为“已修复”：
  - 最优点仍出现在很早的 epoch
  - 后期虽然不再全零，但验证集 `yield_floor_gap_ratio` 仍回升到约 `0.437`
  - 这说明 admission 合同更像是“阻断极端 collapse”，而不是“把 PPO 推向更优长期收敛点”

## 结论
- `v6` 完成了对 `training_update_admission` 的正式 GPU 级检验。
- 结果是部分正面但不充分：
  - 已明显削弱晚期 `0/0` collapse attractor
  - 但没有把最佳 checkpoint 推迟到更晚 epoch，也没有带来优于 `v4` 的最佳质量
- 因此当前更合理的判断是：
  - 保持任务 `In Progress`
  - 下一阶段不应继续做同类轻量 reward tweak
  - 应转向更强的 imitation / anchor / admission 组合设计，目标从“阻止全零坍缩”提升到“让较优活动水平在后期可持续”
