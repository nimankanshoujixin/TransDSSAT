# DSSAT Vanilla / Patched Parity Baseline（2026-06-21）

## 1. 目的

本文件把已经完成的 `vanilla vs patched` official DSSAT 对照结果冻结成正式基线。

这个基线的用途只有一个：

- 在任何交互式 DSSAT 改造开始之前，证明复制出的 `patched` runtime 还没有破坏原始 official DSSAT 的非交互 replay 语义

## 2. 基线对象

- vanilla runtime:
  - `/fs/fast/u2021201693/lym/dssat-runtime`
- patched runtime:
  - `/fs/fast/u2021201693/lym/dssat-runtime-patched`
- 比对入口:
  - `python scripts/compare_dssat_runtimes.py --vanilla-runtime-root ... --patched-runtime-root ... --output-root ...`
- 正式报告:
  - `/fs/fast/u2021201693/lym/TransDSSAT/artifacts/dssat_runtime_compare_full_20260621_221000/dssat_runtime_comparison_report.json`

## 3. 已完成验证

### 3.1 smoke case

- case:
  - `wuhu_rice_calibrated:11`
- 结果:
  - `case_count = 1`
  - `matched_case_count = 1`
  - `all_cases_match = true`

### 3.2 full real-subset parity run

- 运行时间戳:
  - `2026-06-21 22:10 Asia/Shanghai` 启动
- artifact root:
  - `/fs/fast/u2021201693/lym/TransDSSAT/artifacts/dssat_runtime_compare_full_20260621_221000`
- 汇总结果:
  - `case_count = 20`
  - `matched_case_count = 20`
  - `all_cases_match = true`
  - `failing_cases = []`

## 4. 比对内容

当前脚本要求 vanilla 与 patched 在相同 real-subset replay 输入下同时匹配：

- replay-level yield
- anthesis
- maturity
- `Summary.OUT`
- `PlantGro.OUT`
- `SoilWat.OUT`
- `SoilNi.OUT`
- `Evaluate.OUT`

因此这个基线不是“只看最终产量差不多”，而是已经覆盖关键季末汇总与逐日主输出。

## 5. 当前结论

截至 `2026-06-21`，复制出的 `patched` runtime 可以被视为：

- 与 `vanilla` 在默认 real-subset bundle 上 parity-clean
- 可作为后续交互式 DSSAT 改造的起点

但这个结论只适用于：

- 当前尚未插桩 daily interactive loop 的 patched 副本
- 非交互 replay 条件

它不代表：

- 交互式改造已经正确
- patched runtime 已经可以直接用于 step-wise PPO 训练

## 6. 后续使用规则

从现在开始，任何 patched runtime 改动都必须遵守：

1. 不改动 vanilla runtime
2. 在 copied patched runtime 上实施交互式插桩
3. 如果改动影响非交互 replay 输出，必须先回到 parity-clean 状态
4. 只有保持这个 parity gate 通过，patched runtime 才有资格进入下一层交互验证

## 7. 与当前任务的关系

这份基线完成了当前任务中的一项硬前置：

- “先保留 vanilla / patched 双 runtime，并用真实数据 replay 做第一道回归门”

下一步不应再重复做 proxy 诊断，而应继续推进：

- 真正的 patched daily interaction loop
- 在同一 transport/controller 合同下替换掉当前 replay-bridge controller

