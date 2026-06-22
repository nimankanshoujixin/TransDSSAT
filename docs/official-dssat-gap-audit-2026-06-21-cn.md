# Official DSSAT 唯一路线缺口审计（2026-06-21）

## 1. 目标

本审计只服务于一个目标：

- 将 TransDSSAT 切换为 **official DSSAT only** 的训练与评估路线

因此本文件关注的是：

1. 当前代码里哪些地方仍然默认依赖代理环境
2. 哪些地方已经具备 official DSSAT 能力
3. 下一步最小改动应该切哪里

## 2. 已具备的 official DSSAT 基础

当前仓库并不是“完全没有 official DSSAT 能力”，而是 **official DSSAT 已接入，但没有进入主训练闭环**。

已存在的基础包括：

- official DSSAT runtime wrapper
  - [`/G:/TransDSSAT/transdssat/dssat/runner.py`](/G:/TransDSSAT/transdssat/dssat/runner.py)
- official DSSAT 输出解析
  - [`/G:/TransDSSAT/transdssat/dssat/parser.py`](/G:/TransDSSAT/transdssat/dssat/parser.py)
- official DSSAT 输入渲染
  - [`/G:/TransDSSAT/scripts/render_dssat_inputs.py`](/G:/TransDSSAT/scripts/render_dssat_inputs.py)
- 真实子集 official replay
  - [`/G:/TransDSSAT/transdssat/real_subset_runner.py`](/G:/TransDSSAT/transdssat/real_subset_runner.py)
  - [`/G:/TransDSSAT/scripts/evaluate_real_subset_checkpoint.py`](/G:/TransDSSAT/scripts/evaluate_real_subset_checkpoint.py)

结论：

- official DSSAT **不是从零开始**
- 关键缺口在于：**训练主循环与 step-wise 交互接口仍默认建在代理语义上**

## 3. 当前最关键的代理依赖点

### 3.1 训练脚本仍允许并默认走代理引擎

- [`/G:/TransDSSAT/scripts/train_stepwise_ppo.py`](/G:/TransDSSAT/scripts/train_stepwise_ppo.py)
  - 仍保留 `dssat_proxy` / `wofost_proxy` 选项
- [`/G:/TransDSSAT/scripts/train_rl_transformer.py`](/G:/TransDSSAT/scripts/train_rl_transformer.py)
  - 默认引擎仍不是 official-only

这意味着训练入口层还没有被收紧到 official DSSAT。

### 3.2 step-wise 环境接口仍默认走代理环境

- [`/G:/TransDSSAT/transdssat/environments/stepwise.py`](/G:/TransDSSAT/transdssat/environments/stepwise.py)
  - 目前 step-wise 环境仍通过代理环境构造交互

这是当前最核心的结构性缺口。

如果 step-wise `reset/step/reward/done` 不是 official DSSAT 驱动，那么 PPO 训练信号就仍然不是 official DSSAT。

### 3.3 场景池和测试集默认引擎仍指向代理

- [`/G:/TransDSSAT/transdssat/testset.py`](/G:/TransDSSAT/transdssat/testset.py)
  - 默认 `engines` 仍是代理
- [`/G:/TransDSSAT/transdssat/scenarios.py`](/G:/TransDSSAT/transdssat/scenarios.py)
  - 默认引擎集合仍包含代理

这意味着即使不看训练脚本，数据与场景生成层也还在把代理当默认语义。

### 3.4 real-subset step-wise materialization 仍挂代理场景名义

- [`/G:/TransDSSAT/transdssat/real_subset_stepwise_eval.py`](/G:/TransDSSAT/transdssat/real_subset_stepwise_eval.py)
  - `build_real_subset_simulation_scenario(...)` 中 `engine_name="dssat_proxy"`

虽然最终真实子集 replay 是 official DSSAT，但策略 rollout 场景构造仍不是 official-DSSAT-native 语义。

### 3.5 部分 adapter / discrete / validation 工具仍写着代理约束

- [`/G:/TransDSSAT/transdssat/stepwise_adapter.py`](/G:/TransDSSAT/transdssat/stepwise_adapter.py)
- [`/G:/TransDSSAT/transdssat/discrete_actions.py`](/G:/TransDSSAT/transdssat/discrete_actions.py)
- [`/G:/TransDSSAT/scripts/validate_stepwise_rollout.py`](/G:/TransDSSAT/scripts/validate_stepwise_rollout.py)

这些不一定都是第一批必须重写的对象，但它们说明：

- 当前 step-wise 执行合同仍带有明显的代理历史负担

## 4. 这不意味着什么

本审计不意味着：

- 当前仓库完全不能跑 official DSSAT
- 必须重写整个项目
- 必须先做大规模架构重构

更准确的结论是：

- **official DSSAT 基础层已经在**
- **主训练闭环还没切过去**

## 5. 当前最小改动方向

基于当前代码结构，最值得优先做的不是一口气清理所有历史代理代码，而是先完成下面 `1-3` 个最小切换动作：

### 最小动作 1

把训练主入口收紧到 official DSSAT：

- `train_stepwise_ppo.py`
- `train_rl_transformer.py`
- `run_unified_evaluation.py`

至少做到：

- 默认 engine 变为 `dssat_official`
- 明确禁止把代理作为主训练路径启动

### 最小动作 2

重构 step-wise 环境，使 `reset/step` 的主实现不再依赖代理环境，而是面向 official DSSAT 的可执行交互/重放语义。

这是核心缺口，也是最重要的工程任务。

### 最小动作 3

把 real-subset / scenario-pool / step-wise evaluation 中仍残留的代理默认值改成 official DSSAT 语义，并清理旧的“代理是主裁判”表述。

## 6. 当前建议

下一步不建议再做任何代理诊断，也不建议继续讨论“代理是否还能修”。

当前建议是直接进入：

1. official DSSAT step-wise 训练接口缺口梳理
2. 训练入口 official-only 收紧
3. 最小 official DSSAT 闭环改造
