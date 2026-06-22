# TransDSSAT 基础策略模型实现规划

来源：Feishu Wiki `TransDSSAT`，读取时间：2026-05-26。

本文将新的研究方向整理成后续可实施的工程规划。它不替代现有 `implementation-plan-cn.md` 和 `testset-eval-protocol-cn.md`，而是作为下一阶段从“测试集与统一评测”走向“环境条件化 Transformer-PPO”的路线图。

## 1. 核心研究定义

新的主线不再是只在单一场景里优化一套水肥方案，而是训练一个统一的农事决策策略模型：

```text
pi_theta(a_t | c_env, g, h_t)
```

含义：

- `c_env`：环境上下文，包括土壤、作物、地点、初始水氮、播期等。
- `g`：管理目标，包括高产、高利润、节水、低氮流失等。
- `h_t`：历史序列，包括观测、动作、奖励。
- `a_t`：当前农事动作，例如灌溉、施肥或不操作。

项目卖点应表述为：

> 将作物管理建模为跨环境、长历史、部分可观测、多目标约束的基础策略学习问题，并用环境条件化 Transformer-PPO 在 DSSAT 中训练。

## 2. 当前关键决策

### 2.1 作物与品种

第一版建议固定作物和品种，优先用玉米做 MVP。

但接口层必须保留：

- `crop_type`
- `cultivar_id`
- `cultivar_parameters`
- `crop_context`

原因：

- 当前已经有玉米登海605校准参数。
- 后续还会接入水稻校准 DSSAT。
- 不预留接口会导致后续多物种扩展重构。

登海605参数暂存为：

```json
{
  "作物种类": "玉米",
  "品种名称": "登海605",
  "遗传参数向量": [340.9, 1.61, 700.0, 600.0, 10.5, 60.0],
  "参数说明": "missing_details"
}
```

在未拿到参数名、单位、DSSAT cultivar 文件字段映射前，不解释每个数的生理含义。

### 2.2 时间步

建议采用：

- DSSAT 每日推进。
- agent 每 5 天决策一次。
- 施肥最小间隔 10 到 14 天。
- 灌溉最小间隔 3 到 5 天。
- 加入每次操作成本和季节预算约束。

### 2.3 动作空间

第一版使用离散动作空间。

示例：

```text
0: 不操作
1: 灌溉 10 mm
2: 灌溉 20 mm
3: 灌溉 30 mm
4: 施氮 20 kg/ha
5: 施氮 40 kg/ha
6: 灌溉 10 mm + 施氮 20 kg/ha
```

连续动作空间作为第二阶段升级。

### 2.4 天气信息

评测中保留三种天气模式：

| 模式 | 输入天气信息 | 用途 |
| --- | --- | --- |
| Realistic mode | 历史天气 + 短期天气预报 | 主实验 |
| Climatology mode | 历史天气 + 多年气候统计 | 更现实部署 |
| Oracle mode | 全季未来天气 | 上限实验 |

主实验建议用：

```text
past weather history + next 7 days forecast + seasonal climate statistics
```

不得在 realistic 主实验中直接给完整未来天气。

## 3. 与当前仓库的差距

当前 TransDSSAT 已具备：

- official DSSAT 后端接入。
- season-level policy 生成与评测。
- testset、policy registry、统一评测 runner 的第一阶段框架。
- `water_only / nitrogen_only / joint` 的 policy family 接口。

新方向还缺：

- 真正的 step-wise 环境接口。
- 每日或每 5 天可交互的 DSSAT transition 机制。
- action mask。
- Transformer Actor-Critic。
- PPO/GAE 训练循环。
- partial observation 设置。
- unseen soil/weather/objective 的系统评测切分。

重要提醒：

> 不要直接把当前 season-level runner 改成 PPO 训练。应先增加环境接口层和离散动作协议，再逐步接入训练。

## 4. 实施阶段

### Phase 0：文档与数据接口冻结

