# 2026-06-12 Step-wise PPO Gated Continuous 正式结果报告

## 1. 实验结论

本轮正式 `gated continuous-action` GPU 训练已经完成，但结果**没有超过**当前权威对照基线 `discrete transformer`。  
在相同 `10000` 场景池、相同 `seed/pool_seed`、相同 `reward_gain` checkpoint 选择合同下，`gated_continuous + transformer` 的最优 checkpoint 出现在 `epoch = 18`，其 `val.reward_gain`、`test.reward_gain`、`mean_total_score_100` 都低于已发布的离散 transformer 重跑基线。

因此，本轮正式结论是：

- `gated continuous` 路线已经完成首次正式 GPU 闭环，可视为一个**有效但未胜出**的候选策略族
- 当前权威比较基线仍然保持为 `docs/stepwise-ppo-transformer-rerun-result-report-cn.md` 中的离散 transformer 结果
- 当前冻结 proxy 合同下，不应将 `gated continuous` 提升为新的权威策略

## 2. 正式运行记录

- 远端主机：`10.10.252.11`
- tmux 会话/窗口：`transdssat:gc-full`
- 启动时间：`2026-06-12 01:07 Asia/Shanghai`
- 产物落盘完成时间：约 `2026-06-12 01:44 Asia/Shanghai`
- 输出目录：`/fs/fast/u2021201693/lym/TransDSSAT/artifacts/stepwise_ppo_gated_continuous_10000_transformer_20260612_010700`
- checkpoint：`/fs/fast/u2021201693/lym/TransDSSAT/artifacts/stepwise_ppo_gated_continuous_10000_transformer_20260612_010700/stepwise_ppo_policy.pt`
- metrics：`/fs/fast/u2021201693/lym/TransDSSAT/artifacts/stepwise_ppo_gated_continuous_10000_transformer_20260612_010700/metrics.json`
- 持久日志：`/fs/fast/u2021201693/lym/TransDSSAT/artifacts/stepwise_ppo_gated_continuous_10000_transformer_20260612_010700/run.log`

正式收尾核验：

- `tmux` 中不再存在运行中的 `gc-full` 训练窗口
- 当前不存在活动中的 `train_stepwise_ppo.py` 训练进程
- `metrics.json`、`stepwise_ppo_policy.pt`、`run.log` 都已持久化落盘

## 3. 运行合同

本轮正式运行沿用已经冻结的 gated continuous 合同，不改变比较口径：

- 入口脚本：`scripts/train_stepwise_ppo.py`
- PPO 路径：`transdssat.stepwise_ppo`
- 环境接口：`transdssat.environments.stepwise.StepwiseDecisionEnvironment`
- backbone：`transformer`
- action mode：`gated_continuous`
- control mode：`joint`
- selection metric：`reward_gain`
- selection split：`val`
- train / val / test：`9000 / 500 / 500`
- epochs：`20`
- episodes per epoch：`128`
- minibatch size：`256`
- seed：`20260608`
- pool seed：`20260608`
- 逻辑训练设备：`cuda:0`
- 实际物理 GPU：通过 `CUDA_VISIBLE_DEVICES=6` 映射到逻辑 `cuda:0`

作为 staged GPU 闭环的一部分，以下前置阶段也已经完成：

- smoke-run：`/fs/fast/u2021201693/lym/TransDSSAT/artifacts/stepwise_ppo_gated_continuous_smoke_20260612_005840`
- intermediate：`/fs/fast/u2021201693/lym/TransDSSAT/artifacts/stepwise_ppo_gated_continuous_intermediate_20260612_010230`

## 4. 关键结果

### 4.1 gated continuous 最优 checkpoint

最优 checkpoint 出现在 `epoch = 18`，不是最终 `epoch = 20`。这说明该路线在尾段同样出现了轻微回落，因此仍按冻结合同选择 `val.reward_gain` 最优的 `epoch 18`。

| split | mean_reward_gain | mean_total_score_100 | mean_yield_gain_pct | mean_irrigation_mm | mean_nitrogen_kg_ha | mean_budget_adherence_score |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| val | `9.218420` | `52.104` | `-1.652` | `37.98` | `27.442` | `100.0` |
| test | `8.996074` | `52.484` | `-1.631` | `41.178` | `34.038` | `100.0` |

同时记录：

- `best_selection_value = 9.218420`
- `selection_metric = reward_gain`
- `val.mean_reward = 10.729054`
- `test.mean_reward = 9.353590`

### 4.2 与正式离散 transformer 基线对比

当前权威对照基线来自 `docs/stepwise-ppo-transformer-rerun-result-report-cn.md`，其最优 checkpoint 关键数值如下：

| split | mean_reward_gain | mean_total_score_100 | mean_yield_gain_pct | mean_irrigation_mm | mean_nitrogen_kg_ha | mean_budget_adherence_score |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| val | `11.192760` | `54.425` | `-0.796` | `55.98` | `3.40` | `100.0` |
| test | `11.321523` | `54.801` | `-0.767` | `58.40` | `2.52` | `100.0` |

`gated continuous transformer` 相对离散 transformer 的变化如下：

| split | reward_gain delta | score delta | yield_gain_pct delta | irrigation delta | nitrogen delta | budget delta |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| val | `-1.974340` | `-2.321` | `-0.856` | `-18.00` | `+24.042` | `0.0` |
| test | `-2.325449` | `-2.317` | `-0.864` | `-17.222` | `+31.518` | `0.0` |

解读：

- `gated continuous` 确实学到了更强的节水行为，灌溉量进一步下降
- 但这种下降并没有转化为更高的 `reward_gain` 或更高的总分
- 与离散 transformer 相比，它的产量增益更差，施氮量反而显著更高
- 因而在当前冻结 proxy 合同下，`gated continuous` 不是更优策略，只能视为一次已完成的负向对照实验

## 5. 判定与后续意义

本轮结果可以判定为：

- `formal_gpu_cycle_completed`
- `valid_candidate_but_not_authoritative`
- `discrete_transformer_still_authoritative`

支持这一判定的依据：

- smoke-run、intermediate、full-run 三个 GPU 阶段都已完成
- full-run 产物齐全，包含 checkpoint、metrics、persistent log
- 最终比较口径与离散 transformer 基线保持一致
- `gated continuous` 在核心选择指标 `reward_gain` 上未能胜出

这次结果的直接意义是：

- `gated continuous` 训练链路已经打通，后续若要继续迭代，不再是工程打通问题，而是策略质量问题
- 当前冻结奖励合同更偏好“低水低投入”并不自动意味着 gated continuous 会优于离散动作表
- 如果后续还要推进连续动作路线，应重点审计 gate/amount 参数化、动作投影规则、奖励结构，以及氮投入异常偏高的原因

## 6. 最终裁定

当前自动化任务的完成标准已经满足：

- gated continuous smoke-run 已完成
- gated continuous intermediate run 已完成
- gated continuous full formal run 已完成
- 正式结果产物已落盘
- 正式对比报告已经写入持久文档

因此，本任务现在可以从 `In Progress` 更新为 `Completed`。下一次自动化唤醒应等待新的 Bootstrap 任务，而不是继续重复本轮 gated continuous GPU 训练。
