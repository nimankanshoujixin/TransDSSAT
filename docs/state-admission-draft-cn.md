# TransDSSAT 状态准入草案（保守版）

## 1. 目的

这份文档先把当前代码里已经设计进去的状态整理出来，并按照保守口径做第一轮判断。

后续真实资料回来之后，再逐项改判。

本草案采用下面这条硬规则：

1. 如果一个状态在 DSSAT 里有，但现实里稳定采不到，则不能作为真实模型输入。
2. 如果一个状态在现实里能拿到，但 DSSAT 里没有直接对应，则先不急着丢掉，要判断它是：
   - 可映射状态
   - 可换算状态
   - 只作为辅助观测
   - 只作为校验标签
3. 只有“现实可稳定获取 + DSSAT 可对应”的状态，才优先进入共享状态空间。

---

## 2. 判定标签说明

- `保留`
  - 先按真实输入候选保留
- `条件保留`
  - 只有在你确认真实采集渠道稳定时才保留
- `转派生量`
  - 不直接作为原始输入，而是由其他真实信息推导
- `仅模拟器内部`
  - 可以留在 DSSAT / proxy / 环境内部，但不作为真实输入
- `候选新增`
  - 当前代码里没有，但很值得你现场核查是否应加入

---

## 3. 当前设计的初始输入

这里的“初始输入”指一个场景开始时就已经给定的内容，主要来自
[scenarios.py](/G:/TransDSSAT/transdssat/scenarios.py)。

| 当前字段 | 中文含义 | 当前所在位置 | 保守判定 | 你需要核实什么 |
| --- | --- | --- | --- | --- |
| `crop_name` | 作物名称 | `CropSpec` / `CropContext` | `保留` | 现实中是否稳定记录到作物类别 |
| `crop_type` | 作物类型 | `CropContext` | `保留` | 与作物名称是否有重复 |
| `cultivar_id` | 品种编号 | `CultivarParameterRecord` | `保留` | 现实里是否能稳定拿到统一品种标识 |
| `cultivar_name` | 品种名称 | `CultivarParameterRecord` | `保留` | 农户口头品种名和正式品种名是否一致 |
| `cultivar_parameter_vector` | 品种参数向量 | `CultivarParameterRecord` | `仅模拟器内部` | 现实里一般不会直接采到，属于模型/机理参数 |
| `dssat_cultivar_code` 等 | DSSAT 品种映射 | `CultivarParameterRecord` | `仅模拟器内部` | 这是对接 DSSAT 用，不是农户输入 |
| `site_name` | 地点名称 | `SimulationScenario` / `CropContext` | `保留` | 是否还要更细到村、地块、小区 |
| `weather_year` | 天气年份 | `SimulationScenario` | `条件保留` | 真实部署时未必直接作为输入，但可做索引元数据 |
| `planting_date` | 播种日期 | `SimulationScenario` | `保留` | 现实里能否稳定获得准确日期 |
| `soil_name` | 土壤类型名 | `SoilProfile` | `条件保留` | 现实里是否有正式土壤分类，还是只能口头描述 |
| `field_capacity_mm` | 田间持水量 | `SoilProfile` | `仅模拟器内部` | 现实里通常不直接采到 |
| `wilting_point_mm` | 萎蔫点 | `SoilProfile` | `仅模拟器内部` | 现实里通常不直接采到 |
| `saturation_mm` | 饱和含水量 | `SoilProfile` | `仅模拟器内部` | 现实里通常不直接采到 |
| `drainage_coeff` | 排水系数 | `SoilProfile` | `仅模拟器内部` | 更像模型参数，不是现实观测量 |
| `initial_root_zone_water_mm` | 初始根区含水量 | `SoilProfile` | `条件保留` | 只有有稳定测量或可可信估计时才保留 |
| `initial_nitrogen_kg_ha` | 初始土壤氮 | `SoilProfile` | `条件保留` | 只有有土样或阶段检测时才保留 |
| `irrigation_budget_mm` | 灌溉预算 | `SimulationScenario` | `保留` | 现实里是否真有“预算”概念，还是要改成可灌水上限/计划值 |
| `nitrogen_budget_kg_ha` | 施氮预算 | `SimulationScenario` | `保留` | 同上 |
| `objective_id` | 管理目标编号 | `ObjectiveContext` | `条件保留` | 现实里是否真的能显式定义目标，还是要改成标签化 |
| `reward_weights` | 奖励权重 | `ObjectiveContext` | `仅模拟器内部` | 这是训练设计，不是现实输入 |
| `decision_interval_days` | 决策间隔天数 | `DecisionContext` | `保留` | 属于系统设定，不是地块状态 |
| `forecast_horizon_days` | 预报窗口长度 | `DecisionContext` | `保留` | 属于系统设定 |
| `irrigation_min_gap_days` | 灌溉最小间隔 | `DecisionContext` | `条件保留` | 要核查现实里是否真的存在稳定操作间隔 |
| `nitrogen_min_gap_days` | 施氮最小间隔 | `DecisionContext` | `条件保留` | 同上 |
| `allow_combined_actions` | 是否允许水肥同做 | `DecisionContext` | `条件保留` | 要核查农户实际是否会联合作业 |