目标：把后续实现口径先钉住。

任务：

- 更新 scenario schema，加入 `crop_context`、`cultivar_context`、`objective_context`。
- 定义作物/品种参数输入格式。
- 定义天气模式：realistic、climatology、oracle。
- 定义离散动作表和 action mask 规则。
- 定义 full-state 与 partial-observation 字段。

验收：

- 能用 JSON 表示一个玉米登海605场景。
- 能表达固定品种和后续多品种扩展。
- 能表达每 5 天决策、预算、操作间隔。

### Phase 1：多环境场景库

目标：构建可 domain randomization 的环境池。

任务：

- 整理 soil profile 数据结构。
- 整理 weather year 数据结构。
- 整理 initial soil water / nitrogen 采样范围。
- 整理 planting date 采样范围。
- 整理 resource budget 和 objective 权重。
- 生成 train/test split。

推荐最小配置：

- 作物：固定 maize。
- 品种：登海605。
- 土壤：先 5 到 20 个剖面。
- 天气：先 5 到 20 个年份或代表年。
- 目标：先 profit objective。

### Phase 2：交互式环境抽象

目标：在代码层建立 `reset / step / observe / done` 接口。

建议接口：

```text
env.reset(scenario, objective) -> observation
env.step(action) -> observation, reward, done, info
env.get_action_mask() -> mask
```

工程策略：

- 先用 proxy 或 lightweight simulator 打通 step-wise 训练。
- official DSSAT 先作为评测后端或低频校验后端。
- 等 step-wise 逻辑稳定后，再评估 official DSSAT 是否能承受在线逐步调用成本。

原因：

- DSSAT 天然更像整季模拟器，不一定适合每一步都反复重启。
- 直接用 official DSSAT 做 PPO 内循环可能成本过高。
- 先 proxy 后 official，是更稳的工程路线。

### Phase 3：离散动作与 Action Mask

目标：让策略不会输出农艺上明显错误的动作。

任务：

- 定义离散动作表。
- 定义水肥预算约束。
- 定义施肥最小间隔。
- 定义灌溉最小间隔。
- 定义生育阶段限制。
- 定义过湿不灌溉规则。
- 定义收获后禁止操作规则。

验收：

- 每一步可返回合法 action mask。
- random policy 也不会产生违反硬约束的动作。

### Phase 4：Reward 系统

目标：从单纯产量转向综合管理目标。

终端 reward：

```text
R_final =
crop_revenue
- irrigation_cost
- nitrogen_cost
- operation_cost
- water_penalty
- nitrogen_leaching_penalty
- risk_penalty
```

中间 reward：

```text
r_t = lambda_shaping * r_intermediate_t
r_T = R_final
```

建议：

- `lambda_shaping` 初始设为 0.05 到 0.2。
- 主评价仍看季末产量、利润、水耗、氮损失。

### Phase 5：Baseline 与统一评测

最低需要：

| Baseline | 作用 |
| --- | --- |
| Rule-based agronomic policy | 农艺规则基线 |
| Fixed schedule policy | 固定施肥灌溉计划 |
| Random policy | 最低基线 |
| Single-environment PPO | 证明多环境训练有价值 |
| MLP-PPO | 证明历史建模有价值 |
| RNN-PPO | 与 Transformer history modeling 比较 |
| Transformer-PPO without context | 证明环境上下文有价值 |
| Transformer-PPO full model | 主方法 |
| Oracle optimization / GA search | 上限参考 |

第一轮资源有限时，至少实现：

- Rule-based policy
- MLP-PPO
- RNN-PPO
- Transformer-PPO
- Transformer-PPO without context

### Phase 6：Transformer-PPO MVP

目标：实现 Environment-Conditioned Transformer Actor-Critic。

模型输入：

```text
[SOIL]
[WEATHER_CONTEXT]
[CROP_CONTEXT]
[OBJECTIVE]
[BUDGET]
x_1
x_2
...
x_t
```

