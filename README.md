# TransDSSAT

TransDSSAT is a crop-decision training scaffold built around one practical idea:

- the model outputs season-level water and nitrogen actions,
- the backend evaluates those actions,
- the backend returns trajectory data and reward,
- the resulting samples are used to train a decision model such as a Transformer.

The repository supports two backend layers:

- `wofost_proxy` / `dssat_proxy`: local proxy environments for fast development
- `dssat_official`: a server-side wrapper around the official DSSAT runtime

## Current framework

The codebase is now organized around season-level decision evaluation instead of only daily threshold rules.

- `transdssat/scenarios.py`
  Builds Quzhou-style scenarios. It now supports both the legacy fixed grid and random scenario sampling with perturbed soil initials, planting dates, and continuous budget ranges.
- `transdssat/season.py`
  Defines season policies as stage-based actions and provides the baseline policy generator.
- `transdssat/environments/proxy.py`
  Contains local proxy simulators for rapid iteration.
- `transdssat/environments/adapters.py`
  Contains the official DSSAT season backend wrapper.
- `transdssat/dssat/inputs.py`
  Writes a per-run DSSAT workspace and season policy files.
- `transdssat/dssat/runner.py`
  Launches the preprocess command and DSSAT command.
- `transdssat/dssat/parser.py`
  Parses `PlantGro.OUT`, `SoilWat.OUT`, `SoilNi.OUT`, and `Summary.OUT`.
- `transdssat/dataset.py`
  Converts evaluated policies into train/test datasets.
- `transdssat/policy.py`
  Contains the optional Transformer skeleton.

## Decision format

The policy is season-level, not daily online control.

Each policy contains one action for each major stage:

- `emergence`
- `vegetative`
- `reproductive`
- `grain_fill`

Each action has:

- `date`
- `day_index`
- `irrigation_mm`
- `nitrogen_kg_ha`

This matches DSSAT better than forcing a strict daily `step(action)` loop.

## Reward logic

Reward is computed from:

- final yield
- irrigation input cost
- nitrogen input cost
- average water stress
- average nitrogen stress
- per-step biomass growth shaping
- budget-deviation penalties for water and nitrogen
- extra penalties for severe under-irrigation / oversupply behavior

Proxy backends return the reward during the rollout.

The official DSSAT backend reconstructs daily states from output files, then computes the same reward family on top of parsed outputs.

## What can run immediately

You can run the proxy path right now with plain Python.

```bash
python scripts/generate_dataset.py --output-dir data/generated --scenario-count 216
python scripts/evaluate_season_policy.py --engine dssat_proxy --crop wheat --weather-regime normal
```

This produces:

- `train.jsonl`
- `test.jsonl`
- `metadata.json`

The proxy path is the current zero-friction route for generating training data and validating the learning pipeline.

## Official DSSAT backend

Recommended real backend:

