# 水稻真实子集全量 Replay 审计报告（2026-06-17）

## 1. 审计目标

这次审计不是只看两个锚点 treatment，而是把当前两个水稻参考集的全部 treatment 都在原始管理方案下跑一遍，回答两个问题：

1. 这些参考参数是否已经被整体成功接入当前官方 DSSAT 链路。
2. 哪些结果已经可以算“复现成功”，哪些结果仍然依赖 bridge 或还没有真正拿稳。

本次全量审计共运行 `31` 个场景：

- `mx475_migrated`：`8` 个 treatment
- `wuhu_rice_calibrated`：`23` 个 treatment

审计脚本：

- [`audit_real_subset_replays.py`](/G:/TransDSSAT/scripts/audit_real_subset_replays.py)

本地审计产物：

- [`mx475 json`](/G:/TransDSSAT/artifacts/real_subset_replay_audit_mx475_full/real_subset_replay_audit.json)
- [`mx475 csv`](/G:/TransDSSAT/artifacts/real_subset_replay_audit_mx475_full/real_subset_replay_audit.csv)
- [`wuhu json`](/G:/TransDSSAT/artifacts/real_subset_replay_audit_wuhu_full/real_subset_replay_audit.json)
- [`wuhu csv`](/G:/TransDSSAT/artifacts/real_subset_replay_audit_wuhu_full/real_subset_replay_audit.csv)

## 2. 总体结论

结论不能一刀切成“都成功”或者“都失败”，而是已经非常清楚地分成两层：

- `mx475_migrated` 这一套参数已经整体复现成功，8 个 treatment 全部在当前 native DSSAT 路径下稳定运行，且误差集中在较小范围内。
- `wuhu_rice_calibrated` 不能算整体复现成功；它内部已经明显分裂成两组。
  - `WHR006 / Meixiangzhan` 这一组在当前 bridge 路径下复现得比较好。
  - 其余 cultivar 组整体误差很大，说明当前并不是“整套 Wuhu 参数都已经拿过来了”。

所以当前最准确的判断是：

- `mx475`：整体成功。
- `wuhu`：只成功了 bridge 下的 `WHR006` 这一支，整体还不能算成功。

## 3. `mx475_migrated` 全量结果

汇总指标：

- treatment 数：`8`
- bridge treatment 数：`0`
- 平均绝对产量误差：`343.25 kg/ha`
- 平均绝对相对误差：`0.063733`
- 平均带符号相对误差：`0.063733`
- 最大绝对相对误差：`0.092665`

解释：

- 这 8 个 treatment 全部是同一 cultivar `IB2002`。
- 所有 treatment 都能稳定跑通。
- 所有 treatment 都是轻度高估，基本落在 `+0.99%` 到 `+9.27%` 区间。
- 这说明当前 `mx475` 不是“偶然有一个点对了”，而是整组参数已经能比较稳定地落在合理误差带里。

逐 treatment 结果：

| TR | 观测产量 | 模拟产量 | 误差 kg/ha | 相对误差 |
| --- | ---: | ---: | ---: | ---: |
| 1 | 4815 | 5124 | 309 | 0.064174 |
| 2 | 4995 | 5341 | 346 | 0.069269 |
| 3 | 4875 | 5297 | 422 | 0.086564 |
| 4 | 5370 | 5555 | 185 | 0.034451 |
| 5 | 5775 | 5832 | 57 | 0.009870 |
| 6 | 5385 | 5884 | 499 | 0.092665 |
| 7 | 5115 | 5440 | 325 | 0.063539 |
| 8 | 6750 | 7353 | 603 | 0.089333 |

判断：

- `mx475_migrated` 当前已经可以视为稳定的 original-management replay anchor。

## 4. `wuhu_rice_calibrated` 全量结果

全量汇总指标：

- treatment 数：`23`
- bridge treatment 数：`12`
- 平均绝对产量误差：`1880.913 kg/ha`
- 平均绝对相对误差：`0.249831`
- 平均带符号相对误差：`-0.165309`
- 最大绝对相对误差：`0.738888`

如果只看这个全量平均值，会得出“Wuhu 很差”的结论；但这还不够细，因为它内部实际上已经分成两组。

### 4.1 bridge 组：`WHR006`

当前 `WHR006` treatment 会走 replay-only bridge。

bridge 组统计：

- treatment 数：`12`
- 平均绝对相对误差：`0.063764`
- 平均带符号相对误差：`0.007057`

解释：

- 这一组的平均绝对相对误差只有大约 `6.4%`。
- 平均带符号误差接近 `0`，说明不存在明显系统性高估或低估。
- 所以 `WHR006 / Meixiangzhan` 这支在 bridge 下其实已经复现得相当不错。

### 4.2 非 bridge 组：其余 cultivar

