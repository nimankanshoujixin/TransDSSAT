# Patched DSSAT Interactive 协议合同（2026-06-22）

## 1. 目的

这份文档把上一轮已经确定的三处最小补丁面：

- `CSM_Main/CSM.for`
- `CSM_Main/LAND.for`
- `Management/MgmtOps.for`

进一步收敛为一个可执行的协议合同，目标是让后续 Fortran 补丁与当前 Python 侧 `interactive.py` / `interactive_controller.py` 直接对接，而不是再改一次训练接口。

## 2. 当前决定

第一版 patched runtime 继续沿用现有文件协议目录，不改 Python 侧 `reset/step/close` API，只补充 manifest 元数据并把 Fortran 端行为锁定为同一合同。

协议版本：

- `protocol_version = "patched-dssat-v1"`

动作通道首版只允许：

- `irrigation_mm`
- `nitrogen_kg_ha`

首版 backend 语义：

- Python 训练主线目标：`interactive_patched`
- 现有外部 replay bridge 仅作为过渡参考：`season_replay_wrapper_external_controller`

## 2.1 env 合同（Python -> patched runtime）

在 `patched_runtime_subprocess` 模式下，Python 侧除写出 `session_manifest.json` 外，还会把同一份 `interaction` 元数据注入到运行时环境变量，供后续 Fortran 补丁在不先解析完整 manifest 的情况下做启动参数校验。

首版必须注入：
- `DSSAT_INTERACTIVE_MODE=1`
- `DSSAT_INTERACTIVE_PROTOCOL_DIR`
- `DSSAT_INTERACTIVE_SESSION_MANIFEST`
- `DSSAT_INTERACTIVE_PROTOCOL_VERSION`
- `DSSAT_INTERACTIVE_ENGINE_NAME`
- `DSSAT_INTERACTIVE_BACKEND_MODE`
- `DSSAT_INTERACTIVE_RUNTIME_ROLE`
- `DSSAT_INTERACTIVE_RUN_DIR`
- `DSSAT_INTERACTIVE_CROP_NAME`
- `DSSAT_INTERACTIVE_ACTION_CHANNELS`
- `DSSAT_INTERACTIVE_DECISION_INTERVAL_DAYS`
- `DSSAT_INTERACTIVE_HELPER_COMMAND`
- `DSSAT_INTERACTIVE_STATE_INTERFACE_CONTRACT_JSON`

此外，Python 侧 controller launch command 现在允许在字符串模板中使用这些占位符：
- `{session_manifest}`
- `{protocol_dir}`
- `{run_dir}`
- `{controller_script}`
- `{project_root}`
- `{repo_root}`

其中 `controller_script` 必须视为当前主线默认值，因为 controller 是在 `cwd=<run_dir>` 下启动的；使用相对路径
`python scripts/run_interactive_dssat_controller.py ...` 会在真实 interactive session 中失败。

其中：
- `...SESSION_MANIFEST` 作为完整 scenario/protocol 主文档入口。
- `...STATE_INTERFACE_CONTRACT_JSON` 直接锁定 Python `CropState` 字段合同，避免 Fortran 侧各自猜字段。
- `...RUN_DIR` 把协议目录和 DSSAT 实际 run dir 显式分开，便于补丁后做更严格的启动前校验。

## 3. 文件协议

协议目录保持不变：

- `session_manifest.json`
- `session_ready.json`
- `step_request_XXXX.json`
- `step_response_XXXX.json`
- `close_request.json`
- `final_outcome.json`

### 3.0 Fortran bridge helper

为避免第一版 patched runtime 在 Fortran 里直接手写完整 JSON，本仓库新增了最小桥接层：

- `transdssat/dssat/interactive_bridge.py`
- `scripts/dssat_interactive_protocol_helper.py`

这层只做两类事情：

1. 把 Fortran 更容易写出的简单 `key=value` 状态/结果载荷转换成现有 JSON 协议文件。
2. 把 `step_request_XXXX.json` 中的动作转换成 Fortran 易读的 `key=value` 动作文件。

因此下一轮 `CSM.for` / `LAND.for` / `MgmtOps.for` 的最小实现不再是“在 Fortran 中生成完整 JSON”，而是：

