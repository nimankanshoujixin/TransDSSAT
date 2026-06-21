# 连续决策值现状汇报样本

<callout emoji="🌾">
**这份材料是给业务、农艺和研发协同看的，不是新的训练战报。**

目的只有一个：把“连续决策值”这条线当前到底已经做到什么、现在能看什么、还不能拿什么当正式结果，一次说清楚。
</callout>

## 1. 这条线现在走到哪了

先说结论：截至 `2026-06-11`，连续决策值这条线已经完成 **policy contract + rollout/history/PPO wiring + CPU-safe validation**，但**还没有正式 GPU 训练分数**。

| 项目 | 当前状态 |
| --- | --- |
| 当前线名称 | `step-wise gated continuous action` |
| 当前任务状态 | `Completed` |
| 已完成内容 | contract 冻结、代码接线、单测、dry-run |
| 正式训练分数 | **还没有** |
| 当前权威对比基线 | 离散 `Transformer + PPO` 正式 rerun |
| 当前阻塞点 | `2026-06-11 12:43 Asia/Shanghai` live GPU 检查时无空闲 A800 |
| 合同文档 | [stepwise-gated-continuous-contract-2026-06-11.md](/G:/TransDSSAT/docs/stepwise-gated-continuous-contract-2026-06-11.md) |
| 当前权威分数报告 | [stepwise-ppo-transformer-rerun-result-report-cn.md](/G:/TransDSSAT/docs/stepwise-ppo-transformer-rerun-result-report-cn.md) |

这意味着：

- 我们现在已经不是“只有想法，没有接口”
- 但也还不能说“连续值策略已经正式跑出了更高分”
- 目前最诚实的说法是：**接口已经闭环，分数还没有正式产生**

---

## 2. 连续决策值现在到底长什么样

这一版不是让策略只选一个离散动作 id，而是先决定“做不做”，再决定“做多少”。

| 字段 | 含义 |
| --- | --- |
| `action_mode` | 当前策略是 `discrete` 还是 `gated_continuous` |
| `control_mode` | 当前控制家族：`water_only` / `nitrogen_only` / `joint` |
| `irrigation_gate` | 本步是否执行灌溉，`0/1` |
| `nitrogen_gate` | 本步是否执行施氮，`0/1` |
| `irrigation_amount_mm` | 灌溉连续值，单位 `mm` |
| `nitrogen_amount_kg_ha` | 施氮连续值，单位 `kg/ha` |
| `irrigation_max_mm` | 当前步在合法约束下最多还能灌多少 |
| `nitrogen_max_kg_ha` | 当前步在合法约束下最多还能施多少 |
| `action_family` | 当前步最终落成 `noop / water_only / nitrogen_only / joint` 哪一类 |

<callout emoji="💡">
这条线最关键的语义不是“把两个连续数直接回归出来”，而是**显式保留 whether-to-act 这个决策**。

也就是说，`noop` 不是靠“自己学会回归到 0”来表达，而是靠 gate 直接表达。
</callout>

---

## 3. 现在这些连续值会怎样落地

下面不是正式训练后的农业 case，而是一个 **CPU-safe 合法性样本**，用来说明“连续决策值”在当前接口里实际会以什么形式出现。

### 样本场景

| 条件 | 内容 |
| --- | --- |
| 场景编号 | `dssat_proxy-maize-rand00000-wy2019-normal-irr82-n218-balanced-profit-quzhou_deep_loam-sw169-sn101-pd-4` |
| 作物 | `maize` |
| 品种线 | 当前 Quzhou maize proxy 设定 |
| 天气年份 / 类型 | `2019 / normal` |
| 土壤 | `quzhou_deep_loam` |
| 灌溉总预算 | `82.0 mm` |
| 施氮总预算 | `217.7 kg/ha` |
| 目标倾向 | `balanced / profit` |
| 用途说明 | **仅用于展示连续值字段如何落地，不代表正式训练策略** |

### 前 6 个决策步里，连续值长什么样

| 决策日 | day_index | 生育期 | 灌溉 gate | 施氮 gate | 灌溉值 mm | 施氮值 kg/ha | 当前灌溉上限 mm | 当前施氮上限 kg/ha | family |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `2025-06-14` | 0 | emergence | 1 | 1 | 10.0 | 20.0 | 82.0 | 217.7 | `joint` |
| `2025-06-19` | 5 | emergence | 1 | 0 | 10.0 | 0.0 | 72.0 | 0.0 | `water_only` |
| `2025-06-24` | 10 | emergence | 1 | 1 | 10.0 | 20.0 | 62.0 | 197.7 | `joint` |
| `2025-06-29` | 15 | emergence | 0 | 0 | 0.0 | 0.0 | 0.0 | 0.0 | `noop` |
| `2025-07-04` | 20 | emergence | 0 | 1 | 0.0 | 20.0 | 0.0 | 177.7 | `nitrogen_only` |
| `2025-07-09` | 25 | vegetative | 1 | 0 | 10.0 | 0.0 | 52.0 | 0.0 | `water_only` |

