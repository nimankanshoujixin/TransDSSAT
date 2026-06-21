# 基于 anti-collapse 合同的一阶段 rerun 结果报告

## 运行概况
- 时间：2026-06-20 Asia/Shanghai
- 远端主机：`10.10.252.11`
- 训练入口：[`/G:/TransDSSAT/scripts/train_stepwise_ppo.py`](/G:/TransDSSAT/scripts/train_stepwise_ppo.py)
- 远端 wrapper：[`/G:/TransDSSAT/scripts/run_stepwise_ppo_remote.sh`](/G:/TransDSSAT/scripts/run_stepwise_ppo_remote.sh)
- 产物目录：
  - `/fs/fast/u2021201693/lym/TransDSSAT/artifacts/stepwise_ppo_rice_maize_training_data_anticollapse_rerun_20260620_20260620_194317`
- 运行配置：
  - `--sampling-mode training_data`
  - `--crops rice maize`
  - `--train-count 9000 --val-count 500 --test-count 500`
  - `--engine dssat_proxy`
  - `--backbone transformer`
  - `--action-mode continuous`
  - `--control-mode joint`
  - `--seed 20260620 --pool-seed 20260619`
  - `--reward-contract reward_v2`
  - `--selection-metric yield_floor_gap`
  - `--selection-min-activity-ratio 0.05`
  - `--selection-min-yield-floor-attainment-pct 55.0`

## 本次合同包含的改动
- best-checkpoint 不再按单一标量直接选，而是先过 guardrail：
  - 最低启用通道 activity ratio
  - 最低 mean yield-floor attainment
- 在 `reward_v2` 终局奖励上加入第一版 anti-collapse penalty：
  - 仅在产量低于 yield floor 时触发
  - 对极低季节总灌溉 / 总施氮做软惩罚
- official real-subset 评估合同升级为双层对照：
  - `real observation / DSSAT baseline replay / policy replacement replay`
  - `replacement - baseline`

## 核心结果
- rerun 完整跑满 `20` 个 epoch，并正常退出：
  - `started_at = 2026-06-20T19:43:24+08:00`
  - `finished_at = 2026-06-20T20:13:08+08:00`
  - `status = 0`
- 平均每个 epoch 的墙钟时间约为 `89.2` 秒，约 `1.49` 分钟。
- 最终选出的 best checkpoint 仍在 `epoch 5`：
  - `best_selection_value = [1, -0.412211, 58.779, 0.41457641706627324, -0.412211]`
  - `val mean_reward_gain = 1.594913`
  - `test mean_reward_gain = 1.551148`
  - `val mean_yield_floor_gap_ratio = 0.412211`
  - `test mean_yield_floor_gap_ratio = 0.404294`
  - `val mean_irrigation_mm = 196.626`
  - `test mean_irrigation_mm = 193.627`
  - `val mean_nitrogen_kg_ha = 67.435`
  - `test mean_nitrogen_kg_ha = 65.601`

## guardrail 成功的部分
- late-stage collapsed checkpoint 没有再被误选成最终结果。
- 到 `epoch 18` 时，验证集已经坍缩到：
  - `mean_irrigation_mm = 0.0`
  - `mean_nitrogen_kg_ha = 0.0`
  - `mean_yield_floor_gap_ratio = 0.458747`
  - `mean_yield_floor_attainment_pct = 54.125`
- 该点被 guardrail 正确判为 `eligible_for_best_checkpoint = false`。
- `epoch 19-20` 虽然灌溉略有恢复到 `8.725 / 20.643 mm`，但 nitrogen 仍为 `0.0`，同样继续不合格。

## guardrail 没有解决的部分
- 训练轨迹本身仍然会继续滑向低投入吸引子，说明问题不只是 checkpoint 选错。
- 这次不是“后期轻微软过拟合”，而是训练主轨迹仍允许退化到几乎不施水不施氮。
- 第一版 reward-side penalty 只改变了“最后选谁”，没有从目标函数层面消除该 attractor。

## 为什么 reward 里有产量项，训练后期仍会坍缩
- 这里的失败不是“零投入策略最终 reward 更高”，而是 PPO 训练过程中仍可能沿着一个低方差、低成本、低投入的方向持续滑落。
- 对当前合同而言，成本项和预算占用是更稠密、更稳定的即时信号；而 yield floor 惩罚只在季末结算，且跨场景方差更大。
- 从已完成 rerun 的轨迹看，`nitrogen` 是更明显的薄弱通道：
  - `epoch 5` 已降到 `67.435 kg/ha`
  - `epoch 9` 继续降到 `33.016 kg/ha`
  - `epoch 18-20` 直接收缩到 `0.0`
- 同时 proxy 汇总中长期 `mean_avg_nitrogen_stress` 仍接近 `0.0`，终局 `terminal_soil_nitrogen_kg_ha` 仍然偏高，说明在当前训练分布上模型很容易学到“氮再少一点也未必立刻被强惩罚”。
- 结果就是：即便最终验证 reward 已经变差，优化轨迹仍可能缓慢滑向一个更省投入、但更差的局部吸引子。

## 二阶段修正决策
- 结论：一阶段合同只证明了“guardrail 能防止选坏 checkpoint”，还没有证明“guardrail 能防止训练滑落”。
- 因此本轮进入第二次 CPU-safe 合同收紧，重点放在 nitrogen 通道：
  - `minimum_nitrogen_ratio` 从 `0.10` 提到 `0.15`
  - collapse penalty 改成分通道，而不是简单合并 shortfall
  - `nitrogen_shortfall_penalty_weight = 36.0`
  - `irrigation_shortfall_penalty_weight = 24.0`
  - 新增 `zero_nitrogen_extra_penalty = 3.0`
- 设计意图：
  - 让“少量灌溉 + 零氮”的晚期滑坡不再是便宜路径
  - 更早惩罚氮通道的结构性塌缩，而不是等到完全 `0/0` 才明显拉开

## 当前后续动作
- 本地与远端 CPU-safe 校验已通过：
  - `python -m unittest tests.test_stepwise_env tests.test_stepwise_ppo -v`
- 第二阶段 replacement rerun 已于 2026-06-20 20:27 Asia/Shanghai 启动：
  - tmux window: `transdssat:ppo-ac-rerun-v2`
  - artifact dir:
    - `/fs/fast/u2021201693/lym/TransDSSAT/artifacts/stepwise_ppo_rice_maize_training_data_anticollapse_rerun_v2_20260620_20260620_202613`
- 下一次 wakeup 应优先检查：
  - 是否仍然滑到 `nitrogen = 0`
  - best epoch 是否从 `5` 后移
  - `epoch 9-20` 区间的 activity ratio 是否明显抬升
