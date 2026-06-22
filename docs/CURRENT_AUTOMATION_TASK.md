# Current Automation Task

## Task Description
Completed

Current assignment: stop the deprecated proxy route and switch TransDSSAT to an official-DSSAT-only training and evaluation path, explicitly following the gym-DSSAT style of turning DSSAT into an interactive RL environment.

The immediate task is not to launch a new training run. The immediate task is to audit and document:

1. what in the current codebase still depends on proxy-only assumptions
2. what is already available for official DSSAT training/evaluation
3. what exact gaps remain before step-wise PPO can be trained and evaluated only with official DSSAT
4. how to implement the missing step-wise official DSSAT interaction layer by referencing gym-DSSAT
5. which `1-3` minimal engineering interventions are required to complete that switch
6. how to preserve a vanilla DSSAT runtime and validate the patched interactive DSSAT runtime against real-data runs before training

## Current Status
Completed

## Progress This Wakeup

1. Accepted the user decision that proxy is no longer an admissible training or evaluation route.
2. Stopped treating the previous proxy-side collapse diagnosis as a valid forward path.
3. Began replacing the current automation contract with an official-DSSAT-only policy.
4. Removed the temporary proxy-diagnostic artifacts introduced in the previous wakeup:
   - deleted `/G:/TransDSSAT/scripts/analyze_baseline_collapse.py`
   - deleted `/G:/TransDSSAT/docs/baseline-root-cause-analysis-2026-06-21-cn.md`
5. Confirmed the user decision to follow route `1`: directly learn from gym-DSSAT rather than keeping any segmented proxy fallback plan.
6. Confirmed the validation rule for future DSSAT modification:
   - keep the original non-patched DSSAT runtime
   - create and modify a separate patched DSSAT copy
   - use real-data runs as the first correctness check by comparing vanilla vs patched outputs under identical inputs
7. Tightened the mainline code path so the training entrypoints no longer accept proxy engines:
   - `scripts/train_stepwise_ppo.py`
   - `scripts/train_rl_transformer.py`
8. Switched real-subset step-wise scenario materialization to `engine_name="dssat_official"` in:
   - `transdssat/real_subset_stepwise_eval.py`
9. Added dual-runtime configuration support for future vanilla-vs-patched DSSAT execution:
   - `transdssat/dssat/config.py`
   - `transdssat/dssat/runner.py`
   - `scripts/run_stepwise_ppo_remote.sh`
10. Verified the first batch of official-only code-path changes with:
   - `python -m compileall scripts\train_stepwise_ppo.py scripts\train_rl_transformer.py transdssat\dssat\config.py transdssat\dssat\runner.py transdssat\real_subset_stepwise_eval.py`
11. Tightened the evaluation helper scripts and scenario-pool defaults to official DSSAT:
   - `scripts/evaluate_season_policy.py`
   - `scripts/evaluate_policy_report.py`
   - `scripts/run_unified_evaluation.py`
   - `transdssat/testset.py`
12. Reduced the remaining `dssat_proxy` footprint to a small set of explicit legacy/debug paths plus the still-unreplaced proxy-backed step-wise semantics layer.
13. Added a runnable real-data vanilla-vs-patched DSSAT replay comparator:
   - `scripts/compare_dssat_runtimes.py`
   - `transdssat/dssat/validation.py`
14. Verified the new runtime comparator entrypoint with:
   - `python -m compileall scripts\compare_dssat_runtimes.py transdssat\dssat\validation.py`
   - `python scripts\compare_dssat_runtimes.py --help`
15. Created the remote copied patched runtime:
   - `/fs/fast/u2021201693/lym/dssat-runtime-patched`
16. Completed one remote smoke comparison successfully:
   - `wuhu_rice_calibrated:11`
   - result: `all_cases_match = true`
17. Fixed a replay-entry blocker in `transdssat/real_subset_runner.py`:
   - cultivar-range compatibility mismatches are now recorded as clone warnings instead of aborting real-subset replay immediately
18. Launched the full remote vanilla-vs-patched comparison over the default real-subset bundle:
   - tmux window: `transdssat:compare-full`
   - artifact root: `/fs/fast/u2021201693/lym/TransDSSAT/artifacts/dssat_runtime_compare_full_20260621_221000`
19. Completed the full remote vanilla-vs-patched comparison successfully:
   - report: `/fs/fast/u2021201693/lym/TransDSSAT/artifacts/dssat_runtime_compare_full_20260621_221000/dssat_runtime_comparison_report.json`
   - summary:
     - `case_count = 20`
     - `matched_case_count = 20`
     - `all_cases_match = true`
20. Added an explicit official backend mode entry in `transdssat/environments/stepwise.py`:
   - current supported mode: `season_replay_wrapper`
   - reserved future mode: `interactive_patched`
