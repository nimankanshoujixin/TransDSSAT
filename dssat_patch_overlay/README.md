# DSSAT Patch Overlay

This directory is the repo-local staging area for copied-runtime DSSAT Fortran edits.

Expected layout:

```text
dssat_patch_overlay/
  CSM_Main/
    CSM.for
    LAND.for
  Management/
    MgmtOps.for
```

Rules:

- only place files here that intentionally override the copied DSSAT source tree
- keep paths identical to the upstream DSSAT source tree rooted at `dssat-csm-os-v4.8.5`
- do not place generated build outputs here
- patch the copied runtime only; never patch the vanilla runtime in place

Recommended remote workflow:

1. prepare or update the overlay files in this directory
2. upload the overlay directory to the remote host
3. run `bash scripts/build_patched_dssat_runtime_remote.sh --overlay-root <uploaded-overlay> --clean`
4. run parity or interactive smoke against the refreshed patched runtime

The current first-stage target remains:

- `CSM_Main/CSM.for`: interactive mode flag and day-boundary control
- `CSM_Main/LAND.for`: helper-backed `session_ready` and state export gate
- `Management/MgmtOps.for`: later irrigation/nitrogen action injection
