# GPU Retraining Contract `2026-06-10`

## Purpose

This document freezes the training-facing contract for the first formal GPU-stage retraining pass after the objective-aware `step-wise` semantic update.

The goal of this run is not to introduce a new model family yet. The authoritative baseline for this task is a refreshed `10000`-scenario `step-wise` PPO rerun with fresh artifacts under the current semantics.

## Authoritative Training Path For This Run

### Included in the formal result

- entry script: `scripts/train_stepwise_ppo.py`
- environment interface: `transdssat.environments.stepwise.StepwiseDecisionEnvironment`
- rollout / PPO logic: `transdssat.stepwise_ppo`
- scenario pool generator: `transdssat.testset.generate_training_scenario_pool`
- reward backend for this run: proxy-only `dssat_proxy`

### Frozen scenario-pool assumptions

- split sizes: `train=9000`, `val=500`, `test=500`
- engine: `dssat_proxy`
- scenario generator seed policy: keep the same pool seed as the historical `2026-06-08` run for comparability unless a launch-time blocker requires a change
- authoritative interpretation:
  - scenario-pool membership may stay comparable
  - all derived artifacts must be regenerated after this semantic freeze

### Frozen selection rule

- checkpoint selection metric: `reward_gain`
- validation split is the authoritative checkpoint selector

## Active Step-Wise Observation / Sequence Contract

### Step-wise observation features

The current PPO path consumes the `DecisionObservation` contract emitted by `StepwiseDecisionEnvironment`, including:

- state summary:
  - `day_index`
  - `stage_index`
  - `soil_moisture`
  - `root_zone_water_mm`
  - `soil_nitrogen_kg_ha`
  - `canopy_cover`
  - `biomass_kg_ha`
  - `water_stress`
  - `nitrogen_stress`
  - `tmean_c`
  - `precipitation_mm`
  - `et0_mm`
  - `radiation_mj_m2`
- remaining hard budgets:
  - `remaining_irrigation_mm`
  - `remaining_nitrogen_kg_ha`
- action-constraint state:
  - max irrigation
  - max nitrogen
  - remaining irrigation gap days
  - remaining nitrogen gap days
  - whether joint action is allowed
- short-horizon weather context:
  - mean precipitation over the forecast window
  - mean ET0 over the forecast window
  - mean temperature over the forecast window
- crop identity flags:
  - maize flag
  - wheat flag

This produces the current fixed observation width `25`.

### History-conditioned sequence token

The current sequence token used by `stepwise_ppo` includes:

- the full `25`-dim observation block above
- previous discrete recommended action as one-hot over the canonical action table
- previous recommended irrigation / nitrogen
- previous executed irrigation / nitrogen
- previous reward
- previous-action-present flag
- sinusoidal day encoding
- objective-conditioning weights from `objective_context.reward_weights`
- management-mode flags
- decision interval / forecast horizon fields from `decision_context`

This produces the current fixed sequence-token width `52`.

### Objective-aware semantics included in the active PPO path

The current formal PPO path is aligned to the new semantics because it already consumes:

- `objective_context.reward_weights`
- `budget_constraints` through remaining-budget tracking and terminal penalty
- `decision_context.forecast_horizon_days`
- `decision_context.decision_interval_days`
- `crop_context`
- action-mask legality derived from current constraint state

## Reward Contract For This Run

### Proxy reward semantics

The proxy backend is now objective-aware:

- intermediate reward uses biomass shaping plus irrigation / nitrogen / operation / stress costs
- terminal reward applies `reward_from_outcome(...)`
- terminal reward includes:
  - yield revenue
  - irrigation cost
  - nitrogen cost
  - operation cost
  - budget deviation penalty
  - drainage penalty
  - nitrogen leaching penalty
  - risk-related stress penalties

### Current boundary

This run is still a proxy-backed formal baseline, not an official DSSAT full retraining result.

Therefore:

- the run is trustworthy for the current proxy semantic contract
- it is not yet the final official-DSSAT scientific result

## Legacy Or Not-Yet-Aligned Training Paths

### Legacy path 1: `scripts/train_rl_transformer.py`

Status: `legacy_not_authoritative_for_current_semantics`

Reasons:

- the model input is still `encode_scenario_day(...)` with `13` features
- inputs contain daily weather, soil initials, budgets, and crop indicator
- inputs do not include:
  - `objective_context`
  - forecast-window features
  - remaining budget state
  - action-mask state
  - crop/cultivar context beyond a simple crop flag
- control output is still season/daily allocation shares projected into `SeasonPolicy`

Conclusion:

- this path may still be used for exploratory debugging
- it must not be reported as the authoritative current-semantic result without a separate alignment pass

### Legacy path 2: `scripts/train_transformer.py`

Status: `legacy_not_authoritative_for_current_semantics`

Reasons:

- supervised examples are built from `transdssat.policy.iter_supervised_examples(...)`
- the sequence encoder still uses raw `CropState` with `13` numeric fields
- inputs do not include:
  - `objective_context`
  - forecast-window features
  - remaining budget state
  - action legality / masks
  - management-mode conditioning
- dataset metadata still describes the older season-level reward wording

Conclusion:

- any existing supervised dataset or checkpoint from this path is stale for the current semantic freeze

## Stale Derived Artifacts

The following artifact classes must be treated as stale unless regenerated after this contract freeze:

- prior PPO checkpoints and reports, including the historical `2026-06-08` `10000`-scenario run
- any rollout dataset produced from the older feature / reward interpretation
- any supervised dataset consumed by `scripts/train_transformer.py`
- any cached baseline / score / report that depends on the pre-freeze input-reward semantics

## Immediate Launch Decision

Live remote verification on `2026-06-10` found:

- host: `10.10.252.11`
- project tmux session: `transdssat`
- Conda env: `transdssat`
- GPU state: `cuda:3` free at check time; other GPUs occupied

However, the remote repo did not match the current local hashes for the step-wise PPO path, so the remote code must be refreshed before the formal rerun can be treated as valid under this contract.
