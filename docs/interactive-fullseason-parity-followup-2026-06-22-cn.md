# 2026-06-22 全季 parity 续查记录

## 范围

本记录补充两类信息：

1. 为什么 `native final step` 方案被明确拒绝为当前主线。
2. 在第二个 maize 场景上，full-season parity harness 新暴露出的“比较口径”问题，而不是新的农艺数值漂移。

## 1. 被拒绝的 `native final step` 分支

远端重建并复跑 `native final step` 试验后，结论已经固定：

- 该分支虽然仍可在结果字段上与 vanilla 对齐
- 但会让 copied patched runtime 在季末过早暴露 `done=true`
- 这会打断 DSSAT 季节输出文件的完整 flush

代表性后果：

- `PlantGro.OUT` 被截断
- `SoilWat.OUT` 被截断
- `SoilNi.OUT` 被截断
- `Summary.OUT` 被截断
- `Evaluate.OUT` 被截断

因此当前主线必须保持：

- 自然 season-end `final_outcome.json`
- Python transport 对缺失终端 `step_response_XXXX.json` 的恢复逻辑
- 不接受“为了原生终端 step 响应而提前破坏季节输出完整性”的 Fortran 方案

## 2. 第二个 maize 场景的远端复核

### 2.1 运行信息

- artifact:
  - `/fs/fast/u2021201693/lym/TransDSSAT/artifacts/interactive_fullseason_parity_20260622_maize_idx1_20260622175240/interactive_fullseason_parity_report.json`
- scenario:
  - `dssat_official-maize-rand00001-wy2021-dry-irr411-n426-balanced-profit-quzhou_fertile_silt-sw187-sn150-pd+5`

### 2.2 结果摘要

该场景不是新的 agronomic mismatch：

- `interactive_outcome` 与 `vanilla_outcome` 的产量、生物量、总灌溉、总施氮、终态水分、终态土壤氮全部一致
- `interactive_trace.termination.mode = "normal"`
- `transition_count = 26`

但本次报告仍是：

- `status = failed`
- `all_outcome_fields_match = true`
- `all_semantic_files_match = false`

### 2.3 根因定位

根因不是 patched runtime 数值漂移，而是 parity harness 当前把 `vanilla` 侧的多 treatment 输出整文件拿来对比了。

表现为：

- `Summary.OUT`
  - interactive 侧 `left_row_count = 1`
  - vanilla 侧 `right_row_count = 6`
- `Evaluate.OUT`
  - interactive 侧 `left_row_count = 1`
  - vanilla 侧 `right_row_count = 6`
- `PlantGro.OUT`
  - interactive 侧 `left_row_count = 149`
  - vanilla 侧 `right_row_count = 776`
- `SoilWat.OUT`
  - interactive 侧 `left_row_count = 153`
  - vanilla 侧 `right_row_count = 788`
- `SoilNi.OUT`
  - interactive 侧 `left_row_count = 153`
  - vanilla 侧 `right_row_count = 788`

这说明当前比较把“active treatment parity”与“whole experiment file parity”混在了一起：

- interactive path 实际只执行当前活动 treatment
- vanilla replay path 在该场景上保留了同 experiment 内的额外 treatment 输出

因此这个失败应归类为：

- comparison-scope mismatch
- protocol / evaluation-harness issue

而不是：

- patched-vs-vanilla agronomic mismatch

## 3. 终止握手观察

这个场景还暴露了一个次级现象：

- `step_response_0025.json` 已经 `done=true` 且带 `final_outcome`
- 但 controller / runtime 仍会在季末多停留一段时间
- parity harness 需要等 transport 的 terminal finalize 路径收尾后才产出最终 report

这说明当前 transport 主线虽然可完成收尾，但季末退出仍不是最紧凑的实现。

## 4. rice 路径边界

本轮还快速试探了 `--crop rice` 的 parity harness。

结果不是 DSSAT parity 失败，而是脚本边界问题：

- `scripts/run_interactive_fullseason_parity.py` 当前直接调用 `build_quzhou_scenarios(...)`
- 该路径对 `rice` 触发 `KeyError: 'rice'`

因此当前 harness 仍应视为：

- first-pass maize parity harness

而不是通用 crop-agnostic harness。

## 5. 下一步

下一步应优先修正 parity harness 的比较口径，而不是继续追逐新的 Fortran patch：

1. 在 `compare_output_file(...)` 或 parity harness 上增加“只比较活动 run/treatment”的过滤路径。
2. 重新复跑本次 `maize_idx1` 场景，确认失败是否收敛回已知非语义字段。
3. 如果需要支持 rice，再把场景构建入口从 `build_quzhou_scenarios(...)` 抽成 crop-agnostic 入口。
