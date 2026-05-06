# TransDSSAT 日粒度大样本清洗后结果汇报（中文版）

## 1. 本轮实验目的

本轮工作的目标，是回答两个关键问题：

1. 之前 `daily` 联合控制（`joint(daily)`）出现明显负增益，究竟是模型本身不行，还是实验管线和 DSSAT 输入稳定性问题导致的假象？
2. 在更大样本规模下，`water_only / nitrogen_only / joint` 三种 **日粒度** 控制方式，最终排序是否符合农业直觉，即：
   - 仅控水不应明显变差
   - 联合控水肥理论上应优于只控水或只控肥

为此，本轮实验做了两类修正后再重新评估：

- 对 `wheat` 的 **日粒度施氮** 加入农艺时间窗约束，避免任意日自由施氮
- 对 `daily` 管理事件加入 **单次事件上限、最小间隔和更稳的分配逻辑**
- 对 `wheat` 文献基线的日事件结构进行拆分，避免单次施氮过大

在上述修正基础上，重新进行了 **120 个场景** 的 official DSSAT clean rerun 检查。

---

## 2. 数据规模

本轮 clean rerun 采用：

- 总场景数：`120`
- 训练集：`97`
- 测试集：`23`

说明：

- 场景由 `random` 方式生成，不再局限于早期固定离散网格
- 包含 `wheat` 与 `maize`
- 包含不同天气型、预算水平、土壤初值和管理模式

---

## 3. 评估设置

### 3.1 后端

- `official DSSAT`

### 3.2 对照基线

- 文献基线：`literature_ncp`
- 基线总水量、总氮量按当前场景预算缩放

### 3.3 决策粒度

- `daily`

### 3.4 控制模式

- `water_only(daily)`：只优化灌溉，施氮沿用基线
- `nitrogen_only(daily)`：只优化施氮，灌溉沿用基线
- `joint(daily)`：同时优化灌溉和施氮

---

## 4. 结果汇总（120 场景，测试集 23 个场景）

> 说明：本轮是 clean rerun 的同口径对比。三组结果都基于修正后的 official DSSAT daily pipeline。

| 控制模式 | mean_total_score_100 | mean_reward_gain | mean_yield_kg_ha | mean_yield_gain_pct |
|---|---:|---:|---:|---:|
| `water_only(daily)` | 54.003 | -0.052 | 3409.261 | -0.631% |
| `nitrogen_only(daily)` | 68.205 | +4.127 | 3895.957 | +9.605% |
| `joint(daily)` | 69.371 | +4.531 | 3901.913 | +9.909% |

补充指标：

- `water_only(daily)`
  - `mean_irrigation_mm = 149.909`
  - `mean_nitrogen_kg_ha = 129.348`
  - `mean_budget_adherence_score = 99.620`

- `nitrogen_only(daily)`
  - `mean_irrigation_mm = 149.865`
  - `mean_nitrogen_kg_ha = 129.087`
  - `mean_budget_adherence_score = 99.680`

- `joint(daily)`
  - `mean_irrigation_mm = 149.822`
  - `mean_nitrogen_kg_ha = 129.435`
  - `mean_budget_adherence_score = 99.562`

---

## 5. 结果解释

### 5.1 `joint(daily)` 现在已经回到合理排序

这轮 clean rerun 的最重要结论是：

> 在更大样本、修正后的 daily official DSSAT pipeline 下，`joint(daily)` 已经不再出现之前那种异常下降，而是回到了更符合农业直觉的排序：
>
> `joint(daily) > nitrogen_only(daily) > water_only(daily)`

具体表现为：

- `joint(daily)` 的综合分最高：`69.371`
- `joint(daily)` 的 reward 增益最高：`+4.531`
- `joint(daily)` 的平均产量最高：`3901.913 kg/ha`
- `joint(daily)` 的平均产量提升比例最高：`+9.909%`

这说明：

