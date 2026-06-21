# TransDSSAT 唯一主线策略合同（2026-06-15）

## 目标定义

TransDSSAT 的唯一主线，不再定义为：

- proxy 驱动的 step-wise PPO
- 离散动作优先的 step-wise PPO
- “先用替代物跑通，再以后切到真实 DSSAT”的路线

从现在开始，唯一合法主线定义为：

> 使用与 Decision Transformer 同构的序列输入输出合同，但由于当前没有专家策略序列数据，不走监督式 DT，而走 PPO 在线强化学习；动作输出为连续数值水肥决策；奖励与最终结果裁判由 official DSSAT 给出。

## 1. 训练范式

训练范式固定为：

- `Decision-Transformer-style sequence policy interface`
- `PPO online RL training`

原因：

- 我们要的是 DT 风格的条件化序列决策接口
- 但目前没有足够可信的专家策略轨迹用于监督学习
- 因此训练算法用 PPO，输入输出合同保留 DT 结构

禁止再把以下路线当主线：

- 纯 supervised behavior cloning 作为最终路线
- 纯离散 masked PPO 作为最终路线
- proxy-only reward PPO 作为最终路线

## 2. 输入合同

策略输入必须与 DT 风格一致，按“静态上下文 + 滚动历史 token 序列”组织。

### 2.1 静态上下文

每个 season / scenario 固定上下文必须包含：

- soil context
- weather context
- crop context
- cultivar context
- objective context
- budget context

### 2.2 时序 token

每个决策步 `t` 的 token 必须保持如下语义：

```text
x_t = [
  observation_t,
  previous_action_{t-1},
  previous_reward_{t-1},
  time_encoding_t
]
```

其中：

- `observation_t` 是当前可用状态
- `previous_action_{t-1}` 必须是上一时刻真实执行的连续水肥值
- `previous_reward_{t-1}` 必须对应上一时刻及其后续 official DSSAT 记账结果
- `time_encoding_t` 表示季节内时序位置

如果需要额外约束特征，只允许加入：

- 普适物理约束
- 预算剩余
- 操作间隔
- 阶段约束

不允许再把以下内容当作主线输入中心：

- discrete action id one-hot
- discrete action table index
- “上一动作是不是 discrete” 这类兼容层特征

这些如果暂时还在代码里，只能视为待删除技术债，不再是设计合法组成。

## 3. 输出合同

输出合同固定为连续数值决策，而不是候选动作选择。

唯一合法动作输出是：

```text
a_t = [
  irrigation_amount_mm,
  nitrogen_amount_kg_ha
]
```

要求：

- 两个量都是连续数值
- `noop` 由数值为 `0` 表达，不再依赖离散类别
- 合法性裁剪只能基于通用约束完成

不再接受以下主线语义：

- 预定义若干水肥选项供模型分类选择
- 用离散动作 id 再映射为水肥量
- 用 gated discrete 作为默认主动作语义

## 4. Reward 合同

奖励合同固定为：

- 训练 reward 的最终来源必须是 official DSSAT

这条要求比“最终评估用 DSSAT”更强：

- 不只是最终报告由 DSSAT 打分
- 连训练优化方向也必须受 official DSSAT 支配

因此以下路线不再合法：

- `dssat_proxy` 直接作为主训练 reward backend
- 用 proxy reward 排出“权威最优模型”
- 用 proxy 合同内 `reward_gain` 替代真实农业目标

如果 official DSSAT 成本过高，允许做的只有工程优化：

- batched execution
- low-frequency update / rerank
- asynchronous rollout collection
- cache / replay / delayed credit assignment

但不允许把“成本高”变成继续沿用 proxy 主裁判的理由。

## 5. official DSSAT 的角色

official DSSAT 不再是旁路能力，而必须进入主合同。

最少要求：

1. 它定义最终 reward 与 outcome
2. 它定义正式模型优劣排序
3. 它参与训练闭环，而不是只在训练后做展示性复核

如果主循环不能每一步都直接调用 official DSSAT，也必须保证：

- PPO 所优化的信号最终仍由 official DSSAT 回传或校准
- proxy 不能单独决定策略排名

## 6. 对当前代码的纠偏结论

当前以下内容不再属于可接受主线：

1. `dssat_proxy` 作为默认训练引擎
2. `discrete` 作为默认 action mode
3. observation/history 中围绕离散 action id 的主特征设计
4. 用 proxy 语义文档定义“authoritative baseline”
5. 将连续动作仅保留为 sensitivity check 或可选分支

这些内容即便暂时还存在于仓库，也都应视为：

- 历史兼容层
- 待移除技术债
- 非主线实现

## 7. 后续重构顺序

接下来应按这个顺序做：

1. 重写主训练合同文档与任务边界
2. 清理离散默认项与 proxy 默认项
3. 重构序列 token，使其只围绕连续动作与真实回报
4. 重构 reward 链路，使 official DSSAT 成为训练信号源
5. 再恢复新实验

## 8. 执行约束

在完成上述重构前：

- 不继续扩展新的 proxy 主线实验
- 不再发布新的“proxy authoritative baseline”
- 不再把离散主线结果当作最终农业结论

当前目标不是“再多跑几轮”，而是：

> 先把实现路线纠正到与最终目标同构，再恢复训练。
