# Rice Real-Subset Replay Results (2026-06-17)

## 目的

这份文档把当前两条已验证的水稻真实数据 replay 结果沉淀为长期可引用记录，用作后续两类工作的共同锚点：

1. 稳定真实测试子集 `01 / 02`
2. 在原始管理可重放的前提下，仅替换灌溉 / 施肥决策

## 当前已验证 replay 目标

### 1. `mx475_migrated` treatment `1`

- 子集 ID: `mx475_migrated`
- treatment: `1`
- 远端输出目录:
  `/fs/fast/u2021201693/lym/TransDSSAT/artifacts/real_subset_replay_mx475_singletr_fullrerun/mx475_migrated_tr01`
- replay 报告:
  `real_subset_replay_report.json`
- 运行合同:
  - 单 treatment `DSSBatch.v48`
  - batch 模式 `B DSSBatch.v48`
  - clone-local short-profile `DSSATPRO.L48`
  - root-level `RICER048.CUL` / `RICER048.SPE` 镜像
  - root-level `CO2048.WDA`、`FERCH048.SDA`、`RESCH048.SDA`、`SOMFR048.SDA`、`SOMFX048.SDA`、`TILOP048.SDA` 镜像

结果：

- observed yield: `4815 kg/ha`
- simulated yield: `5124 kg/ha`
- yield gap: `309 kg/ha`
- relative gap: `0.064174`
- observed anthesis: `21256`
- simulated anthesis row token: `21253 20`
- observed maturity: `21286`
- simulated maturity row token: `21285 20`

解释：

- 这条结果已经是原始管理下的真实单 treatment native DSSAT replay。
- 当前剩余问题不再是“能不能跑通”，而是后续要把日期 token 解析从固定宽度字符串进一步规范化，便于统一报表。

### 2. `wuhu_rice_calibrated` treatment `11`

- 子集 ID: `wuhu_rice_calibrated`
- treatment: `11`
- 远端输出目录:
  `/fs/fast/u2021201693/lym/TransDSSAT/artifacts/real_subset_replay_ricecompat_whr006remap_singletr_final/wuhu_rice_calibrated_tr11`
- replay 报告:
  `real_subset_replay_report.json`
- 运行合同:
  - 单 treatment `DSSBatch.v48`
  - batch 模式 `B DSSBatch.v48`
  - clone-local short-profile `DSSATPRO.L48`
  - soil / weather / genotype / StandardData root-level 镜像

结果：

- observed yield: `6365 kg/ha`
- simulated yield: `6222 kg/ha`
- yield gap: `-143 kg/ha`
- relative gap: `-0.022467`
- observed anthesis: `253`
- simulated anthesis row token: `21252 20`
- observed maturity: `309`
- simulated maturity row token: `21319 20`

关键兼容性说明：

- 这条结果目前仍是 bridge result，不应误写成“完全原生无补丁复现”。
- 当前可运行路径依赖 replay clone 内的兼容性桥接，而不是修改源数据资产：
  - 复用已被当前 DSSAT 路径接受的 cultivar code identity
  - 将 remapped calibrated row 的 `EXPNO` 从 `1,12` 规范化为 `.`
- 该桥接只应用在 replay clone 内，目的是验证“结果是否接近校准结果”，不是替代长期正式数据链。

## 当前判断

- 两个 first-required rice replay target 都已经具备真实单 treatment replay 结果：
  - `01-tr1`
  - `02-tr11`
- 因此下一阶段不应该继续停留在“能否跑通”层面，而应转入：
  - 把 `01 / 02` 固化为 stable real-data test subsets
  - 在这两个锚点上做“只替换灌溉 / 施肥决策”的受控实验

## 已知技术债

- `Summary.OUT` 里物候日期字段当前仍按 fixed-width token 直接读取，出现了 `21253 20` 这类未完全归一化的 token。
- `wuhu_rice_calibrated tr11` 还没有证明“不依赖 replay-only accepted-code remap 也能在当前 runtime 上得到相近结果”。
- 因此：
  - `mx475_migrated tr1` 可视为稳定 original-management replay anchor
  - `wuhu_rice_calibrated tr11` 目前应视为“可比较结果的 bridge anchor”

## 下一步

1. 把 `mx475_migrated tr1` 和 `wuhu_rice_calibrated tr11` 纳入正式 stable real-data subset 入口。
2. 为 replay case 增加“reference original-management policy + candidate water/nitrogen policy”的组合接口。
3. 做第一版 irrigation-only / nitrogen-only management replacement wiring。
## 2026-06-17 Addendum

- replay 报告中的物候字段现已双轨保留：
  - 原始 token
  - 规范化后的 `yyddd/year/doy/iso_date`
- 官方 DSSAT 解析链也已同步修复：
  - `DSSATOutputParser._summary_phenology(...)` 现在会恢复类似 `21253 20` 的 fixed-width 脏 token
  - 后续评估链路不再因为物候日期列带噪声而静默丢失 `adat/mdat`
