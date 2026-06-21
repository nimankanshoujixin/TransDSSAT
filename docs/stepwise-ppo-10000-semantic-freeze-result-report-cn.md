# 2026-06-10 Step-wise PPO `10000` 场景语义冻结重训结果报告

## 1. 实验结论

本轮正式 GPU 阶段重训已完成，当前可以把这次结果视为在“目标感知输入/奖励语义冻结”后的权威 `step-wise` PPO 代理基线。

- 路线：`10000` 场景池 + `step-wise` 环境 + masked PPO + objective-aware proxy reward
- 远端主机：`10.10.252.11`
- 训练会话：`transdssat:ppo10000-rerun`
- 启动时间：`2026-06-10 14:09:22 Asia/Shanghai`
- 产物落盘时间：`2026-06-10 14:28:27 Asia/Shanghai`
- 总时长：约 `19` 分钟
- 输出目录：`/fs/fast/u2021201693/lym/TransDSSAT/artifacts/stepwise_ppo_10000_semantic_freeze_20260610_140916`
- checkpoint：`/fs/fast/u2021201693/lym/TransDSSAT/artifacts/stepwise_ppo_10000_semantic_freeze_20260610_140916/stepwise_ppo_policy.pt`
- metrics：`/fs/fast/u2021201693/lym/TransDSSAT/artifacts/stepwise_ppo_10000_semantic_freeze_20260610_140916/metrics.json`
- 持久日志：`/fs/fast/u2021201693/lym/TransDSSAT/artifacts/stepwise_ppo_10000_semantic_freeze_20260610_140916/run.log`

与历史 `2026-06-08` PPO 结果相比，本轮刷新后的结果在 `reward_gain`、`mean_total_score_100` 和预算遵守上都有明显提升，同时投入量显著下降。

## 2. 本轮实验合同与启动记录

本轮权威合同已经冻结在 `docs/gpu-retraining-contract-2026-06-10.md`，本报告只记录本次正式跑数实际使用的关键信息。

- 入口脚本：`scripts/train_stepwise_ppo.py`
- 环境接口：`transdssat.environments.stepwise.StepwiseDecisionEnvironment`
- PPO 逻辑：`transdssat.stepwise_ppo`
- 奖励后端：`dssat_proxy`
- checkpoint 选择指标：`reward_gain`
- checkpoint 选择 split：`val`
- backbone：`mlp`
- hidden dim：`128`
- train / val / test：`9000 / 500 / 500`
- seed：`20260608`
- pool seed：`20260608`
- epochs：`20`
- rollout episodes per epoch：`128`
- PPO update epochs：`4`
- minibatch size：`256`
- 逻辑训练设备：`cuda:0`
- 实际空闲 GPU 检查结果：启动前确认物理 GPU `3` 空闲；训练通过 `CUDA_VISIBLE_DEVICES=3` 映射为逻辑 `cuda:0`

正式启动命令：

```bash
python -u scripts/train_stepwise_ppo.py \
  --device cuda:0 \
  --seed 20260608 \
  --pool-seed 20260608 \
  --train-count 9000 \
  --val-count 500 \
  --test-count 500 \
  --epochs 20 \
  --episodes-per-epoch 128 \
  --update-epochs 4 \
  --minibatch-size 256 \
  --hidden-dim 128 \
  --backbone mlp \
  --baseline-name heuristic \
  --selection-metric reward_gain \
  --output-dir /fs/fast/u2021201693/lym/TransDSSAT/artifacts/stepwise_ppo_10000_semantic_freeze_20260610_140916
```

## 3. 场景池与产物新鲜度

本轮继续沿用历史 `2026-06-08` 的场景池 seed 策略以保持可比性，但把所有正式训练产物视为“语义冻结后重新生成”。

场景池摘要：

- `total_records = 10000`
- `split_counts = {train: 9000, val: 500, test: 500}`
- `unique_scenario_id_count = 10000`
- `distinct_signature_count = 10000`
- `crop_counts = {maize: 5000, wheat: 5000}`
- `engine_counts = {dssat_proxy: 10000}`
- `weather_regime_counts = {dry: 3297, normal: 3324, wet: 3379}`
- `soil_profile_counts = {quzhou_deep_loam: 2005, quzhou_fast_drain: 2013, quzhou_fertile_silt: 1996, quzhou_flvo_aquic: 1934, quzhou_water_limited: 2052}`
- `objective_counts = {balanced_resource: 2449, nitrogen_saving: 2535, profit: 2528, water_saving: 2488}`
- `pair_coverage.crop_x_split = 6`
- `pair_coverage.weather_regime_x_soil = 15`
- `pair_coverage.weather_year_x_objective = 40`
- `pair_coverage.budget_water_x_budget_nitrogen = 9`
- `validation_errors = []`

