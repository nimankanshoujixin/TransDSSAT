# Official DSSAT 交互主线路径验证结果（2026-06-22）

## 结论

- 已将 overlay 中验证通过的 Python 辅助逻辑正式同步到远端仓库主路径：
  - `transdssat/dssat/interactive_bridge.py`
  - `scripts/validate_interactive_dssat_action_effect.py`
  - `tests/test_validate_interactive_dssat_action_effect.py`
- 标准远端 repo 路径已完成一次不依赖 `/tmp` Python overlay 的配对验证，结果为 `status = ok`。
- 当前官方 DSSAT 交互补丁链路已经同时满足两条回归门：
  - 动作尺度与请求一致
  - 协议层 `final_outcome` 与归档 DSSAT 产物一致，且为 parser-backed

## 主线验证

- 远端单测：
  - `conda run --no-capture-output -n transdssat python -m unittest tests.test_validate_interactive_dssat_action_effect -v`
- 远端标准 repo 路径配对验证产物：
  - 产物目录：`/fs/fast/u2021201693/lym/TransDSSAT/artifacts/interactive_action_effect_validation_repo_mainline_20260622_142418`
  - 验证报告：`/fs/fast/u2021201693/lym/TransDSSAT/artifacts/interactive_action_effect_validation_repo_mainline_20260622_142418/action_effect_validation.json`

## 关键结果

- `status = ok`
- `irrigation_scale_matches_request = true`
- `nitrogen_scale_matches_request = true`
- `baseline_protocol_matches_archived = true`
- `action_protocol_matches_archived = true`
- `baseline_protocol_is_parser_backed = true`
- `action_protocol_is_parser_backed = true`
- 本次标准 repo 路径验证的动作增量为：
  - `total_irrigation_mm = 12.0`
  - `total_nitrogen_kg_ha = 18.0`

## 对 warning-backed 终止的判定

- 当前 smoke 场景仍带有 `warning_present` 终止标记，且短季节产物中的 `yield_kg_ha` / `biomass_kg_ha` 为 `0.0`。
- 这一现象不再阻断当前回归门，原因是：
  - baseline 与 action 在同一 warning 条件下对比
  - 本轮验证目标是交互协议、动作注入尺度、以及协议结果与 DSSAT 归档产物的一致性
  - 这三项在标准 repo 路径下已经全部通过
- 因此当前 warning-backed smoke 产物：
  - 可作为交互补丁主线回归门
  - 不应作为最终训练质量或农学真实性结论

## 后续含义

- 本轮“停用 proxy 并切换到 official-DSSAT-only 主线”的即时任务可以收束。
- 后续如进入新任务：
  - 若是继续做训练准入，应基于当前 official-only 主线继续扩展
  - 若涉及 GPU 训练，必须先在远端执行 `nvidia-smi` 检查空闲 GPU