21. Added fail-fast protection so explicit `interactive_patched` requests do not silently fall back to the wrapper semantics before implementation exists.
22. Added the Python-side interactive official DSSAT session/transport skeleton:
   - `transdssat/dssat/interactive.py`
   - `transdssat/dssat/__init__.py`
23. Upgraded `transdssat/environments/stepwise.py` so `interactive_patched` can now run end-to-end when an `official_interactive_transport` is injected.
24. Verified the new interactive-patched Python path with fake-transport tests:
   - `python -m unittest tests.test_stepwise_env.StepwiseEnvironmentTests.test_official_interactive_backend_uses_injected_transport -v`
   - plus the existing official wrapper guard tests
25. Added the first real transport/control-channel scaffold for patched DSSAT:
   - file-protocol transport in `transdssat/dssat/interactive.py`
   - interactive env/config plumbing in `transdssat/dssat/config.py`
26. Added direct env-driven transport construction:
   - `build_filesystem_interactive_transport_from_env(...)`
27. Verified the protocol/config path with local unit tests:
   - `python -m unittest tests.test_dssat_interactive tests.test_stepwise_env.StepwiseEnvironmentTests.test_official_interactive_backend_uses_injected_transport -v`
   - `python -m compileall transdssat\dssat\config.py transdssat\dssat\interactive.py transdssat\dssat\__init__.py tests\test_dssat_interactive.py`
28. Made the DSSAT interactive session manifest scenario-complete and round-trippable:
   - `transdssat/scenarios.py`
   - `transdssat/dssat/inputs.py`
29. Added an external controller-side official DSSAT bridge for the new file protocol:
   - `transdssat/dssat/interactive_controller.py`
   - `scripts/run_interactive_dssat_controller.py`
30. Verified the new controller loop locally with unit tests:
   - `python -m unittest tests.test_dssat_interactive_controller tests.test_dssat_interactive tests.test_stepwise_env.StepwiseEnvironmentTests.test_official_interactive_backend_uses_injected_transport -v`
   - `python -m compileall transdssat\scenarios.py transdssat\dssat\inputs.py transdssat\dssat\interactive.py transdssat\dssat\interactive_controller.py transdssat\dssat\__init__.py scripts\run_interactive_dssat_controller.py tests\test_dssat_interactive_controller.py`
31. Archived the finished full vanilla-vs-patched runtime comparison as a formal baseline:
   - `docs/dssat-runtime-parity-baseline-2026-06-21-cn.md`
32. Completed the remaining default-entry tightening pass so new scenario/data generation defaults no longer point to proxy:
   - `transdssat/scenarios.py`
   - `scripts/generate_dataset.py`
33. Wrote an explicit quarantine audit for the remaining proxy-only legacy/debug paths:
   - `docs/proxy-footprint-quarantine-2026-06-21-cn.md`
34. Added a regression test that locks `build_quzhou_scenarios(...)` default engine to `dssat_official`:
   - `tests/test_real_data_sources.py`
35. Completed a remote read-only Fortran source audit of the copied DSSAT source tree and narrowed the first true interactive patch surface to:
   - `CSM_Main/CSM.for` for day-boundary blocking control
   - `CSM_Main/LAND.for` for `get_state -> wait_action`
   - `Management/MgmtOps.for` for irrigation / nitrogen action injection
36. Wrote the concrete file-level insertion report:
   - `docs/patched-dssat-fortran-insertion-audit-2026-06-22-cn.md`
37. Converted that insertion audit into a concrete protocol-and-patch contract for the upcoming copied-runtime implementation:
   - `docs/patched-dssat-interactive-protocol-contract-2026-06-22-cn.md`
38. Tightened the Python interactive scaffold to match that contract before any Fortran patching starts:
   - `transdssat/dssat/interactive.py`
   - `transdssat/dssat/interactive_controller.py`
   - `scripts/run_interactive_dssat_controller.py`
   - `tests/test_dssat_interactive.py`
   - `tests/test_dssat_interactive_controller.py`
39. Locked the first explicit runtime-facing metadata contract into the session manifest / ready payload:
   - `protocol_version = "patched-dssat-v1"`
   - action channels limited to `irrigation_mm` and `nitrogen_kg_ha`
   - explicit `interaction` metadata block in `session_manifest.json`
40. Verified the contract alignment locally with:
   - `python -m unittest tests.test_dssat_interactive tests.test_dssat_interactive_controller -v`
   - `python -m compileall transdssat\dssat\interactive.py transdssat\dssat\interactive_controller.py transdssat\dssat\__init__.py scripts\run_interactive_dssat_controller.py tests\test_dssat_interactive.py tests\test_dssat_interactive_controller.py`
41. Upgraded the interactive controller entrypoint from replay-bridge-only to a dual-driver design:
   - `transdssat/dssat/interactive_controller.py`
   - `scripts/run_interactive_dssat_controller.py`
