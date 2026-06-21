# TransDSSAT 场景与测试集 Schema 设计文档（中文版）

## 1. 文档目的

本文档定义：

- General Random Test Set 的场景结构
- Literature-Matched Scenario Slice 的场景结构
- 统一 metadata schema

用于指导后续测试集生成实现。

---

## 2. 场景层级

后续场景应分为三层：

1. **Base Scenario**
- 单个作季或轮作场景的基础定义

2. **Test Scenario**
- 可直接进入评测的完整场景对象

3. **Scenario Slice Metadata**
- 描述一个测试切片的适用前提和限制

---

## 3. Base Scenario 字段

每个基础场景至少应包含：

- `scenario_id`
- `crop_system`
- `crop_name`
- `season_name`
- `planting_date`
- `season_length_days`
- `weather_series`
- `soil_profile`
- `initial_root_zone_water_mm`
- `initial_nitrogen_kg_ha`
- `irrigation_budget_mm`
- `nitrogen_budget_kg_ha`
- `growth_stage_boundaries`
- `management_mode`

---

## 4. weather_series 字段要求

每个天气序列至少包含逐日：

- `date`
- `tmin_c`
- `tmax_c`
- `precipitation_mm`
- `radiation_mj_m2`
- `et0_mm`

还应支持派生量计算，例如：

- 小麦播种到拔节期累计降雨 `P1`

---

## 5. General Random Test Set schema

随机测试集中的每个场景必须是：

- 全量合法
- 可供 AI policy 和 generalized rules 直接运行

必须包含：

- 上述 Base Scenario 全字段
- `weather_regime`
- `budget_level_water`
- `budget_level_nitrogen`
- `split`
- `sampling_mode`

---

## 6. Literature-Matched Slice schema

matched slice 除 Base Scenario 外，还应附带：

- `slice_id`
- `paper_id`
- `slice_type`
- `matched_conditions`
- `approximated_conditions`
- `missing_conditions`
- `applicable_original_strategies`
- `applicable_generalized_rules`

---

## 7. split 设计建议

建议后续统一采用：

- `train`
- `val`
- `test`

而不再只区分：

- `train`
- `test`

原因：

- 后续模型训练规模更大
- 需要更稳定的模型选择与早停

---

## 8. 规模建议

建议第一版正式目标为：

- `General Random Train = 2000`
- `Validation = 300`
- `Test = 500`
- `Matched Slice per paper = 100`

---

## 9. 结论

后续场景生成器应围绕统一 schema 实现，而不是继续用零散字段和脚本内隐约定。
