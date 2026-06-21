# 基于更强 nitrogen-side anti-collapse 合同的二阶段 rerun 结果报告

## 运行概况
- 时间：2026-06-20 Asia/Shanghai
- 远端主机：`10.10.252.11`
- 产物目录：
  - `/fs/fast/u2021201693/lym/TransDSSAT/artifacts/stepwise_ppo_rice_maize_training_data_anticollapse_rerun_v2_20260620_20260620_202613`
- 运行配置保持与上一轮可比，仅收紧 reward-side anti-collapse 合同：
  - `minimum_nitrogen_ratio = 0.15`
  - `nitrogen_shortfall_penalty_weight = 36.0`
  - `irrigation_shortfall_penalty_weight = 24.0`
  - `zero_nitrogen_extra_penalty = 3.0`

## 运行结果
- rerun 完整跑满 `20` 个 epoch，并正常退出：
  - `started_at = 2026-06-20T20:27:08+08:00`
  - `finished_at = 2026-06-20T20:56:29+08:00`
  - `status = 0`
- 平均每个 epoch 的墙钟时间约为 `88.1` 秒，约 `1.47` 分钟。
- 最终 best checkpoint 仍然是 `epoch 5`：
  - `best_selection_value = [1, -0.412211, 58.779, 0.41457641706627324, -0.412211]`
  - `val mean_yield_floor_gap_ratio = 0.412211`
  - `val mean_irrigation_mm = 196.626`
  - `val mean_nitrogen_kg_ha = 67.435`
- late-stage collapse 仍然存在，并且坍缩形态与上一轮几乎相同：
  - `epoch 18 val irrigation/nitrogen = 0.0 / 0.0`
  - `epoch 19 val irrigation/nitrogen = 0.243 / 0.0`
  - `epoch 20 val irrigation/nitrogen = 0.0 / 0.0`
  - `epoch 18-20 eligible_for_best_checkpoint = false`

## 与一阶段 anti-collapse rerun 的对比结论
- best checkpoint 没变：
  - 仍然是 `epoch 5`
  - best 期的核心 validation 指标与上一轮一致
- collapse 没被阻止：
  - 训练后期仍然滑到 `nitrogen = 0`
  - irrigation 也仍然收缩到接近 `0`
- 唯一显著变化主要体现在 collapsed late epochs 的 reward 更差：
  - 一阶段 `epoch 18 val mean_reward_gain = -10.844628`
  - 二阶段 `epoch 18 val mean_reward_gain = -22.349591`
- 这说明更强的终局软惩罚只是在“坍缩发生以后”把分数拉得更低，但没有改变 PPO 主训练轨迹走向该吸引子的事实。

## 当前判断
- 现在可以更有把握地排除一种假设：
  - “只要继续加大 terminal reward-side anti-collapse penalty，就能把模型从 late-training collapse 拉回来”
- 当前更像是优化过程层面的结构性问题，而不是终局分数不够狠的问题。
- 下一轮更值得优先考虑的方向应当从“只改 terminal reward”前移到“直接改变训练动力学或行为约束”，例如：
  1. 在 rollout / update 期间引入 season-level activity regularization，而不是只在终局结算。
  2. 对 nitrogen gate / amount 增加显式 minimum-activity prior 或 imitation anchor。
  3. 在 checkpoint guardrail 之外，再加训练期 admission rule，阻止策略长期停留在零氮区域。

## 结论
- 二阶段 reward-side 收紧失败。
- 这轮实验的价值不是得到更好的 checkpoint，而是明确证明：
  - `selection guardrail` 只能保住“选点”
  - 更强的 terminal soft penalty 仍不足以保住“训练轨迹”
- 下一阶段应转向训练过程级约束，而不是继续仅靠终局 reward 加码。
