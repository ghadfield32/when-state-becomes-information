# When State Becomes Information: Release-Conditioned Basketball Forecasting

A standalone reproduction package for the historical E1 Sloan research candidate.
Submission and acceptance are not established by this repository.
Code is MIT licensed. SPL data and derived aggregates have separate terms;
see [DATA.md](DATA.md) and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## What the evidence establishes

This retrospective three-athlete study forecasts ball position 100 ms ahead
against supplied motion capture. The final 100 ms before a retrospective
release proxy contains 263 decisions. Equal-athlete endpoint errors are:

| Model | Near-release error (mm) |
|---|---:|
| Constant velocity | 197.263 |
| Ball + core body ridge (M3) | 141.059 |
| Plus coarse hand (M3b) | 138.464 |
| Plus detailed fingers (M4) | 124.269 |

M4 improves over M3b by **14.195 mm** in the rounded aggregate reports
(about 14.2 mm; post hoc trial-cluster interval 12.4–16.1 mm). The 16.8 mm
M3-to-M4 difference is a different comparison. The 73 mm CV-to-M4 difference
changes estimator and information together and is not a finger-only effect.
Across whole trials, CV has the lowest point estimate (the difference is within
trial-level uncertainty); one athlete is worse with M4 than CV under
all six near-release configurations. Three athletes do not establish
population transfer, physical tracking accuracy, or coaching benefit.

See [abstract.md](abstract.md), the [evidence dossier](reports/world_model/v1_2/releasestate01_v1_2/EVIDENCE_DOSSIER_20260929.md)
and [historical review summary](REVIEW.md). Historical document filenames
containing SUBMITTED do not establish a submission receipt.

## Start here

Use Python 3.12 and uv. From this repository root:

```sh
cd docs/backend/projects/world_model/open_world_model
uv sync --locked --no-install-project --extra dev --extra cpu --python 3.12
cd ../../../../..
```

Use that environment's Python for the following commands. On Windows its
path is `docs/backend/projects/world_model/open_world_model/.venv/Scripts/python.exe`;
on Linux/macOS it is `.venv/bin/python` under the same lab directory.
The CPU extra prevents implicitly choosing the CUDA dependency lane.
The inherited manifest is broader than E1 needs; a minimal replacement
requires its own environment/reproduction qualification.

```sh
# Source-only checks: no participant data or private artifacts required
python -m pytest -c pytest-source.ini -q

# Read DATA.md and the upstream terms, then fetch exactly the 396 E1 inputs
python fetch_data.py
python fetch_data.py --verify-only
python reproduce.py

# Full public profile after data setup
cd docs/backend/projects/world_model/open_world_model
python -m pytest tests/ -q
```

`python` above means the activated lab environment, not an arbitrary system
Python. See [TESTING.md](TESTING.md) for the exact difference between profiles.
`reproduce.py` checks the experiment, baselines, six phase reports and
post hoc trial-cluster intervals. Missing inputs cause failure. It creates
private outputs under `outputs/`; do not publish those outputs.

## Package structure

- `docs/backend/projects/world_model/open_world_model/`: historical scientific
  source, tests, frozen protocols and dependency lock. Runtime source and
  numerical evidence remain unchanged. Two inherited test fixtures have a
  documented subprocess-isolation fix for Linux; see `VALIDATION.md`.
  Historical paths are retained so scientific code needs no path rewrite.
- `reports/`: aggregate result tables, figures and provenance summaries.
- `spl_data/`: upstream licence, attribution, revision, input file manifest and archive hashes.
- `fetch_data.py`: pinned public acquisition with per-file SHA-256 verification.
- `reproduce.py`, `unpack_data.py`: unchanged historical reproduction entry points;
  the archive unpacker is an alternative for holders of the four exact archives.
- `SOURCE_MANIFEST.json`, `SHA256SUMS`: extraction provenance and package integrity.
- `PUBLICATION.md`: separate-repository extraction and release checks.

No Git submodule is needed. Never clone the full upstream corpus merely to
run E1: it contains participants outside E1's admission scope. The imported
`run_prefix_forecast.py` supplies helper functions only; its separate CLI
uses P0004 and is outside this package's reproduction path. Do not invoke it.
The public package is not an access-control sandbox.

## Scope and limits

The source-only tests verify software; they do not reproduce basketball
results. A saved forecast replay verifies a retained fit; it is not a fresh
refit or new external validation. The historical review record does not
approve subsequent packaging changes. [VALIDATION.md](VALIDATION.md) separates
executed reproduction evidence from remaining scientific and venue gates.

E1 uses 9,619 eligible decisions from 14,594 scheduled decisions, with
57,714 stored ridge predictions (three models, two grids). Retrospective
selection and phase labels must stay disclosed. The original three-athlete
paper must not absorb later challenger scores or proposed five-athlete
results. Protected-cohort execution belongs to a separately reviewed study.

See [DATA.md](DATA.md), [CONTRIBUTING.md](CONTRIBUTING.md), and
[PUBLICATION.md](PUBLICATION.md) before distribution.
