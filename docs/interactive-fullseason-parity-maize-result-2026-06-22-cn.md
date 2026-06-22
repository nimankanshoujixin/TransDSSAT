# Interactive Patched DSSAT 全季 Parity 结果（Maize，2026-06-22）

## 结论

`interactive patched DSSAT` 与 `vanilla DSSAT` 在 maize 全季 parity gate 上已达到当前主线所需的语义一致性：

- remote official-DSSAT 路径执行
- 相同 rendered scenario 输入
- 相同重建动作序列
- `Summary.OUT` / `PlantGro.OUT` / `SoilWat.OUT` / `SoilNi.OUT` / `Evaluate.OUT` 的 `semantic_match = true`
- outcome 字段一致
- `interactive_trace.termination.mode = "normal"`

当前可接受的剩余差异仅为已知非语义字段，不再构成 parity blocker。

## 关键 artifact

1. 已接受的主线 baseline maize parity：
   - `/fs/fast/u2021201693/lym/TransDSSAT/artifacts/interactive_fullseason_parity_20260622_maize_transportrecover_restored2/interactive_fullseason_parity_report.json`
   - 结果：`status = ok`
   - `all_semantic_files_match = true`
   - `all_outcome_fields_match = true`

2. treatment-aligned 第二个 maize 场景复跑：
   - `/fs/fast/u2021201693/lym/TransDSSAT/artifacts/interactive_fullseason_parity_20260622_maize_idx1_treatmentfilter_20260622_205913/interactive_fullseason_parity_report.json`
   - 结果：`status = ok`
   - `active_output_selector = {"selector_kind": "treatment", "selector_value": 1}`
   - `all_semantic_files_match = true`
   - `all_outcome_fields_match = true`
   - `transition_count = 26`
   - `interactive_trace.termination.mode = "normal"`

## 本轮修复点

为消除第二个 maize 场景中 `interactive` 单 treatment 输出与 `vanilla` 多 treatment / 多 run 输出的比较口径偏差，比较层新增了两级过滤：

1. active output selector
   - 从 `Summary.OUT` / `Evaluate.OUT` / `PlantGro.OUT` 推断 active `treatment` 或 `run`

2. run-section filtering
   - 对 `PlantGro.OUT` / `SoilWat.OUT` / `SoilNi.OUT` 这类可能不带 treatment 列、但带 `*RUN` 分段的文件，按 active run 重新解析后再比较

对应代码位于：

- [`/G:/TransDSSAT/transdssat/dssat/validation.py`](/G:/TransDSSAT/transdssat/dssat/validation.py)
- [`/G:/TransDSSAT/scripts/run_interactive_fullseason_parity.py`](/G:/TransDSSAT/scripts/run_interactive_fullseason_parity.py)
- [`/G:/TransDSSAT/tests/test_dssat_validation.py`](/G:/TransDSSAT/tests/test_dssat_validation.py)

## 已知非语义差异

在当前两份 maize parity artifact 中，仍允许以下 exact-file 级别差异：

- `Summary.OUT`
  - `CH4EM`
  - `OPAM`
  - `OPTAM`

- `SoilWat.OUT`
  - `DTWTM`

这些字段在当前比较层中已被归类为 non-semantic runtime-format artifacts，不影响 agronomic parity 判定。

## 后续建议

当前 maize parity gate 已完成。若后续继续推进，应作为新任务处理：

1. 将 `scripts/run_interactive_fullseason_parity.py` 从当前 maize-only 路径扩展到 rice 或更通用的 crop routing
2. 若未来要追求 exact-file parity，再单独处理 `Summary.OUT` / `SoilWat.OUT` 的格式字段差异
