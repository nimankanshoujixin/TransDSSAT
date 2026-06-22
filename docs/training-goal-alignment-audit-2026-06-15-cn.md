# TransDSSAT 训练主线与最终目标对齐审计（2026-06-15）

## 审计目标

本审计只回答一个问题：

> 当前主训练逻辑，是否真的在逼近“基于真实场景输入，生成农学合理、产量有竞争力、并能被 official DSSAT 支撑或校验的水肥决策模型”这一最终目标？

结论先行：

- 当前主线 **没有完全对齐** 最终目标。
- 偏差不是单点问题，而是一个串联的替代链：
  - `proxy` 主训练
  - `discrete` 主动作语义
  - 以 `proxy` 合同为中心的奖励与排名
  - official DSSAT 仅作为旁路能力存在，而不是主裁判

因此，当前系统更准确的描述不是“真实 DSSAT 驱动的连续水肥决策训练线”，而是：

> 一个以 `dssat_proxy` 为核心、带有连续动作实验分支、但主合同仍受离散 proxy 语义支配的 step-wise PPO 训练线。

## 最关键的不对齐项

### 1. 主训练后端与最终目标不对齐

最终目标要求：

- 至少让主策略优化方向与 official DSSAT 一致
- 不能长期由 proxy 语义单独决定“什么叫好策略”

当前实现：

- [`scripts/train_stepwise_ppo.py:145`](/G:/TransDSSAT/scripts/train_stepwise_ppo.py:145) 把训练场景引擎硬编码为 `engines=("dssat_proxy",)`
- [`transdssat/testset.py:236`](/G:/TransDSSAT/transdssat/testset.py:236)
- [`transdssat/testset.py:340`](/G:/TransDSSAT/transdssat/testset.py:340)
- [`transdssat/testset.py:434`](/G:/TransDSSAT/transdssat/testset.py:434)
  都默认把训练/评测场景池建在 `dssat_proxy` 上
- [`transdssat/environments/adapters.py:21`](/G:/TransDSSAT/transdssat/environments/adapters.py:21) 明确 official DSSAT 是 `Season-level official DSSAT backend`
- [`transdssat/stepwise_adapter.py:87`](/G:/TransDSSAT/transdssat/stepwise_adapter.py:87) 又明确拒绝 `dssat_official`

判断：

- official DSSAT 不是没接上，而是没有进入当前主训练合同
- 这意味着当前训练最优解，只能保证“对 proxy 最优”，不能保证“对真实 DSSAT 更优”

这项问题是 `P0`。

### 2. 主动作语义仍然偏离“连续数值决策”目标

最终目标要求：

- 水肥应以连续数量决策为主语义
- 离散动作只能是兼容层或过渡层，不能继续做主裁判

当前实现：

- [`scripts/train_stepwise_ppo.py:79`](/G:/TransDSSAT/scripts/train_stepwise_ppo.py:79) 允许 `discrete` 和 `gated_continuous`
- [`scripts/train_stepwise_ppo.py:80`](/G:/TransDSSAT/scripts/train_stepwise_ppo.py:80) 默认仍是 `discrete`
- [`transdssat/stepwise_ppo.py:26`](/G:/TransDSSAT/transdssat/stepwise_ppo.py:26) 直接定义了 `STEPWISE_DISCRETE_ACTION_DIM`
- [`transdssat/environments/stepwise.py:77`](/G:/TransDSSAT/transdssat/environments/stepwise.py:77) 环境初始化时仍挂载 `discrete_action_table`
- [`transdssat/stepwise_ppo.py:184`](/G:/TransDSSAT/transdssat/stepwise_ppo.py:184) 到 [`transdssat/stepwise_ppo.py:219`](/G:/TransDSSAT/transdssat/stepwise_ppo.py:219) 仍显式编码上一时刻是否为 `discrete`
- [`transdssat/scenarios.py:185`](/G:/TransDSSAT/transdssat/scenarios.py:185) 还保留了 `action_table_id = "deprecated_v1_joint_discrete"`

判断：

- 虽然执行接口已经支持连续量，但主训练语义还没有真正完成“去离散中心化”
- 现在更像“连续动作是实验分支，离散动作仍是主合同”

这项问题是 `P0`。

### 3. 当前奖励合同未必与“高产且合理”目标一致

最终目标要求：

- 奖励必须稳定推动更高质量农业行为
- 不能出现“少投入但低产，也能因为记账合同而被认为更优”的系统性偏差

当前实现：

- [`transdssat/rewarding.py:15`](/G:/TransDSSAT/transdssat/rewarding.py:15) 默认合同是 `reward_v2`
- [`transdssat/rewarding.py:181`](/G:/TransDSSAT/transdssat/rewarding.py:181) 的 `yield_floor_reference` 使用的是预算线性公式
- [`transdssat/rewarding.py:194`](/G:/TransDSSAT/transdssat/rewarding.py:194) 再乘 `yield_floor_penalty`
- 已发布结果文档自己也承认：
  - [`docs/stepwise-ppo-transformer-rerun-result-report-cn.md:19`](/G:/TransDSSAT/docs/stepwise-ppo-transformer-rerun-result-report-cn.md:19)
  - 最优 checkpoint 几乎把施氮压到接近 `0`
  - 优势主要来自资源节省，不是更高产