---

## 4. 当前设计的中间输入

这里的“中间输入”指每一步决策时环境给出的当前观测，主要来自
[stepwise.py](/G:/TransDSSAT/transdssat/environments/stepwise.py)
和 [domain.py](/G:/TransDSSAT/transdssat/domain.py)。

| 当前字段 | 中文含义 | 当前所在位置 | 保守判定 | 你需要核实什么 |
| --- | --- | --- | --- | --- |
| `day_index` | 距播种后的天数 | `CropState` / `DecisionObservation` | `保留` | 是否更习惯用“距播种几天”还是“实际日期” |
| `decision_date` | 当前决策日期 | `DecisionObservation` | `保留` | 日期是否可稳定记录 |
| `stage` | 当前生育阶段 | `CropState` | `保留` | 现实里能否通过调查稳定判断 |
| `stage_index` | 生育阶段编号 | `CropState` | `转派生量` | 可由生育阶段文字映射得到 |
| `soil_moisture` | 土壤湿度比例 | `CropState` | `条件保留` | 是否有传感器、手持仪或稳定估测方法 |
| `root_zone_water_mm` | 根区含水量 | `CropState` | `仅模拟器内部` | 现实里通常拿不到这种精细量 |
| `soil_nitrogen_kg_ha` | 土壤氮含量 | `CropState` | `仅模拟器内部` | 除非有持续检测，否则不能当实时输入 |
| `canopy_cover` | 冠层覆盖 | `CropState` | `条件保留` | 是否可由人工观察或图像估计稳定获得 |
| `biomass_kg_ha` | 生物量 | `CropState` | `条件保留` | 现实里若有干重/生物量测量，可进一步映射 |
| `water_stress` | 水分胁迫 | `CropState` | `仅模拟器内部` | 现实里通常只能间接判断，不能当直接状态 |
| `nitrogen_stress` | 氮胁迫 | `CropState` | `仅模拟器内部` | 同上 |
| `tmean_c` | 当日平均气温 | `CropState` | `转派生量` | 由最高/最低温计算即可 |
| `precipitation_mm` | 当日降雨 | `CropState` | `保留` | 可由气象站或天气服务提供 |
| `et0_mm` | 参考蒸散 | `CropState` | `条件保留` | 现实里一般不是直接观测，通常来自气象计算 |
| `radiation_mj_m2` | 辐射 | `CropState` | `条件保留` | 现实里常依赖气象数据源，不是农户直接记录 |
| `remaining_irrigation_mm` | 剩余灌溉预算 | `DecisionObservation` | `保留` | 由初始预算和历史操作计算得到 |
| `remaining_nitrogen_kg_ha` | 剩余施氮预算 | `DecisionObservation` | `保留` | 同上 |
| `forecast_weather_window` | 未来几天天气窗口 | `DecisionObservation` | `保留` | 现实部署时能否稳定接天气预报 |
| `action_constraints` | 当前动作约束 | `DecisionObservation` | `转派生量` | 它不是原始状态，而是由状态和规则推导出来的系统信息 |
| `done` | 是否结束 | `DecisionObservation` | `仅系统控制` | 属于环境结束标志，不是现实状态 |

---

