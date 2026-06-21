# TransDSSAT 开发总纲（中文版）

## 1. 文档目的

本文档用于把当前已经形成的需求、测试、连续决策、Decision Transformer 与评测规范文档串联成一套统一开发总纲。

它回答四个问题：

1. 这个项目下一阶段到底要实现什么
2. 为什么当前方案需要升级
3. 各份文档分别管什么
4. 后续代码实现应该按什么顺序推进

本文档是后续新线程启动实现工作的总入口。

---

## 2. 项目目标重述

### 2.1 总体目标

TransDSSAT 的下一阶段目标，不再是继续打磨“整季一次性生成策略”的离线规划器，而是升级为：

> **面向农业生产场景的连续水肥智能决策系统**

该系统应具备以下能力：

- 根据作物、土壤、天气、播种日期、生育进程和剩余预算动态决策
- 在不同控制模式下输出策略：
  - `water_only`
  - `nitrogen_only`
  - `joint`
- 与 DSSAT 或类似机理模型对接，用于评估策略优劣
- 与农学文献中的专家策略进行规范化对比

### 2.2 模型方向

后续主模型方向明确为：

> **Decision Transformer（DT）主体 + RL fine-tuning**

即：

1. 先用离线轨迹训练 DT
2. 再通过连续交互环境做 RL 微调

### 2.3 决策粒度原则

后续不预设“必须逐天控制”。

决策粒度本身作为研究变量处理，至少比较三类：

- `stage`
- `window`
- `daily`

目标不是机械追求最细粒度，而是比较：

- 哪种粒度效果更好
- 哪种粒度更可执行
- 哪种粒度更适合真实农业生产

### 2.4 在合作大项目中的角色定位

根据新增的《稻花香2号舒兰区域最佳农事窗口预测产品开发概念报告》，需要明确：

> TransDSSAT 当前负责的不是整套农业数字化产品，而是其中的“模型与决策引擎”模块。

也就是说，我们负责的重点是：

- 农事窗口预测逻辑
- 连续滚动决策逻辑
- 文献 baseline 与 AI policy 的比较体系
- 与机理模型或数据模型对接的决策引擎

而不是：

- 小程序产品交付
- 商业收费模型
- 数字农艺师培训运营
- 销售推广体系

---

## 3. 为什么要升级当前方案

当前系统虽然已经打通：

- official DSSAT 后端
- 文献启发 baseline
- stage / daily 离线策略生成
- Transformer / RL 原型

但它仍然存在三个根本局限：

1. **默认能看到整季天气**
   - 这不符合真实生产条件

2. **默认农民严格执行整季预案**
   - 这也不符合真实生产

3. **当前 daily 仍是整季离线计划，不是连续闭环控制**

因此，系统必须从：

- 整季离线 planning

升级到：

- 连续滚动 decision making

---

## 4. 总体开发原则

后续开发统一遵循以下原则：

1. **先文档，后实现**
   - 先把规范冻结，再按规范落代码

2. **先测试协议，后模型优化**
   - 先明确比较对象和评测口径，再谈谁优谁劣

3. **先 proxy 打通，后 official DSSAT 落地**
   - 连续决策逻辑优先在 proxy 环境联调

4. **先离线 DT，后在线 RL**
   - 先让模型学会轨迹模式，再做策略提升

5. **AI policy 必须视为 policy family**
   - 不再把 AI 当成单一策略

6. **输出目标从“纯水肥量”扩展为“农事窗口 + 操作建议”**
   - 后续不仅要能生成水肥动作
   - 还要能表达窗口是否到来、建议执行时段和风险提示

---

## 5. 文档体系与分工

### 5.1 需求与总体实现类

- [需求分析文档](/G:/TransDSSAT/docs/requirements-analysis-cn.md)
  - 说明为什么当前系统不够、下一阶段真实目标是什么

- [实现方案文档](/G:/TransDSSAT/docs/implementation-plan-cn.md)
  - 说明后续代码开发的阶段划分、规模建议和推进顺序

### 5.2 测试与 baseline 类

- [测试集生成与评测协议](/G:/TransDSSAT/docs/testset-eval-protocol-cn.md)
  - 定义 `General Random Test Set` 与 `Literature-Matched Scenario Slices`
  - 区分 `generalized rules` 与 `original strategies`
  - 规定 AI policy family 的比较方式

- [Policy Registry 规范](/G:/TransDSSAT/docs/policy-registry-spec-cn.md)
  - 定义每篇文献如何注册为策略条目

- [Scenario Schema 规范](/G:/TransDSSAT/docs/scenario-schema-cn.md)
  - 定义测试场景字段、split、slice metadata 等

- [评测报告规范](/G:/TransDSSAT/docs/evaluation-report-spec-cn.md)
  - 规定正式实验输出哪些表、图和结论口径

### 5.3 连续决策与 DT 类

- [连续决策设计文档](/G:/TransDSSAT/docs/continuous-decision-design-cn.md)
  - 定义系统如何从整季离线 planning 升级为滚动决策

- [Decision Transformer 数据规范](/G:/TransDSSAT/docs/decision-transformer-data-spec-cn.md)
  - 定义 DT 训练样本格式、粒度、`control_mode`、`return_to_go` 等

