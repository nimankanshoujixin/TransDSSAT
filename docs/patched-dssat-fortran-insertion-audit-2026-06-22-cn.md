# Patched DSSAT Fortran 插桩审计（2026-06-22）

## 1. 目标

本审计只回答一个问题：

- 在保持 vanilla DSSAT runtime 不变的前提下，`patched` runtime 最小应该改哪里，才能把 official DSSAT 变成 gym-DSSAT 风格的日级 `reset/step` 环境。

本轮只做源码定位和接口收敛，不启动训练，不改 crop model 数值逻辑。

## 2. 远端源码树与本轮审计范围

已审计远端源码树：

- `/fs/fast/u2021201693/lym/dssat-csm-os-v4.8.5`

本轮重点检查的文件：

- `CSM_Main/CSM.for`
- `CSM_Main/LAND.for`
- `Management/MgmtOps.for`
- `Management/IRRIG.for`
- `Management/Fert_Place.for`

结论先行：

- 真正的日级主循环在 `CSM_Main/CSM.for`
- 最窄、最稳的交互插桩层应放在 `CSM_Main/LAND.for` 与 `Management/MgmtOps.for`
- 第一版 interactive patched runtime 不应直接改作物模型子模块
- 第一版只需要接管“状态导出 + 动作注入 + 单日推进 + 终局导出”四件事

## 3. 已确认的日级执行骨架

### 3.1 顶层日循环在 `CSM_Main/CSM.for`

关键位置：

- `CSM_Main/CSM.for:433-534`

已确认这里存在完整 season/day 调度：

1. `SEASINIT`
2. 进入 `DAY_LOOP`
3. 每日依次执行：
   - `RATE`
   - `INTEGR`
   - `OUTPUT`

其中最关键的日级边界是：

- `CSM_Main/CSM.for:492-531`

这意味着 patched runtime 最自然的 step 边界就是：

- Python 发一次 action
- Fortran 恢复 `DAY_LOOP` 完成一整天的 `RATE -> INTEGR -> OUTPUT`
- Fortran 在日末返回 next state / reward / done

这与 gym-DSSAT 的 blocking daily loop 思路一致。

### 3.2 `LAND.for` 是日级模块汇合点

关键位置：

- `CSM_Main/LAND.for:212-280`
- `CSM_Main/LAND.for:287-318`

这里确认了：

1. `SEASINIT` 阶段已经能构造完整季初状态
2. `RATE` 阶段顺序是：
   - `WEATHR`
   - `MGMTOPS`
   - `SOIL`
   - 后续 `SPAM` / `PLANT`

因此，若要实现 interactive official DSSAT：

- `get_state` 最适合放在 `RATE` 阶段、`WEATHR` 之后、`MGMTOPS` 之前
- `set_action` 最适合在同一位置完成，然后让后续 `MGMTOPS/SOIL/PLANT` 消化该动作

原因：

- 这时当天天气已就绪
- 前一日积分后的土壤/作物状态已稳定
- 当天管理动作尚未生效，仍可安全覆盖

## 4. 已确认的管理动作注入层

### 4.1 `MgmtOps.for` 已经是灌溉/施肥主入口

关键位置：

- `Management/MgmtOps.for:167-183`
- `Management/MgmtOps.for:216-237`
- `Management/MgmtOps.for:253-258`

已确认：

- `Fert_Place(...)` 负责当日施肥事件
- `IRRIG(...)` 负责当日灌溉事件
- `IRRAMT`、`FERTDATA`、`TOTIR` 等量都在这里汇总并传下游

因此第一版 patched 交互不需要去改 crop module，而是优先在 `MGMTOPS` 增加一个 interactive 分支：

1. 若不是 interactive mode，保持现状
2. 若是 interactive mode：
   - 跳过自动灌溉/自动施肥调度
   - 把 Python 传回的 irrigation / nitrogen 动作直接写入 `IRRAMT` 与 `FERTDATA`
   - 其余未接管的管理项继续沿用原逻辑

这比直接入侵 `SOIL`、`PLANT` 或作物专属 `*_OPNIT` 例程更小、更稳。

### 4.2 `IRRIG.for` 与 `Fert_Place.for` 只是“当天管理生成器”

关键位置：

- `Management/IRRIG.for:138-259`
- `Management/Fert_Place.for:297-420`

本轮确认：

- `IRRIG.for` 负责把当天灌溉规则变成 `IRRAMT`
- `Fert_Place.for` 负责把当天施肥事件变成 `AMTFER/FERTDATA`

这两个模块更适合被“旁路”或“条件跳过”，而不是作为第一版交互协议的主通信层。

换句话说，第一版不建议：

- 在 `IRRIG.for` 里直接塞文件轮询
- 在 `Fert_Place.for` 里直接塞 Python 协议

第一版建议：

- 在 `LAND/MGMTOPS` 做统一 interactive gate
- 只把 `IRRIG/Fert_Place` 保留为 vanilla / non-interactive 路径

## 5. 最小交互生命周期应该落在哪些点

### 5.1 `reset`

建议插桩点：

- `CSM_Main/CSM.for` 中 `SEASINIT` 的 `CALL LAND(...)` 之后
- 对应当前文件约 `483-486` 一带

