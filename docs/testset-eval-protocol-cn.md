# TransDSSAT 测试集生成与评测协议（中文版）

## 1. 文档定位

本文档用于定义 TransDSSAT 后续实验中的：

- 测试集结构
- 文献策略 baseline 分类
- 文献策略注册规范
- 评测协议
- AI policy family 的比较口径

本文档是对以下管理文档的专项补充：

- [requirements-analysis-cn.md](/G:/TransDSSAT/docs/requirements-analysis-cn.md)
- [implementation-plan-cn.md](/G:/TransDSSAT/docs/implementation-plan-cn.md)

后续与“测试集生成”“文献策略 baseline”“AI policy 对比”有关的实现，均应优先遵循本协议。

---

## 2. 设计目标

本协议要解决的核心问题是：

> 不能把所有论文中的策略直接堆在一起，在同一批随机场景上简单比较。

原因在于：

- 不同论文策略的适用条件不同
- 有些策略可以自然推广到任意预算场景
- 有些策略只在原论文条件下才有严格意义

因此，本协议同时追求两件事：

1. **通用泛化评测**
   - 评估 AI policy 在广泛随机场景上的整体能力

2. **文献公平对比评测**
   - 在原论文适用条件下，评估 AI policy 是否优于文献原始策略

---

## 3. 文献策略两大类定义

## 3.1 Generalized Literature Rules

中文名称：

- **通用化文献规则**

定义：

- 能在任意合法场景下自动生成完整水肥策略
- 不需要人工调参
- 不依赖原论文某个固定绝对总水量或总氮量
- 借鉴的是：
  - 生育期调度结构
  - 比例分配结构
  - 条件判断结构

典型形式包括：

1. 固定生育期策略
2. 预算归一化施氮规则
3. 季间分配规则
4. 降雨自适应规则

命名要求：

> 代码和文档中必须使用  
> `derived_rule` 或 `generalized_rule`  
> 不能把它们写成 `original policy`。

---

## 3.2 Literature-Matched Original Strategies

中文名称：

- **文献匹配原始策略**

定义：

- 只在满足原论文实验条件时才有严格意义
- 不能直接在所有随机场景上运行
- 需要为其构造专门的 `literature-matched scenario slice`

典型限制包括：

- 固定总氮量
- 固定每次灌溉量
- 特定作物季或轮作系统
- 特定灌溉设施
- 依赖 `local recommended N`

命名要求：

> 文档和代码中必须显式标注为：
>
> - `original_strategy`
> - `paper_exact`
> - `literature_matched`

---

## 4. AI Policy Family 定义

后续评测中，AI 方法不得被视为单一策略。

必须把 AI policy 明确拆成三条控制模式：

1. `water_only`
2. `nitrogen_only`
3. `joint`

含义如下：

- `water_only`
  - AI 只决定灌溉
  - 施氮由固定规则或 baseline 提供

- `nitrogen_only`
  - AI 只决定施氮
  - 灌溉由固定规则或 baseline 提供

- `joint`
  - AI 同时决定灌溉和施氮

原则：

> 后续所有测试、消融和正式报告，都必须把这三条策略分开统计。

不能只写一条笼统的 “AI policy”。

---

## 5. 两层测试集结构

后续测试集必须分为两个层级：

1. `General Random Test Set`
2. `Literature-Matched Scenario Slices`

二者缺一不可。

---

## 6. General Random Test Set

## 6.1 目标

用于评估：

- AI policy family 在广泛随机场景下的通用泛化能力

## 6.2 场景生成原则

如果当前项目围绕冬小麦-夏玉米轮作系统，则 random 场景应围绕该系统生成。

应覆盖：

1. 天气年型
   - 干旱
   - 正常
   - 湿润

2. 水预算水平
   - 低
   - 中
   - 高

3. 氮预算水平
   - 低
   - 中
   - 高

4. 土壤初值
   - 初始土壤水分扰动
   - 初始氮素扰动

5. 播种日期与生育进程
   - 有限播期扰动

6. 管理模式
   - balanced
   - reproductive focus
   - 其他项目定义的通用模式

## 6.3 基本元数据要求

每个 random 场景至少必须包含：

- crop system
- crop season
- planting date
- daily weather series
- growth-stage boundaries 或可推导生育期信息
- total irrigation budget
- total nitrogen budget
- soil initial state
- 足以计算累计降雨等派生量的信息

## 6.4 在该测试集上运行的策略

必须运行：

1. AI policy family
   - `water_only`
   - `nitrogen_only`
   - `joint`

2. 所有 `Generalized Literature Rules`

3. 简单规则 baseline，例如：
   - `equal_allocation`
   - `farmer_practice`
   - `fixed_phenology_schedule`

默认不运行：

- `Literature-Matched Original Strategies`

除非该 original strategy 在当前场景下本身完全 well-defined。

## 6.5 该测试集回答的问题

该测试集用于回答：

- AI 是否具有泛化能力
- AI 的三种控制模式分别优于哪些通用规则
- `joint` 是否优于 `water_only` 和 `nitrogen_only`

---

## 7. Literature-Matched Scenario Slices

## 7.1 目标

用于公平比较：

- AI policy family
- generalized rules
- original strategy

在文献适用条件下谁更优。

## 7.2 Slice 定义原则

每个 slice 应对应：

- 一篇文献
  或
- 一种明确的文献原始策略体系

## 7.3 Slice 约束内容

每个 matched slice 应尽量复现：

- 作物系统
- 作物季
- 总水量 / 总氮量
- 灌溉方式
- 施肥方式
- 降雨年型
- 土壤条件
- 区域限制
- `local recommended N` 的定义方式

若无法完整复现，必须记录为：

