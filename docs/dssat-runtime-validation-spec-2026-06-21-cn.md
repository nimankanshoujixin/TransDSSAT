# DSSAT Runtime 改造验证规范（2026-06-21）

## 1. 目的

本规范用于约束后续 gym-DSSAT 风格的 official DSSAT 改造工作，确保：

- 不破坏当前真实数据正式运行链路
- 改造后的交互式 DSSAT 与原始 DSSAT 可做严格对照
- 真实数据可以直接作为改造正确性的首要验证集

## 2. 双 Runtime 原则

后续必须同时维护两份 DSSAT runtime：

### 2.1 Vanilla Runtime

- 含义：未改造的原始 official DSSAT runtime
- 用途：
  - 真实数据正式 replay
  - 回归基线
  - patched runtime 正确性对照

### 2.2 Patched Runtime

- 含义：为交互式 RL 改造而复制出的 DSSAT runtime 副本
- 用途：
  - Fortran daily loop 插桩
  - 状态/动作交互实验
  - 后续 official DSSAT step-wise 训练

## 3. 禁止事项

- 不允许直接修改 vanilla runtime
- 不允许用 patched runtime 替换当前正式真实数据运行链路，除非它已通过一致性验证
- 不允许在未完成 vanilla vs patched 对照前启动 patched runtime 训练

## 4. 第一验证集

patched runtime 的第一验证集必须是：

- **真实数据 replay**

原因：

- 当前真实数据输入已经存在
- 这是最接近最终目标的验证口径
- 也是最容易发现“改造破坏了原始 DSSAT 语义”的方式

## 5. 第一验证流程

在没有引入任何额外交互动作差异的条件下：

1. 准备同一份真实数据输入
2. 用 vanilla runtime 跑一次
3. 用 patched runtime 跑一次
4. 比较关键输出

至少比较：

- `Summary.OUT`
- `PlantGro.OUT`
- `SoilWat.OUT`
- `SoilNi.OUT`
- 最终产量
- 关键日状态轨迹

## 6. 通过标准

若 patched runtime 在“无交互动作差异”条件下与 vanilla runtime 输出一致，则：

- 说明改造尚未破坏基础仿真语义
- patched runtime 才有资格进入下一步交互式环境验证

若不一致，则：

- 视为改造失败或插桩破坏原始行为
- 必须先修复，再谈训练

## 7. 第二验证流程

只有第一验证通过后，才进入第二层验证：

- 在指定日步注入已知动作
- 检查 patched runtime 是否按预期改变后续状态与最终结果

这一步才是在验证“交互能力是否正确”，而不是“原始语义是否被保留”。

## 8. 当前执行含义

因此，当前最正确的工程顺序是：

1. 保留 vanilla runtime
2. 复制 patched runtime
3. 做真实数据一致性回归
4. 再做交互验证
5. 最后才进入训练
