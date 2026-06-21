# TransDSSAT Decision Transformer 数据规范（中文版）

## 1. 文档目的

本文档定义后续 Decision Transformer（DT）版本所需的数据组织方式，重点回答：

- `state token` 长什么样
- `action token` 长什么样
- `return-to-go` 如何定义
- 不同决策粒度下如何组织轨迹
- AI policy family 如何进入 DT 数据结构

本文档不限定最终必须逐天决策。相反，它要求数据规范同时支持：

- `stage`
- `window`
- `daily`

并支持三种控制模式：

- `water_only`
- `nitrogen_only`
- `joint`

---

## 2. 设计原则

Decision Transformer 不是普通分类器，而是序列建模方法。

后续训练样本必须组织成轨迹序列，核心元素包括：

- `return_to_go`
- `state`
- `action`

因此，当前项目要切换到 DT，不是只改模型代码，而是要先重构数据结构。

---

## 3. 基本轨迹单元

对于每个时间步 `t`，建议至少记录：

- `state_t`
- `action_t`
- `reward_t`
- `return_to_go_t`
- `done_t`

可选补充：

- `next_state_t`
- `executed_action_t`
- `weather_forecast_t`
- `recommended_action_t`

其中需要特别新增两个控制维度字段：

- `decision_granularity`
- `control_mode`

---

## 4. 决策粒度字段

### 4.1 `decision_granularity`

必须显式记录当前样本属于哪种粒度：

- `stage`
- `window`
- `daily`

原因：

- 决策粒度本身就是研究变量
- 后续实验需要比较不同粒度
- 不能默认所有 DT 数据都只适配 daily

### 4.2 粒度含义

- `stage`
  - 一个时间步对应一个生育阶段

- `window`
  - 一个时间步对应一个管理窗口
  - 例如 5 天、7 天或 10 天窗口

- `daily`
  - 一个时间步对应一天

---

## 5. 控制模式字段

### 5.1 `control_mode`

每条 DT 样本必须显式记录：

- `water_only`
- `nitrogen_only`
- `joint`

原因：

- 后续 AI policy 不是一条，而是一个 policy family
- DT 训练和评测必须支持三种控制模式分别学习与比较

### 5.2 控制模式含义

- `water_only`
  - 动作中只有灌溉由模型决定
  - 施氮由固定 baseline、规则或外部策略提供

- `nitrogen_only`
  - 动作中只有施氮由模型决定
  - 灌溉由固定 baseline、规则或外部策略提供

- `joint`
  - 动作中灌溉和施氮都由模型决定

### 5.3 两种实现方式

后续 DT 可采用两种形式之一：

1. **三套独立模型**
   - `DT-water_only`
   - `DT-nitrogen_only`
   - `DT-joint`

2. **一个条件化 DT**
   - 在输入中加入 `control_mode` token
   - 让同一模型在不同模式下输出不同行为空间

无论实现选哪种，数据层都必须显式保存 `control_mode`。

---

## 6. `state token` 设计

`state_t` 建议至少包含：

- 当前时间索引
- 当前生育进度
- 历史天气摘要
- 当前土壤水分状态
- 当前土壤氮素状态
- 当前作物状态
- 剩余灌溉预算
- 剩余施氮预算
- 最近一次建议动作
- 最近一次实际执行动作
- 短期天气预报窗口特征
- 农户执行偏差特征（如有）

对于不同粒度：

- `stage`
  - `state_t` 对应当前阶段状态

- `window`
  - `state_t` 对应当前窗口状态与窗口内历史摘要

- `daily`
  - `state_t` 对应当天状态

---

## 7. `action token` 设计

`action_t` 的定义依赖于：

- `decision_granularity`
- `control_mode`

### 7.1 `stage`

- `water_only`
  - 当前阶段灌溉量

- `nitrogen_only`
  - 当前阶段施氮量

- `joint`
  - 当前阶段灌溉量 + 当前阶段施氮量

### 7.2 `window`

- `water_only`
  - 当前窗口灌溉量

- `nitrogen_only`
  - 当前窗口施氮量

- `joint`
  - 当前窗口灌溉量 + 当前窗口施氮量

### 7.3 `daily`

- `water_only`
  - 当天灌溉量

- `nitrogen_only`
  - 当天施氮量

- `joint`
  - 当天灌溉量 + 当天施氮量

---

## 8. `return-to-go` 设计

建议 `return_to_go_t` 定义为：

- 从当前时间步到季末的累计回报

第一版可采用：

- 未折扣累计回报

如果后续需要，再引入折扣形式。

为了保证三种控制模式之间可比较，RTG 的定义必须保持一致：

- `water_only`
- `nitrogen_only`
- `joint`

不能为不同控制模式使用不同 reward 口径。

---

## 9. 轨迹切片方式

训练样本不一定必须整季完整输入，建议支持：

1. 全轨迹训练
2. 前缀切片训练
3. 固定长度窗口训练

推荐优先支持：

- 前缀切片
- 固定长度窗口

因为更适合连续决策场景。

---

## 10. 数据文件建议

建议输出以下训练文件：

- `stage_dt_train.jsonl`
- `stage_dt_val.jsonl`
- `stage_dt_test.jsonl`
- `window_dt_train.jsonl`
- `window_dt_val.jsonl`
- `window_dt_test.jsonl`
- `daily_dt_train.jsonl`
- `daily_dt_val.jsonl`
- `daily_dt_test.jsonl`

每条记录至少包含：

- `scenario_id`
- `paper_slice_id`（若适用）
- `decision_granularity`
- `control_mode`
- `trajectory`

其中 `trajectory` 内部至少含有：

- `state`
- `action`
- `reward`
- `return_to_go`
- `done`

---

## 11. 评测侧要求

DT 数据规范必须与评测规范一致。

也就是说，后续任何 DT 模型的输出和结果统计都必须支持：

- `AI-water_only`
- `AI-nitrogen_only`
- `AI-joint`

不能只生成一个“AI policy”结果文件。

如果使用单模型条件化训练，也必须在评测输出中拆成三组结果。

---

## 12. 结论

后续如果正式切换到 Decision Transformer，必须同时满足以下条件：

1. 支持多粒度：
   - `stage`
   - `window`
   - `daily`

2. 支持三种控制模式：
   - `water_only`
   - `nitrogen_only`
   - `joint`

3. 在样本层显式记录：
   - `decision_granularity`
   - `control_mode`

因此，DT 版本的数据规范必须默认把：

> **AI 方法视为一个由 `water_only`、`nitrogen_only`、`joint` 组成的 policy family**

作为基础前提，而不是把 AI 当成单一策略对象。