- [合作范围对齐说明](/G:/TransDSSAT/docs/collaboration-scope-alignment-cn.md)
  - 定义新收到的稻花香 2 号合作方案中，哪些属于我们、哪些不属于我们

---

## 6. AI Policy Family 统一定义

后续实现、训练、评测和汇报中，AI 方法必须统一视为三条策略线：

1. `water_only`
2. `nitrogen_only`
3. `joint`

这三条线都要在以下层面独立存在：

- 数据生成
- 模型训练
- baseline 比较
- 报告输出

不能再只保留一个笼统的 “AI policy” 结果。

---

## 7. 测试集与数据规模总要求

### 7.1 General Random Test Set

用途：

- 衡量 AI 在广泛随机场景上的通用泛化能力

推荐目标规模：

- `Train = 2000`
- `Validation = 300`
- `Test = 500`

这是当前最合理的下一阶段目标。

### 7.2 Literature-Matched Scenario Slices

用途：

- 在满足文献适用条件的前提下，公平比较 original strategy、generalized rule 与 AI policy

推荐目标规模：

- 每篇文献 `100` 个 matched 场景

### 7.3 双层数据策略

为了兼顾计算代价和结果质量，后续采用双层数据方案：

1. **大规模训练主集**
   - 优先由 proxy / 近似环境生成
   - 用于训练 DT 和早期 RL

2. **高质量 official DSSAT 评测集**
   - 用于正式比较与最终汇报

---

## 8. 推荐开发阶段

后续实现建议严格按以下 Phase 推进。

### Phase 1：基础规范落地

目标：

- 将文档规范转成代码层 schema 与 registry

包括：

1. `policy_registry`
2. `scenario schema`
3. `test set metadata schema`

### Phase 2：测试集生成器

目标：

- 先把测试与评测基础设施搭起来

包括：

1. `General Random Test Set` generator
2. `Literature-Matched Scenario Slice` generator
3. applicability / `not_applicable` 判定器

### Phase 3：文献 baseline 体系

目标：

- 建立 generalized rules 与 original strategies 的统一运行接口

包括：

1. generalized literature rules
2. original strategies
3. simple baselines

### Phase 4：统一评测 runner

目标：

- 先让测试 protocol 真正可跑

包括：

1. AI family 评测
2. generalized rules 评测
3. matched slice 评测
4. 报告生成

### Phase 5：连续决策环境

目标：

- 从 season-level offline planning 升级到 rolling decision environment

包括：

1. `DailyDecisionContext`
2. proxy 连续决策环境
3. 农户实际执行偏差接口
4. 历史天气 + 短期预报输入
5. 田间真实观测输入
   - 叶龄
   - 茎蘖数
   - 水层
   - 病虫害
   - 无人机长势指标
6. 窗口级输出接口
   - 晒田窗口
   - 穗肥窗口
   - 化调窗口
   - 防病窗口
   - 收获窗口

### Phase 6：Decision Transformer 数据生成

目标：

- 构造 DT 需要的轨迹数据

包括：

1. `stage` 粒度轨迹
2. `window` 粒度轨迹
3. `daily` 粒度轨迹
4. `control_mode` 支持

### Phase 7：离线 DT 训练

目标：

- 在三种 control mode 和多粒度设置下训练 DT

包括：

1. `DT-water_only`
2. `DT-nitrogen_only`
3. `DT-joint`

或一个条件化 DT + `control_mode` token

### Phase 8：RL fine-tuning

目标：

- 在连续交互环境中进一步优化 DT

### Phase 9：official DSSAT 回映

目标：

- 在 official DSSAT 上做高质量评测与最终对比

---

## 9. 第一轮实现建议边界

为了保证推进顺畅，建议下一线程的第一轮实现只做到：

1. `policy_registry`
2. `General Random Test Set`
3. `Literature-Matched Scenario Slices`
4. generalized rules
5. original strategies
6. 统一评测 runner

也就是说：

> **先把测试集生成 + 文献 baseline + 评测协议落地**

而不是立刻开始写 DT 训练代码。

因为如果测试协议和 baseline 体系没先定好，后面训练出的模型也没有统一口径可比较。

---

## 10. 下一线程的默认目标

新线程建议默认目标写成：

> 基于当前管理文档，实现 TransDSSAT 的测试集生成、文献 baseline registry、generalized rules、matched original strategies、AI family 评测 runner，并产出统一的评测结果结构，为后续连续决策与 Decision Transformer 训练打基础。

如果后续开启“合作方案对齐”分支，则默认目标应升级为：

> 在上述基础上，把 TransDSSAT 从“水肥策略研究框架”进一步整理为“农事窗口预测与决策引擎”框架，使其能够接收短期天气预报、田间观测和品种化参数，并输出窗口级管理建议。

---

## 11. 结论

当前文档体系已经形成闭环：

- 需求已明确
- 测试协议已明确
- baseline 分类已明确
- 连续决策方向已明确
- DT 数据方向已明确
- AI family 评测口径已明确

后续实现应遵循的总路线是：

> **先落测试与 baseline 基础设施，再落连续决策框架，再落 DT 与 RL。**

本文档作为后续实现线程的总入口使用。