<grid>
<column width-ratio="0.500000">
<callout emoji="✅">
**从接口角度，已经能看见的东西**

- gate 和 amount 被明确分开
- 当前 legal max 会随步变化
- `noop / water_only / nitrogen_only / joint` 可以直接读出来
- rollout 记录里已经不再只依赖离散 action id
</callout>
</column>
<column width-ratio="0.500000">
<callout emoji="⚠️">
**现在还不能误读的地方**

- 这不是正式训练后的策略输出
- 这不是农业上已经认可的管理方案
- 这也不是可用于对外宣称的连续策略得分
</callout>
</column>
</grid>

---

## 4. 当前已经验证了什么

截至 `2026-06-11`，这条线已经完成的验证包括：

| 类别 | 已验证内容 |
| --- | --- |
| 语义合同 | gate 语义、amount 语义、`noop` 语义、control family 映射 |
| 环境执行 | continuous payload 仍由 `StepwiseDecisionEnvironment.step(...)` 作为最终执行权威 |
| rollout 记录 | transition 已记录 `action_mode / control_mode / gates / legal maxima / action_family` |
| history token | 已显式编码前一步 gates、amounts、ratio、family，而不再只靠离散 id |
| PPO 训练链路 | actor 输出、采样、log-prob、entropy、batch schema 已接通 |
| 单元测试 | `tests.test_stepwise_ppo`、`tests.test_stepwise_env`、`tests.test_unified_eval_stepwise`、`tests.test_stepwise_adapter` |
| dry-run | `scripts/train_stepwise_ppo.py` 的 discrete 和 gated continuous 两条 dry-run 都已闭环 |

直接说人话：

- **接口闭环已经完成**
- **CPU-safe 验证已经完成**
- **统一评估兼容性没有被破坏**

---

## 5. 在“分数”这件事上，现在应该怎么表述

这是当前最需要说清楚的边界。

| 线 | 当前是否有正式分数 | 当前是否可作为权威比较 |
| --- | --- | --- |
| 离散 `Transformer + PPO` | 有 | 是 |
| gated continuous | 没有 | 还不是 |

当前权威说法应该是：

- 已发布、可比较的正式结果，仍然是离散 `Transformer + PPO` rerun
- gated continuous 当前只完成到 **CPU-safe implementation closure**
- 没有正式 checkpoint、没有正式 `metrics.json`、没有正式 side-by-side score report
- 根因不是接口没接好，而是当时 live GPU 检查没有空闲卡

<callout emoji="🔍">
如果后面有人问“连续决策值现在分数怎么样”，最准确的回答不是报一个猜测值，而是：

**目前还没有正式训练分数；当前结果是接口闭环和 CPU-safe 验证已经完成。**
</callout>

---

## 6. 后面真正值得业务和农艺一起判断什么

等这条线有了正式训练结果之后，最值得重点看的不是“它是不是连续的”，而是下面这些问题：

1. gate 是否真的学会了“该停手就停手”，还是每一步都出很小的正值。
2. continuous amount 是否在农业上可解释，而不是技术上合法但行为上很怪。
3. 相比离散 baseline，连续线到底是在换更好的资源配置，还是只是把动作打碎了。
4. 连续值策略是否会把施氮或灌溉压到过低，从而形成新的 reward loophole。
5. 如果 continuous 线得分更高，它提升的是产量、总分、预算遵守，还是单纯更省投入。

---

## 7. 这份文档真正想帮助回答什么

这份文档不是为了证明“连续决策值已经赢了”。

它真正想帮助回答的是：

<callout emoji="💬">
**我们现在是否已经把连续动作这条线推进到了可以正式比成绩的前一站。**

- 如果答案是“是”，下一步就是 live GPU 检查通过后做 staged training
- 如果答案是“不是”，那就应该回到 contract / mask / reward guardrail 继续收口
</callout>

当前答案是：

- 从接口和 CPU-safe 验证看，**已经到前一站了**
- 从正式分数和业务结论看，**还没有到终点**

---

## 附录 A. 后续 case study 固定写法应该怎么复用这份文档

后面凡是再写 case study，建议默认沿用这份文档的顺序：

1. 先说这份材料给谁看、不是给谁看。
2. 先交代“这条线当前阶段”，不要一上来就贴结果。
3. 如果是新接口或新语义，先把动作/状态字段解释清楚。
4. 必须把“正式结果”和“示例值 / 样本值”分开标注。
5. 必须明确当前权威基线是谁。
6. 必须给出业务/农艺真正要判断的问题，而不是只展示技术指标。

参考样式来源：

- 当前参考 Feishu 文档：[农艺复核样本：Transformer 单场景决策](https://my.feishu.cn/docx/AWpfdMTTXoktTGxAWpZc5K2TnPf)
- 本文飞书版本：[连续决策值现状汇报样本](https://my.feishu.cn/docx/HRPcdu1SwoaCW5xpQSOc80Esn6e)