判断：

- 当前奖励合同已经能防止最极端崩坏，但还没有证明它与“真实高产、合理管理”的目标严格一致
- 特别是 `yield_floor_reference` 现在更像工程护栏，不像基于 crop/cultivar/site 校准的真实产量目标

这项问题是 `P0`。

### 4. 当前“权威基线”定义仍然是 proxy 内部定义，不是真实目标定义

最终目标要求：

- 权威基线应尽量接近最终部署目标
- 不能把“proxy 合同内最优”误当成“农业上更优”

当前实现和文档口径：

- [`docs/stepwise-ppo-transformer-rerun-result-report-cn.md:17`](/G:/TransDSSAT/docs/stepwise-ppo-transformer-rerun-result-report-cn.md:17)
- [`docs/stepwise-ppo-transformer-rerun-result-report-cn.md:19`](/G:/TransDSSAT/docs/stepwise-ppo-transformer-rerun-result-report-cn.md:19)
- [`docs/stepwise-ppo-transformer-rerun-result-report-cn.md:173`](/G:/TransDSSAT/docs/stepwise-ppo-transformer-rerun-result-report-cn.md:173)

这些文档其实已经明确承认：

- 当前“authoritative”只在 proxy 合同内成立
- 不能直接外推到真实生产决策

判断：

- 这不是文档问题，而是训练目标定义问题
- 只要主排名体系还由 proxy 合同决定，case study 改进就可能在错误裁判下收敛

这项问题是 `P1`。

### 5. 数据池“真实化”不等于仿真目标“真实化”

最终目标要求：

- 真实天气/土壤来源只是第一步
- 更重要的是仿真后端、产量尺度、品种参数、奖励目标一起对齐

当前实现：

- realistic pool 已经做了真实天气/土壤替换
- 但其训练引擎仍挂在 `dssat_proxy`
- [`scripts/generate_dataset.py:35`](/G:/TransDSSAT/scripts/generate_dataset.py:35) 默认后端仍是 `["wofost_proxy", "dssat_proxy"]`

判断：

- 当前“更真实”主要发生在输入分布层
- 但输出裁判层和策略优化层仍然是 proxy 语义
- 所以 realistic pool 不能自动推出 realistic agronomic optimum

这项问题是 `P1`。

## 不应继续保留的“临时替代”清单

以下项不应继续以主线身份存在：

1. `dssat_proxy` 作为唯一主训练裁判
2. `discrete` 作为默认主动作模式
3. 用 proxy 合同内 `reward_gain` 直接代表真实农业优劣
4. 用预算驱动的经验 `yield_floor_reference` 代替 cultivar/site 产量标尺
5. 将 official DSSAT 仅保留为“以后再说的一致性检查”

## 建议的整改顺序

### 第一优先级：先重写主合同，再谈新实验

1. 明确官方目标合同
   - 主优化目标要如何与 official DSSAT 对齐
   - official DSSAT 在训练链中承担什么角色：低频校准、rerank、DPO-like preference、还是小样本 critic 校准
2. 明确连续动作主语义
   - 将 `discrete` 改为兼容模式，而不是默认模式
   - 清理 observation/history 中对离散 action id 的中心依赖
3. 重写奖励标尺
   - 用 crop/cultivar/site-aware 的目标产量或收益标尺替代当前经验下限
   - 避免“省投入胜过高产”的系统偏差

### 第二优先级：再处理 official DSSAT 接口重构

1. 定义 step-wise 策略如何映射到 official DSSAT 可评估对象
2. 区分：
   - 高频训练后端
   - 低频真实校准后端
   - 正式报告后端
3. 明确哪些指标必须来自 official DSSAT，而不是 proxy 估计

### 第三优先级：最后才恢复实验

只有当以下条件满足，才应该重启新的 staged run：

1. 主动作语义已改成连续优先
2. 主奖励合同不再鼓励伪优的极端省投入行为
3. official DSSAT 已经进入主评估闭环，而不是纯旁路

## 当前审计结论

当前系统不是“完全错了”，但它确实还停留在一条过渡性训练线：

- 适合做接口打通和快速迭代
- 不适合作为最终农业决策结论的主依据

因此，后续工作重点不该是“继续堆实验”，而该是：

> 先把主训练合同改成真正服务最终目标的合同，再恢复实验。
# 状态更新说明（2026-06-21）

本审计文档对 proxy 主训练路线的风险判断已经被用户最终结论确认：

- proxy 路线不再继续
- 后续 TransDSSAT 训练与评估只允许 official DSSAT

因此，本文件中关于“是否继续保留 proxy 主线”的讨论只保留历史追溯价值，不再作为待决问题。
