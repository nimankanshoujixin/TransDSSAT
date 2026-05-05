# Literature Baseline Notes

## Purpose

The original repository compared RL policies against an internal heuristic stage-split rule.
That was useful for debugging, but weak as an agricultural reference.

The repository now includes a literature-informed baseline named `literature_ncp`.

## Agronomic source used

The baseline is derived from North China Plain wheat-maize rotation studies that report:

- critical irrigation timings for winter wheat and summer maize under drip fertigation
- split-N structure with basal application plus topdressing/fertigation
- crop-season water and nitrogen recommendations in a wheat-maize system

In the current implementation, the baseline uses:

- wheat critical events:
  - basal nitrogen at sowing
  - irrigation / fertigation at jointing
  - irrigation / fertigation at anthesis
- maize critical events:
  - basal nitrogen at sowing
  - irrigation / fertigation at seedling
  - irrigation / fertigation at jointing
  - irrigation / fertigation at tasseling

## How the repository maps the paper strategy

Two budget-source modes are supported.

### `--baseline-budget-source scenario`

Use the paper's timing and split structure, but scale total irrigation and total nitrogen to the current TransDSSAT scenario budget.

This is the recommended default for training and evaluation because:

- it keeps the comparison fair under randomized scenario budgets
- it tests whether RL improves on the literature timing pattern under the same resource envelope

### `--baseline-budget-source paper`

Use the paper-level crop totals directly.

This is useful for:

- sensitivity analysis
- reproducing the external recommendation more literally
- comparing a budget-constrained controller against a fixed agronomic recommendation

## Stage vs daily baseline

The same baseline can be rendered in two controller granularities:

- `stage`
  Approximate the literature strategy on the four TransDSSAT control stages.
- `daily`
  Keep sparse event days closer to the published management schedule.

This means the literature baseline can be used consistently in:

- dataset generation
- RL reward-gain comparison
- ablation experiments
- stage-level and daily-level policy evaluation
