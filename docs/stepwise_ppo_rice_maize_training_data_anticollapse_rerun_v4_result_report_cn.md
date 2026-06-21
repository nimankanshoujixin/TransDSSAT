# 基于训练期 activity regularizer 与延迟递减资源结算合同的第四阶段 rerun 结果报告

## 运行概况
- 时间：2026-06-21 Asia/Shanghai
- 远端主机：`10.10.252.11`
- 产物目录：
  - `/fs/fast/u2021201693/lym/TransDSSAT/artifacts/stepwise_ppo_rice_maize_training_data_anticollapse_rerun_v4_20260620_20260620_235839`
- 运行合同相对 `v2` 的新增点：
  - PPO update-time `training_activity_regularizer`
  - terminal `resource_settlement` 的递减边际收益合同
  - official `reward_v2` step semantics 与 proxy 合同对齐
  - 既有 checkpoint selection guardrail 保持启用

## 运行结果
- rerun 正常完成 `20` 个 epoch：
  - `started_at = 2026-06-20T23:59:09+08:00`
  - `finished_at = 2026-06-21T00:29:07+08:00`
  - `status = 0`
- 最终 `best checkpoint` 仍然是 `epoch 5`：
  - `best_selection_value = [1, -0.412211, 58.779, 0.41457641706627324, -0.412211]`
  - `val mean_yield_floor_gap_ratio = 0.412211`
  - `val mean_yield_floor_attainment_pct = 58.779`
  - `val mean_irrigation_mm = 196.626`
  - `val mean_nitrogen_kg_ha = 67.435`
  - `test mean_irrigation_mm = 193.627`
  - `test mean_nitrogen_kg_ha = 65.601`
- late-stage collapse 仍然出现，而且形态仍是向 `0` nitrogen / near-zero irrigation 退化：
  - `epoch 18 val irrigation/nitrogen = 0.0 / 0.0`
  - `epoch 19 val irrigation/nitrogen = 6.541 / 0.0`
  - `epoch 20 val irrigation/nitrogen = 0.0 / 0.0`
  - `epoch 18-20 eligible_for_best_checkpoint = false`

## 与前两轮 corrective rerun 的比较结论
- `v4` 没有把最佳 checkpoint 从 `epoch 5` 推迟到更晚 epoch。
- `v4` 的最佳点保住了非零氮肥，但氮肥水平仅约为 baseline 的 `41.46%`：
  - `candidate_mean_nitrogen_kg_ha = 67.435`
  - `baseline_mean_nitrogen_kg_ha = 162.66`
  - `nitrogen_activity_ratio = 0.414576`
- `v4` 也没有阻止后期重新掉回 collapse attractor：
  - `epoch 18-20` 的 validation nitrogen 仍为 `0.0`
  - irrigation 也收缩到 `0.0` 或接近 `0.0`
- 训练期 regularizer 确实开始产生轻微信号，但强度明显不足：
  - `epoch 18 activity_regularizer_penalty = 0.0`
  - `epoch 19 activity_regularizer_penalty = 0.000448`
  - `epoch 20 activity_regularizer_penalty = 0.000241`
  - `epoch 18-20 mean_expected_nitrogen_activity_ratio` 约为 `0.125-0.139`
- 这说明当前组合合同的效果主要是：
  - 让 selection guardrail 继续挡住塌缩末期 checkpoint
  - 让早期最佳点保持一定非零投入
  - 但仍不足以改变 PPO 训练后期持续滑向零投入吸引子的动力学

## 当前判断
- 现在可以进一步排除另一种较弱假设：
  - “只要在 terminal reward 侧继续细化成本形状，并叠加轻量 activity regularizer，就足以稳定训练后期行为”
- 当前证据更支持把下一轮 corrective 设计提升到更强的训练过程级约束，而不再只是 reward-shape 微调：
  1. 更强的 behavior-anchor / imitation-anchor
  2. 明确的 training-time admission rule，拒绝长期停留在低氮低水区域的更新轨迹
  3. state-conditioned minimum activity floor，而不是全局弱 regularizer
  4. 必要时把 action distribution 约束纳入 PPO 更新目标，而不是只看 terminal settlement

## 结论
- `v4` 完成了对“训练期轻量 regularizer + 延迟递减资源结算”组合合同的正式检验。
- 结果是否定的：
  - collapse 没有被消除
  - 最佳 checkpoint 没有后移
  - late-stage 零氮吸引子仍然存在
- 下一阶段应停止继续追加同类 reward-side 小修补，转向更强的训练期锚定或准入规则设计。