42. Added manifest/runtime contract validation plus a new `patched_runtime_subprocess` driver that can launch a copied DSSAT runtime through the existing role-specific `DSSAT_*_RUN_COMMAND` path while injecting the interactive contract via env vars.
43. Verified the new driver path locally with:
   - `python -m unittest tests.test_dssat_interactive_controller tests.test_dssat_interactive tests.test_stepwise_env.StepwiseEnvironmentTests.test_official_interactive_backend_uses_injected_transport -v`
   - `python -m compileall transdssat\dssat\interactive_controller.py scripts\run_interactive_dssat_controller.py tests\test_dssat_interactive_controller.py`
44. Tightened the subprocess-side launch contract so the future Fortran patch can validate more runtime-boundary metadata without first parsing the whole manifest:
   - `DSSAT_INTERACTIVE_ENGINE_NAME`
   - `DSSAT_INTERACTIVE_RUN_DIR`
   - `DSSAT_INTERACTIVE_CROP_NAME`
   - `DSSAT_INTERACTIVE_DECISION_INTERVAL_DAYS`
   - `DSSAT_INTERACTIVE_STATE_INTERFACE_CONTRACT_JSON`
45. Locked those additional env fields with the patched-runtime subprocess controller test and mirrored them into the protocol contract doc:
   - `tests/test_dssat_interactive_controller.py`
   - `docs/patched-dssat-interactive-protocol-contract-2026-06-22-cn.md`
46. Added a reusable official-DSSAT interactive subprocess smoke entrypoint:
   - `scripts/smoke_interactive_dssat_session.py`
47. Found and fixed the real interactive launch-path bug where the controller was started under `cwd=<run_dir>` but the launch command still assumed a repo-relative script path:
   - `transdssat/dssat/interactive.py` now supports absolute placeholders:
     - `{controller_script}`
     - `{project_root}`
     - `{repo_root}`
   - `scripts/run_interactive_dssat_controller.py` now bootstraps `PROJECT_ROOT` for direct script execution from a DSSAT run dir
   - `tests/test_dssat_interactive.py` now locks the absolute controller-script launch contract
48. Completed the first remote `patched_runtime_subprocess` smoke using a temporary boundary-probe runtime as a stand-in for the future Fortran patch:
   - artifact root: `/fs/fast/u2021201693/lym/TransDSSAT/artifacts/interactive_patched_subprocess_smoke_20260622_030429`
   - smoke report: `/fs/fast/u2021201693/lym/TransDSSAT/artifacts/interactive_patched_subprocess_smoke_20260622_030429/smoke_report.json`
   - verified that the real subprocess boundary received and mirrored the expected `protocol_version`, `engine_name`, `backend_mode`, `runtime_role`, `crop_name`, `decision_interval_days`, `action_channels`, and `state_interface_contract` contract values
49. Added controller-log diagnostics for the first real copied-runtime handshake:
   - `transdssat/dssat/config.py`
   - `transdssat/dssat/interactive.py`
   - `scripts/smoke_interactive_dssat_session.py`
   - `tests/test_dssat_interactive.py`
50. The interactive transport now writes controller stdout/stderr to a per-run log file controlled by `DSSAT_INTERACTIVE_CONTROLLER_LOG_FILENAME` instead of discarding them, and timeout / early-exit failures now include the log path plus a short tail.
51. Verified the startup-diagnostics pass locally with:
   - `python -m unittest tests.test_dssat_interactive tests.test_dssat_interactive_controller -v`
   - `python scripts\smoke_interactive_dssat_session.py --help`
52. Added a reusable boundary-only patched-runtime stand-in at:
   - `scripts/dssat_interactive_boundary_probe.py`
   - it validates env + manifest startup metadata, captures runtime-boundary info, and serves a minimal `session_ready -> step_response -> final_outcome` loop without relying on a temp script outside the repo
53. Extended `transdssat/dssat/interactive_controller.py` so `DSSAT_*_RUN_COMMAND` now supports:
   - `{project_root}`
   - `{repo_root}`
   - this fixes the remaining copied-runtime subprocess issue where repo scripts could not be launched safely from `cwd=<run_dir>`
54. Added a reusable remote smoke wrapper:
   - `scripts/run_interactive_dssat_smoke_remote.sh`
   - purpose: standardize tmux-launched copied-runtime interactive smokes with persistent `run.log` and `smoke_report.json`
