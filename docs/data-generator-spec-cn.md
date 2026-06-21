# 新训练数据生成器规格说明书

## 1. 背景与动机

旧版 `generate_training_scenario_pool()` 存在以下问题：

- 天气数据使用合成方法而非真实逐日观测，可能产生不合理降水模式（如连续每日降水）
- 场景数据缺失 DSSAT 必需的种植详情、初始条件、田间信息等参数
- 土壤和天气数据来源不明确，与参考测试集可能存在泄露
- 输出格式仅支持内部 schema，无法直接灌入 official DSSAT 执行

本 spec 定义新的数据生成器 `generate_training_data()`，替代旧版。

## 2. 数据来源（与测试集完全隔离）

### 2.1 天气数据

**来源**: `逐日数据.xlsx`，气象站 53893 和 54076
**可用年限**: 2016-2026，每站约 11 年
**与测试集隔离**: 测试集使用 WH20 站（mx475）和 EQAH 站（wuhu），无重叠

**每条训练场景的天气生成规则**:
1. 从两个气象站中随机选一站
2. 从 2016-2026 中随机选一年
3. 在播期锚点（水稻 6月18日，玉米 6月18日）±8 天窗口内随机偏移
4. 截取 `season_length_days` 天的逐日 SRAD/TMAX/TMIN/RAIN 序列

**年际错配扩增**（增加多样性）:
- 温度年 + 降水年可来自不同年份，例如：用站 53893 2020 年的温度序列 + 站 54076 2023 年的降水序列组合
- 实现方式：分别从温度年和降水年池中独立抽样，按 DOY 拼接

**生成限制**: 一条场景生成时，播种日期、湿润年份、降水年份三个维度不允许三者同时与参考测试集（mx475 或 wuhu 子集）完全一致

### 2.2 土壤数据

**来源**: `土壤/` 目录，40 个真实土壤样本
**分组**: 江西第一次、江西第二次、舒兰第一次（共 3 批）
**与测试集隔离**: 测试集使用 SOIL.SOL（mx475）和 CN.SOL/WH.SOL（wuhu），无重叠

**每条训练场景的土壤生成规则**:
1. 从 40 个真实样本中有放回均匀采样
2. 对采样剖面施加合理微扰（含水量 ±5%，硝态氮 ±10%）
3. 微扰后的剖面标记 `synthetic` 标签

**统计扩增**（可选，需求量大时启用）:
- 对 40 个样本的有机质、全氮、有效磷、速效钾、pH 拟合多元分布
- 从拟合分布中采样生成合成剖面，保持属性间相关性
- 合成剖面标记 `synthetic`，不与真实样本混淆

### 2.3 品种基因参数

| 作物 | 品种 | cultivar_id | DSSAT code | 参数维度 | 数据来源 |
|------|------|-------------|------------|----------|----------|
| 水稻 | 美香占2号 (mx475) | `meixiangzhan2` | IB2002 | 11 参数 | 4.7.5 迁移模型 |
| 水稻 | 美香占2号 (wuhu) | `meixiangzhan2-wh` | WHR006 | 11 参数 | GenCalc 标定 |
| 玉米 | 登海605 | `denghai605` | DH6051 | 6 参数 | 农业同学校准 |
| 小麦 | — | — | — | — | **跳过，暂无标定参数** |

每条水稻场景从 {IB2002, WHR006} 中独立随机选择一个品种。

### 2.4 种植管理参数

#### 2.4.1 种植详情 (PLANTING DETAILS)

| 参数 | 符号 | 取值范围/策略 | 说明 |
|------|------|-------------|------|
| 播种日期 | PDATE | 锚点日 ±8天偏移 | 根据天气窗口确定 |
| 播种方式 | PLME | T(移栽)=90%, S(直播)=10% | 水稻为主移栽 |
| 种植密度 | PLDS | Uniform(20, 35) plants/m² | 参考 mx475 密度 12-20 |
| 行距 | PLRS | Uniform(15, 30) cm | 参考值 20 cm |
| 播深 | PLDP | Uniform(2, 5) cm | 参考值 3 cm |
| 推荐群体 | PPOP | =PLDS | 与种植密度一致 |

#### 2.4.2 初始条件 (INITIAL CONDITIONS)

