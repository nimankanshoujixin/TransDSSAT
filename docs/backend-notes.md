# Backend Notes

## Recommended backend

Use the official DSSAT runtime as the high-fidelity backend:

- [DSSAT/dssat-csm-os](https://github.com/DSSAT/dssat-csm-os)
- [DSSAT/dssat-csm-data](https://github.com/DSSAT/dssat-csm-data)

Keep the repository's proxy backends for local development and smoke tests.

## Why this repository uses a wrapper around official DSSAT

The repository now assumes this division of responsibility:

- TransDSSAT:
  - creates season-level water and nitrogen decisions,
  - materializes a run workspace,
  - launches DSSAT,
  - parses `PlantGro.OUT`, `SoilWat.OUT`, `SoilNi.OUT`, and `Summary.OUT`,
  - converts outputs into reward-bearing trajectories.
- Server-side DSSAT runtime:
  - contains the compiled DSSAT executable,
  - contains crop-specific base experiment templates,
  - optionally runs a preprocessing script to turn TransDSSAT manifests into final DSSAT input files.

This is more stable than binding the repository to an unofficial Python wrapper.

## Required environment variables for the official backend

- `DSSAT_HOME`: root of the DSSAT runtime on the server
- `DSSAT_TEMPLATE_ROOT`: directory containing crop-specific base run templates
- `DSSAT_RUN_COMMAND`: command template that executes one prepared run directory

Optional:

- `DSSAT_PREPROCESS_COMMAND`: command template that converts `transdssat_manifest.json` into final DSSAT input files before execution
- `DSSAT_WORK_ROOT`: where per-run folders are created, default `data/dssat_runs`
- `DSSAT_TIMEOUT_SECONDS`: run timeout, default `600`

Command templates can use:

- `{run_dir}`
- `{manifest}`
- `{policy}`
- `{scenario}`
- `{crop}`
- `{experiment}`

## Practical template contract

For each crop, place one validated base template directory under `DSSAT_TEMPLATE_ROOT`.

Example:

- `DSSAT_TEMPLATE_ROOT/wheat_quzhou_base/...`
- `DSSAT_TEMPLATE_ROOT/maize_quzhou_base/...`

When TransDSSAT evaluates a policy, it will:

1. copy the selected template directory into a new run folder,
2. write:
   - `transdssat_manifest.json`
   - `transdssat_scenario.json`
   - `transdssat_soil.json`
   - `transdssat_weather.csv`
   - `transdssat_policy.tsv`
3. run the optional preprocess command,
4. run the DSSAT command,
5. parse the generated output files.

## What still must be customized on the server

One server-side customization remains unavoidable:

- either a crop template that is already runnable as copied,
- or a preprocess script that reads `transdssat_manifest.json` and writes the final DSSAT experiment files expected by your DSSAT setup.

That last mile depends on your cultivar files, weather file naming, soil file layout, and experiment template conventions.

Current repository status:

- `scripts/render_dssat_inputs.py` now provides a first working policy-injection path for the copied maize and wheat experiment templates already used in server validation
- it rewrites treatment 1 irrigation and inorganic fertilizer events from `transdssat_policy.tsv`
- it regenerates DSSAT weather files directly from `transdssat_weather.csv`
- the generated weather files now cover cross-year seasons, which is required for winter wheat
- when a copied template contains multiple experiment files, it prefers the `experiment_file` defined on the scenario, and the DSSAT command can reference that file via `{experiment}`
- this is a practical bridge from "template runs" to "policy-driven runs", even though full Quzhou-specific cultivar, soil, and weather rendering still remains to be completed

## Policy learning modes

The repository now supports two different learning modes:

- supervised imitation:
  - train on existing stage decisions from generated trajectories
  - useful for smoke tests and pipeline verification
- season-level RL:
  - directly sample four stage decisions from scenario context
  - evaluate them with DSSAT reward
  - optimize the policy with REINFORCE-style updates

The RL path is the direction to use if the goal is "given a scenario, directly generate a strong policy" rather than "imitate one existing policy library."

## Agronomic reporting

Do not rely only on optimization loss when reporting model quality.

Use `scripts/evaluate_policy_report.py` to export agronomic scorecards that summarize:

- yield
- water and nitrogen inputs
- water-use efficiency
- nitrogen-use efficiency
- cumulative reward
- average water and nitrogen stress
- composite `total_score_100`

This makes final model quality interpretable for non-ML users.
