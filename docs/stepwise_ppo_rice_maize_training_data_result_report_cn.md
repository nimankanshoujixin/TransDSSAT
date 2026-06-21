# 基于真实训练数据池的 Step-wise PPO/Transformer 训练结果报告

## 运行概况
- 时间：2026-06-20 Asia/Shanghai
- 远端主机：`10.10.252.11`
- 训练入口：`scripts/train_stepwise_ppo.py`
- 运行模式：
  - `--sampling-mode training_data`
  - `--crops rice maize`
  - `--train-count 9000 --val-count 500 --test-count 500`
  - `--engine dssat_proxy`
  - `--backbone transformer`
  - `--action-mode continuous`
  - `--control-mode joint`
  - `--device cuda:0`
  - `--seed 20260619 --pool-seed 20260619`
- 产物目录：`/fs/fast/u2021201693/lym/TransDSSAT/artifacts/stepwise_ppo_rice_maize_training_data_20260620_1544`

## 正式产物
- checkpoint：`/fs/fast/u2021201693/lym/TransDSSAT/artifacts/stepwise_ppo_rice_maize_training_data_20260620_1544/stepwise_ppo_policy.pt`
- metrics：`/fs/fast/u2021201693/lym/TransDSSAT/artifacts/stepwise_ppo_rice_maize_training_data_20260620_1544/metrics.json`
- log：`/fs/fast/u2021201693/lym/TransDSSAT/artifacts/stepwise_ppo_rice_maize_training_data_20260620_1544/run.log`

## 核心结果
- 训练完整跑满 `20` 个 epoch。
- 按 `selection_metric=yield_floor_gap` 选出的最优 checkpoint 在 `epoch 4`。
- 最优 checkpoint 指标：
  - `val mean_reward_gain = 0.313969`
  - `test mean_reward_gain = 0.171241`
  - `val mean_yield_floor_gap_ratio = 0.422744`
  - `test mean_yield_floor_gap_ratio = 0.409486`
  - `val mean_yield_kg_ha = 2709.524`
  - `test mean_yield_kg_ha = 2780.918`
  - `val mean_irrigation_mm = 173.923`
  - `test mean_irrigation_mm = 169.776`
  - `val mean_nitrogen_kg_ha = 135.04`
  - `test mean_nitrogen_kg_ha = 136.412`
- 最终 epoch 20 指标明显退化：
  - `final val mean_reward_gain = -1.359368`
  - `final test mean_reward_gain = -1.564371`
  - `final val mean_yield_floor_gap_ratio = 0.460663`
  - `final test mean_yield_floor_gap_ratio = 0.448024`
  - `final val irrigation_mm = 0.0`
  - `final test irrigation_mm = 0.0`
  - `final val nitrogen_kg_ha = 56.215`
  - `final test nitrogen_kg_ha = 54.81`

## 结果解读
- 这次训练确实成功跑通了 Stage 4 的正式 GPU 流程，并产出了 checkpoint 与 metrics。
- 但模型质量并不稳定：
  - 中期 `epoch 4` 曾短暂取得正的 `reward_gain`
  - 后续训练持续退化，到末期基本收缩到“几乎不灌溉、显著降氮”的保守策略
- 即使在最佳 `epoch 4`，产量仍明显偏低：
  - `val/test mean_yield_kg_ha` 仅约 `2.7-2.8 t/ha`
  - 对应 `yield_floor_gap_ratio` 仍在 `0.41-0.42` 区间，距离目标带较远

## 新发现的问题
- `metrics.json` 明确给出了训练池校验错误：
  - `duplicate_scenario_id_detected`
  - `duplicate_cross_dimension_signature_detected`
- 这说明 `10000` 条真实训练数据池在大规模生成时存在重复样本或重复标识问题。
- `run.log` 为空文件；本次真实 stdout 实际写到了 tmux pane，而没有进入预期日志文件，说明远端日志重定向链路仍有缺陷。

## 结论
- 本轮可以确认“Stage 4 正式训练已完成并有正式产物”。
- 但当前结果不应视为可接受终版，因为同时存在两类问题：
  - 训练池存在重复校验错误
  - 训练后期策略退化明显，最终收缩为近零灌溉/低氮策略
- 因此当前更合理的状态是：保留任务 `In Progress`，先修复训练数据池去重与日志链路，再决定是否基于修复后的数据池重跑 GPU 训练。

## 建议的下一步
1. 审计 `generate_training_data(...)` / `generate_training_scenario_pool(...)`，定位重复 `scenario_id` 和重复 cross-dimension signature 的来源。
2. 修复训练池唯一性问题后，在 CPU 侧先对 `10000` 条池重新执行完整验证，不通过则禁止再次提交 GPU 训练。
3. 修复远端 wrapper / tmux 日志链路，确保下次正式训练的 stdout 能稳定进入 `run.log`。
4. 只有在去重验证通过后，才考虑发起下一次正式 GPU 重跑。
