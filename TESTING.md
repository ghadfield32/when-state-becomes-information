# Verification profiles

From the package root, using the activated lab Python:

```sh
python -m pytest -c pytest-source.ini -q
```

This source-only profile runs public acquisition boundary tests plus synthetic,
protocol, storage, leakage, unit and end-to-end fixture tests. It explicitly
deselects nine historical tests that
read real files but lack a real-data marker, and excludes three checks marked
`private_evidence`. Exact node IDs live in `pytest-source.ini`; they are not
silently turned into passes. Two inherited fixture helpers now isolate their
fake Git response to the study module so Matplotlib's Linux font discovery
uses the real subprocess API. Their scientific assertions are unchanged;
two regression tests cover the unrelated-subprocess boundary.

After authorized data acquisition, run the original public profile:

```sh
cd docs/backend/projects/world_model/open_world_model
python -m pytest tests/ -q
```

That profile includes the nine data checks. Three private-evidence checks
remain excluded because their inputs were never part of this public package.
Explicit private selection requires a separately authorized private checkout;
do not add those artifacts to the public repository.

For numeric result reproduction, use `python reproduce.py` from the package
root after data setup. It rebuilds fits and all six phase reports and compares
trial-cluster intervals. Its inherited comparison deliberately ignores some
metadata including `analysis_identity`; separately verify source/config hashes
and input custody. A numerical comparison does not establish provenance alone.

Push and pull-request CI run the source-only profile and protocol validation
with read-only GitHub permissions. The manually dispatched `full_reproduction`
option additionally downloads exactly the pinned 396 inputs, runs the full
public profile and refits/reconciles the historical results. Neither workflow
uploads participant data or prediction stores. Actual remote execution is
reported separately from local validation; a workflow file is not a passing run.
