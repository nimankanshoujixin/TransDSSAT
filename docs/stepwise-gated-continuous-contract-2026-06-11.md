# Step-wise Gated Continuous Action Contract

Date: `2026-06-11`

## Scope

This document freezes the first authoritative `gated continuous-action` contract for the active `transdssat.stepwise_ppo` line.

The scope is deliberately limited to:

- policy contract
- rollout / history / PPO wiring
- CPU-safe validation

It does not claim that a formal GPU training run has already been launched for this contract.

## Trust Boundary

The continuous-execution trust boundary remains:

1. `transdssat.stepwise_ppo` produces a policy-side recommendation.
2. `transdssat.environments.stepwise.StepwiseDecisionEnvironment.step(...)` remains the authority that executes the recommendation.
3. `transdssat.discrete_actions.validate_continuous_action(...)` remains the hard legality check for the final executed continuous action.

The old discrete wrapper is therefore now treated as one policy parameterization, not as the environment's fundamental action semantics.

## Policy Fields

The first formal policy-side gated continuous decision is:

- `action_mode`
  - `discrete` or `gated_continuous`
- `control_mode`
  - `water_only`
  - `nitrogen_only`
  - `joint`
- `irrigation_gate`
  - binary execute / do-not-execute decision
- `nitrogen_gate`
  - binary execute / do-not-execute decision
- `irrigation_amount_mm`
  - non-negative continuous amount
- `nitrogen_amount_kg_ha`
  - non-negative continuous amount

For `gated_continuous`, the policy is not expected to "discover noop by regressing to zero". `noop` is represented explicitly by closed gates.

## Noop And Family Mapping

Action family is derived from gates after control-mode projection:

- `noop`
  - irrigation gate `0`, nitrogen gate `0`
- `water_only`
  - irrigation gate `1`, nitrogen gate `0`
- `nitrogen_only`
  - irrigation gate `0`, nitrogen gate `1`
- `joint`
  - irrigation gate `1`, nitrogen gate `1`

Control-family projection is frozen as:

- `water_only`
  - nitrogen gate is forced to `0`
  - nitrogen amount is forced to `0`
- `nitrogen_only`
  - irrigation gate is forced to `0`
  - irrigation amount is forced to `0`
- `joint`
  - both dimensions may be active

## Legal-Bound Handling

For the first authoritative implementation:

- policy-side continuous amounts are clipped to the current legal maxima exposed by `DecisionObservation.action_constraints`
- dimensions with `max_value == 0` are forced to closed gates
- if a control family disables one dimension, that dimension is also forced to closed gate and zero amount
- the environment still re-validates the final continuous payload before execution

This keeps the policy contract bounded under current legal constraints without removing the environment-side legality authority.

## Rollout / History / PPO Contract

The active implementation now carries gated continuous semantics through:

- rollout decision records
  - transition stores `action_mode`, `control_mode`, gates, per-step legal maxima, and derived `action_family`
- history token encoding
  - no longer relies exclusively on discrete action-id one-hot semantics
  - previous-step gates, amounts, ratios, action family, and action/control mode are encoded explicitly
- actor outputs
  - discrete path remains available
  - gated continuous path now uses:
    - Bernoulli gates
    - Beta-distributed normalized continuous amounts
- PPO batch / loss
  - discrete masked categorical branch remains intact
  - gated continuous branch now computes log-prob / entropy from gate and amount factors

## Baseline Preservation

The discrete baseline remains available and is still the authoritative comparison target until new gated continuous GPU-stage results exist.

- discrete models:
  - `StepwisePPOActorCritic`
  - `StepwiseTransformerActorCritic`
- gated continuous models:
  - `StepwiseGatedContinuousActorCritic`
  - `StepwiseGatedContinuousTransformerActorCritic`

## CPU-safe Validation Completed

Local CPU-safe validation completed on `2026-06-11` with:

- `python -m unittest tests.test_stepwise_ppo`
- `python -m unittest tests.test_stepwise_env`
- `python -m unittest tests.test_unified_eval_stepwise`
- `python -m unittest tests.test_stepwise_adapter`
- `python scripts/train_stepwise_ppo.py --dry-run --train-count 8 --val-count 2 --test-count 2 --seed 20260611 --action-mode discrete --control-mode joint`
- `python scripts/train_stepwise_ppo.py --dry-run --train-count 8 --val-count 2 --test-count 2 --seed 20260611 --action-mode gated_continuous --control-mode joint`

Observed result:

- discrete dry-run closed successfully
- gated continuous dry-run closed successfully
- unified evaluation compatibility stayed intact because scoring still consumes `Trajectory` / executed `CropAction` rather than a discrete-only policy id

## GPU Status For This Wakeup

Formal GPU training was not started in this wakeup.

Live remote snapshot on `2026-06-11 12:43 Asia/Shanghai`:

- host: `10.10.252.11`
- command: `nvidia-smi --query-gpu=index,name,utilization.gpu,memory.used,memory.total --format=csv,noheader,nounits`
- result: all 8 `NVIDIA A800-SXM4-80GB` devices already had high memory occupancy, roughly `55 GB` to `80 GB`
- GPU 4 also showed `100%` utilization

Therefore this wakeup stops at CPU-safe implementation closure and records `no idle GPU` as the blocker for staged training.
