# TransDSSAT 连续决策设计文档（中文版）

## 1. 文档目的

本文档定义 TransDSSAT 从“整季离线策略生成”向“逐日连续决策”演进时的设计原则、输入输出接口和模型形态。

本文档同时明确：

- 连续决策版本的推荐模型形态为 **Decision Transformer**
- 训练方式采用：
  - 先离线轨迹训练
  - 再在线 RL fine-tuning
- 决策粒度不预设为逐天，而应作为研究变量进行比较

---

## 2. 为什么需要连续决策

真实农业场景中：

- 农户不会严格执行整季预案
- 天气不会在播种时就完整已知
- 当前状态与实际执行会不断影响后续最优操作

因此系统应从：

- 一次性整季规划

转向：

- 每天根据当前状态滚动推荐

---

## 3. 连续决策核心输入

建议 `DailyDecisionContext` 至少包含：

- `current_day`
- `observed_weather_history`
- `forecast_weather_window`
- `current_soil_state`
- `current_crop_state`
- `farmer_last_action`
- `recommended_last_action`
- `remaining_irrigation_budget`
- `remaining_nitrogen_budget`

说明：

- 天气输入不再是整季真实天气
- 而是：
  - 历史真实天气
  - 当前观测
  - 短期预报

---

## 4. 决策粒度设计

连续决策不等于“必须每天操作一次”。

真实农业生产中，更合理的理解是：

- 系统每天都可以更新判断
- 但不一定每天都建议实际操作

因此后续系统应支持多种动作粒度：

### 4.1 阶段级（stage）

- 在关键生育期做少数几次决策
- 优点：
  - 可解释
  - 动作空间小
  - 易于与传统农学经验对接

### 4.2 管理窗口级（window）

- 将整季切成若干可操作窗口
- 例如：
  - 7 天窗口
  - 10 天窗口
  - 关键农事窗口
- 优点：
  - 比 stage 更灵活
  - 比 daily 更符合农户执行习惯

### 4.3 日级（daily）

- 每天都允许给出建议
- 优点：
  - 最细粒度
  - 适合研究连续控制上限
- 缺点：
  - 不一定最符合实际执行方式
  - 训练更难

因此，后续研究问题不应写成：

> 是否做 daily 决策

而应写成：

> 在不同决策粒度下，哪一种既有效又可执行。

## 5. 连续决策核心输出

模型每天输出：

- 当前决策粒度下的下一步动作

若粒度为 `daily`，则输出：

- `next_day_irrigation_mm`
- `next_day_nitrogen_kg_ha`

若粒度为 `window`，则输出：

- 当前窗口内的建议操作

若粒度为 `stage`，则输出：

- 当前阶段建议操作

可选输出：

- `confidence`
- `rule_override_flag`
- `budget_warning_flag`

---

## 6. 环境交互接口

建议后续 daily 环境统一提供：

- `reset()`
- `observe()`
- `step(action, executed_action=None)`
- `is_done()`

其中：

- `action` 是模型推荐动作
- `executed_action` 是农户真实执行动作

如果 `executed_action` 为空，则默认视为按推荐执行。

---

## 7. Decision Transformer 设计原则

连续决策版本的模型应采用 DT 风格输入，而不是普通编码器直接回归动作。

推荐序列组织为：

- `return_to_go_t`
- `state_t`
- `action_t`

其中 `state_t` 应由 daily context 编码而成，至少覆盖：

- 历史天气
- 当前土壤状态
- 当前作物状态
- 当前预算剩余量
- 最近实际执行动作
- 短期天气预报

模型输出：

- 当前粒度下的下一步动作

---

## 8. 训练路径

### 阶段 1：离线 DT 训练

数据来源：

- proxy 生成的大规模 daily 轨迹
- 后续逐步补充 official DSSAT 高质量 daily 轨迹

目标：

- 让模型先学会高回报轨迹中的序列决策结构

### 阶段 2：在线 RL fine-tuning

在 daily 环境中继续优化：

- 提高闭环决策适应能力
- 增强对执行偏差和天气变化的鲁棒性
- 比较不同决策粒度的效果

因此后续的推荐训练路线不是：

- 直接跳到纯在线 RL

而是：

- **离线 DT 先学结构**
- **在线 RL 再做策略提升**

---

## 9. 环境优先级

### 第一优先级：proxy

先在 proxy 上实现：

- 逐日状态推进
- 农户执行偏差
- 短期预报输入
- DT 训练所需 daily 轨迹

原因：

- 速度快
- 易调试
- 适合先建立连续决策框架

### 第二优先级：official DSSAT

在 proxy 框架稳定后，再考虑：

- official DSSAT 的分段重放
- 滚动评估
- 高质量 daily 轨迹构造

---

## 10. 迭代顺序

推荐顺序：

1. 在 proxy 上实现连续决策环境
2. 加入农户实际执行偏差
3. 改成历史天气 + 短期天气预报输入
4. 定义 stage / window / daily 三类动作粒度
5. 生成 DT 所需轨迹
6. 先做离线 DT
7. 再做 RL fine-tuning
8. 最后考虑 official DSSAT 的滚动对接

---

## 11. 结论

连续决策不是对当前 `daily` 方案的小修补，而是系统范式的升级。

后续实现应围绕：

- daily closed-loop 环境
- Decision Transformer 主模型
- RL fine-tuning

三者一体化设计推进。

同时需要强调：

> “连续决策”描述的是滚动更新机制，
> 不等于最终一定采用“日级操作频率”。

后续应把决策粒度本身作为研究变量纳入比较。
# 废弃说明（2026-06-21）

本文件中所有把 `proxy` 作为连续决策主实现路径的内容，现已不再适用。

后续连续决策设计只能面向 official DSSAT 落地，不再以 proxy 作为训练或评估后端。
