# 2026-06-15 现实数据驱动 Step-wise PPO 正式结果报告

## 1. 结论

现实天气/土壤驱动的 10,000 场景池已经生成、验证并用于 staged 远程 GPU 训练。主线正式结果已经落盘，当前最稳妥的结论是：

- 现实数据池与 CPU-safe 校验都已完成
- 远程 staged GPU cycle 已完成 smoke / intermediate / full 三阶段
- 主线正式 checkpoint 已经生成并保存
- 现有结果在预算遵守和综合 reward 上是成立的，但相对 heuristic 的产量增益仍偏弱，说明后续优化重点不应再是粗粒度动作桶，而应更细地看 reward 敏感性与控制质量

## 2. 数据与校验

现实数据池来源于新接入的真实天气 workbook 与土壤样本目录，生成结果如下：

- 输出目录：[`/G:/TransDSSAT/data/generated_realistic_10000`](/G:/TransDSSAT/data/generated_realistic_10000)
- 总场景数：`10000`
- split：`train=9000`，`val=500`，`test=500`
- crop 覆盖：`maize=5000`，`wheat=5000`
- weather regime 覆盖：`dry / normal / wet` 三类均衡分布
- unique scenario id：`10000`
- distinct signature：`10000`
- validation errors：`[]`

CPU-safe 校验已通过：

- `python -m unittest tests.test_scenario_pool tests.test_real_data_sources`
- `python -m unittest tests.test_real_data_sources`
- `python -m unittest tests.test_stepwise_env tests.test_stepwise_ppo`

## 3. staged GPU 记录

主线现实数据线的远程 staged 结果如下：

- smoke：[`/fs/fast/u2021201693/lym/TransDSSAT/artifacts/stepwise_ppo_realistic_smoke_20260615_20260615_183036`](/fs/fast/u2021201693/lym/TransDSSAT/artifacts/stepwise_ppo_realistic_smoke_20260615_20260615_183036)
- intermediate：[`/fs/fast/u2021201693/lym/TransDSSAT/artifacts/stepwise_ppo_realistic_intermediate_20260615_20260615_183514`](/fs/fast/u2021201693/lym/TransDSSAT/artifacts/stepwise_ppo_realistic_intermediate_20260615_20260615_183514)
- full：[`/fs/fast/u2021201693/lym/TransDSSAT/artifacts/stepwise_ppo_realistic_full_20260615_20260615_184419`](/fs/fast/u2021201693/lym/TransDSSAT/artifacts/stepwise_ppo_realistic_full_20260615_20260615_184419)

正式 full run 的关键结果：

| split | mean_reward_gain | mean_total_score_100 | mean_yield_kg_ha | mean_yield_gain_pct | mean_irrigation_mm | mean_nitrogen_kg_ha | mean_budget_adherence_score |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| val | `0.521441` | `58.545` | `2184.457` | `-2.117` | `131.42` | `129.04` | `100.0` |
| test | `0.590349` | `58.656` | `2166.748` | `-1.911` | `132.52` | `129.92` | `100.0` |

补充信息：

- best epoch：`20`
- selection metric：`reward_gain`
- best_selection_value：`0.521441`
- checkpoint：[`/fs/fast/u2021201693/lym/TransDSSAT/artifacts/stepwise_ppo_realistic_full_20260615_20260615_184419/stepwise_ppo_policy.pt`](/fs/fast/u2021201693/lym/TransDSSAT/artifacts/stepwise_ppo_realistic_full_20260615_20260615_184419/stepwise_ppo_policy.pt)
- metrics：[`/fs/fast/u2021201693/lym/TransDSSAT/artifacts/stepwise_ppo_realistic_full_20260615_20260615_184419/metrics.json`](/fs/fast/u2021201693/lym/TransDSSAT/artifacts/stepwise_ppo_realistic_full_20260615_20260615_184419/metrics.json)
- run.log：[`/fs/fast/u2021201693/lym/TransDSSAT/artifacts/stepwise_ppo_realistic_full_20260615_20260615_184419/run.log`](/fs/fast/u2021201693/lym/TransDSSAT/artifacts/stepwise_ppo_realistic_full_20260615_20260615_184419/run.log)

## 4. 结果解读

这条主线的结果说明：

1. 现实池已经能稳定跑通，训练、验证、测试、checkpoint 保存都正常。
2. 策略的预算遵守是干净的，`mean_budget_adherence_score` 始终为 `100.0`。
3. 综合 reward 已经高于 baseline 方向，但产量增益仍略为负值，说明当前策略更像是“稳健守约”而不是“显著增产”。
4. 这不是接口不通，而是控制策略本身还可以更细地调优，尤其是产量敏感度和资源分配的平衡。

## 5. 连续动作敏感性检查

为了响应“不要停留在粗粒度动作”的方向，我额外做了一个 `gated_continuous` 的远程敏感性检查：

- smoke：[`/fs/fast/u2021201693/lym/TransDSSAT/artifacts/stepwise_ppo_realistic_gated_continuous_smoke_20260615_20260615_210614`](/fs/fast/u2021201693/lym/TransDSSAT/artifacts/stepwise_ppo_realistic_gated_continuous_smoke_20260615_20260615_210614)
- intermediate：[`/fs/fast/u2021201693/lym/TransDSSAT/artifacts/stepwise_ppo_realistic_gated_continuous_intermediate_20260615_20260615_210943`](/fs/fast/u2021201693/lym/TransDSSAT/artifacts/stepwise_ppo_realistic_gated_continuous_intermediate_20260615_20260615_210943)

这个敏感性检查的结论是：

- smoke 能跑通，说明 `gated_continuous` 路径在现实池上是可用的
- intermediate 没有把 reward_gain 或产量稳定抬到可以替代主线的程度
- 因此目前不把它升级成新的正式主线

## 6. 当前建议

当前最合理的后续方向是：

- 先把这条现实数据线的正式结果作为当前主结论封存
- 如果后面还要继续优化，优先从 reward 敏感性、baseline 对齐和产量竞争力去找机制层面的修正
- 不要为了单个 case 再加新的 hard mask 或一次性规则

