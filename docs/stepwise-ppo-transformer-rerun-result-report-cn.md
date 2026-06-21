# 2026-06-10 Step-wise PPO Transformer 重跑结果报告

## 1. 实验结论

本轮正式 GPU 重跑已经完成，当前可以把这次结果视为在当前 objective-aware `step-wise` proxy 语义合同下的首个正式 transformer-backed PPO 基线结果。

- 远端主机：`10.10.252.11`
- 训练会话：`transdssat:ppo10000-transformer-rerun`
- 启动时间：`2026-06-10 23:42:13 Asia/Shanghai`
- 产物落盘时间：`2026-06-11 00:16:45 Asia/Shanghai`
- 总时长：约 `34` 分 `32` 秒
- 输出目录：`/fs/fast/u2021201693/lym/TransDSSAT/artifacts/stepwise_ppo_10000_transformer_semantic_freeze_20260610_233643`
- checkpoint：`/fs/fast/u2021201693/lym/TransDSSAT/artifacts/stepwise_ppo_10000_transformer_semantic_freeze_20260610_233643/stepwise_ppo_policy.pt`
- metrics：`/fs/fast/u2021201693/lym/TransDSSAT/artifacts/stepwise_ppo_10000_transformer_semantic_freeze_20260610_233643/metrics.json`
- 持久日志：`/fs/fast/u2021201693/lym/TransDSSAT/artifacts/stepwise_ppo_10000_transformer_semantic_freeze_20260610_233643/run.log`

与已发布的正式 `mlp` semantic-freeze 基线相比，这次 transformer 重跑在同一 `10000` 场景池合同下，`reward_gain` 与 `mean_total_score_100` 都更高，因此在“当前 proxy 语义合同”这一定义范围内，可以把 transformer 结果提升为新的权威基线。

但需要同时明确一个重要边界：这次最优 checkpoint 几乎把施氮压到了接近 `0`，并接受了相对 `heuristic` baseline 的轻微负产量增益。也就是说，transformer 的优势主要来自当前奖励合同更偏好资源节省，而不是来自更高产的农学行为。因此它只能被视为“当前 proxy 语义下的权威基线”，不能被误读为更接近真实农业最优策略，更不能替代后续 official DSSAT 一致性验证。

## 2. 本轮实验合同与正式运行记录

本轮重跑沿用 `docs/stepwise-ppo-transformer-rerun-contract-2026-06-10.md` 冻结的合同，只做 backbone 替换，不改动当前 `step-wise PPO` 语义接口。

- 入口脚本：`scripts/train_stepwise_ppo.py`
- 环境接口：`transdssat.environments.stepwise.StepwiseDecisionEnvironment`
- PPO 逻辑：`transdssat.stepwise_ppo`
- 奖励后端：`dssat_proxy`
- checkpoint 选择指标：`reward_gain`
- checkpoint 选择 split：`val`
- backbone：`transformer`
- hidden dim：`128`
- attention heads：`4`
- transformer layers：`2`
- max sequence length：`64`
- train / val / test：`9000 / 500 / 500`
- seed：`20260608`
- pool seed：`20260608`
- epochs：`20`
- rollout episodes per epoch：`128`
- PPO update epochs：`4`
- minibatch size：`256`
- 逻辑训练设备：`cuda:0`
- 实际物理 GPU：`GPU 1`，通过 `CUDA_VISIBLE_DEVICES=1` 映射到逻辑 `cuda:0`

正式启动前的 live GPU 检查记录于 `2026-06-10 23:36 Asia/Shanghai`：

- GPU `0`：`75955 / 81920 MiB`
- GPU `1`：`0 / 81920 MiB`
- GPU `2`：`0 / 81920 MiB`
- GPU `3`：`80583 / 81920 MiB`
- GPU `4`：`55479 / 81920 MiB`，`75%` util
- GPU `5`：`57671 / 81920 MiB`
- GPU `6`：`76267 / 81920 MiB`
- GPU `7`：`81187 / 81920 MiB`

正式启动命令如下：

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
  --backbone transformer \
  --num-heads 4 \
  --num-layers 2 \
  --max-sequence-length 64 \
  --baseline-name heuristic \
  --selection-metric reward_gain \
  --output-dir /fs/fast/u2021201693/lym/TransDSSAT/artifacts/stepwise_ppo_10000_transformer_semantic_freeze_20260610_233643