55. Verified the reusable boundary-probe path locally with:
   - `python -m unittest tests.test_dssat_interactive_controller tests.test_dssat_interactive -v`
   - `python -m compileall transdssat\dssat\interactive_controller.py scripts\dssat_interactive_boundary_probe.py tests\test_dssat_interactive_controller.py`
   - full subprocess smoke using:
     - `DSSAT_PATCHED_RUN_COMMAND="python {repo_root}/scripts/dssat_interactive_boundary_probe.py --mark-done-after-step"`
     - `DSSAT_PATCHED_INTERACTIVE_LAUNCH_COMMAND="python {controller_script} --driver-mode patched_runtime_subprocess {session_manifest}"`
   - report:
     - `/G:/TransDSSAT/automation_tmp/local_interactive_smoke/smoke_report.json`
56. Replayed the same copied-runtime subprocess smoke through the new remote tmux wrapper path on `10.10.252.11` using a temporary overlay rather than overwriting the dirty remote repo:
   - overlay root: `/tmp/transdssat_remote_smoke_overlay_20260622_050445`
   - tmux window: `transdssat:interactive-smoke`
57. Found and fixed a real wrapper bug in `scripts/run_interactive_dssat_smoke_remote.sh`:
   - bash `${VAR:-default}` assignments were corrupting DSSAT placeholder strings such as `{experiment}` and `{session_manifest}`
   - symptom on remote smoke:
     - `ValueError: Single '}' encountered in format string`
   - fix:
     - switched those command defaults to explicit `if [[ -z ... ]]` assignments
58. Verified the standardized remote wrapper path after that fix:
   - artifact root:
     - `/fs/fast/u2021201693/lym/TransDSSAT/artifacts/interactive_patched_subprocess_smoke_20260622_050445_retry`
   - report:
     - `/fs/fast/u2021201693/lym/TransDSSAT/artifacts/interactive_patched_subprocess_smoke_20260622_050445_retry/smoke_report.json`
   - result:
     - `status = ok`
     - completed `reset -> step -> close`
     - `backend_mode = interactive_patched`
     - `probe_mode = boundary_probe`
59. Added a repo-local Fortran bridge helper so the first copied-runtime patch can stay on simple text payloads instead of handcrafting full JSON inside legacy DSSAT source:
   - `transdssat/dssat/interactive_bridge.py`
   - `scripts/dssat_interactive_protocol_helper.py`
60. Locked the helper contract with new regression coverage:
   - `tests/test_dssat_interactive_bridge.py`
   - local validation:
     - `python -m unittest tests.test_dssat_interactive_bridge tests.test_dssat_interactive tests.test_dssat_interactive_controller -v`
     - `python -m compileall transdssat\dssat\interactive_bridge.py scripts\dssat_interactive_protocol_helper.py tests\test_dssat_interactive_bridge.py`
61. Updated the interactive protocol contract so the next real Fortran patch is explicitly helper-backed:
   - Fortran writes simple `key=value` state/outcome payloads
   - helper translates them into `session_ready.json`, `step_response_XXXX.json`, and `final_outcome.json`
   - helper also translates `step_request_XXXX.json` into a Fortran-friendly action file for `wait_action`
62. Added a repo-local overlay convention for copied-runtime DSSAT Fortran edits:
   - `dssat_patch_overlay/README.md`
63. Added a remote patched-runtime rebuild wrapper that:
   - clones the DSSAT source tree into a temporary patched workspace
   - overlays repo-managed Fortran files by upstream-relative path
   - rebuilds `dscsm048` with `cmake`
   - refreshes `/fs/fast/u2021201693/lym/dssat-runtime-patched/dscsm048`
   - optional report output:
     - `scripts/build_patched_dssat_runtime_remote.sh`
64. Wrote the corresponding workflow note so the next wakeup can go straight from overlay edits to rebuild + smoke:
   - `docs/patched-dssat-remote-build-workflow-2026-06-22-cn.md`
65. Performed a local shell syntax check attempt on the new remote build wrapper:
   - `bash -n scripts/build_patched_dssat_runtime_remote.sh`
   - the Windows host emitted a WSL localhost/NAT warning, but no shell syntax error from the script itself
66. Added a dedicated helper-command env contract for the first real Fortran patch:
   - `DSSAT_INTERACTIVE_HELPER_COMMAND`
   - source: `transdssat/dssat/interactive_controller.py`
   - locked by: `tests/test_dssat_interactive_controller.py`
67. Implemented the first real copied-runtime Fortran overlay stage in:
   - `dssat_patch_overlay/CSM_Main/LAND.for`
68. The current stage-1 runtime behavior is intentionally limited to:
   - helper-backed `session_ready.json` at reset
   - helper-backed `await-action` at the `LAND RATE` boundary
   - helper-backed early-close `final_outcome.json`
   - no real `step_response_XXXX.json` yet
   - no irrigation / nitrogen injection in `MgmtOps.for` yet
69. Upgraded `scripts/build_patched_dssat_runtime_remote.sh` so it can auto-reuse the known working Fortran compiler recorded in the existing v4.8.5 build cache, rather than requiring a manual `FC` export each wakeup.
70. Rebuilt the copied patched runtime successfully with the new stage-1 overlay:
   - refreshed binary: `/fs/fast/u2021201693/lym/dssat-runtime-patched/dscsm048`
