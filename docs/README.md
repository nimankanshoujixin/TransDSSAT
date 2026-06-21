# TransDSSAT 文档导航

本文档只负责说明各文档职责和推荐阅读顺序，不承载具体任务状态。

## 自动化入口

1. [CURRENT_AUTOMATION_TASK.md](CURRENT_AUTOMATION_TASK.md)
   - 当前自动化任务的唯一真源。
   - 新任务发布时覆盖 Task Description，并将 Task Status 设为 `Bootstrap`。

2. [CURRENT_AUTOMATION_STATE.md](CURRENT_AUTOMATION_STATE.md)
   - 当前滚动检查点。
   - 每次有意义的 wakeup 后更新最新核验、活跃运行和下一步动作。

3. [AUTOMATION_RUNBOOK.md](AUTOMATION_RUNBOOK.md)
   - 长期执行规则。
   - 包含远端运行规范、tmux 规范、GPU 检查、文档回写和记忆同步规则。

## 方法与实现规范

4. [development-master-outline-cn.md](development-master-outline-cn.md)
   - 项目总纲和阶段目标。

5. [requirements-analysis-cn.md](requirements-analysis-cn.md)
   - 需求分析和模型方向判断。

6. [implementation-plan-cn.md](implementation-plan-cn.md)
   - 实现路线和阶段拆解。

7. [foundation-policy-implementation-plan-cn.md](foundation-policy-implementation-plan-cn.md)
   - 基于 Feishu 新需求整理的基础策略模型路线图。
   - 说明 Environment-Conditioned Transformer-PPO、多环境 DSSAT、action mask 和泛化评测的实施顺序。

8. [testset-eval-protocol-cn.md](testset-eval-protocol-cn.md)
   - 测试集、baseline、评测 protocol 的直接规范。

9. [policy-registry-spec-cn.md](policy-registry-spec-cn.md)
   - policy registry 与文献策略登记规范。

10. [scenario-schema-cn.md](scenario-schema-cn.md)
   - 场景 schema 规范。

11. [evaluation-report-spec-cn.md](evaluation-report-spec-cn.md)
   - 统一评测报告结构规范。

12. [continuous-decision-design-cn.md](continuous-decision-design-cn.md)
   - 连续决策设计。

13. [decision-transformer-data-spec-cn.md](decision-transformer-data-spec-cn.md)
   - Decision Transformer 数据规范。

## 真实场景落地

14. [real-scenario-parameter-checklist-cn.md](real-scenario-parameter-checklist-cn.md)
    - 玉米 / 水稻真实 DSSAT 场景所需参数、样例和中英文字段对应。

15. [collaboration-scope-alignment-cn.md](collaboration-scope-alignment-cn.md)
    - 与稻花香 2 号农事窗口预测任务的范围对齐。

16. [task-gap-analysis-cn.md](task-gap-analysis-cn.md)
    - 当前 TransDSSAT 能力与真实农事窗口产品之间的差距。

## 历史报告与证据

- `research_notes/`
  - 存放历史实验、远端证据、候选配置和缓存信息。
  - 不作为当前自动化任务入口页。

- 历史汇报类文档，例如 `agri-report-*.md`、`literature-baseline.md`、HTML 汇报页。
  - 用于追溯阶段结果，不作为当前执行状态依据。
