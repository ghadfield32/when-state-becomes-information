# Local validation — 2026-10-01

This separates executed local evidence from remote CI, public acquisition,
measurement validity and scientific approval. A passing historical
reproduction is not a new-athlete or prospective validation.

## Fresh locked environment

On October 1, 2026, the 101-file source extraction was independently unpacked
into a new standalone scratch directory. This command completed with exit 0:

```sh
uv sync --locked --no-install-project --extra dev --extra cpu --python 3.12
```

Runtime: Python 3.12.6, NumPy 2.5.3, Matplotlib 3.11.1, PyTorch 2.14.0+cpu,
pytest 9.1.1. Lock SHA-256:
`9010ccc0e7610375e4d45333ebfff29012c1b9a02e806b787a2587e1ac1ac203`.
The original four admitted archive hashes all matched, and 396 files unpacked.
The unchanged full public profile executed in this fresh environment:
**630 passed, 3 private-evidence checks deselected, exit 0** (48.02 seconds).
No protected participant was acquired or evaluated.

The fresh `reproduce.py` run completed with **exit 0**. It rebuilt the fits,
replayed 57,714 forecasts at the fixed 1e-9 m tolerance, regenerated all six
stratum reports and all six trial-cluster interval blocks. The final verdict
was: **experiment, baselines, six stratum reports and interval analysis all
match the committed results**. No comparator or scientific source was changed.
Input/config/source identity was checked separately because the inherited
numerical comparator omits machine-dependent metadata and `analysis_identity`.

The expanded source profile, including the new acquisition boundary tests,
also passed in the fresh environment: **649 passed, 12 deselected, exit 0**
(10.02 seconds). The new helper's focused suite passed **28 tests, zero skips**.
Public acquisition also completed with **exit 0: 396 downloaded** directly
from the pinned upstream URLs without authentication. Offline verification
passed for all 396 downloaded files and separately for all 396 archive-extracted
inputs used in the fresh refit; both sets match every published original hash.
No full upstream clone or other participant was requested. Machine-readable
evidence is in [REPRODUCTION_RECEIPT.json](REPRODUCTION_RECEIPT.json).

## Source checks

### Linux CI fixture correction

The first public Linux CI run at commit `7636cd4` executed the source suite:
645 passed and four failed because two inherited test helpers replaced the
shared `subprocess.check_output` function with a string-returning Git stub.
Matplotlib's first Linux font query legitimately expected bytes from that API.
The failure did not involve an experiment fit or a scientific assertion.

The correction replaces only each study module's test-time subprocess binding.
Two new regression checks first failed by receiving the fake revision instead
of real child-process bytes, then passed. The complete affected test modules
passed **36 tests, 2 existing private-evidence exclusions**. Runtime scientific
source, configs, lock, results and numerical comparators remain unchanged.
`SOURCE_MANIFEST.json` records the two test-file exceptions explicitly.
Remote verification of this correction is tracked in GitHub Actions.

From this root, using an existing Python 3.12.6 / NumPy 2.3.5 / pytest 9.0.2
environment (not a newly synchronized lock):

```sh
python -B -m pytest -c pytest-source.ini -q -p no:cacheprovider
```

**621 passed, 12 deselected, exit 0.** A separate read-only reviewer reran the
same profile: **621 passed, 12 deselected, exit 0**. See `TESTING.md` for exact
data/private exclusions. A pre-existing requests dependency warning was
emitted; it did not fail these tests.

From the lab directory:

```sh
uv lock --check --offline
python scripts/validate_release_state_protocol.py configs/experiments/release_state_v1_2.json
```

Lock check: **exit 0**, 104 packages resolved. Protocol: **PASS**, empty
refusal list. This checks existing lock consistency, not installation.

## Real-data retained-fit replay

Executed using this package's unchanged scientific source and the existing
E1 environment, Python 3.12.6 / NumPy 2.5.3 / Matplotlib 3.11.1. The external
input directory contains the historical admitted P0001–P0003 population.
No P0004/P0005 input or new fit was used.

From the lab directory, substitute authorized paths for the capitalized inputs:

```sh
python scripts/verify_release_state_forecasts.py --store SAVED_STORE --config configs/experiments/release_state_v1_2.json --data-root ADMITTED_SPL --report ABSOLUTE_EXPERIMENT_REPORT --tolerance-m 1e-9
```

`ABSOLUTE_EXPERIMENT_REPORT` must exist and point to this package's
`reports/world_model/v1_2/releasestate01_v1_2/experiment_report.json`.
The inherited verifier does not fail merely because an optional report is
missing. Check that output contains `reconciles: true` and all six comparisons;
`REPLAYED` by itself is insufficient for report reconciliation.

Executed result: **REPLAYED**, **57,714** forecasts checked, maximum absolute
difference **6.394884621840902e-14 m**, tolerance **1e-9 m**, `refitted: false`,
`reconciles: true`. All six grid/family report values matched exactly:

| Grid | M3 | M3b | M4 |
|---|---:|---:|---:|
| preregistered | 0.15986 | 0.15949 | 0.15853 |
| amended_RS_A2 | 0.16138 | 0.16171 | 0.16076 |

Values are mean-of-athlete-means endpoint error in metres. Accounting:
14,594 intended, 9,619 input eligible, 57,714 emitted/paired scoreable ridge
forecasts, 4,975 M4 unavailable. Constant velocity is not a stored ridge forecast.

## Primary trial-cluster interval replay

The unchanged interval script was executed against the same real source and
retained forecast store, primary preregistered grid and default release boundary:

```sh
python reports/world_model/v1_2/releasestate01_v1_2/interval_analysis/trial_cluster_intervals.py docs/backend/projects/world_model/open_world_model SAVED_STORE ADMITTED_SPL preregistered None reports/world_model/v1_2/releasestate01_v1_2/release_stratum_report_preregistered_near100.json
```

Exit 0; 10,000 resamples, seed 20260929, trial-within-athlete units. Output
matches the primary block of retained `interval_analysis/RESULTS_RAW.txt`:
M4 minus coarse-hand M3b **-14.2 mm [-16.1,-12.4]**; M4 minus CV
**-73.0 mm [-79.4,-66.2]** near release; whole-trial M4 minus CV
**+8.0 mm [-18.7,+23.8]**. Conditional fixed-fit intervals do not measure
new-athlete uncertainty. That initial retained-fit check covered the primary
block only; the later fresh reproduction above regenerated all six blocks.

## Remaining verification gates at this checkpoint

- Anonymous clone of the subsequently published exact source commit.
- Remote execution of the included workflow.
- Hand/direction real studies, five-athlete evaluation and prospective validation.

Historical fresh-clone logs were inspected but are not presented as a new
execution of this exact extraction. The source/result SHA manifests preserve
identity separately from numerical equality.
