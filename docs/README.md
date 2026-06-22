# TransDSSAT 文档导航

## 先读这些

1. [OFFICIAL_DSSAT_ONLY_POLICY_CN.md](OFFICIAL_DSSAT_ONLY_POLICY_CN.md)
   - 当前最高优先级路线政策
   - 后续训练与评估只允许 official DSSAT
2. [CURRENT_AUTOMATION_TASK.md](CURRENT_AUTOMATION_TASK.md)
   - 当前自动化任务的唯一事实来源
3. [CURRENT_AUTOMATION_STATE.md](CURRENT_AUTOMATION_STATE.md)
   - 当前滚动状态与下一步动作
4. [AUTOMATION_RUNBOOK.md](AUTOMATION_RUNBOOK.md)
   - 长期执行规则

## 当前解释规则

从现在开始，文档解释遵循以下优先级：

1. `OFFICIAL_DSSAT_ONLY_POLICY_CN.md`
2. `CURRENT_AUTOMATION_TASK.md`
3. `CURRENT_AUTOMATION_STATE.md`
4. 其他设计/规划文档

如果历史文档中出现：

- proxy-first
- proxy baseline
- proxy authoritative
- “先 proxy 后 official” 这类主路线表述

则一律视为**历史归档信息**，不再作为当前执行依据。

## 当前主线文档

- [OFFICIAL_DSSAT_ONLY_POLICY_CN.md](OFFICIAL_DSSAT_ONLY_POLICY_CN.md)
- [CURRENT_AUTOMATION_TASK.md](CURRENT_AUTOMATION_TASK.md)
- [CURRENT_AUTOMATION_STATE.md](CURRENT_AUTOMATION_STATE.md)
- [AUTOMATION_RUNBOOK.md](AUTOMATION_RUNBOOK.md)
- [dssat-runtime-parity-baseline-2026-06-21-cn.md](dssat-runtime-parity-baseline-2026-06-21-cn.md)
- [proxy-footprint-quarantine-2026-06-21-cn.md](proxy-footprint-quarantine-2026-06-21-cn.md)
- [foundation-policy-implementation-plan-cn.md](foundation-policy-implementation-plan-cn.md)
- [implementation-plan-cn.md](implementation-plan-cn.md)
- [development-master-outline-cn.md](development-master-outline-cn.md)
- [canonical-policy-route-2026-06-15-cn.md](canonical-policy-route-2026-06-15-cn.md)

## 历史材料说明

`research_notes/`、历史报告、历史 case study、旧 HTML 汇报页仍然保留，用于追溯项目演进。

但它们不是当前主线规范。

尤其是其中凡是把 proxy 视为可接受主路线的内容，均已失效。
