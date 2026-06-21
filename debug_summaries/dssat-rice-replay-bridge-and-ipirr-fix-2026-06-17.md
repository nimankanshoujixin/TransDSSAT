# DSSAT Rice Replay Bridge And IPIRR Fix (2026-06-17)

## Scope

This note records the two main rice replay debugging chains that were needed to get the first real-data replay and replacement paths running under native DSSAT:

- `wuhu_rice_calibrated tr11` original-management replay bridge
- `wuhu_rice_calibrated tr11 water_only` replacement `IPIRR` fix

## Confirmed Root Causes

### 1. Replay bridge for `wuhu tr11`

The native DSSAT path did not accept the calibrated Meixiangzhan row directly under the current runtime contract.

Confirmed working bridge behavior:

- keep native DSSAT execution
- rewrite only the replay clone, not the source asset
- remap the accepted cultivar-code identity on the replay clone
- normalize the remapped calibrated row `EXPNO` from `1,12` to `.`

Interpretation:

- this is still a DSSAT-native replay result
- it is not a proxy simulator result
- but it is also not yet a fully bridge-free original replay

### 2. Replacement `IPIRR` failure for `wuhu tr11 water_only`

The first replacement implementation rewrote the irrigation section too aggressively.

Observed bad behavior:

- the whole irrigation section was effectively rebuilt
- non-target treatment blocks were not preserved
- target treatment metadata such as `WATER_11` and `IR003` was replaced by generic content
- event lines were emitted in compact decimal form such as `30.0`

Native DSSAT symptom:

- `WHRI2101.RIX`
- line `300`
- error key `IPIRR`

## Final Fix

Implemented in [`/G:/TransDSSAT/transdssat/real_subset_runner.py`](/G:/TransDSSAT/transdssat/real_subset_runner.py):

- replace only the target treatment irrigation block
- preserve other treatment blocks unchanged
- preserve original target control metadata such as `WATER_11`
- preserve original event operation codes such as `IR003`
- write replacement event rows back in DSSAT-compatible fixed-width style

Expected line shape:

```text
11 21185 IR003    30
11 21227 IR003    35
```

Avoid this shape:

```text
 11 21185 IR003  30.0
```

## Validation

Local CPU-safe validation:

- `python -m unittest tests.test_real_subset_assets`
- `python -m unittest tests.test_render_dssat_inputs tests.test_dssat_parser`

Remote native result:

- `wuhu_rice_calibrated tr11 water_only` now completes and writes `real_subset_replacement_report.json`
- output root:
  `/fs/fast/u2021201693/lym/TransDSSAT/artifacts/real_subset_replacement_wuhu_tr11_water_smoke/wuhu_rice_calibrated_tr11`

## Reuse Guidance

If a future DSSAT crop/model integration fails in a similar way, check these classes of issues first:

1. fixed-width file formatting, especially control/event sections
2. replay-clone compatibility patches versus source-asset mutation
3. whether a failure is caused by generic section rebuilds that destroy native metadata
4. whether accepted code identity and `EXPNO` tokens are part of the runtime contract

## Status

This bug can be treated as fixed for the current rice replacement path.

Remaining limitation:

- `wuhu tr11` still depends on the replay-only bridge for the original replay chain
- so the replacement bug is fixed, but bridge removal is still a separate unfinished task
