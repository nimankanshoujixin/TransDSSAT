# Proxy Footprint Quarantine Audit（2026-06-21）

## 1. 目的

本审计只回答一个问题：

- 在 official-DSSAT-only 主线已经确定后，仓库里剩余的 `proxy` 足迹哪些必须迁移，哪些可以隔离，哪些暂时只能保留为历史/调试路径

## 2. 当前判断原则

- 主训练入口、主评测入口、主场景入口：
  - 必须 default-official
- 为了历史复现实验而保留的脚本：
  - 可以保留，但必须视为 legacy/debug，不得重新进入主线
- 真正阻塞 official step-wise 训练的，不是“还有 proxy 代码存在”，而是：
  - 交互式 official DSSAT backend 还没有替换掉当前 replay wrapper

## 3. 本轮已收紧到 official 的默认入口

- [`/G:/TransDSSAT/transdssat/scenarios.py`](/G:/TransDSSAT/transdssat/scenarios.py)
  - `build_quzhou_scenarios(...)`
  - `build_realistic_quzhou_scenarios(...)`
  - 默认 `engines` 已改为 `("dssat_official",)`
- [`/G:/TransDSSAT/scripts/generate_dataset.py`](/G:/TransDSSAT/scripts/generate_dataset.py)
  - 默认 `--engines` 已改为 `dssat_official`
- [`/G:/TransDSSAT/transdssat/testset.py`](/G:/TransDSSAT/transdssat/testset.py)
  - `generate_general_random_test_set(...)`
  - `generate_training_scenario_pool(...)`
  - `generate_literature_matched_slices(...)`
  - 已经是 official 默认

这意味着新一轮如果有人直接调用默认场景/数据入口，默认不会再掉回 proxy。

## 4. 应继续保留但明确隔离的 proxy 路径

以下对象目前更适合作为 legacy/debug 保留，而不是本轮强行重写：

- [`/G:/TransDSSAT/transdssat/environments/proxy.py`](/G:/TransDSSAT/transdssat/environments/proxy.py)
  - 历史代理环境实现
  - 仍被旧单测和兼容路径引用
- [`/G:/TransDSSAT/scripts/compare_stepwise_semantics.py`](/G:/TransDSSAT/scripts/compare_stepwise_semantics.py)
  - 历史语义对比工具
- [`/G:/TransDSSAT/scripts/run_ablation_report.py`](/G:/TransDSSAT/scripts/run_ablation_report.py)
  - 历史 ablation/报告脚本
- [`/G:/TransDSSAT/scripts/validate_stepwise_rollout.py`](/G:/TransDSSAT/scripts/validate_stepwise_rollout.py)
  - 仍依赖旧 proxy rollout 语义

这些文件当前不应被删除，原因是：

- 它们仍然承载历史结果复现和回溯价值
- 它们不是 official 主线切换的关键阻塞项
- 贸然重写只会扩大改动面，而不会解决真实交互式 DSSAT 缺口

## 5. 当前最关键的非 proxy 问题

仓库现在最大的主线缺口已经不是“默认值是否还带 proxy”，而是：

- [`/G:/TransDSSAT/transdssat/dssat/interactive_controller.py`](/G:/TransDSSAT/transdssat/dssat/interactive_controller.py)
  - 仍是 `ReplayBridgeInteractiveController`
- [`/G:/TransDSSAT/transdssat/environments/stepwise.py`](/G:/TransDSSAT/transdssat/environments/stepwise.py)
  - official `interactive_patched` 虽已贯通 Python API，但真实 runtime 侧仍未进入日级交互

也就是说：

- proxy 默认入口的问题，本轮已经进一步收紧
- 还没完成的是 official backend 的真实 daily loop，而不是更多 proxy 清理

## 6. 建议的处置策略

当前最合理的 quarantine 策略是：

1. 继续保留 legacy proxy 文件，但不让默认入口、训练入口、评测入口指向它们
2. 在后续文档里把这些路径标注为 archival/debug only
3. 把主要工程精力集中在 patched runtime daily interaction loop

## 7. 结论

截至本轮：

- mainline 默认入口已进一步收紧到 official DSSAT
- 剩余 proxy 足迹已足够集中，可以被视为 quarantine 状态
- 下一步不应继续做大范围 proxy 迁移，而应直接推进 patched runtime 的真实交互层实现
