# TransDSSAT 远端服务器历史信息抽取

更新时间：2026-05-26

本文记录从本机 Codex 历史会话中抽取到的远端服务器信息。它用于接管线索，不替代实时 SSH 核验。

## 已确认信息

### SSH

```bash
ssh -p 22951 u2021201693@10.10.252.11
```

历史证据中多次出现该 SSH 目标，并且同一远端输出中存在 `transdssat` tmux session 与 `/fs/fast/u2021201693/lym/TransDSSAT` 目录。

### 服务器基础信息

- hostname: `workstation`
- user: `u2021201693`
- home: `/home/u2021201693`
- project root: `/fs/fast/u2021201693/lym/TransDSSAT`
- parent work root: `/fs/fast/u2021201693/lym`

### DSSAT 相关路径

- DSSAT runtime: `/fs/fast/u2021201693/lym/dssat-runtime`
- DSSAT template root: `/fs/fast/u2021201693/lym/dssat-templates`
- DSSAT source/data directories observed:
  - `/fs/fast/u2021201693/lym/dssat-csm-os`
  - `/fs/fast/u2021201693/lym/dssat-csm-data`

建议环境变量：

```bash
export DSSAT_HOME=/fs/fast/u2021201693/lym/dssat-runtime
export DSSAT_TEMPLATE_ROOT=/fs/fast/u2021201693/lym/dssat-templates
export DSSAT_PREPROCESS_COMMAND="python scripts/render_dssat_inputs.py {manifest}"
export DSSAT_RUN_COMMAND="/fs/fast/u2021201693/lym/dssat-runtime/dscsm048 A {experiment}"
```

### tmux

历史中存在 TransDSSAT 专用 session：

- `transdssat`

历史窗口：

- `0:bash`
- `1:rl-clean120`
- `2:rl-water-check`
- `3:rl-joint-check-`
- `4:rl-nitrogen-check`

### GPU

历史中观察到 8 张 GPU：

- `NVIDIA A800-SXM4-80GB`
- index: `0` 到 `7`

## 待实时核验

每次正式远端自动化启动前，应实时核验：

```bash
hostname
whoami
pwd
ls -la /fs/fast/u2021201693/lym
ls -la /fs/fast/u2021201693/lym/TransDSSAT
ls -la /fs/fast/u2021201693/lym/dssat-runtime
ls -la /fs/fast/u2021201693/lym/dssat-templates
tmux list-sessions
tmux list-windows -t transdssat
nvidia-smi
```

## 重要注意

- Rel-LLM 历史中也使用了同一台服务器和 `lymtmux`，但不能把 Rel-LLM 的 run root、窗口名和任务状态当作 TransDSSAT 事实。
- 早期 TransDSSAT 接入 DSSAT 时曾使用写死的 maize 命令 `UFGA8201.MZX`，后续统一运行应使用 `{experiment}`。
- 如果服务器没有空闲 GPU，不启动 AI policy / Transformer / RL 训练。
- DSSAT 仿真可视为 CPU 侧工作，但涉及模型训练时必须按 GPU 资源管理。
