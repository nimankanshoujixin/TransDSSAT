# 实际水肥序列 Rice Interactive Parity 结果报告（2026-06-23）

## 目标

验证 `wuhu_rice_calibrated-tr11` 真实测试子集上的实测水肥序列，能否在 `interactive patched DSSAT` 路径中被逐日无语义损失地重建，并且在同一观测管理输入下与 `vanilla DSSAT` 保持语义等价。

## 结论

验证通过。

- 远端正式报告：
  - [`/fs/fast/u2021201693/lym/TransDSSAT/artifacts/interactive_real_subset_observed_management_parity_wuhu_tr11_20260623_024449/interactive_real_subset_observed_management_parity_report.json`](/fs/fast/u2021201693/lym/TransDSSAT/artifacts/interactive_real_subset_observed_management_parity_wuhu_tr11_20260623_024449/interactive_real_subset_observed_management_parity_report.json)
- 关键结果：
  - `status = ok`
  - `source_policy_matches_reconstructed_interactive_policy = true`
  - `all_semantic_files_match = true`
  - `all_outcome_fields_match = true`
  - `transition_count = 93`

## 被验证的源实测管理序列

- day 0 / `2021-07-04`: irrigation `30.0 mm`, nitrogen `47.2 kg/ha`
- day 5 / `2021-07-09`: nitrogen `35.9 kg/ha`
- day 42 / `2021-08-15`: irrigation `35.0 mm`
- day 50 / `2021-08-23`: nitrogen `35.9 kg/ha`

报告中的 `reconstructed_interactive_policy` 与上述 4 个事件逐项一致，说明 interactive 协议层没有再把实测动作裁成全零。

## 结果摘要

`interactive patched DSSAT` 与 `vanilla DSSAT` 在该同一输入下的最终结果一致：

- `yield_kg_ha = 1850.0`
- `biomass_kg_ha = 9556.0`
- `total_irrigation_mm = 65.0`
- `total_nitrogen_kg_ha = 173.0`

保留的 exact-file 差异仍是已知的非语义字段，因此 `all_files_match = false` 不阻断此次准入。

## 本轮准入含义

1. Rice `real_subset` 的 observed-management replay 现在已同时满足：
   - 动作序列重建一致
   - patched interactive 与 vanilla 的 season-level 语义输出一致
2. 当前主线默认 step-wise 接口已经移除 TransDSSAT 自己的阶段/湿土/最小间隔硬掩码，只保留数值与预算合法性。
3. 这一任务已达到当前完成条件；后续应等待新的 `Bootstrap` 任务，而不是继续扩展无关范围。
