# TransDSSAT 文献策略注册表规范（中文版）

## 1. 文档目的

本文档定义 TransDSSAT 中 `policy_registry` 的结构、字段规范和使用方式。

目标是让后续所有文献策略都通过统一入口注册，而不是散落在不同脚本和条件分支中。

---

## 2. 设计原则

`policy_registry` 的设计必须满足：

1. 能区分：
- `generalized_rule`
- `original_strategy`

2. 能表达：
- 适用测试集
- 适用场景切片
- 所需元数据
- 预算处理方式

3. 能记录：
- 是否实现
- 是否只是保守近似
- 哪些论文信息仍然缺失

---

## 3. registry 条目结构

每篇文献至少对应一个顶层条目。

推荐结构：

```yaml
paper_id:
  title:
  source_url:
  crop_system:
  generalized_rules:
  original_strategies:
  required_metadata:
  applicable_test_sets:
  required_scenario_slice:
  budget_handling:
  notes:
  missing_details:
  implementation_status:
```

---

## 4. 字段定义

### 4.1 基本标识字段

- `paper_id`
  - 全局唯一短标识
  - 推荐格式：`journal_year_shortname`

- `title`
  - 论文全名

- `source_url`
  - 论文 DOI 或主链接

- `crop_system`
  - 例如：
    - `wheat-maize rotation`
    - `winter wheat only`
    - `summer maize only`

### 4.2 策略字段

- `generalized_rules`
  - 列出所有通用化规则定义

- `original_strategies`
  - 列出所有原始策略定义

### 4.3 场景依赖字段

- `required_metadata`
  - 执行该论文策略至少需要的场景字段

- `applicable_test_sets`
  - 可运行在哪些测试集上：
    - `general_random`
    - `matched_slice`

- `required_scenario_slice`
  - 如果只在 matched slice 中有意义，这里应写明所需 slice 类型

### 4.4 预算处理字段

- `budget_handling`
  - 可取：
    - `original_absolute`
    - `budget_normalized`
    - `requires_reference_N`

### 4.5 实现状态字段

- `implementation_status`
  - 可取：
    - `implemented`
    - `conservative_approximation`
    - `not_implemented`

- `missing_details`
  - 若文献信息不足，必须明确列出

- `notes`
  - 记录近似、假设、限制

---

## 5. generalized rule 子条目规范

每个 generalized rule 推荐包含：

- `rule_id`
- `rule_name`
- `description`
- `trigger_conditions`
- `required_metadata`
- `budget_handling`
- `outputs`
- `applicable_crops`
- `applicable_test_sets`
- `implementation_status`
- `notes`

### 示例

```yaml
rule_id: awm2023_di5_nsplit
rule_name: DI5 + 40/60 split-N
description: 小麦拔节/开花灌溉，玉米苗期/拔节/抽雄灌溉，总氮按 40% 基肥 + 60% 追肥分配
budget_handling: budget_normalized
applicable_test_sets: [general_random, matched_slice]
implementation_status: implemented
```

---

## 6. original strategy 子条目规范

每个 original strategy 推荐包含：

- `strategy_id`
- `strategy_name`
- `description`
- `absolute_inputs`
- `required_metadata`
- `required_scenario_slice`
- `budget_handling`
- `applicable_crops`
- `implementation_status`
- `missing_details`
- `notes`

### 示例

```yaml
strategy_id: awm2023_di5_n60
strategy_name: DI5N60 original treatment
description: 原论文 DI5N60 处理，使用论文中的绝对总氮量和灌溉制度
budget_handling: original_absolute
required_scenario_slice: ncp_wm_dripfert_matched
implementation_status: conservative_approximation
```

---

## 7. 使用规则

### 7.1 random test 上的使用规则

在 `General Random Test Set` 上：

- 可调用 generalized rules
- 不应默认调用 original strategies

### 7.2 matched slice 上的使用规则

在 `Literature-Matched Scenario Slice` 上：

- 可调用 generalized rules
- 可调用当前 slice 对应的 original strategy

### 7.3 not applicable 规则

若场景不满足该条目所需前提，应直接返回：

- `not_applicable`

而不是强行运行。

---

## 8. 第一批推荐注册文献

后续应优先为以下文献建立 registry 条目：

1. AWM 2023 水肥节约管理实践
2. ICARDA 滴灌施肥氮管理
3. AWM 2024 基于降雨的灌溉优化
4. AWM 2023 缩小水分生产力差距
5. JAFR 2024 季间氮肥分配
6. Agriculture 2023 地面灌溉随水施肥
7. AWM 2020 冬小麦滴灌施肥
8. Sci Rep 2020 冬小麦分次施氮
9. AWM 2024 夏玉米滴灌施肥
10. International Agrophysics DSSAT 推导方案

---

## 9. 结论

后续所有文献策略都必须先注册到 `policy_registry`，再进入实现与评测流程。

这一步的价值在于：

- 保证概念清晰
- 保证实现可追踪
- 保证评测协议一致
