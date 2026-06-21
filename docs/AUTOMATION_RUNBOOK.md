# TransDSSAT 自动化长期执行规则

本文档记录长期工作方式、远端运行规范、监控规则和文档回写规则。不要在这里写某一轮具体任务目标。

## 1. 启动顺序

每次自动化 wakeup 必须先读：

1. `docs/CURRENT_AUTOMATION_TASK.md`
2. `docs/CURRENT_AUTOMATION_STATE.md`

如果满足任一条件，再继续读导航和方法文档：

- `Task Status` 为 `Bootstrap`
- 当前任务描述明显变更
- 当前状态缺失、过期或与仓库状态冲突
- 即将启动新的远端训练、评测或数据生成

随后按需读取：

- `docs/README.md`
- `docs/AUTOMATION_RUNBOOK.md`
- `docs/implementation-plan-cn.md`
- `docs/testset-eval-protocol-cn.md`
- `docs/policy-registry-spec-cn.md`
- `docs/scenario-schema-cn.md`
- `docs/evaluation-report-spec-cn.md`

## 2. 当前任务真源

`docs/CURRENT_AUTOMATION_TASK.md` 是当前任务唯一真源。

新任务发布时：

- 覆盖 `Task Description`
- 将 `Task Status` 设为 `Bootstrap`
- 清空或重写 `Result Report`
- 不依赖历史聊天作为唯一依据

任务状态只使用：

- `Bootstrap`
- `In Progress`
- `Completed`

## 3. 滚动状态真源

`docs/CURRENT_AUTOMATION_STATE.md` 是当前滚动检查点。

每次有意义的 wakeup 后必须更新：

- `Last updated`
- `Mode`
- `Task status`
- `Execution status`
- `What Was Verified This Wakeup`
- `Current Active Runs`
- `Next Immediate Action`

如果没有启动任何远端运行，也要记录“未启动”的原因，例如 GPU 不空闲、等待用户确认、缺少任务。

## 4. 远端服务器信息

以下信息来自 Codex 历史会话抽取，应作为接管线索使用。关键路径在首次自动化 wakeup 时仍需 SSH 实时核验。

### 已确认远端入口

```bash
ssh -p 22951 u2021201693@10.10.252.11
```

历史核验信息：

- hostname: `workstation`
- user: `u2021201693`
- home: `/home/u2021201693`
- project root: `/fs/fast/u2021201693/lym/TransDSSAT`
- DSSAT runtime: `/fs/fast/u2021201693/lym/dssat-runtime`
- DSSAT templates: `/fs/fast/u2021201693/lym/dssat-templates`
- GPU: 8 x `NVIDIA A800-SXM4-80GB`

### DSSAT 环境变量建议

```bash
cd /fs/fast/u2021201693/lym/TransDSSAT

export DSSAT_HOME=/fs/fast/u2021201693/lym/dssat-runtime
export DSSAT_TEMPLATE_ROOT=/fs/fast/u2021201693/lym/dssat-templates
export DSSAT_PREPROCESS_COMMAND="python scripts/render_dssat_inputs.py {manifest}"
export DSSAT_RUN_COMMAND="/fs/fast/u2021201693/lym/dssat-runtime/dscsm048 A {experiment}"
```

注意：

- 早期历史里曾出现写死 `UFGA8201.MZX` 的命令，只适合 maize 样例，不适合作为统一运行命令。
- 当前统一口径应优先使用 `{experiment}`。
- 首次运行前必须确认 `wheat_quzhou_base`、`maize_quzhou_base` 或新作物模板是否存在。

## 5. tmux 规范

历史中存在 TransDSSAT 专用 tmux session：

```bash
tmux list-sessions
tmux list-windows -t transdssat
```

历史窗口名：

- `bash`
- `rl-clean120`
- `rl-water-check`
- `rl-joint-check-`
- `rl-nitrogen-check`

长期规则：

- 长任务必须放入 tmux。
- 每个逻辑任务一个窗口。
- 启动替换任务前，只 kill 同名旧窗口，不清理不相关窗口。
- 不要把 Rel-LLM 的 `lymtmux` 运行状态当作 TransDSSAT 当前状态。
- 如果要启动新窗口，优先使用 `transdssat` session；若不存在，先创建：

