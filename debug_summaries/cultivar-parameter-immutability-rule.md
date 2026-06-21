# ⚠️ Cultivar Parameter Immutability Rule (2026-06-17)

## Rule

All cultivar genetic coefficients in `RICER048.CUL` files come from agricultural expert calibration results and **MUST NOT BE MODIFIED** under any circumstances.

## Parameters Covered

P1, P2R, P5, P2O, G1, G2, G3, PHINT, THOT, TCLDP, TCLDF

## Incident Log

- 2026-06-17: Probe-modified WHR008 (P5=420→600→750, THOT=24.3→28.0→29.5, P1=400→500).
  - Yield moved from 2156 → 5274 → 9037 kg/ha.
  - Changes reverted immediately upon user directive.
  - Lesson: parameter changes can dramatically alter simulation but this is NOT the correct troubleshooting path.

## Root Issue (Instead)

The actual cause of Wuhu non-bridge cultivar replay errors is a DSSAT version mismatch:
- Remote server: DSSAT v4.8.5.50 (development build from dssat-csm-os git)
- Expert environment: DSSAT v4.8.5.0 (official release, 2024-12-01)
- The RICER048 model behavior may differ between these versions.

## Resolution Path

Install DSSAT v4.8.5.0 (official release) on the remote server and re-run all rice replay audits.