- [DSSAT/dssat-csm-os](https://github.com/DSSAT/dssat-csm-os)
- [DSSAT/dssat-csm-data](https://github.com/DSSAT/dssat-csm-data)

TransDSSAT does not try to replace DSSAT's own runtime. Instead it wraps it.

### Server-side installation concept

On the server you need:

1. the official DSSAT runtime installed under `DSSAT_HOME`
2. one template directory per crop under `DSSAT_TEMPLATE_ROOT`
3. a `DSSAT_RUN_COMMAND` that can execute one prepared run directory
4. optionally a `DSSAT_PREPROCESS_COMMAND` that converts the TransDSSAT manifest into final DSSAT experiment files

Details are in `docs/backend-notes.md`.

### What TransDSSAT writes before running DSSAT

For each run, TransDSSAT creates a working directory and writes:

- `transdssat_manifest.json`
- `transdssat_scenario.json`
- `transdssat_soil.json`
- `transdssat_weather.csv`
- `transdssat_policy.tsv`

Then it:

1. copies the crop template directory into that run directory
2. runs the optional preprocess command
3. runs the DSSAT command
4. parses the resulting output files

### Important limitation

The repository now includes the official DSSAT wrapper and parser, but your server still needs one local customization:

- either a ready-to-run crop template,
- or a preprocess script that turns `transdssat_manifest.json` into the exact DSSAT input files used by your runtime.

That final step depends on your actual DSSAT installation, cultivar files, template conventions, and weather/soil file layout.

## Environment variables for the official backend

Required:

- `DSSAT_HOME`
- `DSSAT_RUN_COMMAND`

Usually required in practice:

- `DSSAT_TEMPLATE_ROOT`

Optional:

- `DSSAT_PREPROCESS_COMMAND`
- `DSSAT_WORK_ROOT`
- `DSSAT_TIMEOUT_SECONDS`
- `DSSAT_PRESERVE_RUN_DIRS`

The command templates can reference:

- `{run_dir}`
- `{manifest}`
- `{policy}`
- `{scenario}`

Example:

```bash
export DSSAT_HOME=/opt/dssat
export DSSAT_TEMPLATE_ROOT=/opt/transdssat/templates
export DSSAT_PREPROCESS_COMMAND="python /opt/transdssat/scripts/render_dssat_inputs.py {manifest}"
export DSSAT_RUN_COMMAND="/opt/dssat/bin/dscsm048 A {experiment}"
python scripts/evaluate_season_policy.py --engine dssat_official --crop wheat --weather-regime normal
```

Current repository support:

- `scripts/render_dssat_inputs.py` can inject TransDSSAT season policies into a copied DSSAT experiment template
- the current implementation supports the stock maize and wheat template paths already validated on the server
- it rewrites treatment 1 irrigation and fertilizer events and regenerates DSSAT weather files from `transdssat_weather.csv`
- weather generation now supports cross-year crop seasons such as winter wheat
- when multiple experiment files exist in one copied template directory, the preprocessor prefers `scenario.experiment_file`; `DSSAT_RUN_COMMAND` can use `{experiment}` so one command template works for both crops

## Dataset generation flow

The default dataset generation flow is:

1. build Quzhou scenarios
2. generate one baseline season policy per scenario
3. evaluate that policy on the selected backend
4. export trajectory data into train/test JSONL files

Command:

```bash
python scripts/generate_dataset.py --output-dir data/generated --scenario-count 216 --engines wofost_proxy dssat_proxy
```

To move beyond the legacy 108-scenario grid, use random sampling:

```bash
python scripts/generate_dataset.py --output-dir data/generated_random --scenario-count 400 --sampling-mode random --engines dssat_proxy
```

To restrict generation to one crop:

```bash
python scripts/generate_dataset.py --output-dir data/generated_dssat_maize --scenario-count 6 --engines dssat_official --crops maize
```

For winter wheat on the current server-side template path:

```bash
export DSSAT_RUN_COMMAND="/opt/dssat/dscsm048 A {experiment}"
python scripts/evaluate_season_policy.py --engine dssat_official --crop wheat --weather-regime normal
```

If the official backend is ready on the server:

```bash
python scripts/generate_dataset.py --output-dir data/generated_dssat --scenario-count 72 --engines dssat_official
```

## Transformer training

The Transformer code is still optional and requires PyTorch.

The current supervised-example loader treats each stage decision as one training target:

- prefix state sequence up to the decision day
- target irrigation and nitrogen dose for that stage

```bash
python scripts/train_transformer.py --dataset data/generated/train.jsonl
```

If `torch` is missing, the script will stop with a clear message.

## Agronomic evaluation

For reporting, use the agronomic report script instead of only reading training loss.

The report outputs:

- yield and yield gain
- irrigation and nitrogen use
- water-use efficiency and nitrogen-use efficiency
- cumulative reward
- average water and nitrogen stress
- a composite `total_score_100` for agricultural interpretation

Example:

```bash
python scripts/evaluate_policy_report.py --engine dssat_official --scenario-count 108 --split test
```

If you provide an RL checkpoint, the script compares the RL policy against the baseline policy on the same scenarios:

```bash
python scripts/evaluate_policy_report.py \
  --engine dssat_official \
  --scenario-count 108 \
  --split test \
  --checkpoint artifacts/rl_transformer/rl_transformer_policy.pt
```

## RL training

The repository now also includes a season-level RL training entry point.

This RL path does not select one policy from a fixed candidate library. Instead, the model reads the scenario context and directly generates the four stage decisions:

- emergence
- vegetative
- reproductive
- grain_fill

The RL policy now allocates the scenario irrigation budget and nitrogen budget across those four stages. In other words, the model learns:

- how much of the seasonal irrigation budget to place into each stage
- how much of the seasonal nitrogen budget to place into each stage

The sampled season policy is then evaluated by the selected backend, and REINFORCE-style updates optimize DSSAT reward directly.

Example:

```bash
python scripts/train_rl_transformer.py \
  --engine dssat_official \
  --scenario-count 300 \
  --sampling-mode random \
  --epochs 10 \
  --batch-size 4 \
  --output-dir artifacts/rl_transformer
```

Recommended workflow:

1. validate the RL loop on `dssat_proxy` with `--sampling-mode random`
2. switch to `dssat_official`
3. evaluate the trained checkpoint with `scripts/evaluate_policy_report.py`

## Git and deployment

The repository is designed for Git-based deployment.

Typical server flow:

```bash
git pull
python scripts/generate_dataset.py --output-dir data/generated --scenario-count 216
```

Generated datasets and DSSAT run directories are ignored by default in `.gitignore`.