```bash
tmux has-session -t transdssat 2>/dev/null || tmux new-session -d -s transdssat
```

## 6. GPU 与训练规则

TransDSSAT 的 DSSAT 仿真主要依赖 CPU，但 AI policy / Transformer / RL 训练默认按 GPU 任务管理。

启动训练前必须检查：

```bash
nvidia-smi
nvidia-smi --query-gpu=index,name,utilization.gpu,memory.used,memory.total --format=csv
tmux list-windows -a
ps -eo pid,ppid,etime,cmd | grep -E "python|torch|train|TransDSSAT" | grep -v grep || true
```

如果没有空闲 GPU：

- 不启动训练。
- 可以继续做 CPU 轻量任务，例如代码检查、文档更新、测试集配置生成、评测脚本 dry-run。
- 在 `CURRENT_AUTOMATION_STATE.md` 记录 GPU 不空闲并等待用户通知。

## 7. 远端运行方式

短命令可以直接 SSH。

长任务必须使用远端 wrapper：

1. 在远端 `/tmp` 或项目下生成 `.sh` wrapper。
2. wrapper 内执行：
   - `set -euo pipefail`
   - 激活 conda 或 Python 环境
   - `cd /fs/fast/u2021201693/lym/TransDSSAT`
   - export DSSAT 环境变量
   - 运行目标命令
3. 用 tmux 启动 wrapper。
4. stdout/stderr 写入明确日志路径。

示例：

```bash
tmux new-window -d -t transdssat: -n rl-joint-check \
  "bash -lc 'bash /tmp/transdssat_rl_joint_check.sh > /tmp/transdssat_rl_joint_check.log 2>&1'"
```

### Wakeup stop rule for long remote jobs

- If a meaningful long-running remote job such as a staged `full run` has been launched successfully into `tmux`, with a persistent log path and artifact directory recorded, that wakeup should normally stop there.
- Do not keep the same wakeup alive just to poll until the remote `full run` finishes.
- The correct pattern is:
  1. current wakeup: validate, verify GPU, launch remote job, record window/log/artifact path
  2. next wakeup: inspect the completed or active remote job result and decide the next case-study-driven step
- Immediate inline polling is only for launch verification, startup failure diagnosis, or a very short staged smoke/intermediate job that is expected to end quickly inside the same wakeup.

## 8. 文档回写规则

每次有意义的 wakeup 后必须同步三类记录：

- `docs/CURRENT_AUTOMATION_TASK.md`
  - 任务状态变化或产生最终结果时更新。

- `docs/CURRENT_AUTOMATION_STATE.md`
  - 每次 wakeup 更新。

- `$CODEX_HOME/automations/<automation_id>/memory.md`
  - 仓库外持久记忆。
  - 追加简短总结：做了什么、结论是什么、下次从哪里继续。

如果当前没有 automation id，则只更新仓库内 task/state，并在 state 里注明未写 memory 的原因。

## 9. 证据与历史归档

历史实验、报告、候选配置和缓存证据放入 `research_notes/`。

规则：

- `research_notes/` 不作为当前任务入口。
- 当前事实必须回写到 `CURRENT_AUTOMATION_TASK.md` 或 `CURRENT_AUTOMATION_STATE.md`。
- 远端历史信息要标注“已确认”或“待实时核验”。
- 不要把其他项目的信息当作 TransDSSAT 事实；尤其要区分 Rel-LLM 的 `lymtmux` 与 TransDSSAT 的 `transdssat`。

## 10. 安全与协作规则

- 不运行 `git reset --hard`、`git checkout --` 等破坏性命令。
- 不删除远端 untracked 文件，除非用户明确要求。
- 不覆盖用户未确认的实验产物。
- 不在无 GPU 空闲时启动训练。
- 不把小样本异常结果写成最终科学结论。
- 不硬编码缺失文献信息；信息不足时标记 `missing_details` 或 `conservative_approximation`。
## Execution Environment

- All code execution, tests, validation, training, and experiment runs for TransDSSAT must run on the remote server/workdir.
- Local Windows work is limited to editing, inspection, and file synchronization; do not run project code locally unless explicitly requested for a non-code task.