```

远端运行结束后再次检查确认：

- `tmux` 窗口 `ppo10000-transformer-rerun` 已退出
- 不再存在活跃的 `train_stepwise_ppo.py` 训练进程
- `metrics.json` 与 `stepwise_ppo_policy.pt` 已完整落盘
- `run.log` 保持 `0` 字节，但不影响正式产物完整性，因为 checkpoint 与 metrics 已成功生成且 `tmux` 训练窗口正常退出

## 3. 场景池合同与新鲜度

本轮 transformer 重跑与已发布 `mlp` 基线保持完全一致的场景池合同：

- `total_records = 10000`
- `split_counts = {train: 9000, val: 500, test: 500}`
- `crop_counts = {maize: 5000, wheat: 5000}`
- `engine_counts = {dssat_proxy: 10000}`
- `weather_regime_counts = {dry: 3297, normal: 3324, wet: 3379}`
- `weather_year_counts = {2014: 957, 2015: 1006, 2016: 1034, 2017: 1071, 2018: 994, 2019: 1012, 2020: 980, 2021: 1004, 2022: 979, 2023: 963}`
- `soil_profile_counts = {quzhou_deep_loam: 2005, quzhou_fast_drain: 2013, quzhou_fertile_silt: 1996, quzhou_flvo_aquic: 1934, quzhou_water_limited: 2052}`
- `objective_counts = {balanced_resource: 2449, nitrogen_saving: 2535, profit: 2528, water_saving: 2488}`
- `distinct_signature_count = 10000`
- `unique_scenario_id_count = 10000`
- `validation_errors = []`

结论：

- pool membership 与 split 结构保持可比
- transformer 正式产物是按照当前语义合同重新生成的，不是历史旧 checkpoint 复用
- 本轮比较满足“同 pool 合同、同 seed / pool seed、仅 backbone 替换”的要求

## 4. 关键结果

### 4.1 transformer 最优 checkpoint

本轮最优 checkpoint 出现在 `epoch = 19`，不是最终 `epoch = 20`。这说明 transformer 路径在尾段出现了轻微回落，但根据冻结合同，仍应以 `val.reward_gain` 最优的 `epoch 19` 作为权威 checkpoint。

| split | mean_reward_gain | mean_total_score_100 | mean_yield_gain_pct | mean_irrigation_mm | mean_nitrogen_kg_ha | mean_budget_adherence_score |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| val | `11.192760` | `54.425` | `-0.796` | `55.98` | `3.40` | `100.0` |
| test | `11.321523` | `54.801` | `-0.767` | `58.40` | `2.52` | `100.0` |

同时记录：

- `best_selection_value = 11.192760`
- `selection_metric = reward_gain`
- `val.mean_reward = 12.703394`
- `test.mean_reward = 11.679040`

### 4.2 与正式 `mlp` semantic-freeze 基线对比

已发布 `mlp` 基线来自 `docs/stepwise-ppo-10000-semantic-freeze-result-report-cn.md`，其最优 checkpoint 关键数值为：

| split | mean_reward_gain | mean_total_score_100 | mean_yield_gain_pct | mean_irrigation_mm | mean_nitrogen_kg_ha | mean_budget_adherence_score |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| val | `8.755795` | `53.883` | `0.075` | `92.00` | `58.68` | `100.0` |
| test | `8.392682` | `53.605` | `0.224` | `97.52` | `67.80` | `100.0` |

transformer 相对 `mlp` 的变化如下：

| split | reward_gain delta | score delta | yield_gain_pct delta | irrigation delta | nitrogen delta | budget delta |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| val | `+2.436965` | `+0.542` | `-0.871` | `-36.02` | `-55.28` | `0.0` |
| test | `+2.928841` | `+1.196` | `-0.991` | `-39.12` | `-65.28` | `0.0` |

解读：

- 在冻结的当前奖励合同下，transformer 明显优于 `mlp`
- 提升主要体现在 `reward_gain` 与总分，而不是产量增益
- transformer 学到了一种更极端的资源节约策略，尤其是施氮几乎降到零附近
- 如果把“当前 proxy 语义合同”视为唯一裁决标准，那么 transformer 胜出
- 如果把“不能出现负产量增益”视为额外业务约束，那么当前合同本身还需要补充 guardrail，而不是简单把这个结果当作农业最优策略

## 5. 可置信度判断与最终裁决

本轮 transformer 结果可以判定为：

- `trustworthy_for_current_proxy_semantics`
- `authoritative_proxy_baseline_for_current_semantics`

支持这一裁决的证据：

- 正式运行前完成了 live GPU 检查并记录了具体 GPU 快照
- 训练使用的仍然是当前权威入口 `scripts/train_stepwise_ppo.py`
- 场景池合同、seed、pool seed 与已发布 `mlp` 基线保持一致
- `metrics.json`、`stepwise_ppo_policy.pt` 两类核心正式产物已经落盘
- 训练窗口已退出，活跃训练进程已消失，说明正式 rerun 已完成
- 以冻结合同规定的 `val.reward_gain` 为标准时，transformer 优于 `mlp`

边界与限制：

- 本轮仍然是 `dssat_proxy` 合同下的结果，不是 official DSSAT 训练或验证结果
- `run.log` 为空，后续如果希望更强的审计可追踪性，应补日志输出或在 wrapper 中增加阶段性 echo
- 最优 checkpoint 伴随负的 `yield_gain_pct`，说明当前奖励语义仍可能鼓励“极端省资源”而不是“保产增效”
- 因此这次“authoritative”只在当前 proxy 语义合同内成立，不应直接外推到真实生产决策

## 6. 对下一轮 Bootstrap 的建议

下一阶段更合理的方向是：

1. 审计当前 `reward_gain` 合同，决定是否加入产量下限、施氮下限或更明确的 agronomic guardrail。
2. 复核 `mean_total_score_100` 与 `reward_gain` 的业务含义，确认是否允许“负产量增益但高总分”的策略继续作为主目标。
3. 在小规模样本上补 official DSSAT 一致性验证，检查 transformer 的极端省资源行为是否只是 proxy 语义偏差。