结论：

- 场景池成员与切分结构保持可比
- 形式化训练产物已经在当前语义下重新生成
- 没有把旧 checkpoint、旧 cache 或旧报告混入本轮权威结论

## 4. 关键结果

### 4.1 最佳 checkpoint

本轮最佳 checkpoint 出现在最终 `epoch = 20`，说明这次刷新后的训练并没有复现历史报告中的后段明显回落。

| split | mean_reward_gain | mean_total_score_100 | mean_yield_gain_pct | mean_irrigation_mm | mean_nitrogen_kg_ha | mean_budget_adherence_score |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| val | `8.755795` | `53.883` | `0.075` | `92.00` | `58.68` | `100.0` |
| test | `8.392682` | `53.605` | `0.224` | `97.52` | `67.80` | `100.0` |

同时记录：

- `val.mean_reward = 10.266429`
- `test.mean_reward = 8.750198`
- `val.mean_yield_kg_ha = 3876.492`
- `test.mean_yield_kg_ha = 3871.961`
- `val.mean_irrigation_budget_violation_ratio = 0.0`
- `test.mean_irrigation_budget_violation_ratio = 0.0`
- `val.mean_nitrogen_budget_violation_ratio = 0.0`
- `test.mean_nitrogen_budget_violation_ratio = 0.0`

### 4.2 训练末尾状态

本轮最佳 checkpoint 与最终 epoch 一致，因此不存在“最佳点在中段、末尾明显退化”的问题。

- final epoch：`20`
- final val `mean_reward_gain`：`8.755795`
- final test `mean_reward_gain`：`8.392682`
- final val `mean_total_score_100`：`53.883`
- final test `mean_total_score_100`：`53.605`

## 5. 与历史 `2026-06-08` PPO 报告对比

历史正式报告的最佳 checkpoint 位于 `epoch = 7`，当时关键数值为：

| split | mean_reward_gain | mean_total_score_100 | mean_yield_gain_pct | mean_irrigation_mm | mean_nitrogen_kg_ha | mean_budget_adherence_score |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| val | `4.221956` | `50.365` | `0.582` | `134.26` | `149.60` | `90.413` |
| test | `4.172476` | `50.352` | `0.639` | `132.22` | `154.32` | `90.487` |

本轮相对历史最佳 checkpoint 的变化：

| split | reward_gain delta | score delta | irrigation delta | nitrogen delta | budget adherence delta |
| --- | ---: | ---: | ---: | ---: | ---: |
| val | `+4.533839` | `+3.518` | `-42.26` | `-90.92` | `+9.587` |
| test | `+4.220206` | `+3.253` | `-34.70` | `-86.52` | `+9.513` |

解读：

- 在当前目标感知奖励语义下，刷新后的 PPO 策略相对 `heuristic` baseline 的优势明显扩大
- 总体分数上升，同时预算遵守恢复到 `100.0`
- 灌溉和施氮投入明显收缩，说明策略更贴合新语义里的资源约束和成本项
- 单纯从产量增益百分比看，新策略没有继续追求高投入换高增产，而是转向更保守的资源使用与综合回报

## 6. 可信度判断

本轮结果可以判定为：

- `trustworthy_for_current_proxy_semantics`

支持这一判断的证据：

- 训练前完成了远端 live GPU 检查并记录了 GPU 状态
- 正式跑数在远端 `tmux` 中完整结束，而不是只停留在 dry-run
- `run.log`、`metrics.json`、`stepwise_ppo_policy.pt` 三类核心正式产物都已落盘
- 场景池 seed 保持可比，但正式训练产物是重生成的，不再混用旧语义下的结果
- 当前权威 PPO 路径已经消费 `objective_context.reward_weights`、预算约束、forecast/decision context 和动作合法性状态
- `validation_errors` 为空，`val` 和 `test` 都保持正的 `reward_gain`

边界与限制：

- 本轮仍然是 `dssat_proxy` 代理语义基线，不是官方 DSSAT 全量正式重训
- 历史 Transformer 训练路径仍未对齐当前输入/奖励合同，不能复用旧数据直接宣称与本轮等价
- 本轮结果只能证明“当前 proxy 语义下的 PPO 基线已刷新”，不能替代后续 official-DSSAT 一致性验证

## 7. 对后续 Bootstrap 的建议

下一阶段更合理的两个方向是：

1. 基于冻结合同重生 Transformer 路径所需数据与特征，再启动下一轮 GPU 训练
2. 在较小规模样本上增加 official DSSAT 一致性验证，确认新 proxy 语义基线没有偏离目标
