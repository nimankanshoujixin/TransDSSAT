# TransDSSAT 实现文档（下一阶段方案）

## 1. 文档目的

本文档基于：

- [requirements-analysis-cn.md](/G:/TransDSSAT/docs/requirements-analysis-cn.md)
- [testset-eval-protocol-cn.md](/G:/TransDSSAT/docs/testset-eval-protocol-cn.md)

给出 TransDSSAT 下一阶段的实现路线、模块拆分和推荐迭代顺序。

---

## 2. 总体实现目标

下一阶段目标不是继续强化“整季一次性策略生成”，而是实现：

> **逐日滚动输入、逐日推荐、接收实际执行反馈、再进行下一天决策的连续动态控制框架。**

并在模型层面转向：

> **Decision Transformer 主模型 + RL fine-tuning**

---

## 3. 总体架构变化

### 3.1 当前架构

当前架构：

1. 构建整季场景
2. 模型读取整季逐日天气和预算
3. 一次性输出整季策略
4. DSSAT 一次性跑完整季
5. 输出整季结果

### 3.2 目标架构

目标架构：

1. 第 `t` 天输入：
   - 历史天气
   - 当前状态
   - 农户已执行动作
   - 短期天气预报
2. 模型输出第 `t+1` 天建议动作
3. 环境推进到下一天
4. 接收真实执行动作与新状态
5. 再进入下一轮决策

一句话概括：

> 从整季一次性 planning，改为逐日闭环 sequential decision making。

---

## 4. 核心模块改造

### 4.1 场景模块

新增 daily 级别上下文对象，例如：

- `DailyDecisionContext`

建议字段包括：

- `current_day`
- `observed_weather_history`
- `forecast_weather_window`
- `current_soil_state`
- `current_crop_state`
- `farmer_last_action`
- `recommended_last_action`
- `remaining_irrigation_budget`
- `remaining_nitrogen_budget`

### 4.2 环境模块

从整季整次评估，改为逐日推进接口：

- `reset()`
- `observe()`
- `step(action, executed_action=None)`
- `is_done()`

推荐先在 proxy 上实现真正的日步进环境，再逐步考虑 official DSSAT 的滚动对接。

### 4.3 数据模块

从整季 trajectory 扩展到日度决策样本。

未来至少要支持：

- `state_t`
- `action_t`
- `reward_t`
- `done`
- `return_to_go_t`

建议新增：

- `daily_dt_train.jsonl`
- `daily_dt_val.jsonl`
- `daily_dt_test.jsonl`

### 4.4 模型模块

下一阶段的主模型方向应明确为：

- **Decision Transformer**

而不是继续使用当前：

- 普通 Transformer 编码器 + 动作头

DT 训练所需序列建议为：

- `return_to_go_t`
- `state_t`
- `action_t`

但这里的 `action_t` 不应被预设为“每天一个动作”。

建议把动作粒度设计成可配置变量，至少支持：

- `stage`
- `window`
- `daily`

其中：

- `stage`：适合可解释和低维控制
- `window`：更贴近真实管理频率，可能是后续重点
- `daily`：适合研究连续控制上限与鲁棒性

### 4.5 训练模块

训练路线建议分两阶段：

#### 阶段 A：离线 DT 训练

基于历史轨迹训练 DT，使模型学习：

- 在给定目标收益和历史上下文时
- 如何生成下一步动作

#### 阶段 B：在线 RL fine-tuning

在连续交互环境中再优化：

- 策略鲁棒性
- 对执行偏差的适应能力
- 对天气变化的适应能力

### 4.6 评估模块

从单纯整季产量扩展为：

- 最终产量
- reward
- budget adherence
- 连续决策稳定性
- 对实际执行偏差的鲁棒性
- 对短期天气波动的适应性
- 不同决策粒度之间的效果与可执行性比较

---

## 5. 推荐实现顺序

### 第一步：先把文档体系补齐

在正式实现前，先完成并冻结以下文档：

1. `requirements-analysis-cn.md`
2. `implementation-plan-cn.md`
3. `testset-eval-protocol-cn.md`
4. `policy-registry-spec-cn.md`
5. `scenario-schema-cn.md`
6. `evaluation-report-spec-cn.md`
7. `continuous-decision-design-cn.md`

