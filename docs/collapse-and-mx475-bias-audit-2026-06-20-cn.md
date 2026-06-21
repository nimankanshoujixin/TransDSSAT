# late-training collapse 与 mx475 偏高归因审计报告（2026-06-20）

## 1. 审计范围

本次只做 CPU-safe / artifact-only 审计，不启动新的训练或正式 replay。使用的既有产物：

- 训练轨迹：
  - `/fs/fast/u2021201693/lym/TransDSSAT/artifacts/stepwise_ppo_rice_maize_training_data_rerun_20260620_1710/metrics.json`
- `mx475` 原始管理 replay：
  - `/fs/fast/u2021201693/lym/TransDSSAT/artifacts/real_subset_replay_audit_mx475_full/real_subset_replay_audit.json`
- `best checkpoint` 的 real-subset replacement replay：
  - `/fs/fast/u2021201693/lym/TransDSSAT/artifacts/real_subset_checkpoint_eval_full_rerun_20260620/real_subset_checkpoint_eval_full_rerun_report.json`

## 2. 结论摘要

### 2.1 late-training collapse

结论：这不是“末期轻微过拟合”那么简单，而是更接近一个会收敛到 `0` 灌溉 / `0` 施氮的退化 attractor。

证据：

- `best checkpoint` 在 `epoch 5`，随后不是小幅波动，而是投入量持续萎缩。
- 到 `epoch 15`，验证集已掉到：
  - `mean_irrigation_mm = 36.768`
  - `mean_nitrogen_kg_ha = 1.101`
- 到 `epoch 18-20`，验证集和测试集都稳定为：
  - `mean_irrigation_mm = 0.0`
  - `mean_nitrogen_kg_ha = 0.0`
- 与此同时，指标同步恶化而不是“省投入但更优”：
  - `val mean_reward_gain`: `epoch 5 = 1.594913` -> `epoch 20 = -0.720261`
  - `test mean_reward_gain`: `epoch 5 = 1.551148` -> `epoch 20 = -0.876687`
  - `val mean_yield_floor_gap_ratio`: `0.412211` -> `0.458747`
  - `test mean_yield_floor_gap_ratio`: `0.404294` -> `0.451843`

补充判断：

- 这条退化线并不伴随 KL 爆炸；`epoch 16-20` 的 `approx_kl` 只有 `0.003615-0.012601`。
- 说明 `target_kl` 早停只是在抑制过大的单步更新，不能阻止策略逐步滑向“零投入局部最优”。
- 因此“只加早停”只能掩盖问题，不能算根治。

关键 epoch 摘要：

| epoch | val reward_gain | val yield_floor_gap_ratio | val irrigation_mm | val nitrogen_kg_ha | test reward_gain | test irrigation_mm | test nitrogen_kg_ha |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 5 | 1.594913 | 0.412211 | 196.626 | 67.435 | 1.551148 | 193.627 | 65.601 |
| 9 | 1.638358 | 0.420207 | 166.801 | 33.016 | 1.694777 | 162.789 | 31.569 |
| 15 | -0.233426 | 0.451190 | 36.768 | 1.101 | -0.629350 | 24.598 | 0.366 |
| 18 | -0.720261 | 0.458747 | 0.000 | 0.000 | -0.876687 | 0.000 | 0.000 |
| 20 | -0.720261 | 0.458747 | 0.000 | 0.000 | -0.876687 | 0.000 | 0.000 |

### 2.2 `mx475_migrated` 偏高归因

结论：`mx475` 的系统性偏高不是单纯由 PPO replacement 引起，也不是单纯由 DSSAT baseline 引起；两层误差都存在，但 replacement 在大多数 treatment 上继续把偏高推得更大。

分解后可得到：

1. DSSAT baseline replay 相对真实值，已经整体偏高。
2. PPO replacement replay 相对 baseline replay，又进一步把模拟产量抬高了一截。

`mx475` 的三方对照（默认只报 `mean / min / max`）：

| 指标 | mean | min | max |
| --- | ---: | ---: | ---: |
| 真实产量 `observed_yield_kg_ha` | `5385.000` | `4815.000` | `6750.000` |
| DSSAT baseline replay `simulated_yield_kg_ha` | `5728.250` | `5124.000` | `7353.000` |
| PPO replacement replay `simulated_yield_kg_ha` | `5991.125` | `5392.000` | `7113.000` |
| baseline 相对真实误差 `kg/ha` | `343.250` | `57.000` | `603.000` |
| baseline 相对真实误差比 | `0.063733` | `0.009870` | `0.092665` |
| replacement 相对真实误差 `kg/ha` | `606.125` | `303.000` | `1237.000` |
| replacement 相对真实误差比 | `0.117125` | `0.052468` | `0.256906` |
| replacement 相对 baseline 增量 `kg/ha` | `262.875` | `-240.000` | `928.000` |
| replacement 相对 baseline 增量比 | `0.053392` | `-0.035556` | `0.192731` |

补充事实：

- `8` 个 treatment 里，`7` 个在 replacement 后比 baseline 更高。
- 只有 `tr08` 出现了 replacement 低于 baseline。
- 所以当前 `mx475` 偏高不能直接表述成“baseline 本来就高，所以 PPO 没问题”；更准确的说法是：
  - baseline 已经有约 `+6.37%` 的系统正偏差；
  - replacement 又额外叠加了约 `+5.34%` 的平均正偏差；
  - 二者叠加后，replacement 对真实值的平均正偏差扩大到约 `+11.71%`。

## 3. 对下一轮方法修改的判断

### 3.1 是否只加 early stopping

结论：不建议把下一轮动作简化为“只加 early stopping”。

原因：

- 当前最优点已经能被 checkpoint 选择抓到，但训练主轨迹仍会继续收缩到零投入策略。
- 这说明问题不只是“后几轮白跑了”，而是训练目标本身允许并鼓励退化 attractor 存在。
- 只加 early stopping 最多能保住产物，不能解释也不能消除 collapse。

### 3.2 建议的优先修正方向

建议优先级：

1. 强化 checkpoint selection 约束，而不是只看单一 reward 指标。
   - 推荐至少加入 `minimum irrigation / nitrogen activity` 或 `yield_floor_attainment` 约束。
   - 更稳妥的是使用 lexicographic 规则：先过滤明显零投入/低达标 checkpoint，再按主指标排序。
2. 给训练目标增加反退化 guardrail。
   - 方向应优先考虑“禁止零投入塌缩”，而不是单纯鼓励更高 reward。
   - 可选形式包括：极低投入惩罚、低于 floor 时的更强代价、或 season-level activity floor。
3. 保留 early stopping / patience，但只把它当外层保险。
   - 它应该防止无意义继续训练，不应承担主要病灶修复责任。

## 4. 最终判断

本阶段任务可视为完成，已经回答了当前 Bootstrap 任务要求的三个问题：

1. `late-training collapse` 是否只是普通末期回落：
   - 不是，更接近零投入退化 attractor。
2. `mx475` 偏高是否可以直接归咎 PPO：
   - 不可以，baseline 本身已正偏，但 replacement 又在其上继续抬高。
3. 下一轮是否只加 early stopping：
   - 不建议；应同时修改 checkpoint selection 与 collapse guardrail。
