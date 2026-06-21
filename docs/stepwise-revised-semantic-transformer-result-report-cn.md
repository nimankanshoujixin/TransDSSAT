# 2026-06-13 Revised-Semantic Step-wise PPO Transformer 正式结果报告

## 1. 实验结论

本轮 revised-semantic 正式 GPU 闭环已经完成，`heuristic_v2 + reward_v2 + discrete transformer PPO` 的正式产物已落盘，当前自动化任务可以按完成收口。

- 远端主机：`10.10.252.11`
- 训练会话：`transdssat:rev-sem-full`
- 启动时间：`2026-06-13 02:11:19 Asia/Shanghai`
- 结束时间：`2026-06-13 02:42:45 Asia/Shanghai`
- 输出目录：`/fs/fast/u2021201693/lym/TransDSSAT/artifacts/stepwise_ppo_revised_semantic_discrete_transformer_10000_20260613_20260613_021119`
- checkpoint：`/fs/fast/u2021201693/lym/TransDSSAT/artifacts/stepwise_ppo_revised_semantic_discrete_transformer_10000_20260613_20260613_021119/stepwise_ppo_policy.pt`
- metrics：`/fs/fast/u2021201693/lym/TransDSSAT/artifacts/stepwise_ppo_revised_semantic_discrete_transformer_10000_20260613_20260613_021119/metrics.json`
- 持久日志：`/fs/fast/u2021201693/lym/TransDSSAT/artifacts/stepwise_ppo_revised_semantic_discrete_transformer_10000_20260613_20260613_021119/run.log`

需要明确两点：

1. 这次任务的完成标准是“重做 heuristic / reward 语义、完成 CPU-safe 验证、完成 staged GPU cycle、写正式报告”，不是必须在旧合同下刷出更高的 `reward_gain`。
2. `reward_v2` 已改变奖励语义，因此跨旧合同与新合同的 `reward_gain` 只能做趋势参考，不能当作完全同口径排名。

## 2. staged GPU 记录

在 formal full run 之前，两个前置阶段都已完成：

- smoke：`/fs/fast/u2021201693/lym/TransDSSAT/artifacts/stepwise_ppo_revised_semantic_smoke_20260613_20260613_020121`
  - best `reward_gain = 1.604344`
- intermediate：`/fs/fast/u2021201693/lym/TransDSSAT/artifacts/stepwise_ppo_revised_semantic_intermediate_20260613_20260613_020247`
  - best `reward_gain = 3.054374`
- full：`/fs/fast/u2021201693/lym/TransDSSAT/artifacts/stepwise_ppo_revised_semantic_discrete_transformer_10000_20260613_20260613_021119`

正式收尾核验：

- `metrics.json`、`stepwise_ppo_policy.pt`、`run.log` 均已落盘
- 训练日志写到 `epoch 20`
- 选择结果已写入日志尾部：`best_epoch = 2`，`best_selection_value = 3.01334`
- 当前远端不再存在该 formal run 的活跃训练窗口

## 3. revised semantics 的 CPU-safe 语义对照

本轮正式 GPU 前，已经用 `artifacts/semantic_comparison/stepwise_semantics_seed20260612.json` 做了 24 场景受控对照：

- `heuristic_legacy + reward_v1` 与 `heuristic_legacy + reward_v2`
  - 平均产量、灌溉、施氮完全一致
  - 说明单独替换 `reward_v2` 不改变 proxy rollout 动力学，只改变奖励记账语义
- `heuristic_v2 + reward_v2` 相对 `heuristic_legacy + reward_v1`
  - `mean_yield_kg_ha`：`+20.183`
  - `mean_cumulative_reward`：`+28.129445`
  - `mean_irrigation_mm`：`+35.701`
  - `mean_nitrogen_kg_ha`：`+95.792`
  - `mean_avg_water_stress`：`-0.010952`

解释：

- `heuristic_v2` 的主要变化不是“更省投入”，而是按 live step-wise 合法性原生生成动作，因此在受控池上换来了更高产量和更低水分胁迫，同时显著增加了投入。
- `reward_v2` 的作用是把奖励从旧合同的重复扣罚里拆出来，提高产量敏感度，并把低产保护显式写进终局项。

## 4. revised-semantic formal full run 结果

本轮最优 checkpoint 出现在 `epoch = 2`，不是最终 `epoch = 20`，因此正式结果按验证集 `reward_gain` 最优的 `epoch 2` 固定。

