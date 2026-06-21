# 基于去重训练池的 Step-wise PPO/Transformer 重跑结果报告

## 运行概况
- 时间：2026-06-20 Asia/Shanghai
- 远端主机：`10.10.252.11`
- 训练入口：[`/G:/TransDSSAT/scripts/train_stepwise_ppo.py`](/G:/TransDSSAT/scripts/train_stepwise_ppo.py)
- 远端 wrapper：[`/G:/TransDSSAT/scripts/run_stepwise_ppo_remote.sh`](/G:/TransDSSAT/scripts/run_stepwise_ppo_remote.sh)
- 运行模式：
  - `--sampling-mode training_data`
  - `--crops rice maize`
  - `--train-count 9000 --val-count 500 --test-count 500`
  - `--engine dssat_proxy`
  - `--backbone transformer`
  - `--action-mode continuous`
  - `--control-mode joint`
  - `--device cuda:0`
  - `--seed 20260620 --pool-seed 20260619`
- 训练产物目录：
  - `/fs/fast/u2021201693/lym/TransDSSAT/artifacts/stepwise_ppo_rice_maize_training_data_rerun_20260620_1710`

## 预修复结果
- 训练池修复后重新验证通过：
  - `unique_scenario_id_count = 10000`
  - `distinct_signature_count = 10000`
  - `validation_errors = []`
- `run.log` 持久化链路修复成功：
  - 正式 rerun 全程都有 live stdout 落盘
  - 不再出现上轮“tmux pane 有输出但 run.log 为空”的问题

## 正式产物
- checkpoint：
  - `/fs/fast/u2021201693/lym/TransDSSAT/artifacts/stepwise_ppo_rice_maize_training_data_rerun_20260620_1710/stepwise_ppo_policy.pt`
- metrics：
  - `/fs/fast/u2021201693/lym/TransDSSAT/artifacts/stepwise_ppo_rice_maize_training_data_rerun_20260620_1710/metrics.json`
- run log：
  - `/fs/fast/u2021201693/lym/TransDSSAT/artifacts/stepwise_ppo_rice_maize_training_data_rerun_20260620_1710/run.log`

## 重跑核心结果
- 训练完整跑满 `20` 个 epoch。
- 按 `selection_metric=yield_floor_gap` 选出的最优 checkpoint 在 `epoch 5`。
- 最优 checkpoint 指标：
  - `val mean_reward_gain = 1.594913`
  - `test mean_reward_gain = 1.551148`
  - `val mean_yield_floor_gap_ratio = 0.412211`
  - `test mean_yield_floor_gap_ratio = 0.404294`
  - `val mean_yield_kg_ha = 2763.128`
  - `test mean_yield_kg_ha = 2803.387`
  - `val mean_irrigation_mm = 196.626`
  - `test mean_irrigation_mm = 193.627`
  - `val mean_nitrogen_kg_ha = 67.435`
  - `test mean_nitrogen_kg_ha = 65.601`
- 最终 `epoch 20` 再次明显退化：
  - `final val mean_reward_gain = -0.720261`
  - `final test mean_reward_gain = -0.876687`
  - `final val mean_yield_floor_gap_ratio = 0.458747`
  - `final test mean_yield_floor_gap_ratio = 0.451843`
  - `final val/test irrigation_mm = 0.0 / 0.0`
  - `final val/test nitrogen_kg_ha = 0.0 / 0.0`

## 与上一轮正式训练对比
- 上一轮 best checkpoint：
  - `best_epoch = 4`
  - `best val/test mean_reward_gain = 0.313969 / 0.171241`
  - `best val/test mean_yield_floor_gap_ratio = 0.422744 / 0.409486`
- 本轮 best checkpoint：
  - `best_epoch = 5`
  - `best val/test mean_reward_gain = 1.594913 / 1.551148`
  - `best val/test mean_yield_floor_gap_ratio = 0.412211 / 0.404294`
- 结论：
  - 训练池重复问题已经消失
  - `reward_gain` 和 best checkpoint 的 `yield_floor_gap_ratio` 都有实质改善
  - 但 late-training collapse 仍然存在，而且末期塌缩比上一轮更极端，收缩到 `0` 灌溉、`0` 氮

## 新 best checkpoint 的真实子集后评估

### 锚点 case
- 产物目录：
  - `/fs/fast/u2021201693/lym/TransDSSAT/artifacts/real_subset_checkpoint_eval_anchor_rerun_20260620`
- `mx475_migrated:1`
  - observed `4815`
  - simulated `6052`
  - gap ratio `0.256906`
- `wuhu_rice_calibrated:11`
  - observed `6365`
  - simulated `6626`
  - gap ratio `0.041005`

### Full validated subset
- 产物目录：
  - `/fs/fast/u2021201693/lym/TransDSSAT/artifacts/real_subset_checkpoint_eval_full_rerun_20260620`
- 总体汇总：
  - `case_count = 20`
  - `mx475_migrated = 8`
  - `wuhu_rice_calibrated = 12`
  - `mean_yield_gap_kg_ha = 431.35`
  - `mean_abs_yield_gap_kg_ha = 566.35`
  - `mean_yield_gap_ratio = 0.080018`
- 分子集汇总：
  - `mx475_migrated`
    - `mean_ratio = 0.117125`
    - `mean_abs_ratio = 0.117125`
    - `min/max ratio = 0.052468 / 0.256906`
  - `wuhu_rice_calibrated`
    - `mean_ratio = 0.055279`
    - `mean_abs_ratio = 0.084301`
    - `min/max ratio = -0.130859 / 0.170535`
- 误差最大的若干 case：
  - `mx475_migrated:1` `+0.256906`
  - `wuhu_rice_calibrated:13` `+0.170535`
  - `mx475_migrated:3` `+0.163077`
  - `wuhu_rice_calibrated:15` `+0.147104`
  - `wuhu_rice_calibrated:23` `-0.130859`

## 结果解读
- 这次 rerun 在“数据质量”和“审计可追踪性”上是成功的：
  - 训练池去重通过
  - `run.log` 修复通过
  - 正式 rerun、锚点评估、full validated real-subset 都完成
- 从模型质量看，本轮 best checkpoint 比上一轮更好：
  - best `yield_floor_gap_ratio` 小幅改善
  - best `reward_gain` 明显改善
- 但训练稳定性问题并没有解决：
  - 末期仍然塌缩，而且塌成全零水肥策略
- 从真实子集后评估看：
  - `wuhu_rice_calibrated` 的整体偏差相对可控
  - `mx475_migrated` 子集在新 best checkpoint 下偏高更明显，尤其 `tr01` 和 `tr03`

## 结论
- 本轮阶段性任务可以视为完成：
  - 训练池重复问题已修复
  - 正式 rerun 已完成
  - 正式 rerun 结果已审计
  - 新 best checkpoint 的真实子集后评估已从锚点扩展到 full validated subset
- 但这不代表模型问题已解决。下一阶段更值得做的是：
  1. 处理 late-training collapse
  2. 分析为何 `mx475` 在新 checkpoint 上系统性偏高
  3. 决定是否要引入早停、checkpoint selection 约束或更强的 collapse regularization
