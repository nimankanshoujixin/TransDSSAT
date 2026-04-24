# TransDSSAT Pipeline Summary

This note is written for reporting and Feishu synchronization. It intentionally focuses on the pipeline, architecture, and current status rather than low-level debugging details.

## Objective

Build a crop decision training pipeline in which:

1. a decision model outputs season-level water and nitrogen actions,
2. a crop mechanism backend evaluates those actions,
3. the backend returns trajectory data and a reward,
4. the resulting samples support Transformer training and validation.

## Current architecture

The repository now uses a dual-backend design.

### 1. Proxy backends

- `wofost_proxy`
- `dssat_proxy`

Purpose:

- fast local development,
- quick dataset generation,
- schema design for state, action, trajectory, and reward.

### 2. Official DSSAT backend

Backend choice:

- official `DSSAT/dssat-csm-os`
- official `DSSAT/dssat-csm-data`

Purpose:

- provide a high-fidelity season evaluator,
- run real DSSAT simulations on the server,
- parse daily outputs and convert them into training trajectories.

## Decision format

The decision unit is season-level stage control rather than daily online control.

Each policy contains one action for four major stages:

- emergence
- vegetative
- reproductive
- grain_fill

Each action includes:

- date
- day index
- irrigation amount
- nitrogen amount

This is more compatible with DSSAT's natural whole-season execution model than forcing a day-by-day interactive API.

## Data flow

The current pipeline is:

1. build a scenario
2. generate a season policy
3. materialize a DSSAT run directory
4. execute DSSAT
5. parse `Summary.OUT`, `PlantGro.OUT`, `SoilWat.OUT`, `SoilNi.OUT`
6. reconstruct state-action-result trajectories
7. compute reward
8. export train/test datasets

## Repository modules

- `transdssat/scenarios.py`
  Scenario construction for crop, soil, weather regime, budgets, planting date, cultivar code, and template name.
- `transdssat/season.py`
  Season policy abstraction and baseline policy generator.
- `transdssat/dssat/inputs.py`
  Writes per-run manifests, policy files, soil files, scenario files, and weather files.
- `transdssat/dssat/runner.py`
  Launches the DSSAT command for one prepared run directory.
- `transdssat/dssat/parser.py`
  Parses official DSSAT output files into structured states and outcomes.
- `transdssat/environments/adapters.py`
  Wraps official DSSAT as a season-level evaluator.
- `transdssat/dataset.py`
  Builds trajectory datasets for training and testing.
- `transdssat/policy.py`
  Contains the Transformer-oriented supervised example iterator and model skeleton.

## Server-side runtime setup

The server-side DSSAT runtime has been validated in principle:

1. official DSSAT source compiled successfully,
2. official experimental data repository downloaded,
3. a combined runtime directory was assembled,
4. official maize example execution succeeded,
5. the runtime was connected to `TransDSSAT` through environment variables.

Required server variables:

- `DSSAT_HOME`
- `DSSAT_TEMPLATE_ROOT`
- `DSSAT_RUN_COMMAND`

Optional:

- `DSSAT_PREPROCESS_COMMAND`
- `DSSAT_WORK_ROOT`
- `DSSAT_TIMEOUT_SECONDS`

## Current status

### Already completed

- Git-based project structure
- proxy backend dataset generation
- season-level action abstraction
- official DSSAT runner scaffold
- server-side DSSAT compilation and runtime assembly
- first successful `TransDSSAT -> official DSSAT` execution path
- season policy injection into DSSAT maize template
- scenario weather injection into DSSAT weather files
- differentiated real-DSSAT maize results under dry / normal / wet representative years
- season policy injection into DSSAT wheat template
- cross-year DSSAT weather generation for winter wheat
- differentiated real-DSSAT wheat results under dry / normal / wet representative years
- unified experiment-file routing so maize and wheat can share one `DSSAT_RUN_COMMAND` template through `{experiment}`

### Current integration level

- real DSSAT `maize` path: connected
- real DSSAT `wheat` path: connected
- proxy backends: still available for fast local iteration
- remaining work is no longer basic connectivity, but scaling, Quzhou-specific template refinement, and training-loop integration

### Next milestone

Expand the real backend from "validated single-crop template execution" to "stable sample generation and model training" by:

- generating larger wheat and maize sample sets,
- refining cultivar / soil / weather templates toward Quzhou-specific inputs,
- connecting the real DSSAT sample library to Transformer training.

## Training meaning

Once template injection is completed, the full intended loop is:

1. Transformer proposes stage-level water and nitrogen actions
2. TransDSSAT builds a DSSAT run for that policy
3. DSSAT simulates the season
4. TransDSSAT parses outputs into trajectory and reward
5. results are used for supervised learning, offline RL, or policy improvement

## Practical conclusion

The project has moved from concept validation to a partially connected real-backend pipeline.

The most important result so far is that the official DSSAT backend is no longer only theoretical:

- it compiles on the server,
- it runs official example experiments,
- it is already callable from the TransDSSAT codebase.

The remaining work is mainly scale-up and domain adaptation:

- larger sample construction,
- Quzhou-specific template refinement,
- Transformer training and validation on the real-backend sample library.