| 参数 | 符号 | 策略 | 说明 |
|------|------|------|------|
| 分层含水量 | SH2O | 从土壤剖面推導 | 基于 field_capacity 和播前降水调整 |
| 分层铵态氮 | SNH4 | Uniform(2, 6) kg/ha | 参考 mx475 值 2.5-4.6 |
| 分层硝态氮 | SNO3 | Uniform(0.4, 1.5) kg/ha | 参考 mx475 值 0.4-1.0 |
| 播前日期 | ICDAT | =PDATE - 15 | 播种前15天 |
| 层深度 | ICBL | [10, 10, 10, 10] cm | 4层，每层10cm（参考 mx475） |

#### 2.4.3 田间信息 (FIELDS)

| 参数 | 策略 |
|------|------|
| ID_FIELD | 自动生成唯一标识 |
| WSTA | 关联选中的气象站 |
| ID_SOIL | 关联选中的土壤剖面 |
| 坐标/高程/面积 | 置为 -99（非必需） |

### 2.5 水肥策略基线

**训练池场景**: 使用 heuristic/literature 策略：
- 灌溉: `literature_ncp` 策略 — 基于文献推荐的水稻灌溉制度
- 施肥: 同样使用文献推荐的分次施肥方案
- 水肥联合: `heuristic` 策略的联合分配

**测试集场景（mx475/wuhu）**: 保留源管理方案（original management replay），不做替换。

## 3. 输出格式

### 3.1 内部 schema (Python 对象)

保持与现有 `SimulationScenario` 兼容，扩展 `CropManagement` 字段：

```python
@dataclass
class CropManagement:
    # 已有
    planting_date: str
    # 新增
    planting_method: str = "T"       # T=transplant, S=seed
    plant_density: float = 25.0      # plants/m²
    row_spacing: float = 20.0        # cm
    planting_depth: float = 3.0      # cm
    # 初始条件
    initial_soil_water: list[float]  # by layer
    initial_no3: list[float]         # kg/ha by layer
    initial_nh4: list[float]         # kg/ha by layer
    # 水肥策略
    irrigation_schedule: list[IrrigationEvent]
    fertilizer_schedule: list[FertilizerEvent]
```

### 3.2 DSSAT 原生格式 (文件)

每条场景产出完整的 DSSAT 输入文件包：
- `{exp_name}.RIX` — 实验文件，包含所有 TREATMENTS / CULTIVARS / FIELDS / PLANTING DETAILS / IRRIGATION / FERTILIZERS / INITIAL CONDITIONS / SIMULATION CONTROLS 等全量 section
- `{exp_name}.WTH` — 天气文件
- 引用 `${runtime}/Soil/{soil_id}.SOL` — 土壤文件
- 引用 `${runtime}/Genotype/RICER048.CUL` — 基因参数文件

两种格式内容一致，只是表示方式不同。内部 schema 供模型训练使用，DSSAT 原生格式供 official DSSAT 运行和评测。

## 4. 生成流程

```
for each crop in [rice, maize]:
    for i in range(target_count_per_crop):
        1. 随机选品种（水稻从 {IB2002, WHR006} 随机）
        2. 随机选气象站 (53893 or 54076)
        3. 随机选温度年份 + 降水年份（可不同，年际错配）
        4. 在播期窗口内随机偏移播期
        5. 截取逐日天气序列
        6. 随机选土壤样本 + 微扰
        7. 生成种植详情参数
        8. 生成初始条件剖面
        9. 使用 heuristic/literature 策略生成水肥基线
        10. 输出内部 schema + DSSAT 文件包
        11. 写入 manifest
```

## 5. 验证清单

- [ ] 生成的天气站 ID 不在 {WH20, EQAH} 中
- [ ] 生成的土壤 ID 不在测试集土壤集合中
- [ ] 播种日期窗口不与测试集处理完全重合
- [ ] 水稻品种为 IB2002 或 WHR006，不是 placeholder
- [ ] 玉米品种为 DH6051
- [ ] 每个输出包含完整 RIX section（PLANTING DETAILS, INITIAL CONDITIONS, IRRIGATION, FERTILIZERS, SIMULATION CONTROLS）
- [ ] 天气序列无缺失值，降水值合理（非负）
- [ ] 土壤剖面参数在合理范围内
- [ ] 内部 schema 和 DSSAT 文件内容一致
- [ ] RIX 文件可被 DSSAT 正常解析运行

## 6. 与旧系统的断舍离

- 弃用 `generate_training_scenario_pool()` 及相关 `generate_realistic_scenario` / `generate_grid_scenarios` / `generate_random_scenarios`
- 弃用 proxy simulator 路径，统一使用 official DSSAT 作为仿真执行器
- 弃用旧的场景验证逻辑，替换为上述验证清单
- 保留 `RealSubsetBundle` 和 `real_subset_replay` 作为测试集管理