- `approximated_conditions`
或
- `missing_conditions`

## 7.4 Slice 内的随机化

matched slice 不是只能有一个场景。

在不破坏论文适用前提的情况下，仍可加入有限随机扰动，例如：

- 年内天气扰动
- 初始水氮扰动
- 小范围播期扰动
- 小范围土壤差异

## 7.5 Slice Metadata

每个 slice 必须保存：

- `paper_id`
- `title`
- `source_url`
- `slice_name`
- `reproduced_conditions`
- `approximated_conditions`
- `missing_conditions`
- `scenario_constraints`
- `notes`

## 7.6 在 Slice 中运行的策略

必须运行：

1. AI policy family
   - `water_only`
   - `nitrogen_only`
   - `joint`

2. 所有适用于该 slice 的 generalized rules

3. 当前 slice 对应的 original strategy

4. 简单 baseline

其他文献 original strategies：

- 若满足前提，可运行
- 若不满足前提，必须标记为 `not_applicable`

---

## 8. Policy Registry 规范

后续代码中必须建立统一的 `policy_registry`。

每篇文献至少建立一个 registry 条目，字段如下：

```text
paper_id
title
source_url
crop_system
original_strategy_available
generalized_rule_available
required_metadata
applicable_test_sets
required_scenario_slice
budget_handling
notes
missing_details
implementation_status
```

### 8.1 字段解释

- `paper_id`
  - 短标识

- `title`
  - 论文全名

- `source_url`
  - DOI 或论文链接

- `crop_system`
  - 如 `wheat-maize rotation`、`winter wheat only`

- `original_strategy_available`
  - 是否能实现 original strategy

- `generalized_rule_available`
  - 是否能实现 generalized rule

- `required_metadata`
  - 执行该策略必须具备的场景字段

- `applicable_test_sets`
  - 如：
    - `general_random`
    - `matched_slice`

- `required_scenario_slice`
  - 若需专门 slice，则标明 slice 类型

- `budget_handling`
  - 必须从以下三类中选择：
    - `original_absolute`
    - `budget_normalized`
    - `requires_reference_N`

- `notes`
  - 实现说明

- `missing_details`
  - 文献信息缺失说明

- `implementation_status`
  - 建议值：
    - `implemented`
    - `conservative_approximation`
    - `not_implemented`

---

## 9. 文献实现原则

### 9.1 信息不足时不能硬编码

如文献信息不足以精确实现：

- 不能伪造绝对数值
- 不能冒充严格复现

只能采用：

1. `conservative_approximation`
2. `not_implemented`

### 9.2 使用 `local recommended N` 的策略

凡涉及：

- `60% local recommendation`
- `70% local recommendation`
- `100% local recommendation`

这类策略时：

- 不能直接把百分比表达用于 `General Random Test Set`

必须转成以下两类之一：

1. **Original version**
   - 用论文原始绝对氮量
   - 只在 matched slice 中运行

2. **Generalized version**
   - 转成预算归一化 generalized rule

---

## 10. 重点文献实现要求

以下 10 篇文献应作为优先支持对象。

每篇至少抽取：

1. `Original Strategy`
2. `Generalized Rule`
3. `Applicability Conditions`

具体论文清单及抽象要求，按你之前给出的 10 篇文献执行。

本文档不重复逐篇展开原始摘要，而要求后续在 `policy_registry` 中逐条落地。

---

## 11. 评测协议

## 11.1 最小比较单位

最小比较单位是：

- **同一个场景**

即所有策略必须在同一场景上运行后再比较。

## 11.2 适用性优先

比较前必须先判断：

- 策略在该场景下是否 `applicable`

若不适用：

- 必须标记为 `not_applicable`
- 不参与该场景数值比较

## 11.3 两类测试集上的比较规则

### 在 `General Random Test Set` 上

比较：

- AI policy family
- generalized rules
- simple baselines

不强制比较：

- original strategies

### 在 `Literature-Matched Scenario Slices` 上

比较：

- AI policy family
- slice-specific original strategy
- generalized rules
- simple baselines

## 11.4 核心指标

建议保留：

- `yield_kg_ha`
- `reward`
- `reward_gain`
- `yield_gain_pct`
- `budget_adherence_score`
- `total_score_100`

并对每个测试层输出：

- 平均值
- 标准差或方差
- `applicable_count`
- `not_applicable_count`

## 11.5 必须比较 AI family

所有正式报告中，AI 结果必须单独输出：

- `AI-water_only`
- `AI-nitrogen_only`
- `AI-joint`

不能只写一条 “AI policy”。

这是因为：

- 控水与控肥的价值来源不同
- 联合控制是否真正带来额外收益，本身就是研究问题

---

## 12. 当前项目的直接影响

基于本协议，当前项目必须立即做概念调整：

1. 当前 `literature_ncp` 不应再被表述为 original strategy
   - 它更准确地属于：
     - `generalized literature rule`
     - `literature-informed derived rule`

2. 后续必须补充真正的 `paper_exact / original_strategy`

3. 后续测试集实现不能只有单一 random test
   - 必须增加 matched slices

4. 后续 AI 评测不能只给一条 AI 结果
   - 必须按 `water_only / nitrogen_only / joint` 三条策略分别统计

---

## 13. 结论

后续测试集生成与评测协议应建立在以下原则之上：

1. 区分 generalized rule 与 original strategy
2. 区分 random generalization test 与 literature-matched slice test
3. 为每篇文献建立统一 registry
4. 不适用的策略必须显式标记为 `not_applicable`
5. AI policy 必须作为 policy family 报告：
   - `water_only`
   - `nitrogen_only`
   - `joint`

本协议应作为 TransDSSAT 后续测试与 baseline 评测部分的直接规范。