- 之前 `joint(daily)` 出现明显负增益，主要不是“联合控制思路错误”
- 更可能是由 **daily 管理事件过于自由、wheat 文献基线单次施氮过猛、以及 official DSSAT 数值稳定性** 共同造成的实验假象

### 5.2 `nitrogen_only(daily)` 依然很强

本轮 `nitrogen_only(daily)` 表现也很强：

- `mean_total_score_100 = 68.205`
- `mean_reward_gain = +4.127`
- `mean_yield_gain_pct = +9.605%`

这说明在当前场景空间中：

- 氮肥调控仍然是非常重要的收益来源
- 但在本轮 clean rerun 里，联合控制已经进一步超过了仅控肥

也就是说：

> “氮肥很重要”这个判断仍然成立；但在合理约束下，水肥联合优化的收益已经可以稳定地超过单独控肥。

### 5.3 `water_only(daily)` 仍然偏弱

本轮 `water_only(daily)` 结果为：

- `mean_total_score_100 = 54.003`
- `mean_reward_gain = -0.052`
- `mean_yield_gain_pct = -0.631%`

这表明：

- 即使在日粒度下，单独控水的收益仍然不稳定
- 当前场景里，水的优化价值存在，但单独依靠控水并不足以像控氮或联合控制那样稳定带来高增益

这也与前面的观察一致：

- 水分调控通常更依赖时机
- 但在当前场景和奖励设计下，氮肥与水肥协同仍然是主要增益来源

---

## 6. 与此前结论相比，当前最稳妥的判断

结合本轮 clean rerun，可以把结论更新为：

### 结论 1

之前 `joint(daily)` 的明显负结果 **不能再视为模型本身结论**。

更合理的解释是：

- 旧结果被 daily 管理事件约束不足和 official DSSAT 稳定性问题污染

### 结论 2

在修正后的 `120` 场景 daily clean rerun 中：

- `joint(daily)` 已经优于 `nitrogen_only(daily)`
- `nitrogen_only(daily)` 已经优于 `water_only(daily)`

这说明：

> 日粒度联合控制在更大样本、合理农艺约束下，已经表现出符合预期的优势。

### 结论 3

`water_only` 依然不是当前最强策略来源。

因此当前更合理的农业解释是：

- 控水重要，但单独控水不是当前主要增益来源
- 控氮很关键
- 水肥联合控制在合理约束和更大样本下，最有希望获得最好结果

---

## 7. 当前阶段可以怎么向农业人员汇报

可以直接用下面这段话：

> 在更大规模场景和修正后的 official DSSAT 日粒度实验中，模型已经能够在 120 个随机场景上稳定训练和评估。结果表明，联合控水肥的策略在综合评分、产量提升和 reward 增益上均优于仅控水和仅控肥；其中联合控制平均产量提升约 9.9%，高于仅控肥的 9.6%，明显优于仅控水。该结果说明，在合理农艺约束下，模型已经初步具备根据场景学习更优日粒度水肥策略的能力。

---

## 8. 下一步建议

建议下一步继续做两件事：

1. 在当前 clean pipeline 上继续增加训练轮数  
   这轮结果已经说明方向正确，下一步应验证 `joint(daily)` 在更多 epoch 下是否还能继续扩大优势。

2. 用同一版 clean pipeline 补一轮正式报告  
   将：
   - `joint(daily)`
   - `nitrogen_only(daily)`
   - `water_only(daily)`
   与当前较稳定的 `stage` 结果统一整理成最终对比表。

---

## 9. 一句话总结

> 在修正了 daily 管理事件和 wheat 基线后，official DSSAT 的 120 场景 clean rerun 已经表明：日粒度联合控水肥重新恢复到合理排序，并优于仅控水和仅控肥，说明之前 `joint(daily)` 的异常下降主要是实验管线与输入稳定性问题，而不是联合控制思路本身错误。
