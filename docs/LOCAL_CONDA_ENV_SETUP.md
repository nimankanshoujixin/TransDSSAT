# Local Conda Environment Setup

This project now uses a dedicated local Conda environment named `transdssat`.

## Why

- The default system Python on this machine is `3.13`, but the training stack is more stable on `3.11`.
- The current Transformer PPO workflow needs `torch`, and the previous local environment did not have it installed.
- A repo-scoped environment definition makes later local smoke tests and remote reproduction easier.

## Canonical environment file

Use the repo-root file:

```powershell
conda env create -f environment.yml
```

If the environment already exists:

```powershell
conda env update -f environment.yml --prune
```

## Activate

```powershell
conda activate transdssat
```

## Quick verification

```powershell
python -c "import torch; print(torch.__version__)"
python -m unittest discover -s tests -v
python scripts/train_stepwise_ppo.py --dry-run --backbone transformer --train-count 8 --val-count 2 --test-count 2 --seed 20260609
```

## Notes

- This local environment is for CPU-safe development and smoke validation.
- Remote GPU training should still follow the SSH + tmux workflow in `docs/AUTOMATION_RUNBOOK.md`.
- Official DSSAT runtime is managed separately and is not installed through this Conda environment file.