71. Completed the first real copied-runtime smoke on patched `dscsm048` itself with `--skip-step`:
   - artifact root:
     - `/fs/fast/u2021201693/lym/TransDSSAT/artifacts/interactive_session_ready_smoke_20260622_retry`
   - report:
     - `/fs/fast/u2021201693/lym/TransDSSAT/artifacts/interactive_session_ready_smoke_20260622_retry/smoke_report.json`
   - result:
   - `status = ok`
   - real patched runtime produced `session_ready`
   - `reset_info.backend_mode = interactive_patched`
   - `bridge_stage = reset`
   - early-close helper path produced `final_outcome`
72. Extended the copied-runtime `LAND.for` overlay from `session_ready + await-action` to the first real decision-window `step_response_XXXX.json` loop:
   - action wait now happens once per decision window rather than once per `RATE` call
   - the patched runtime advances for the requested interval and then emits one helper-backed `step_response`
   - current limits remain:
     - no `MgmtOps.for` action injection yet
     - placeholder `reward = 0.0`
     - placeholder early-close `final_outcome`
73. Rebuilt the copied patched runtime with the new step-response overlay using a temporary remote overlay:
   - overlay root: `/tmp/transdssat_overlay_stepresponse_20260622_090414`
   - build report:
     - `/fs/fast/u2021201693/lym/TransDSSAT/artifacts/patched_runtime_build_stepresponse_20260622_090414/build_report.json`
74. Rejected one intermediate smoke artifact because it accidentally launched the controller default `replay_bridge` path instead of the real patched runtime:
   - diagnostic-only artifact:
     - `/fs/fast/u2021201693/lym/TransDSSAT/artifacts/interactive_step_response_smoke_20260622_090414/smoke_report.json`
   - rejection reason:
     - `reset_info.backend_mode = season_replay_wrapper_external_controller`
75. Completed the first real copied-runtime patched subprocess smoke that exercised `session_ready -> step_response -> final_outcome` on patched `dscsm048` itself:
   - artifact root:
     - `/fs/fast/u2021201693/lym/TransDSSAT/artifacts/interactive_step_response_patched_smoke_20260622_090414`
   - report:
     - `/fs/fast/u2021201693/lym/TransDSSAT/artifacts/interactive_step_response_patched_smoke_20260622_090414/smoke_report.json`
   - result:
     - `status = ok`
     - `reset_info.backend_mode = interactive_patched`
     - `step.info.bridge_stage = step_response`
     - `step.info.days_executed = 5`
     - `step.next_state.day_index = 5`
76. Implemented the first real `MgmtOps.for` interactive action-injection overlay in:
   - `dssat_patch_overlay/Management/MgmtOps.for`
77. The new `MgmtOps.for` overlay behavior is now:
   - keep vanilla initialization through `Fert_Place`
   - skip daily automatic fertilizer / irrigation scheduling in interactive mode
   - inject `irrigation_mm` directly through `IRRAMT`
   - inject `nitrogen_kg_ha` through the native `FERTLAYERS` + `FERTAPPLY` path as a surface urea-style N application
   - preserve the existing non-interactive code path when `DSSAT_INTERACTIVE_MODE` is not enabled
78. Rebuilt and smoke-validated the copied patched runtime with the new `MgmtOps.for` overlay:
   - build report:
     - `/fs/fast/u2021201693/lym/TransDSSAT/artifacts/patched_runtime_build_mgmtops_20260622_094717/build_report.json`
   - smoke artifact root:
     - `/fs/fast/u2021201693/lym/TransDSSAT/artifacts/interactive_mgmtops_injection_smoke_20260622_094717`
   - smoke report:
     - `/fs/fast/u2021201693/lym/TransDSSAT/artifacts/interactive_mgmtops_injection_smoke_20260622_094717/smoke_report.json`
   - observed result:
     - `status = ok`
     - `reset_info.backend_mode = interactive_patched`
     - `step.next_state.day_index = 5`
     - `step.next_state.root_zone_water_mm = 25.1393`
     - `step.next_state.soil_nitrogen_kg_ha = 37.6901`
     - controller-log summary now shows a non-zero `TIRR` line on the action-applied run, while `final_outcome` remains placeholder-only
79. Replaced the helper-side placeholder reward/final-outcome logic with a parser-backed interactive progress tracker:
   - `transdssat/dssat/interactive_bridge.py`
80. The helper now:
   - records `last_state`, cumulative reward, action totals, and operation count in protocol-local `interactive_progress.json`
   - reconstructs step reward from the real `step_request_XXXX.json` action plus `step_reward(...)`
   - derives terminal `final_outcome` from real DSSAT outputs via `DSSATOutputParser` plus `reward_from_outcome(...)`
   - reuses the cached terminal outcome when `write-final-outcome` is called after `close_request`
