# TransDSSAT Automation Runbook

## 1. Startup Order

Every meaningful wakeup must read:

1. `docs/OFFICIAL_DSSAT_ONLY_POLICY_CN.md`
2. `docs/CURRENT_AUTOMATION_TASK.md`
3. `docs/CURRENT_AUTOMATION_STATE.md`

If the task changed materially, then also read:

- `docs/README.md`
- `docs/AUTOMATION_RUNBOOK.md`

## 2. Route Policy

TransDSSAT is now under an **official-DSSAT-only** execution policy.

This means:

- official DSSAT is the only admissible training backend
- official DSSAT is the only admissible evaluation backend
- proxy is not an acceptable fallback for mainline progress

Historical docs or reports that mention proxy are archival only and must not be used as normative guidance.

## 3. Current Task Source of Truth

`docs/CURRENT_AUTOMATION_TASK.md` is the only source of truth for the active assignment.

Allowed statuses:

- `Bootstrap`
- `In Progress`
- `Completed`

## 4. Rolling State Source of Truth

`docs/CURRENT_AUTOMATION_STATE.md` is the rolling checkpoint.

Update it after every meaningful wakeup with:

- timestamp
- current mode
- what was verified
- active runs
- next immediate action

## 5. Remote Host

Canonical remote target:

```bash
ssh -p 22951 u2021201693@10.10.252.11
```

Canonical remote repo:

```bash
/fs/fast/u2021201693/lym/TransDSSAT
```

Canonical tmux session:

```bash
transdssat
```

## 6. DSSAT Environment

Before any official DSSAT run, verify:

```bash
cd /fs/fast/u2021201693/lym/TransDSSAT

export DSSAT_VANILLA_HOME=/fs/fast/u2021201693/lym/dssat-runtime
export DSSAT_PATCHED_HOME=/fs/fast/u2021201693/lym/dssat-runtime-patched
export DSSAT_HOME=$DSSAT_PATCHED_HOME
export DSSAT_TEMPLATE_ROOT=/fs/fast/u2021201693/lym/dssat-templates
export DSSAT_PREPROCESS_COMMAND="python scripts/render_dssat_inputs.py {manifest}"
export DSSAT_VANILLA_RUN_COMMAND="$DSSAT_VANILLA_HOME/dscsm048 A {experiment}"
export DSSAT_PATCHED_RUN_COMMAND="$DSSAT_PATCHED_HOME/dscsm048 A {experiment}"
export DSSAT_RUN_COMMAND="$DSSAT_PATCHED_RUN_COMMAND"
```

For future interactive patched DSSAT work, the Python-side transport now also supports:

```bash
export DSSAT_PATCHED_INTERACTIVE_LAUNCH_COMMAND="python {controller_script} {session_manifest}"
export DSSAT_INTERACTIVE_PROTOCOL_DIRNAME=interactive_protocol
export DSSAT_INTERACTIVE_POLL_INTERVAL_SECONDS=0.2
export DSSAT_INTERACTIVE_READY_TIMEOUT_SECONDS=60
export DSSAT_INTERACTIVE_STEP_TIMEOUT_SECONDS=60
export DSSAT_INTERACTIVE_CLOSE_TIMEOUT_SECONDS=30
```

Important launch-path rule:

- the controller is launched with `cwd=<run_dir>`, not `cwd=<repo_root>`
- do not use a relative script path like `python scripts/run_interactive_dssat_controller.py ...` in `DSSAT_*_INTERACTIVE_LAUNCH_COMMAND`
- use the built-in absolute placeholder `python {controller_script} {session_manifest}` instead
- optional placeholders now available for future wrappers:
  - `{controller_script}`
  - `{project_root}`
  - `{repo_root}`

Current interpretation:

- the command above is the transitional external controller bridge
- it is official-DSSAT-only, but it still evaluates through whole-season replay under the hood
- it is not yet the final gym-DSSAT-style patched daily DSSAT loop
- when the copied runtime is instrumented, keep the same launch/transport contract and swap the controller internals rather than redesigning the training-side API again

Current reusable smoke helpers:

- local or remote boundary-only subprocess probe:
  - `python {repo_root}/scripts/dssat_interactive_boundary_probe.py --mark-done-after-step`
- remote smoke wrapper:
  - `bash scripts/run_interactive_dssat_smoke_remote.sh <output-dir> [smoke args...]`

Interpretation rule:

- the boundary probe is admissible only as a startup-contract smoke for the copied patched-runtime subprocess boundary
- it does not replace the vanilla-vs-patched parity gate
- it does not count as the real Fortran-instrumented interactive DSSAT implementation

### Vanilla / Patched Rule

- preserve the current vanilla DSSAT runtime as the regression baseline
- create a separate copied patched DSSAT runtime for interactive gym-DSSAT-style work
- never patch the vanilla runtime in place

Before the patched runtime is allowed into training:

1. run the same real-data input on vanilla DSSAT
2. run the same real-data input on patched DSSAT
3. compare outputs under identical non-interactive conditions

Preferred repo entrypoint:

```bash
python scripts/compare_dssat_runtimes.py \
  --vanilla-runtime-root /fs/fast/u2021201693/lym/dssat-runtime \
  --patched-runtime-root /fs/fast/u2021201693/lym/dssat-runtime-patched \
  --output-root /fs/fast/u2021201693/lym/TransDSSAT/artifacts/dssat_runtime_compare
```

If outputs differ unexpectedly, the patched runtime is not admissible for training yet.

## 7. GPU Rule

All AI policy / Transformer / PPO / RL training is GPU work.

Before starting training:

```bash
nvidia-smi
```

If no GPU is free:

- do not start training
- continue only CPU-safe official-DSSAT preparation work such as docs, code audit, static checks, parser/input validation, and small unit tests

## 8. Remote Execution Rule

Long official DSSAT experiments and training runs must be launched remotely in `tmux`.

Required pattern:

1. verify remote repo and environment
2. verify GPU availability if training is requested
3. write a remote wrapper script
4. launch it in `tmux`
5. record wrapper path, log path, artifact path, and tmux window in `CURRENT_AUTOMATION_STATE.md`

## 9. Documentation Rule

After each meaningful wakeup:

- update `docs/CURRENT_AUTOMATION_STATE.md`
- update `docs/CURRENT_AUTOMATION_TASK.md` if the task status or result changed
- append a concise entry to automation memory

If the vanilla/patched DSSAT validation rule changes or new runtime paths are introduced, record them in:

- `docs/CURRENT_AUTOMATION_TASK.md`
- `docs/CURRENT_AUTOMATION_STATE.md`
- `docs/OFFICIAL_DSSAT_ONLY_POLICY_CN.md`

## 10. Safety Rule

- do not use destructive git commands
- do not overwrite unrelated user changes
- do not restart proxy work as a substitute for missing official DSSAT capabilities
- if official DSSAT is not ready, the correct next step is to close the gap, not to fall back to proxy