| split | mean_reward_gain | mean_total_score_100 | mean_reward | mean_yield_kg_ha | mean_yield_gain_pct | mean_irrigation_mm | mean_nitrogen_kg_ha | mean_budget_adherence_score |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| val | `3.013340` | `54.129` | `35.054510` | `3877.788` | `-0.314` | `141.52` | `0.00` | `100.0` |
| test | `3.060007` | `54.199` | `34.754866` | `3869.237` | `-0.296` | `138.78` | `0.00` | `100.0` |

同时记录：

- `best_selection_value = 3.013340`
- `selection_metric = reward_gain`
- `validation_errors = []`
- 场景池合同仍为 `10000` 条、`9000 / 500 / 500`、`maize=5000`、`wheat=5000`

这说明 revised semantics 下，PPO 仍然学到了一条“低氮、较高灌溉、轻微负产量增益”的稳定策略，但它相对 heuristic 的正向优势已经不再主要来自极端节氮之外的重复扣罚漏洞。

## 5. 与旧语义离散 transformer 的关系

旧权威离散 transformer 来自 `docs/stepwise-ppo-transformer-rerun-result-report-cn.md`，其旧合同最佳 checkpoint 为 `epoch 19`。

相对旧离散 transformer，本轮 revised semantics 的差值如下：

| split | reward_gain delta | score delta | yield_gain_pct delta | irrigation delta | nitrogen delta |
| --- | ---: | ---: | ---: | ---: | ---: |
| val | `-8.179420` | `-0.296` | `+0.482` | `+85.540` | `-3.400` |
| test | `-8.261516` | `-0.602` | `+0.471` | `+80.380` | `-2.520` |

解释时必须保留合同边界：

- `reward_gain` 大幅下降，不应直接解读成策略退化，因为 `reward_v2` 已经改变了奖励口径
- 更稳定的信息是：
  - 总分只小幅下降
  - 相对 heuristic 的负产量增益明显收窄
  - 策略从“极低水、近零氮”转成“高灌溉、零施氮”

因此，本轮 revised semantics 并没有在旧合同意义上“打败”旧离散 transformer，但它完成了任务真正要求的事情：把训练闭环迁移到了新语义，并拿到了第一份正式产物。

## 6. 与 gated continuous 路线的关系

已完成的 gated continuous 正式结果来自 `docs/stepwise-gated-continuous-10000-transformer-result-report-cn.md`，其最佳 checkpoint 为 `epoch 18`。

本轮 revised semantics 离散线相对 gated continuous 的差值如下：

| split | reward_gain delta | score delta | yield_gain_pct delta | irrigation delta | nitrogen delta |
| --- | ---: | ---: | ---: | ---: | ---: |
| val | `-6.205080` | `+2.025` | `+1.338` | `+103.540` | `-27.442` |
| test | `-5.936067` | `+1.715` | `+1.335` | `+97.602` | `-34.038` |

含义：

- revised semantics 离散线在新合同下的 `reward_gain` 低于 gated continuous 旧合同结果
- 但它的总分更高，且相对 heuristic 的产量损失更小
- 代价是灌溉显著上升，而施氮进一步下降到 `0`

这再次说明：旧合同与新合同之间，不能只拿单一 `reward_gain` 做跨线排序；更合理的做法是分别在各自合同内看最优结果，再用产量、投入、总分和胁迫模式辅助解释。

## 7. 最终裁决

本轮 revised-semantic 任务现在可以判定为：

- `formal_revised_semantic_gpu_cycle_completed`
- `heuristic_v2_and_reward_v2_validated`
- `task_completed_with_persistent_report`

理由：

- `heuristic_v2` 已实现并成为默认 live step-wise baseline
- `reward_v2` 已实现并成为默认奖励合同
- CPU-safe 验证、dry-run、语义对照已完成
- staged GPU 三阶段已完成并有持久产物
- 正式结果报告已写入持久文档

当前更合理的后续 Bootstrap 方向不是重复这次训练，而是：

1. 审计 revised semantics 下“高灌溉、零施氮”行为是否仍需 agronomic guardrail。
2. 在 official DSSAT 一致性或小样本复核里检查该策略是否只是 proxy 特有偏置。
3. 只有在新任务明确要求时，再继续下一轮奖励/动作合同迭代。