## 5. 当前代码里已经缺失、但高度值得你核查的状态

这些字段当前没有成为正式状态，或者没有被显式放进中间输入，但我认为非常值得你带着问题去核查。

### 5.1 高优先级候选新增状态

| 候选状态 | 为什么值得核查 | 初步建议用途 |
| --- | --- | --- |
| 最近一次灌溉日期与灌溉量 | 真实决策高度依赖最近一次操作 | 很可能应进中间输入 |
| 最近一次施肥日期、肥料类型、施肥量 | 真实决策高度依赖最近一次操作 | 很可能应进中间输入 |
| 历史累计灌溉量 | 现实里容易从日志累计出来 | 可替代部分内部预算感知 |
| 历史累计施肥量 | 同上 | 可替代部分内部预算感知 |
| 当前田间长势等级 | 现实里农户常用 | 可作为简化状态或辅助观测 |
| 叶色/SPAD/黄化程度 | 可反映氮素相关状态 | 值得核查能否稳定获取 |
| 株高 | 现实里易测 | 很值得纳入候选状态 |
| 叶面积指数或其替代指标 | 文档里已有对应项 | 值得核查是否现实里真会测 |
| 地上部干重 / 生物量 | 现实里可能测，DSSAT 也可能映射 | 优先做映射核查 |
| 病虫害情况 | 现实里对决策影响很大 | 当前完全没进状态，值得补充 |
| 地块可进入性/是否能作业 | 现实操作约束强 | 更像动作约束输入 |
| 水源可用性/灌溉条件 | 直接影响是否能执行灌溉 | 很可能应进约束层 |

### 5.2 稻田场景特别要补问的状态

如果你后面看的是水稻，不只要沿用玉米这套，还要额外问：

- 田面水层深度
- 排水/晒田/复水状态
- 断水日期
- 移栽信息

这些在当前玉米导向状态里几乎没有体现，但现实上非常重要。

---

## 6. 干重 / 生物量这一类状态怎么先保守看

当前代码里已经有一条“生物量”线：

- 代理环境里直接维护 `biomass_kg_ha`
- 官方 DSSAT 解析里会从这些变量尝试取生物量或干物质量：
  - `CWAD`
  - `TWAD`
  - `VWAD`
  - `TOPWT`
  - `CWAM`
  - `VWAM`
  - `BWAH`
  - `PWAM`
  - `BIOMAS`

所以保守结论是：

1. “干重”不是当前系统完全没有对应的状态。
2. 但“干重”不是一个单独概念，必须先问清：
   - 是整株还是地上部
   - 是鲜重还是干重
   - 单位是 `g/株`、`g/m²` 还是 `kg/ha`
   - 是哪个时期测的
3. 在这些定义没确认前，先把“干重/生物量”归为 `条件保留`。

---

## 7. 你这次最值得带回来的判定结果

后面你搜集真实资料时，我建议你优先对下面这些状态逐项给出结论：

### A. 一定要判定

- 生育阶段是否能稳定判断
- 最近一次灌溉记录是否能拿到
- 最近一次施肥记录是否能拿到
- 预算在现实里有没有明确表达
- 土壤湿度是否有真实测量手段
- 土壤氮是否有真实测量手段
- 冠层覆盖能否由人工或图像稳定获得
- 干重/生物量的具体定义、单位、频率

### B. 很值得补充

- 株高
- 叶色/SPAD
- 地上部干重
- 叶面积指数
- 病虫害情况
- 地块是否能进机械/人工
- 水源可用性

---

## 8. 当前一版最保守的共享状态建议

如果现在立刻要收缩成一版最保守、最不容易“想当然”的真实输入，我建议先只保留：

### 初始输入

- 作物名称
- 品种名称/编号
- 地点/地块标识
- 播种日期
- 管理目标标签
- 灌溉预算
- 施肥预算
- 土壤类型的粗分类

### 中间输入

- 当前日期
- 距播种天数
- 当前生育阶段
- 最近天气历史
- 未来几天天气预报
- 最近一次灌溉记录
- 最近一次施肥记录
- 累计已用水、累计已用肥、剩余预算
- 田间可观察长势指标

其余字段都先不要默认作为真实输入，等你带回资料后再逐项放开。

