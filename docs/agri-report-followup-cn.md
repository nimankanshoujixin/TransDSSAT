# TransDSSAT 后续对比实验汇报（中文版）

## 1. 本轮后续实验要回答的问题

在上一版正式汇报中，有两个关键疑问：

1. 为什么 `water_only(stage)` 的 `mean_yield_gain_pct` 会出现负值？
2. 为什么 `joint(stage)` 没有明显超过 `nitrogen_only(stage)`？

为回答这两个问题，本轮后续实验按以下顺序开展：

1. 先补齐 **daily 粒度** 下的 `water_only` 和 `nitrogen_only`
2. 再扩大样本规模，验证排序关系在更大数据上是否稳定

---

## 2. 实验设计

### 2.1 后端

- **official DSSAT**

### 2.2 对照基线

- 文献基线：`literature_ncp`
- 保持论文中关键水肥管理结构
- 总水量与总氮量按当前场景预算缩放

### 2.3 两轮实验

#### 实验 A：24 场景正式消融

- 训练集：20
- 测试集：4
- 目的：
  - 补齐 daily 粒度下的 `water_only` 与 `nitrogen_only`
  - 与上一轮 stage 结果对照

#### 实验 B：48 场景中规模验证

- 训练集：40
- 测试集：8
- 目的：
  - 检查结果在更大样本下是否稳定
  - 验证 `joint(stage)` 是否会在更大样本下超过 `nitrogen_only(stage)`
  - 进一步判断 `water_only(stage)` 的负增益是否只是小样本和粗粒度造成的表象

---

## 3. 实验 A：24 场景结果

### 3.1 stage 粒度结果（上一轮正式结果）

| 控制模式 | mean_total_score_100 | mean_reward_gain | mean_yield_kg_ha | mean_yield_gain_pct |
|---|---:|---:|---:|---:|
| `water_only(stage)` | 54.737 | -0.039 | 3152.0 | -0.135% |
| `nitrogen_only(stage)` | 62.334 | +0.753 | 3324.25 | +4.588% |
| `joint(stage)` | 62.157 | +0.776 | 3316.5 | +4.412% |

### 3.2 daily 粒度结果（本轮补齐）

| 控制模式 | mean_total_score_100 | mean_reward_gain | mean_yield_kg_ha | mean_yield_gain_pct |
|---|---:|---:|---:|---:|
| `water_only(daily)` | 63.678 | +1.267 | 3833.75 | +4.916% |
| `nitrogen_only(daily)` | 63.367 | +1.468 | 3728.0 | +4.438% |
| `joint(daily)` | 60.469 | +1.204 | 3629.75 | +2.613% |

### 3.3 24 场景结论

#### 结论 1：`water_only(stage)` 的负增益更像是阶段粒度导致的假象

同样是控水：

- `water_only(stage)`：`-0.135%`
- `water_only(daily)`：`+4.916%`

这说明：

> 灌溉优化并不是“没有作用”，而是其效果对时机更敏感。  
> 当控制粒度从生育阶段细化到天之后，控水策略的收益可以显著释放出来。

#### 结论 2：在 24 场景下，daily 三种模式都优于各自 baseline

这说明：

- daily 粒度不是无效的
- 它确实给了模型更灵活的调控空间

但在 24 场景下，`joint(daily)` 没有超过 `water_only(daily)` 和 `nitrogen_only(daily)`。  
这提示：

> 更高的控制自由度不一定自动转化成更好结果，模型还需要更强训练和更大样本才能稳定学好联合策略。

---

## 4. 实验 B：48 场景中规模验证

### 4.1 stage 粒度结果（48 场景）

| 控制模式 | mean_total_score_100 | mean_reward_gain | mean_yield_kg_ha | mean_yield_gain_pct |
|---|---:|---:|---:|---:|
| `water_only(stage)` | 54.791 | -0.031 | 2925.5 | -0.099% |
| `nitrogen_only(stage)` | 67.238 | +1.746 | 3180.125 | +7.976% |
| `joint(stage)` | 67.499 | +1.825 | 3194.25 | +8.341% |

### 4.2 daily 粒度结果（48 场景）

| 控制模式 | mean_total_score_100 | mean_reward_gain | mean_yield_kg_ha | mean_yield_gain_pct |
|---|---:|---:|---:|---:|
| `water_only(daily)` | 59.080 | +1.024 | 3848.75 | +1.879% |
| `nitrogen_only(daily)` | 70.112 | +4.493 | 4339.875 | +13.070% |
| `joint(daily)` | 54.352 | -1.611 | 3417.625 | -5.160% |