- 写简单 bridge payload；
- 用 `SYSTEM(...)` 调 helper；
- 继续复用现有 Python 侧 transport/controller contract。

### 3.1 `session_manifest.json`

必须包含：

- `scenario_id`
- `protocol`
- `scenario`
- `decision_context`
- `interaction`

其中 `interaction` 是新锁定的最小合同，至少包含：

- `protocol_version`
- `engine_name`
- `backend_mode`
- `runtime_role`
- `run_dir`
- `crop_name`
- `action_channels`
- `decision_interval_days`
- `state_interface_contract`
- `poll_interval_seconds`

这层信息的作用不是给 PPO 直接消费，而是把 “patched runtime 应该按什么协议运行” 写死在单次 session manifest 里，避免 Python 配置与 Fortran 补丁漂移。

### 3.2 `session_ready.json`

patched runtime 在 `SEASINIT` 后、首个决策前必须写出：

- `state`
- `run_dir`
- `info`

其中 `info` 至少回显：

- `protocol_version`
- `engine_name`
- `backend_mode`
- `runtime_role`

这样 Python 侧一旦接到错误 runtime 或错误 patch 版本，可以在第一步前直接 fail fast。

### 3.3 `step_request_XXXX.json`

Python 侧继续写：

- `step_index`
- `decision_interval_days`
- `action`

其中 `action` 首版只允许：

- `irrigation_mm`
- `nitrogen_kg_ha`

### 3.4 `step_response_XXXX.json`

patched runtime 每完成一次单日或单决策窗推进后写：

- `next_state`
- `reward`
- `done`
- `daily_trace`
- `run_dir`
- `info`

若 season 已结束，再补：

- `final_outcome`

`info` 至少应包含：

- `protocol_version`
- `engine_name = "dssat_official"`
- `backend_mode = "interactive_patched"`
- `days_executed`

## 4. 三处最小补丁与协议映射

### 4.1 `CSM.for`

职责：

- 增加 interactive mode 开关读取
- 在 `SEASINIT` 后触发首个 `session_ready`
- 在每次单日推进完成后允许阻塞等待下一次 action
- 在 season 结束时写 `final_outcome`

不做：

- 不改作物数值模块
- 不在这里直接拼 irrigation / nitrogen 业务逻辑

### 4.2 `LAND.for`

职责：

- 在 `RATE` 分支的 `WEATHR(...)` 之后、`MGMTOPS(...)` 之前导出首版状态
- 在同一位置作为 `wait_action` 的最小交互门
- 只输出当前 Python `CropState` 合同所需字段

不做：

- 不暴露整套内部数组
- 不在这里重写土壤或作物积分逻辑

### 4.3 `MgmtOps.for`

职责：

- interactive mode 下跳过自动灌溉与自动施肥调度
- 将 controller 给出的 `irrigation_mm` / `nitrogen_kg_ha` 直接落到 `IRRAMT` / `FERTDATA`

不做：

- 不接管 tillage / residue / chemical / harvest
- 不把文件轮询散落进 `IRRIG.for` 或 `Fert_Place.for`

## 5. 首版验证关口

patched runtime 进入训练前，至少要过两层验证：

1. 非交互 parity：
   - patched runtime 在 interactive mode 关闭时，必须继续通过 `compare_dssat_runtimes.py` 的 real-data vanilla-vs-patched 一致性门。
2. 交互 smoke：
   - 先在单作物单场景上打通 `session_ready -> request -> response -> final_outcome`。
   - 再确认 `interactive_patched` 后端能被 `StepwiseDecisionEnvironment` 真正消费。
3. helper contract：
   - `scripts/dssat_interactive_protocol_helper.py` 先通过本地单测。
   - Fortran 只依赖 helper 已锁定的 `key=value` bridge contract，不再发明第二套文件协议。

## 6. 下一步最小实现顺序

1. 在 copied patched runtime 中加入明确的 interactive mode flag，并保证默认关闭时仍保持 vanilla 等价行为。
2. 按本合同在 `CSM.for` / `LAND.for` 打通 “写简单 state payload -> helper 生成 `session_ready` / helper 等待动作 -> helper 生成 `step_response`”。
3. 在 `MgmtOps.for` 接入首版双通道动作注入，然后做单场景 parity + interactive smoke。
