# 2026-06-08 Step-wise PPO `10000` 场景正式实验报告

## 1. 实验结论

本轮正式实验已完成。

- 路线：`10000` 场景池 + `step-wise` 环境 + masked PPO 训练闭环。
- 远端主机：`10.10.252.11`
- 训练设备：`cuda:0`
- 启动时间：`2026-06-08 22:37:55 Asia/Shanghai`
- 产物落盘时间：`2026-06-08 22:49:55 Asia/Shanghai`
- 总时长：约 `12` 分钟
- 输出目录：`/fs/fast/u2021201693/lym/TransDSSAT/artifacts/stepwise_ppo_10000_run_20260608_223333`
- checkpoint：`/fs/fast/u2021201693/lym/TransDSSAT/artifacts/stepwise_ppo_10000_run_20260608_223333/stepwise_ppo_policy.pt`
- metrics：`/fs/fast/u2021201693/lym/TransDSSAT/artifacts/stepwise_ppo_10000_run_20260608_223333/metrics.json`
- 持久日志：`/fs/fast/u2021201693/lym/TransDSSAT/artifacts/stepwise_ppo_10000_run_20260608_223333/run.log`

本轮结果可作为当前工程阶段的有效 PPO 基线实验结论，但不能被误解为最终 Transformer 序列决策产品已完成。

## 2. 训练配置

- 数据生成口径：`transdssat.testset.generate_training_scenario_pool()`
- 场景池规模：`10000`
- split：`train=9000`，`val=500`，`test=500`
- 引擎：`dssat_proxy`
- baseline：`heuristic`
- checkpoint 选择指标：`reward_gain`
- epoch：`20`
- 每个 epoch rollout episode 数：`128`
- PPO update epochs：`4`
- minibatch size：`256`
- 学习率：`3e-4`
- `gamma=0.99`
- `gae_lambda=0.95`
- `clip_epsilon=0.2`
- `value_coef=0.5`
- `entropy_coef=0.01`
- seed：`20260608`

模型结构：

- 共享两层 MLP backbone + policy head + value head
- `obs_dim = 25`
- `action_dim = 7`
- `hidden_dim = 128`
- 总参数量：`20,872`

## 3. 场景池检查

本轮正式训练使用的场景池统计如下：

- `total_records = 10000`
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

结论：当前 `10000` 场景池的 split、唯一性和主要维度 coverage 正常，没有发现明显重复采样或切分异常。

## 4. 关键结果

`reward_gain > 0` 表示候选策略在同场景下优于当前 step-wise `heuristic` baseline。

### 4.1 最佳 checkpoint

最佳 checkpoint 按验证集 `reward_gain` 选择在 `epoch = 7`：

| split | mean_reward_gain | mean_total_score_100 | mean_yield_gain_pct | mean_irrigation_mm | mean_nitrogen_kg_ha | mean_budget_adherence_score |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| val | `4.221956` | `50.365` | `0.582` | `134.26` | `149.60` | `90.413` |
| test | `4.172476` | `50.352` | `0.639` | `132.22` | `154.32` | `90.487` |

同时记录：

- `val.mean_reward = -8.004454`
- `test.mean_reward = -11.373979`
- `val.mean_yield_kg_ha = 3897.818`
- `test.mean_yield_kg_ha = 3889.414`

### 4.2 最终 epoch

训练跑到 `epoch = 20` 正常结束，但最终指标回落：

| split | mean_reward_gain | mean_total_score_100 | mean_yield_gain_pct | mean_irrigation_mm | mean_nitrogen_kg_ha | mean_budget_adherence_score |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| val | `2.274818` | `46.884` | `0.428` | `137.68` | `83.64` | `72.820` |
| test | `2.570005` | `47.727` | `0.514` | `135.94` | `93.12` | `74.864` |

### 4.3 训练趋势

按验证集 `reward_gain` 看，最优区间集中在 `epoch 7-10`：

| epoch | val mean_reward_gain | test mean_reward_gain | val score | test score |
| --- | ---: | ---: | ---: | ---: |
| 7 | `4.221956` | `4.172476` | `50.365` | `50.352` |
| 8 | `4.203480` | `4.246863` | `50.307` | `50.357` |
| 9 | `3.984894` | `4.052068` | `50.320` | `50.513` |
| 10 | `3.887941` | `3.990574` | `50.653` | `50.731` |

结论：

- PPO 训练前半段确实学到了优于 heuristic baseline 的策略。
- 后半段没有继续提升，反而出现性能回落。
- 当前 best-checkpoint 选择逻辑是必要的，不能直接拿最终 epoch 作为部署模型。

## 5. 可信度判断

本轮结果在“当前工程目标”下是可信的，但存在明确边界。

支持其可信的证据：

- 远端真实完成了 `20` 个 epoch，而不是只做 smoke。
- `run.log`、`metrics.json`、`stepwise_ppo_policy.pt` 三个核心产物均已落盘。
- 验证集和测试集在最佳 checkpoint 上都保持正的 `reward_gain`，不是单 split 偶然抖动。
- `mean_total_score_100`、`yield_gain_pct`、`budget_adherence_score` 没有出现离谱爆炸值，暂未观察到明显 reward hacking 痕迹。
- rollout、critic、GAE、clipped objective、多轮 minibatch update 都已进入远端正式闭环，而非 REINFORCE 误报。

仍然存在的限制：

- 当前实验引擎是 `dssat_proxy`，不是官方 DSSAT 全量正式仿真。
- 当前 baseline 是项目内 step-wise `heuristic`，不是更强的 `literature_ncp` 文献基线。
- 当前模型是“基于当前 observation 的 MLP actor-critic”，不是最终目标中的 history-conditioned Transformer。
- `epoch 7-10` 后出现回落，说明继续训练会带来策略漂移或目标退化风险，后续应补早停、正则或更稳定的调参策略。

## 6. 对任务完成状态的判断

对照当前自动化任务的完成条件，本轮已经满足：

- 已统一到 `10000` 场景池 + `step-wise` 环境 + PPO 主训练路线。
- 已补齐并验证真正的 PPO 关键机制。
- 已在远端完成一轮完整正式实验。
- 已拿到 checkpoint、metrics、配置记录和结果摘要。
- 已形成面向用户的结果报告，并明确结果有效性与边界。

因此，本轮自动化主任务可以标记为 `Completed`。

## 7. 建议的后续 Bootstrap 方向

如果后续发布新任务，建议优先从以下两类中选择一条：

1. 把当前 PPO 基线继续升级为更可信的实验基线
   - 对 `literature` baseline 重跑同口径比较
   - 在小规模样本上接 DSSAT 正式运行做一致性抽检
   - 加入早停或基于验证集的更稳定 checkpoint 策略

2. 回到最终产品方向
   - 设计显式历史 token 化输入
   - 把 `recommended action / executed action / current state` 前缀串联成序列
   - 落地 history-conditioned Transformer actor-critic 或 DT 风格闭环