81. Locked the helper-side real reward/outcome path with local regression coverage:
   - `tests/test_dssat_interactive_bridge.py`
82. Verified the new helper behavior locally with:
   - `python -m unittest tests.test_dssat_interactive_bridge tests.test_dssat_interactive_controller tests.test_dssat_interactive -v`
   - `python -m compileall transdssat\dssat\interactive_bridge.py tests\test_dssat_interactive_bridge.py`
83. Added artifact-isolated action-effect validation support for patched interactive smokes:
   - `scripts/smoke_interactive_dssat_session.py` now records `requested_action`, `decision_interval_days`, and optional `archived_run_dir`
   - `scripts/validate_interactive_dssat_action_effect.py` compares baseline-vs-action archived DSSAT outputs directly
   - `scripts/run_interactive_dssat_action_validation_remote.sh` runs paired remote smokes plus the validator
   - `tests/test_validate_interactive_dssat_action_effect.py` locks the new validator contract
84. Verified the new tooling locally with:
   - `python -m unittest tests.test_validate_interactive_dssat_action_effect tests.test_dssat_interactive_bridge tests.test_dssat_interactive_controller tests.test_dssat_interactive -v`
   - `python -m compileall scripts\smoke_interactive_dssat_session.py scripts\validate_interactive_dssat_action_effect.py scripts\run_interactive_dssat_action_validation_remote.sh tests\test_validate_interactive_dssat_action_effect.py`
85. Completed the first remote artifact-level paired validation on patched `dscsm048` itself:
   - artifact root:
     - `/fs/fast/u2021201693/lym/TransDSSAT/artifacts/interactive_action_effect_validation_20260622_131500`
   - result:
     - `status = ok`
     - action-effect checks all passed against archived DSSAT artifacts
86. The same paired validation exposed the next main-line bug:
   - requested action was only `irrigation_mm=12` and `nitrogen_kg_ha=18`
   - but archived DSSAT artifact deltas landed at `total_irrigation_mm=60` and `total_nitrogen_kg_ha=90`
   - this indicates the current patched `MgmtOps.for` path is likely applying one step request repeatedly across the 5-day decision window instead of once per PPO step
87. Also confirmed a secondary boundary:
   - smoke-report `final_outcome` returned through `close_session()` is still placeholder-like zero
   - archived run snapshots already carry enough real DSSAT outputs for parser-side validation, so protocol-side terminal-outcome alignment remains unfinished
88. Implemented the first corrective pass for the `5x` action-scale bug:
   - `dssat_patch_overlay/Management/MgmtOps.for` now clears interactive `TDINT_IRR` and `TDINT_N` immediately after the RATE-stage application, so a step request is consumed once instead of remaining active for every day in the decision window
89. Tightened the artifact-level action validator so scale amplification is now a hard failure rather than an informational delta only:
   - `scripts/validate_interactive_dssat_action_effect.py`
   - `tests/test_validate_interactive_dssat_action_effect.py`
90. Local CPU-safe validation passed for that corrective pass:
   - `python -m unittest tests.test_validate_interactive_dssat_action_effect tests.test_dssat_interactive_bridge tests.test_dssat_interactive_controller -v`
   - `python -m compileall scripts\validate_interactive_dssat_action_effect.py tests\test_validate_interactive_dssat_action_effect.py transdssat\dssat\interactive_bridge.py`
91. Remote copied-runtime rebuild succeeded with the updated `MgmtOps.for` overlay:
   - refreshed binary:
     - `/fs/fast/u2021201693/lym/dssat-runtime-patched/dscsm048`
   - build artifact root:
     - `/fs/fast/u2021201693/lym/TransDSSAT/artifacts/interactive_action_effect_validation_fix_20260622_20260622_114650`
92. The remote paired-validation rerun did not yet produce an admissible action-scale verdict because the launcher path itself exposed new blockers:
   - one baseline smoke artifact in `/fs/fast/u2021201693/lym/TransDSSAT/artifacts/interactive_action_effect_validation_fix_retry_20260622_20260622_115246` still landed in `backend_mode = season_replay_wrapper_external_controller`, so it is not proof for the patched runtime
   - the action-applied smoke in that same artifact root failed before `step_response_0000.json` appeared, with controller-log tail ending in `json.decoder.JSONDecodeError: Expecting value`
93. Current interpretation:
   - the main-line `MgmtOps.for` repeated-application logic is fixed in source
   - the stricter validator is ready to reject any future `12/18 -> 60/90` amplification
   - but the next blocking issue has shifted to the remote smoke/driver route, which must be forced onto true `interactive_patched` execution and debugged through the action-applied controller failure before the new Fortran semantics can be proven