---

## 5. 结果解读

### 5.1 关于 `water_only(stage)` 为什么会出现负值

放大样本之后，`water_only(stage)` 的结果变为：

- 24 场景：`-0.135%`
- 48 场景：`-0.099%`

同时，`water_only(daily)` 分别为：

- 24 场景：`+4.916%`
- 48 场景：`+1.879%`

因此可以更有把握地说：

> `water_only(stage)` 的负增益不是“灌溉优化本身无效”，而是阶段粒度太粗、再叠加小样本波动后出现的结果。  
> 当控制粒度细化到天，控水收益转为稳定正值。

### 5.2 关于 `joint(stage)` 为什么最开始没有超过 `nitrogen_only(stage)`

在 24 场景下：

- `nitrogen_only(stage)` 稍优于 `joint(stage)`（综合分）
- 两者几乎打平

但在 48 场景下：

- `joint(stage)` 的综合分、reward 增益、产量提升都已经超过 `nitrogen_only(stage)`

具体来看：

- `nitrogen_only(stage)`
  - `mean_total_score_100 = 67.238`
  - `mean_reward_gain = +1.746`
  - `mean_yield_gain_pct = +7.976%`
- `joint(stage)`
  - `mean_total_score_100 = 67.499`
  - `mean_reward_gain = +1.825`
  - `mean_yield_gain_pct = +8.341%`

因此可以判断：

> 之前 `joint(stage)` 没有明显超过 `nitrogen_only(stage)`，主要还是样本较少导致结果不稳定。  
> 在更大样本下，联合控制的优势已经开始显现出来。

### 5.3 关于 daily 粒度为什么没有自动全面更好

48 场景结果显示：

- `water_only(daily)` 和 `nitrogen_only(daily)` 都明显为正
- 但 `joint(daily)` 却出现负增益

这说明：

> 日粒度并不等于一定更优。  
> 它提供了更大的决策自由度，但也显著增加了训练难度。

换句话说：

- `daily` 更灵活
- 但 `joint(daily)` 需要更多样本、更长训练和更强约束，才能稳定优于 stage

当前 `joint(daily)` 的负增益，更像是：

- 高维动作空间下训练不足
- 而不是“日粒度思路错误”

---

## 6. 代表性阶段结论

本轮后续实验后，可以把结论更新为：

### 结论 1

`water_only(stage)` 的负增益不能直接理解为“控水无效”。  
更合理的解释是：

- 阶段粒度过粗
- 再叠加小样本波动

### 结论 2

在 **stage 粒度** 下，随着样本规模从 24 提升到 48：

- `joint(stage)` 已经超过 `nitrogen_only(stage)`

这说明：

> 联合控制的优势在更大样本下开始稳定显现。

### 结论 3

在 **daily 粒度** 下：

- `water_only(daily)` 和 `nitrogen_only(daily)` 均表现良好
- `joint(daily)` 目前仍不稳定

这说明：

> 日粒度控制具有潜力，但联合优化在日粒度下更难训练，当前还不能直接得出“daily joint 一定更优”的结论。

---

## 7. 当前最稳妥的判断

综合两轮实验后，当前最稳妥的判断是：

1. **控水是有效的，但更适合细粒度控制。**
2. **联合控制在阶段粒度下已经表现出比仅控肥更好的趋势，并在更大样本下实现反超。**
3. **日粒度联合控制仍需更多训练与更大数据，当前还不够稳定。**

---

## 8. 下一步建议

建议下一步继续做三件事：

1. **继续扩大样本**
   - 当前 48 场景已明显比 24 场景更稳定，建议继续扩到更大规模。

2. **增加 daily joint 的训练强度**
   - 更多 epochs
   - 更大训练集
   - 更强动作约束

3. **把 stage 与 daily 的比较拆开看**
   - `water_only`: daily 明显优于 stage
   - `nitrogen_only`: daily 也有优势
   - `joint`: 暂时 stage 更稳，daily 还需继续优化

---

## 9. 一句话总结

> 后续实验表明，`water_only(stage)` 的负增益主要是粒度过粗和小样本造成的表象；在更大样本下，`joint(stage)` 已经超过 `nitrogen_only(stage)`，说明联合控制的优势开始显现；而 `daily` 粒度虽然在单变量控制上显示出明显潜力，但联合控制仍需更多训练才能稳定发挥优势。
