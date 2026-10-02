# E1 claim ledger

Every material claim in `abstract.txt`, bound to its evidence and its limitation.

Scope: the historical three-athlete E1 study, frozen at tag `e1-2026-10-01`
(commit `9f4b38df3e1ffc577d670463ee5b74d4fbba7255`). Evidence paths are relative
to this repository.

| Claim | Evidence | Qualification |
|---|---|---|
| Three athletes at 60 Hz, SPL Open Data | `SOURCE_MANIFEST.json`; `spl_data/UPSTREAM_FILES.json`; pinned revision `a3f9cffb…` | One source corpus. Not a population sample; three athletes cannot establish generalization |
| 9,619 forecast decisions of 14,594 scheduled | `experiment_report.json`; independent recomputation in `REVIEW.md` | Eligibility needs a fully observed preceding 267 ms (hand and finger markers) plus a reference sample within 8 ms. This is **retrospective selection**, not a live test |
| Whole-trial constant velocity best at 150.5 mm | `release_stratum_report_*.json`; equal-athlete mean 150.5167 mm | Point estimate. M4's whole-trial superiority is **not** established |
| Whole-trial M4 8.0 mm worse (−18.7 to +23.8) | Same reports; 8.0133 mm; trial-cluster interval | Interval covers trial sampling within these three athletes only. Between-athlete heterogeneity is larger and is not in the interval |
| More than 100 ms before release: M4 worse for every athlete | Phase-stratum reports | Richer state is not universally better; this is the direction that contradicts a naive "more state = better" reading |
| Final 100 ms: M4 124 mm vs CV 197 mm | `…near100.json`; 124.2695 / 197.2633 mm | Retrospective release grouping, used only for evaluation. The release is a detector proxy, not physical truth |
| Near-release advantage 66–79 mm better, 263 trials | Trial-cluster interval, 263 decisions from 263 distinct trials | One decision per trial near release; resampling unit is the whole trial |
| Advantage held across declared boundaries and both grids (21–77 mm) | Six stratum configurations; 21.034–77.174 mm | Sensitivity, not independent confirmation. Boundaries are detector configs |
| Gain from two athletes (−116, −118 mm); third worse (+12 to +71) | Per-athlete tables; P0003 range 11.709–71.245 mm | **Central heterogeneity result.** Two of three improve; the third reverses in every configuration |
| Of the 73 mm equal-athlete mean, 56 mm is extrapolation→M3 | Decomposition in the stratum reports; M4−M3 = −16.7894 mm near release | The estimator **and** the inputs change together at that step. It is not a pure body-state effect |
| Detailed hands add 14.2 mm (12.4–16.1) over coarse hands | `interval_analysis/RESULTS_RAW.txt` | This is the clean detailed-hand increment. Do **not** present the full ~73 mm as a finger effect |
| Exception: third athlete, wider grid, two of three boundaries | Sensitivity tables | The increment is not universal; the exception is retained rather than smoothed |
| Three athletes cannot establish generalization | Design limit | Stated in the abstract. No population or transfer claim is made |
| Forecast errors against supplied motion capture, not tracking accuracy | Design limit | Physical tracking accuracy is untested. A live system would have to estimate release phase itself |

## Not established by this abstract

- Any four- or five-athlete result, or athlete-to-athlete transfer.
- Directional correctness versus endpoint error.
- Hand-feature ablation after refitting.
- Physical tracking accuracy, live forecasting, make/miss, or coaching benefit.
- Any claim that richer measurement is generally better, or generally worse.

Those belong to a separate full-paper extension. The three-athlete study supports
a hypothesis about conditional state value; it does not establish a general law.

## Post hoc vs frozen

The whole-trial result existed before the phase grouping. The grouping by timing
relative to a retrospectively detected release, the decomposition of the
near-release gain, the across-grid/boundary sensitivity, and the trial-cluster
intervals in `interval_analysis/` were all added **after** those reports. They are
**descriptive and post hoc**, and are labelled as such in the abstract.
