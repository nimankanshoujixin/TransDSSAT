# TransDSSAT

This repository provides a minimal, extensible scaffold for:

- crop simulation interfaces aligned with WOFOST and DSSAT style workflows,
- water and nitrogen decision trajectories for reinforcement learning or imitation learning,
- small-scale, representative scenario generation for Quzhou-like conditions,
- a Transformer policy skeleton that can be enabled once PyTorch is installed.

## What is implemented

The current version focuses on the first milestone: make the simulation and dataset pipeline runnable with the Python standard library only.

- `transdssat.scenarios`: representative weather years, soil, crop, and management scenario construction
- `transdssat.environments.proxy`: WOFOST-like and DSSAT-like proxy environments with daily water/nitrogen dynamics
- `transdssat.environments.adapters`: optional real-model adapter entrypoints, including `pyDSSAT`
- `transdssat.dataset`: trajectory rollout, train/test split, and JSON dataset export
- `transdssat.policy`: optional Transformer policy skeleton for supervised action prediction

The proxy environments are not replacements for the real WOFOST/DSSAT engines. They exist to:

1. lock down the state, action, reward, and trajectory schema,
2. generate an initial small-scale dataset before full model coupling,
3. provide a stable interface so real engine adapters can be dropped in later.

## Git workflow

The project is intended to be versioned with Git and deployed by `git pull` on a server.

Recommended flow:

```bash
git clone <your-remote-url>
cd TransDSSAT
python scripts/generate_dataset.py --output-dir data/generated --scenario-count 216
```

If you want the generated datasets tracked by Git, remove the corresponding lines from `.gitignore`. By default they are ignored because they can be regenerated.

## Backends

Supported backend names:

- `wofost_proxy`
- `dssat_proxy`
- `pydssat`

`pydssat` is treated as an optional real DSSAT backend. The adapter is prepared in this repository, but it requires a server-side installation of `pyDSSAT` and a valid DSSAT runtime.

Current recommendation:

- use proxy backends for local schema design and fast sample generation,
- use `pydssat` only on the server after its runtime is fully prepared.

Why not hard-bind to `pyDSSAT` by default:

- its public docs describe a manual `f2py` wrapping workflow around DSSAT 4.5,
- the documented install path assumes an existing DSSAT environment and source-level changes,
- that makes it risky to treat as a portable dependency in this repository.

## State / action / reward design

The default state emphasizes the signals relevant to water-fertilizer control:

- soil moisture
- root zone water
- soil nitrogen
- canopy cover
- biomass
- development stage
- water stress
- nitrogen stress
- daily temperature
- precipitation
- reference evapotranspiration
- solar radiation

Actions:

- irrigation in mm/day
- nitrogen application in kg/ha/day

Reward:

- positive reward from biomass accumulation and final yield
- penalties for irrigation, nitrogen cost, and water/nitrogen stress

## Generate datasets

```bash
python scripts/generate_dataset.py --output-dir data/generated --scenario-count 216
```

Outputs:

- `train.jsonl`
- `test.jsonl`
- `metadata.json`

Each JSONL line stores one full trajectory with scenario metadata and daily transitions.

To force a single backend:

```bash
python scripts/generate_dataset.py --output-dir data/generated --scenario-count 72 --engines pydssat
```

## Transformer policy

The Transformer implementation is optional and only activated when `torch` is available.

```bash
python scripts/train_transformer.py --dataset data/generated/train.jsonl
```

If PyTorch is missing, the script will explain the expected dependency instead of silently failing.

## Server-side notes for `pyDSSAT`

If you decide to run the real DSSAT path on the server:

1. prepare a dedicated DSSAT runtime directory on the server,
2. install or build `pyDSSAT` there,
3. set `PYDSSAT_HOME` to that runtime directory,
4. generate scenarios with `--engines pydssat`,
5. adjust the adapter in `transdssat/environments/adapters.py` to match your actual cultivar, soil, weather, and file layout.

The current adapter intentionally fails fast with a clear error if `pyDSSAT` is not installed or the runtime directory is missing.