94. Fixed the remote launcher default so patched-runtime smokes no longer rely on the controller's `auto` driver selection:
   - `scripts/run_interactive_dssat_smoke_remote.sh` now defaults `DSSAT_PATCHED_INTERACTIVE_LAUNCH_COMMAND` to:
     - `python {controller_script} --driver-mode patched_runtime_subprocess {session_manifest}`
95. Hardened the Python-side interactive file protocol against partial JSON races:
   - `transdssat/dssat/interactive.py`
   - `transdssat/dssat/interactive_controller.py`
96. Added regression coverage for those protocol fixes:
   - `tests/test_dssat_interactive.py`
   - `tests/test_dssat_interactive_controller.py`
97. Verified the launcher/protocol hardening locally with:
   - `python -m unittest tests.test_dssat_interactive tests.test_dssat_interactive_controller tests.test_validate_interactive_dssat_action_effect -v`
   - `python -m compileall transdssat\dssat\interactive.py transdssat\dssat\interactive_controller.py tests\test_dssat_interactive.py tests\test_dssat_interactive_controller.py`
   - `bash -n scripts/run_interactive_dssat_smoke_remote.sh`
98. Synced the minimum runtime/validation script fixes to the remote TransDSSAT worktree and reran the paired validation through the repo-path chain:
   - artifact root:
     - `/fs/fast/u2021201693/lym/TransDSSAT/artifacts/interactive_action_effect_validation_fix_repo_20260622_123200`
99. That rerun changed the blocker boundary again:
   - the run no longer failed through the previous replay-bridge fallback or the old `step_request_0000.json` decode-race symptom
   - instead, the zero-action baseline on patched `dscsm048` exited before `session_ready.json` was emitted
   - controller-log tail showed only season-output lines, so the next blocker is now in the copied-runtime interactive reset path itself rather than the launcher glue
100. Diagnosed the reset-handshake failure to a rebuild regression rather than a new runtime-protocol bug:
   - remote runtime env propagation was verified as correct on the failing path
   - the rebuilt binary in `/fs/fast/u2021201693/lym/dssat-runtime-patched/dscsm048` matched a partial-overlay build that only carried `Management/MgmtOps.for`
   - that partial rebuild silently dropped the interactive `CSM_Main/LAND.for` bridge back to vanilla source, which explains why the copied runtime completed a full season without ever emitting `session_ready.json`
101. Hardened the remote rebuild wrapper so future interactive patched-runtime builds now require the full overlay contract:
   - `scripts/build_patched_dssat_runtime_remote.sh`
   - required files:
     - `CSM_Main/CSM.for`
     - `CSM_Main/LAND.for`
     - `Management/MgmtOps.for`
102. Rebuilt the copied patched runtime remotely from the full repo overlay and reran the paired validator:
   - build artifact root:
     - `/fs/fast/u2021201693/lym/TransDSSAT/artifacts/patched_runtime_build_full_overlay_20260622_1318`
   - validation artifact root:
     - `/fs/fast/u2021201693/lym/TransDSSAT/artifacts/interactive_action_effect_validation_full_overlay_20260622_1318`
103. Confirmed the repaired full-overlay runtime closes the previous main blockers:
   - `status = ok`
   - `irrigation_scale_matches_request = true`
   - `nitrogen_scale_matches_request = true`
   - action deltas now match the requested step:
     - `total_irrigation_mm = 12.0`
     - `total_nitrogen_kg_ha = 18.0`
104. Narrowed the remaining main-line gap again:
   - the `session_ready` reset path is restored when the full overlay is preserved
   - the previous `5x` action amplification is no longer present on the admissible runtime
   - the next remaining contract issue is that protocol-level `final_outcome` in the smoke report is still placeholder-like zero and must be aligned with parser-backed DSSAT outputs before the patched interactive path is considered complete
105. Diagnosed the terminal-outcome blocker to a remote Python sync gap rather than a new Fortran bug:
   - local `interactive_bridge.py` already had parser-backed `final_outcome` logic
   - the remote repo helper path was still on an older implementation, which explains the zero-placeholder protocol outcomes on repo-path smokes
106. Proved the parser-backed terminal-outcome contract on the real patched runtime by staging a temporary remote Python overlay instead of overwriting the dirty remote repo:
   - overlay root:
     - `/tmp/transdssat_final_outcome_overlay_20260622_1428`
   - paired validation artifact root:
     - `/fs/fast/u2021201693/lym/TransDSSAT/artifacts/interactive_action_effect_validation_final_outcome_overlay_20260622_1452`
107. Confirmed the real patched-runtime smoke reports no longer end with placeholder protocol outcomes:
   - baseline `final_outcome.cumulative_reward = -15.0`
   - action `final_outcome.cumulative_reward = -15.121284`
   - both smoke reports now carry parser-backed terminal metadata:
     - `interactive_reward_source = "dssat_output_parser"`