非 bridge 组统计：

- treatment 数：`11`
- 平均绝对相对误差：`0.452812`
- 平均带符号相对误差：`-0.353345`

解释：

- 非 bridge 组平均绝对相对误差约 `45.3%`，明显不可接受。
- 而且整体偏负，说明这些 cultivar 在当前链路下普遍被严重低估。
- 这说明当前 Wuhu 的主要问题已经不是 `WHR006` 这支，而是其余 cultivar 参数/运行契约并没有被整体拿稳。

### 4.3 最需要关注的异常点

误差最大的几个非 bridge treatment：

| TR | Cultivar | 观测产量 | 模拟产量 | 误差 kg/ha | 相对误差 |
| --- | --- | ---: | ---: | ---: | ---: |
| 6 | WHR008 | 8257 | 2156 | -6101 | -0.738888 |
| 2 | WHR001 | 7174 | 2512 | -4662 | -0.649847 |
| 1 | WHR001 | 7499 | 3061 | -4438 | -0.591812 |
| 5 | WHR008 | 7418 | 3092 | -4326 | -0.583176 |
| 3 | WHR002 | 7201 | 3081 | -4120 | -0.572143 |
| 4 | WHR005 | 7162 | 3084 | -4078 | -0.569394 |
| 7 | WHR004 | 10458 | 6124 | -4334 | -0.414420 |
| 9 | WHR009 | 8912 | 6112 | -2800 | -0.314183 |

而 `WHR006` 组里表现最好的几个点：

| TR | Cultivar | 观测产量 | 模拟产量 | 误差 kg/ha | 相对误差 |
| --- | --- | ---: | ---: | ---: | ---: |
| 19 | WHR006 | 6656 | 6615 | -41 | -0.006160 |
| 11 | WHR006 | 6365 | 6222 | -143 | -0.022467 |
| 16 | WHR006 | 6399 | 6595 | 196 | 0.030630 |
| 22 | WHR006 | 6387 | 6178 | -209 | -0.032723 |
| 20 | WHR006 | 6820 | 6555 | -265 | -0.038856 |

判断：

- `wuhu_rice_calibrated` 当前不能视为整体稳定的 real-data replay subset。
- 它目前更准确的状态是：
  - `WHR006` 这支在 bridge 下有较好复现结果。
  - 其它 cultivar 组仍然明显不成立。

## 5. 关于 bridge 的准确含义

这里的 `bridge` 不是“不用 DSSAT”，也不是“换成代理模拟器”。

当前 bridge 的含义是：

- 仍然运行 native DSSAT。
- 但在 replay clone 上做兼容性桥接，而不是完全原样直跑源资产。

当前已确认的 bridge 内容主要包括：

- replay clone 内的 accepted-code remap
- remapped calibrated row 的 `EXPNO` 从 `1,12` 规范化为 `.`

所以：

- `bridge = 仍然是 DSSAT 结果`
- `bridge ≠ 完全无兼容层的原样复现`

## 6. 这次 bug 现在算不算修好

如果说的是最近这个 replacement 注入导致 `IPIRR` 报错的 bug，那么现在可以算修好了。

已修内容：

- replacement 只改目标 treatment block，不再整段重建 irrigation section
- 保留目标 treatment 的原始 metadata，例如 `WATER_11`、`IR003`
- 灌溉事件回写为 DSSAT 兼容的 fixed-width 格式

对应 debug 总结已沉淀到：

- [`debug_summaries README`](/G:/TransDSSAT/debug_summaries/README.md)
- [`bridge and IPIRR fix summary`](/G:/TransDSSAT/debug_summaries/dssat-rice-replay-bridge-and-ipirr-fix-2026-06-17.md)

但要区分两个层次：

- `replacement IPIRR bug`：已修好。
- `wuhu 非 WHR006 cultivar 全量复现`：还没有修好。

## 7. 最终判断

当前不能说“这两个参考集的参数都整体拿过来了”。

可以更严谨地表述为：

- `mx475_migrated`：整组参数已经较成功地复现到当前官方 DSSAT 链路。
- `wuhu_rice_calibrated`：只有 `WHR006` 这一支在 bridge 下复现较好，其余 cultivar 仍有大误差，暂时不能判定为整体迁移成功。

## 8. 下一步建议

1. 先把这份全量审计结果作为当前阶段的正式判断基线。
2. 后续优先排查 `wuhu` 非 bridge cultivar 组：
   - `WHR001`
   - `WHR002`
   - `WHR004`
   - `WHR005`
   - `WHR008`
   - `WHR009`
3. 在 `mx475` 上可以继续把 replacement 路径从 smoke 往更真实管理策略推进。
4. 在 `wuhu` 上不要把当前 bridge 下的 `WHR006` 成功误判成整套参考集已经迁移完成。