此时：

- 季节初始化已完成
- 初始状态可读
- 日循环尚未开始

应执行：

1. 导出初始 observation
2. 写 `session_ready`
3. 阻塞等待第一步 action

### 5.2 `get_state`

建议插桩点：

- `CSM_Main/LAND.for` 的 `RATE` 分支内
- 在 `CALL WEATHR(...)` 之后、`CALL MGMTOPS(...)` 之前
- 对应约 `294-304` 一带

应导出的最小状态：

- `YRDOY` / `DAS` / day index
- 生育阶段与阶段索引
- 土壤含水
- 根区水量
- 土壤氮
- 冠层/LAI/生物量
- 水分胁迫 / 氮胁迫
- 当天气象

第一版不必一次暴露全部内部数组；只需先对齐当前 Python `CropState` 合同。

### 5.3 `set_action`

建议插桩点：

- 同样在 `LAND RATE` 内部完成读取
- 真正的动作落地放在 `MGMTOPS RATE` 分支

第一版建议仅接管两个动作通道：

- `irrigation_mm`
- `nitrogen_kg_ha`

对应落地策略：

1. interactive mode 下跳过自动 `IRRIG(...)`
2. interactive mode 下跳过自动 `Fert_Place(...)`
3. 用 controller 返回值直接构造当天 `IRRAMT`
4. 用 controller 返回值直接构造当天 `FERTDATA`

暂不建议首版接管：

- tillage
- chemical
- harvest
- residue

### 5.4 `resume_step`

建议做法：

- 完成动作注入后，不额外改 `SOIL/SPAM/PLANT` 主逻辑
- 直接让原生 `RATE -> INTEGR -> OUTPUT` 继续跑完当天

这一步的核心思想是：

- patch 控制边界
- 不 patch 作物数值核心

### 5.5 `step_result`

建议插桩点：

- `CSM_Main/CSM.for` 中 `CONTROL % DYNAMIC = OUTPUT` 对应的 `CALL LAND(...)` 返回之后
- 对应约 `527-531` 一带

此时当天已完整推进，应执行：

1. 导出 `next_state`
2. 导出当天 reward 或日级 reward 组成项
3. 判断 `done`
4. 写出 `step_response`
5. 阻塞等待下一步 action

### 5.6 `finalize`

建议插桩点：

- `DAY_LOOP` 结束后、`SEASEND` 最终收尾阶段

应导出：

- yield
- biomass
- total irrigation
- total nitrogen
- cumulative reward
- 必要的环境指标

这与当前 Python 侧 `final_outcome.json` 合同一致。

## 6. 这轮审计后的工程判断

### 6.1 不建议的路线

本轮审计后，不建议第一版去做：

- 直接在作物模型文件里逐个加 agent 钩子
- 直接把 Python 文件协议写进 `IRRIG.for` / `Fert_Place.for`
- 一开始就做多动作、多作物、多管理通道全覆盖
- 为了交互而改动 vanilla runtime

### 6.2 建议的最小 patched runtime 结构

建议把 Fortran 改造限制在三个层次：

1. `CSM.for`
   - 增加日级 blocking 控制点
2. `LAND.for`
   - 增加状态导出与 interactive gate
3. `MgmtOps.for`
   - 增加 irrigation / nitrogen 两通道的动作注入

这样可以把第一版“会动”的 patched runtime 收敛为：

- 不碰 crop-specific 生长方程
- 不碰 parser / runner 主契约
- 只新增 interactive 控制薄层

## 7. 与当前 Python 文件协议的对应关系

当前仓库已存在文件协议骨架：

- `transdssat/dssat/interactive.py`
- `transdssat/dssat/interactive_controller.py`

本轮结论是：

- 这套协议不需要重设计
- 下一步应该替换 controller 内核，而不是替换 Python API

也就是把当前：

- `season_replay_wrapper_external_controller`

替换成：

- `patched_dssat_daily_loop_controller`

但继续保留：

- `session_manifest.json`
- `session_ready.json`
- `step_request_XXXX.json`
- `step_response_XXXX.json`
- `close_request.json`
- `final_outcome.json`

## 8. 下一步最小实现顺序

下一步建议严格按下面顺序推进：

1. 在 copied patched runtime 中新增一个 interactive mode flag，与 vanilla 默认行为完全隔离。
2. 在 `CSM.for` + `LAND.for` 打通 `session_ready -> wait_action -> single_day_resume -> step_response` 闭环。
3. 在 `MgmtOps.for` 只接入 irrigation / nitrogen 两通道动作注入，并先用单作物单情景做 parity + step smoke。

## 9. 当前结论

本轮已经把“patched runtime 到底该改哪里”从泛泛讨论收敛成了具体文件级判断：

- 日循环边界：`CSM_Main/CSM.for`
- 状态导出边界：`CSM_Main/LAND.for`
- 动作注入边界：`Management/MgmtOps.for`
- 自动管理旁路对象：`Management/IRRIG.for`、`Management/Fert_Place.for`

因此，下一个 wakeup 不需要再重复做源码摸排，而应直接开始设计：

- interactive mode flag
- `CSM/LAND/MGMTOPS` 的最小补丁草案