108. Upgraded the paired artifact-level validator so final result reports now prove both contracts on the same artifact set:
   - file:
     - `scripts/validate_interactive_dssat_action_effect.py`
   - regression coverage:
     - `tests/test_validate_interactive_dssat_action_effect.py`
   - new report checks:
     - `baseline_protocol_matches_archived`
     - `action_protocol_matches_archived`
     - `baseline_protocol_is_parser_backed`
     - `action_protocol_is_parser_backed`
109. Regenerated the paired validator report on the overlay-backed smoke artifacts:
   - report:
     - `/fs/fast/u2021201693/lym/TransDSSAT/artifacts/interactive_action_effect_validation_final_outcome_overlay_20260622_1452/action_effect_validation.json`
   - result:
     - `status = ok`
     - `irrigation_scale_matches_request = true`
     - `nitrogen_scale_matches_request = true`
     - `baseline_protocol_matches_archived = true`
     - `action_protocol_matches_archived = true`
     - `baseline_protocol_is_parser_backed = true`
     - `action_protocol_is_parser_backed = true`
110. Promoted the validated helper / validator Python updates into the normal remote repo path:
   - synced to `/fs/fast/u2021201693/lym/TransDSSAT`:
     - `transdssat/dssat/interactive_bridge.py`
     - `scripts/validate_interactive_dssat_action_effect.py`
     - `tests/test_validate_interactive_dssat_action_effect.py`
111. Verified the promoted remote repo path with:
   - `conda run --no-capture-output -n transdssat python -m unittest tests.test_validate_interactive_dssat_action_effect -v`
112. Reran the paired patched-runtime validation through the standard remote repo path without `/tmp` Python overlay assistance:
   - artifact root:
     - `/fs/fast/u2021201693/lym/TransDSSAT/artifacts/interactive_action_effect_validation_repo_mainline_20260622_142418`
   - validation report:
     - `/fs/fast/u2021201693/lym/TransDSSAT/artifacts/interactive_action_effect_validation_repo_mainline_20260622_142418/action_effect_validation.json`
113. Confirmed the standard repo-path validation now closes both remaining contracts on the real patched runtime:
   - `status = ok`
   - `irrigation_scale_matches_request = true`
   - `nitrogen_scale_matches_request = true`
   - `baseline_protocol_matches_archived = true`
   - `action_protocol_matches_archived = true`
   - `baseline_protocol_is_parser_backed = true`
   - `action_protocol_is_parser_backed = true`
114. Decided the current warning-backed short-season smoke artifact is acceptable as the interactive regression gate, but not as final agronomic/training-quality evidence:
   - rationale:
     - baseline/action are compared under the same warning envelope
     - the gate target is protocol alignment plus action-scale correctness
     - those checks now pass on the standard repo path
115. Archived the completion result in persistent documentation:
   - `docs/interactive-patched-mainline-validation-2026-06-22-cn.md`

## Expected Deliverables

1. A clear official-DSSAT-only execution policy in the repository docs.
2. A documented gap audit for official DSSAT step-wise PPO training and evaluation.
3. A documented gym-DSSAT-style implementation plan for the official step-wise interaction layer.
4. A short next-step plan limited to `1-3` minimal interventions.
5. A documented vanilla-vs-patched DSSAT validation contract using real data as the first regression oracle.

## Remaining Work

1. No active development work remains under this completed task.
2. Wait for a new Bootstrap assignment before starting the next implementation cycle.
3. If the next assignment requires GPU training, verify remote GPU availability with `nvidia-smi` before launching anything.

## Minimal Intervention Shortlist

The active engineering plan is now intentionally limited to these `3` interventions:

1. **Official-only mainline enforcement**
   - Remove proxy from the main training/evaluation entrypoints and real-subset evaluation path.
2. **Patched official DSSAT interactive layer**
   - Build the gym-DSSAT-style daily interaction mechanism on a copied patched runtime.
3. **Vanilla-vs-patched replay regression gate**
   - Use identical real-data inputs to require output agreement before patched DSSAT training is admissible.
   - Current entrypoint: `python scripts/compare_dssat_runtimes.py --vanilla-runtime-root ... --patched-runtime-root ... --output-root ...`

## Constraints

- Do not launch any new proxy-backed training, validation, rollout, or evaluation.
- Do not present proxy results as evidence for future model quality.
- From this point onward, the intended training and evaluation route is official DSSAT only.
- The preferred implementation reference for interactive official DSSAT training is gym-DSSAT's Fortran-instrumented daily loop approach, not a new proxy or surrogate path.
- Any DSSAT modification must happen on a copied patched runtime, never on the preserved vanilla runtime.
- Real-data replay is the first regression oracle for validating patched DSSAT correctness against the vanilla DSSAT baseline.
