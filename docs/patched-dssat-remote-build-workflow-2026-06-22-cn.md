# Patched DSSAT 远端构建工作流（2026-06-22）

## 目的

把 copied patched runtime 的 Fortran 改动收敛为仓库内可复现流程，而不是继续依赖零散 SSH 命令。

本工作流只解决三件事：

1. 用 repo-local overlay 承载 `CSM.for` / `LAND.for` / `MgmtOps.for` 改动。
2. 在远端把 overlay 覆盖到 copied DSSAT source tree。
3. 重新构建 `dscsm048` 并刷新 `/fs/fast/u2021201693/lym/dssat-runtime-patched/dscsm048`。

## 新增仓库入口

- overlay 目录约定：
  - [`/G:/TransDSSAT/dssat_patch_overlay/README.md`](/G:/TransDSSAT/dssat_patch_overlay/README.md)
- 远端构建 wrapper：
  - [`/G:/TransDSSAT/scripts/build_patched_dssat_runtime_remote.sh`](/G:/TransDSSAT/scripts/build_patched_dssat_runtime_remote.sh)

## Overlay 约定

overlay 根目录下的相对路径必须与 DSSAT 源码树一致。例如：

```text
dssat_patch_overlay/
  CSM_Main/
    CSM.for
    LAND.for
  Management/
    MgmtOps.for
```

远端 wrapper 会执行两次同步：

1. `rsync -a --delete <source-root>/ <patched-source-root>/`
2. `rsync -a <overlay-root>/ <patched-source-root>/`

因此 overlay 里只需要放“被替换的源文件”，不需要放完整源码树。

## 远端构建命令

在远端运行：

```bash
bash scripts/build_patched_dssat_runtime_remote.sh \
  --overlay-root /tmp/transdssat_dssat_overlay \
  --clean \
  --report-json /fs/fast/u2021201693/lym/TransDSSAT/artifacts/dssat_build_stage1/build_report.json
```

默认参数：

- source root:
  `/fs/fast/u2021201693/lym/dssat-csm-os-v4.8.5`
- build root:
  `/tmp/transdssat_dssat_build`
- runtime root:
  `/fs/fast/u2021201693/lym/dssat-runtime-patched`

构建完成后，wrapper 会：

1. 在临时 patched source tree 上执行 `cmake -S ... -B ...`
2. 执行 `cmake --build ... --target dscsm048`
3. 用新二进制覆盖 patched runtime 下的 `dscsm048`
4. 可选写出 JSON build report

## 与当前任务的关系

这一步还不是 Fortran interactive patch 本身，但它补上了下一阶段最缺的工程底座：

- patch 不再只是文档计划，而是有了固定 overlay 入口
- copied runtime 的刷新动作有了单一 wrapper
- 后续每次 `CSM/LAND/MgmtOps` 改动后，都能立刻接：
  - runtime rebuild
  - parity gate
  - interactive smoke

## 下一步建议

1. 先在 `dssat_patch_overlay/` 放入第一版 `CSM.for` + `LAND.for`，只打通 helper-backed `session_ready`。
2. 用新 wrapper 远端重建 patched runtime。
3. 先跑单场景 interactive smoke，再决定是否继续接 `wait_action -> step_response`。