### 第二步：实现 registry 和测试集基础设施

阶段拆分：

1. `Phase 1`：实现 `policy_registry`
2. `Phase 2`：实现 `General Random Test Set` 生成器
3. `Phase 3`：实现 `Literature-Matched Scenario Slice` 生成器
4. `Phase 4`：实现 `generalized rules`
5. `Phase 5`：实现 `original strategies`
6. `Phase 6`：实现 `applicability / not_applicable` 判定
7. `Phase 7`：实现统一评测 runner 与报告输出

### 第三步：实现连续决策框架

建议顺序：

1. 定义 `DailyDecisionContext`
2. 在 proxy 上实现连续决策环境
3. 加入农户实际执行偏差
4. 改为历史天气 + 短期预报输入
5. 定义可配置决策粒度层：
   - `stage`
   - `window`
   - `daily`
6. 生成 DT 所需轨迹数据
7. 实现离线 Decision Transformer
8. 再做 RL fine-tuning
9. 最后逐步映射回 official DSSAT

---

## 6. 训练集与测试集规模建议

当前跑过的 `120` 场景只够：

- 联调
- bug 定位
- 早期趋势判断

但不够：

- 稳定训练
- 降低测试偏差
- 做正式结论

### 6.1 推荐规模分层

#### 联调级别

- 训练集：`800-1000`
- 验证集：`150-200`
- 测试集：`200-300`

#### 第一版正式规模

- 训练集：`2000-3000`
- 验证集：`300-500`
- 测试集：`500-800`

#### 研究增强规模

- 训练集：`5000+`
- 验证集：`800+`
- 测试集：`1000+`

### 6.2 matched slices 规模建议

每篇文献建议：

- 最低：`50-80`
- 较稳：`100-200`

### 6.3 当前最合理目标

建议先定为：

- `General Random Train = 2000`
- `Validation = 300`
- `Test = 500`
- `Matched Slice per paper = 100`

### 6.4 现实执行策略

建议采用双层数据方案：

1. **训练主集**
- 先在 proxy 或近似环境下生成大规模场景
- 规模 `2000-5000+`

2. **精调与正式评测集**
- 在 official DSSAT 上构建高质量评测集
- 规模 `1000-3000`

---

## 7. 第一版交付物建议

### 交付物 A：测试与 baseline 框架

包括：

- `policy_registry`
- random test generator
- matched slice generator
- generalized rules
- original strategies
- unified evaluator

### 交付物 B：连续决策原型

包括：

- proxy 日步进环境
- 农户执行偏差接口
- 历史天气 + 短期预报输入

### 交付物 C：DT 训练主线

包括：

- daily DT dataset
- offline DT training
- RL fine-tuning

---

## 8. 暂不建议现在做的事

1. 暂不建议删除当前 season-level 架构  
它仍然是 baseline、样本生成和对照实验的重要工具。

2. 不建议只改模型名字，不改数据与训练流程  
如果要上 Decision Transformer，就必须同步改：
- 数据格式
- 输入组织
- 训练目标
- 环境交互

3. 暂不建议一开始就把全部连续决策压到 official DSSAT 上  
先在 proxy 打通逻辑更高效。

---

## 9. 结论

下一阶段最核心的实现方向应该是：

> 把 TransDSSAT 从整季离线策略生成器，升级为可接收实际执行反馈的逐日连续决策系统。

对应的模型主线应明确为：

> **Decision Transformer 主模型 + RL fine-tuning**

后续实现应严格按：

1. 文档先行
2. registry 与测试集先行
3. proxy 连续决策先行
4. DT 训练与 RL fine-tuning 再接入
5. 最后映射回 official DSSAT

的顺序推进。
# 废弃说明（2026-06-21）

本文件中关于 `proxy` 优先、`先 proxy 后 official DSSAT`、或用近似环境先完成主训练的表述，现已全部作废。

当前只允许 official DSSAT 作为训练与评估主路线，规范以 [`/G:/TransDSSAT/docs/OFFICIAL_DSSAT_ONLY_POLICY_CN.md`](/G:/TransDSSAT/docs/OFFICIAL_DSSAT_ONLY_POLICY_CN.md) 为准。
