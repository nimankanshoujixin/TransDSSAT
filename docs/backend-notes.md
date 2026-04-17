# Backend Notes

## Recommendation

Keep the repository backend-agnostic and use proxy environments for local development.
Switch to a real DSSAT backend only on the server where the runtime can be controlled.

## `pyDSSAT`

Pros:

- Python-facing workflow
- conceptually close to the current environment wrapper design

Risks:

- public documentation describes a manual `f2py` wrapping workflow
- examples are tied to DSSAT 4.5 style setup
- not a drop-in modern package workflow

Use `pyDSSAT` only if the server owner is comfortable maintaining a DSSAT runtime and Python bindings together.

## Official `pythia`

Pros:

- official DSSAT Foundation Python package
- better fit if you want a supported DSSAT-facing Python layer

Risks:

- still expects a working DSSAT installation underneath
- environment constraints can be stricter than a lightweight pure-Python package

## Practical path for this repository

1. design state/action/reward and dataset schema locally with proxy backends,
2. validate trajectory quality and Transformer inputs,
3. on the server, wire one real backend into `transdssat/environments/adapters.py`,
4. keep the rest of the pipeline unchanged.