其中：

```text
x_t = [observation_t, previous_action_{t-1}, previous_reward_{t-1}, time_encoding_t]
```

模型头：

- Actor head：输出离散动作分布。
- Critic head：输出状态价值 `V(h_t)`。

训练：

- PPO clipped objective。
- GAE。
- entropy bonus。
- 周期性 held-out 环境评测。

注意：

> 这一步需要 GPU。当前服务器没有空闲 GPU 时，不启动训练。

### Phase 7：泛化评测协议

必须覆盖：

- In-distribution test。
- Unseen weather years。
- Unseen soils。
- Unseen soil-weather combinations。
- Objective generalization。
- Partial observation test。

核心目标：

> 证明模型不是单环境 RL agent，而是跨环境可泛化策略。

### Phase 8：消融实验

建议消融：

- 历史长度：当天、过去 7 天、过去 30 天、全季历史。
- 上下文：无 soil、无 weather、无 objective、无 budget、完整 context。
- 模型结构：MLP、GRU、LSTM、Transformer、Mamba optional。
- Reward：终端 reward、终端 + 中间 reward、yield-only、profit + resource penalties。
- 训练规模：10、50、100、500 个环境。

### Phase 9：真实场景扩展

在 MVP 稳定后加入：

- 水稻。
- 多品种 cultivar sampling。
- partial observation。
- multi-objective conditioning。
- continuous action。
- offline pretraining optional。

## 5. 推荐近期执行顺序

在没有空闲 GPU 的情况下，先做 CPU/文档/接口工作：

1. 更新 schema：加入 crop/context/objective/action mask 字段。
2. 整理登海605品种参数记录，标记 `missing_details`。
3. 设计离散动作表。
4. 设计 action mask 规则。
5. 设计 step-wise environment interface。
6. 用 proxy 环境做最小 step rollout。
7. 等 GPU 空闲后，再启动 PPO/Transformer 训练。

## 6. 关键风险

### 风险 1：DSSAT 在线 step 成本过高

缓解：

- 先 proxy 训练。
- official DSSAT 做评测和校验。
- 后续再考虑缓存或批量 episode 模拟。

### 风险 2：现实中不能获得 full-state

缓解：

- 主结果先 full-state。
- 同步预留 partial-observation。
- 论文中把 partial-state 作为现实部署潜力实验。

### 风险 3：作物/品种扩展太早导致复杂度爆炸

缓解：

- 第一版固定 maize + 登海605。
- 但 schema 和模型接口保留 crop/cultivar context。

### 风险 4：奖励设计主观性强

缓解：

- 将 reward 权重显式化为 objective context。
- 做 reward 消融。
- 同时报告产量、利润、水耗、施氮量、氮损失等原始指标。

## 7. 当前结论

建议下一阶段主线定为：

```text
Environment-Conditioned Transformer-PPO
+
DSSAT multi-environment domain randomization
+
unseen soil/weather evaluation
+
history/context ablations
```

实现上不要一步跳到完整 PPO 训练，而是先补齐：

- 场景 schema
- 作物/品种上下文
- 离散动作协议
- action mask
- step-wise 环境接口
- baseline/eval runner 对齐

这样后续真正开始训练时，才不会把模型训练、DSSAT 接口、数据 schema、评测 protocol 全部绑在一起爆炸。
# 废弃说明（2026-06-21）

本文件中的任何 `proxy` / `lightweight simulator` / `先 proxy 后 official` 路线表述，现已失效。

当前唯一有效路线以 [`/G:/TransDSSAT/docs/OFFICIAL_DSSAT_ONLY_POLICY_CN.md`](/G:/TransDSSAT/docs/OFFICIAL_DSSAT_ONLY_POLICY_CN.md) 为准：

- 后续训练只允许 official DSSAT
- 后续评估只允许 official DSSAT
- 不再接受 proxy 作为主训练、主评估或中间替代路线
