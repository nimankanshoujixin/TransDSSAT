# TransDSSAT 评测报告规范（中文版）

## 1. 文档目的

本文档规定后续正式实验的统一报告口径，明确：

- 报告必须输出哪些指标
- 报告必须比较哪些策略
- 报告如何区分随机泛化测试与文献匹配测试
- 报告如何呈现 AI policy family，而不是把 AI 方法误写成单一策略

本文档服务于后续：

- `General Random Test Set` 评测
- `Literature-Matched Scenario Slices` 评测
- generalized literature rules、original strategies 与 AI policy 的统一比较

---

## 2. 报告对象分层

每次正式实验至少输出三类结果：

1. `general_random_summary`
2. `matched_slice_summary`
3. `strategy_applicability_summary`

其中最重要的要求是：

> **AI 方法必须按 policy family 报告，而不是只报一个 AI 总结果。**

---

## 3. AI Policy Family 规范

后续所有正式报告中，AI policy 必须拆成至少三条独立策略线：

1. `water_only`
2. `nitrogen_only`
3. `joint`

含义如下：

- `water_only`
  - AI 只负责灌溉决策
  - 施氮采用固定 baseline 或外部给定规则

- `nitrogen_only`
  - AI 只负责施氮决策
  - 灌溉采用固定 baseline 或外部给定规则

- `joint`
  - AI 同时负责灌溉和施氮决策

要求：

- 报告中不得把这三种模式合并成一行“AI policy”
- 所有平均指标都应分别统计
- 如采用统一模型条件化支持三种模式，也必须在结果表中拆开展示

---

## 4. General Random Summary

### 4.1 目标

用于评估模型在广泛随机场景下的通用泛化能力。

### 4.2 必须输出的指标

对每种策略，至少输出：

- `mean_yield_kg_ha`
- `mean_reward`
- `mean_reward_gain`
- `mean_yield_gain_pct`
- `mean_budget_adherence_score`
- `mean_total_score_100`
- `scenario_count`

如条件允许，还建议补充：

- `std_yield_kg_ha`
- `std_reward`
- `std_total_score_100`

### 4.3 General Random 必须比较的对象

1. AI policy family
   - `water_only`
   - `nitrogen_only`
   - `joint`

2. `Generalized Literature Rules`

3. 简单规则 baseline，例如：
   - `equal_allocation`
   - `farmer_practice`
   - `fixed_phenology_schedule`

默认不纳入：

- `Literature-Matched Original Strategies`

除非该策略在该随机场景下本身完全 well-defined 且满足适用条件。

---

## 5. Matched Slice Summary

### 5.1 目标

用于公平比较：

- AI policy family
- generalized rules
- original strategy

在与论文适用条件匹配的测试切片上谁更优。

### 5.2 每个 matched slice 必须输出

- `paper_id`
- `slice_id`
- `matched_scenario_count`
- `approximated_conditions`
- `missing_conditions`
- `applicable_strategies`
- `not_applicable_strategies`

并分别对以下对象输出指标：

1. AI policy family
   - `water_only`
   - `nitrogen_only`
   - `joint`

2. generalized literature rules

3. 当前 slice 对应的 original strategy

4. 简单规则 baseline

### 5.3 指标口径

每个 slice 中仍然建议统一输出：

- `mean_yield_kg_ha`
- `mean_reward`
- `mean_reward_gain`
- `mean_yield_gain_pct`
- `mean_budget_adherence_score`
- `mean_total_score_100`

---

## 6. Applicability Summary

对每个策略，必须显式统计：

- `applicable_count`
- `not_applicable_count`
- `failed_count`

对 original strategy 必须额外说明：

- 哪些场景不能运行
- 不能运行的原因
- 是 metadata 不足、设施不符、预算不符，还是作物系统不符

原则：

> 不适用必须显式标记为 `not_applicable`，不能静默跳过。

---

## 7. 最终表格规范

正式汇报建议至少输出四张表。

### 表 1：General Random 主表

行：

- `water_only`
- `nitrogen_only`
- `joint`
- 各 generalized rules
- simple baselines

列：

- `mean_yield_kg_ha`
- `mean_reward_gain`
- `mean_yield_gain_pct`
- `mean_budget_adherence_score`
- `mean_total_score_100`
- `scenario_count`

### 表 2：Matched Slice 总表

每个 slice 一组结果，行包括：

- `AI-water_only`
- `AI-nitrogen_only`
- `AI-joint`
- generalized rules
- slice-specific original strategy
- simple baselines

### 表 3：Applicability 表

列出每个策略在各测试集上的：

- `applicable_count`
- `not_applicable_count`
- `failed_count`

### 表 4：Ablation 表

专门比较 AI family：

- `water_only`
- `nitrogen_only`
- `joint`

用于支撑如下研究结论：

- 联合控制是否优于单独控制
- 控水与控肥哪一项在当前场景更敏感
- 不同控制模式在不同粒度下是否表现一致

---

## 8. 图表规范

建议统一输出以下图表：

1. `yield_gain_pct` 柱状图
   - 按 `water_only / nitrogen_only / joint / baselines` 对比

2. `reward_gain` 柱状图
   - 特别用于比较 AI family 与 generalized rules

3. `total_score_100` 柱状图
   - 作为面向非技术汇报的综合指标展示

4. matched slice 箱线图或小提琴图
   - 显示不同策略在不同 slice 内的分布差异

5. applicability 条形图
   - 展示 original strategies 的适用范围

---

## 9. 报告文字规范

### 9.1 必须避免的表述

避免写：

- “AI policy 优于 baseline”

因为这会掩盖控制模式差异。

### 9.2 推荐表述

必须明确写成：

- `AI-water_only` 相对 baseline 的结果
- `AI-nitrogen_only` 相对 baseline 的结果
- `AI-joint` 相对 baseline 的结果

如果三者共用同一个模型主体，也必须写明：

- “同一模型在不同 control mode 条件下的三条策略输出”

而不是把它们混成一个整体结果。

---

## 10. 结论

后续所有正式实验都应按本规范输出，不再接受以下做法：

- 只给单一 AI 总结果
- 只给零散 JSON 数值
- 不区分 `water_only / nitrogen_only / joint`
- 不区分 random test 与 matched slice test

一切正式汇报、论文表格和阶段性总结，都应默认把：

> **AI policy 视为一个由 `water_only`、`nitrogen_only`、`joint` 组成的 policy family**

作为统一前提。
