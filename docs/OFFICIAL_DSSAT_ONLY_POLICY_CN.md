# TransDSSAT Official DSSAT 唯一路线政策

## 1. 结论

自本文档生效起，TransDSSAT 后续训练与评估路线统一为：

- 只允许使用 official DSSAT 进行训练与评估

以下路线不再被视为可接受主线：

- proxy 训练
- proxy 排名
- proxy 评估
- proxy 作为“先训练、后校验”的默认主流程

## 2. 原因

用户已经明确判定：

1. proxy 与真实 DSSAT 差距过大
2. proxy 训练出的策略不可信
3. 后续结果不能再建立在 proxy 语义上

因此，后续不得再把 proxy 输出作为：

- 模型优劣依据
- checkpoint 选择依据
- 正式实验报告依据
- 训练路线合理性的依据

## 3. 执行规则

### 3.1 训练

- PPO / Transformer / RL 主训练只允许 official DSSAT
- 如果 official DSSAT 接口尚未补齐，应先补接口，不得退回 proxy 训练

### 3.2 评估

- 验证集、测试集、真实场景子集评估都必须以 official DSSAT 为准
- 不再接受 proxy 指标作为正式结果

### 3.3 文档口径

- 当前及后续规范性文档，必须以 official DSSAT 为唯一主路线
- 历史文档中若出现 proxy-first、proxy baseline、proxy authoritative 等表述，一律视为过时归档信息，不再具有指导效力

### 3.4 自动化执行

- 自动化 wakeup 不得再启动 proxy-backed 训练、rollout、dry-run 或结果分析作为主线工作
- 遇到 official DSSAT 接口缺口，应优先记录缺口并修补缺口，而不是以 proxy 替代

### 3.5 交互实现参考

- official DSSAT 的 step-wise 交互实现，优先参考 gym-DSSAT 路线
- 不以“重新设计一个 surrogate / proxy / 近似环境”作为替代方案
- 后续如需实现 daily interactive RL 环境，应优先考虑：
  - DSSAT Fortran daily loop 插桩
  - 状态读取事件
  - 动作写回事务
  - Python 侧与 DSSAT 的进程间通信

### 3.6 Runtime 改造与验证规则

- 必须保留一份原始 vanilla DSSAT runtime
- 任何交互式改造都必须在复制出的 patched DSSAT runtime 上进行
- 不允许直接在当前 vanilla runtime 上修改并替换正式真实数据运行链路

改造正确性的第一验证方式必须是：

1. 使用同一份真实数据输入
2. vanilla DSSAT 运行一次
3. patched DSSAT 运行一次
4. 对比输出是否一致

在“未引入交互动作差异”的情况下：

- 若 patched 与 vanilla 输出不一致，则视为改造错误
- 不得进入训练闭环

因此，真实数据不仅是最终评估数据，也是 patched DSSAT 的首要回归验证数据。

## 4. 当前工作含义

当前最重要的工作不再是继续分析 proxy 表现，也不是继续修 proxy。

当前最重要的工作是：

1. 审计当前代码距离 official DSSAT 直接训练还差什么
2. 定义最小可行 official DSSAT 训练闭环
3. 只做 `1-3` 个最小工程改动，把主路线切回 official DSSAT

## 5. Startup Contract Smoke

在真正的 Fortran interactive patch 完成之前，允许做一层更窄的 startup-contract smoke：

- script: `scripts/dssat_interactive_boundary_probe.py`
- purpose: 验证 `interactive controller -> patched_runtime_subprocess -> env/manifest/protocol` 连线是否成立
- scope: 仅限启动合同验证

这层 smoke 不能替代：

- vanilla-vs-patched 的真实数据 parity gate
- copied patched runtime 上真正的 Fortran interactive 实现
