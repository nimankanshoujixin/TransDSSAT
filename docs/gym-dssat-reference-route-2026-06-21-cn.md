# gym-DSSAT 参考路线（2026-06-21）

## 1. 这条路线为什么成立

gym-DSSAT 的核心价值，不是“又做了一个训练任务”，而是它展示了如何把 **official DSSAT 本体** 变成一个可交互的 RL 环境。

根据 gym-DSSAT 文档和论文：

- gym-DSSAT 是对 DSSAT Fortran 软件的改造，使其成为 Python Gym 环境
- 它允许 agent 在生长季中按日交互
- 它使用 **PDI Data Interface**
- 它通过 **Python/ZeroMQ** 与外部 agent 进程通信
- DSSAT 日循环在每一步是 **blocking** 的，必须收到动作后才继续推进

参考来源：

- gym-DSSAT 文档：<https://rgautron.gitlabpages.inria.fr/gym-dssat-docs/>
- gym-DSSAT 论文：<https://arxiv.org/pdf/2207.03270>

论文中最关键的技术描述是：

1. DSSAT-PDI 进入 daily loop
2. 在 `get state` 事件时，把 DSSAT 内部状态写入 PDI store
3. Python 侧读取状态，执行 agent 交互逻辑
4. 在 `set action` 事件时，把 agent 动作写回 DSSAT 内存
5. DSSAT daily loop 恢复执行

这正是当前 TransDSSAT 后续路线应该参考的对象。

## 2. 对 TransDSSAT 的直接含义

这意味着我们现在不该再继续以下路线：

- proxy 训练
- surrogate 训练
- 用代理环境先替代 official DSSAT 的主交互层

而应该直接瞄准：

- 把 official DSSAT 变成 step-wise `reset/step` 环境
- 让 PPO 的训练信号直接来自 official DSSAT

## 3. 与当前仓库的差距

当前仓库已有：

- DSSAT 输入渲染
- DSSAT 运行 wrapper
- DSSAT 输出解析
- real-subset official replay

当前缺少：

1. **Fortran 侧可交互 daily loop 插桩**
2. **状态提取与动作注入的双向接口**
3. **Python 侧 official step-wise environment 封装**
4. **训练主入口与 official step-wise environment 的连接**

## 4. 推荐实施顺序

在所有实施步骤之前，先固定一条工程规则：

- 保留原始 vanilla DSSAT runtime
- 复制一份 patched DSSAT runtime 作为交互改造对象
- 真实数据 replay 用于验证 patched 版本没有破坏原始 DSSAT 语义

### 第一步：确认 official DSSAT 插桩路线

目标：

- 明确是直接改现有 DSSAT 源码，还是基于 gym-DSSAT 提供的机制移植

交付：

- 列出需要插桩的 daily loop 节点
- 列出需要暴露的状态变量
- 列出需要写回的动作变量
- 明确 vanilla runtime 路径与 patched runtime 路径
- 明确第一批真实数据回归样例

### 第二步：先做最小单通道交互闭环

推荐先只做：

- 单作物
- 单管理通道
- 单日步进

目的不是马上全功能训练，而是先证明：

- official DSSAT 可以真正被 `reset/step`
- Python 侧可以读状态、写动作、继续仿真
- patched runtime 在“无额外交互差异”条件下与 vanilla runtime 输出一致

### 第三步：再接 PPO

只有当第二步跑通后，才值得把：

- step-wise PPO
- Transformer actor-critic
- 训练脚本

真正挂到 official DSSAT 上。

## 5. 当前建议的 `1-3` 个最小工程动作

### 动作 1

补一份 official DSSAT step-wise 交互接口设计文档，直接按 gym-DSSAT 思路定义：

- `get_state`
- `set_action`
- `resume_step`
- `finalize`

### 动作 2

审计当前 DSSAT 源码与 runner，确定 daily loop 插桩点和动作写回点。

### 动作 3

建立 vanilla / patched DSSAT 的双 runtime 验证链，并先用真实数据 replay 做一致性回归。

## 6. 当前结论

是的，TransDSSAT 后续缺的关键东西，**可以从 gym-DSSAT 学到核心做法**。

更准确地说：

- 不是直接抄它的任务定义
- 而是直接参考它把 DSSAT 改造成可交互 RL 环境的工程方案

这已经足够成为我们当前任务书里的正式路线。
