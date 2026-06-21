# Remote Conda Environment Setup

The preferred remote training environment for this project is the existing Conda env named `transdssat` on the SSH host:

- host: `10.10.252.11`
- env name: `transdssat`
- repo: `/fs/fast/u2021201693/lym/TransDSSAT`

## Canonical files

- Base cross-platform dependencies: `environment.yml`
- Remote GPU-oriented environment definition: `environment.remote.gpu.yml`

## Recommended remote update flow

```bash
cd /fs/fast/u2021201693/lym/TransDSSAT
conda env update -n transdssat -f environment.remote.gpu.yml --prune
```

If the remote environment does not exist yet:

```bash
conda env create -f environment.remote.gpu.yml
```

## Verification

```bash
conda run -n transdssat python -c "import torch; print(torch.__version__); print(torch.cuda.is_available())"
conda run -n transdssat python -m unittest discover -s tests -v
```

## Notes

- Remote GPU training should use this environment together with the SSH + tmux workflow in `docs/AUTOMATION_RUNBOOK.md`.
- DSSAT runtime and templates are managed separately and are not installed by the Conda env files.
- The repo scripts already insert `PROJECT_ROOT` into `sys.path`, so editable installation is optional for remote smoke runs.
- If the remote `.condarc` mirror configuration makes the `nvidia` Conda channel unavailable, a practical fallback is:

```bash
conda run -n transdssat python -m pip install --upgrade --force-reinstall \
  torch==2.7.1+cu118 \
  --index-url https://download.pytorch.org/whl/cu118
```
