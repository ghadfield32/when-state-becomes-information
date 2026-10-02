# SSAC27 E1 evidence dossier — 2026-09-29

**Paper:** "When Richer State Helps: Release-Conditioned Basketball Forecasting" (`SSAC27_ABSTRACT_DRAFT.md`, same folder).
**Status:** DRAFT dossier for operator and independent review. Nothing here has been reviewed. The abstract is **not** changed by this file.
**Base:** `origin/main` `7dec50b50`. **Packet:** `SSAC27-E1-EVIDENCE-DOSSIER-01`. Prepared by the author; a reviewer must be a different fresh session.

This is not the consumer-video "practice cue" project in `docs/backend/projects/research/ssac27-release-state-world-model/`. That workspace's `ABSTRACT.md` is a placeholder skeleton with no data and should be marked superseded.

## 1. What is new here

Three things the earlier reports lacked, all **descriptive and post hoc** (computed after the E1 reports and their independent review):

1. **Uncertainty.** The stratum reports carry point estimates only. `interval_analysis/` adds trial-cluster bootstrap intervals for every contrast used in the abstract.
2. **A decomposition of the near-release gain** into ball+core body, coarse hand and detailed hand steps.
3. **Sensitivity of both** across the two tuning grids and the three release-proxy boundaries the detector config declares.

Method (`interval_analysis/trial_cluster_intervals.py`, output in `RESULTS_RAW.txt`): refit nothing; reuse the committed stratifier's join and constant-velocity reconstruction; **first reproduce the committed report's equal-athlete means for that exact configuration** (max difference 5e-7 m across all six, and the script refuses otherwise); resample whole trials within each athlete, 10,000 times, seed 20260929, order-statistic percentile interval. The unit matches the pre-registration convention that `OW-ROBUST-VELOCITY-01` review enforced (round 1 caught decision-level resampling).

**Scope of every interval:** it covers trial sampling within these three athletes. It says nothing about future athletes. The equal-athlete interval averages three independently resampled athlete means. With two athletes helped and one hurt, between-athlete heterogeneity is the larger uncertainty and is not in any interval below.

## 2. Near-release result (final 100 ms before the retrospective release; 263 decisions, 263 trials)

Primary configuration (pre-registered grid, primary release boundary). Equal-athlete mean endpoint error, mm:

| Model | Error | Step |
|---|---:|---|
| Constant velocity | 197.263 | |
| M3 ball + core body | 141.059 | −56.204 vs constant velocity |
| M3b + coarse hand | 138.464 | −2.595 vs M3 |
| M4 + detailed hand/finger | 124.269 | −14.195 vs M3b |

Total M4 vs constant velocity −72.994 mm. The constant-velocity → M3 step changes **both** the estimator (extrapolation vs fitted ridge) and the information (body features), so its −56.2 mm must not be attributed to body features alone; isolating that needs a matched ball-only ridge, which this dossier does not have. The M3 → M3b → M4 steps are clean within-family information contrasts: detailed hand markers add about 14 mm beyond coarse hands. The abstract's "hand-level capture" framing should say so.

Paired contrasts, equal-athlete mm with 95% trial-cluster interval, across all six configurations (grid / release boundary in ball radii):

| Config | M4 − CV | M4 − M3 | M4 − M3b | M3b − M3 |
|---|---|---|---|---|
| pre-reg / primary | −73.0 [−79.4, −66.2] | −16.8 [−19.2, −14.4] | **−14.2 [−16.1, −12.4]** | −2.6 [−3.7, −1.5] |
| pre-reg / 1.5 | −77.2 [−83.6, −70.7] | −13.4 [−15.8, −11.0] | −12.4 [−14.3, −10.6] | −1.0 [−2.0, +0.2] |
| pre-reg / 3.0 | −41.8 [−49.5, −33.7] | −25.5 [−27.9, −23.1] | −19.0 [−20.9, −17.1] | −6.5 [−7.4, −5.7] |
| wider / primary | −63.9 [−70.5, −56.9] | −22.0 [−24.3, −19.7] | −15.2 [−16.6, −13.6] | −6.9 [−8.0, −5.7] |
| wider / 1.5 | −73.3 [−79.9, −66.7] | −16.1 [−18.9, −13.1] | −11.7 [−13.6, −9.7] | −4.4 [−5.7, −3.1] |
| wider / 3.0 | −21.0 [−29.2, −12.7] | −32.4 [−34.5, −30.2] | −20.6 [−22.2, −19.1] | −11.8 [−12.6, −10.9] |

- The M4 − CV range across configurations (−21.0 to −77.2) reproduces the abstract's "21 to 77 mm", which cross-checks this analysis against the reviewed claim map.
- **The M4 − M3b sign is negative in all six configurations**, range −11.7 to −20.6. It is not uniform by athlete: P0003 is **+3.7 [+2.4, +5.0]** and **+3.8 [+2.5, +5.1]** under the wider grid at the primary and 1.5 boundaries, and P0002 under pre-reg / 1.5 is −3.0 [−7.2, +1.2] (includes zero).
- **The third athlete's counterexample is not noise.** M4 − CV for P0003 is positive with an interval excluding zero in all six configurations (+11.7 to +71.2). Primary: P0001 −115.7 [−128.0, −101.2], P0002 −118.2 [−131.7, −104.4], P0003 +14.9 [+10.5, +19.7].
- Do not present "M4 improves on M3b within each athlete" as general: it holds in the primary configuration and fails for P0003 under the wider grid.

## 3. Where constant velocity "was best" needs softer wording

M4 − constant velocity, equal-athlete mm, pre-registered grid, primary boundary:

| Window | Equal-athlete | P0001 | P0002 | P0003 |
|---|---|---|---|---|
| Whole trial | **+8.0 [−18.7, +23.8]** | −45.5 [−124.4, +0.2] | +19.9 [+13.1, +26.2] | +49.6 [+44.6, +54.4] |
| More than 100 ms before | +16.6 [+12.2, +20.5] | +10.9 [−1.7, +21.6] | +23.4 [+19.5, +27.2] | +15.6 [+12.3, +18.5] |
| At or after release | **+9.9 [−34.2, +36.1]** | −74.6 [−203.8, −0.5] | +24.3 [+8.3, +38.6] | +79.8 [+69.8, +89.6] |

- **Whole trial and after release: the equal-athlete interval includes zero in all six configurations** (whole +8.0 to +10.2, upper bound at most +26.2; post +9.9 to +16.3). The abstract's "constant velocity was best" is a point ranking, and the athletes disagree in sign after release (−75 / +24 / +80). Suggested wording: "had the lowest error", plus that the difference was within trial-level variation.
- **Before release (more than 100 ms):** M4 is worse for all three athletes, and the equal-athlete interval excludes zero in all six configurations (+11.6 to +16.6). That claim is solid.
- P0001's whole-trial and post-release intervals are very wide (−124 to +0.2; −204 to −0.5). That is a heavy-tailed athlete.

## 4. Robust-velocity result and the paper

`OW-ROBUST-VELOCITY-01` (`causal_cvg_sub.v1`, tau 16.636 m/s, frozen on the 2024-08-28 development session, not promoted) reports −30.9 mm equal-athlete [−66.5, −10.4], median difference 0, and 37 scored forecasts changed (40 issued, 3 unscoreable).

- **The headline stratum is untouched.** The gate fired on 0 of 271 opportunities within 100 ms before release, so the near-release numbers above are unchanged by that candidate.
- **A hypothesis to test, not a finding:** M4's whole-trial and post-release advantage for P0001 sits in the same heavy tail that the gate repairs (P0001's paired improvement is −85.1 mm, against −4.5 and −3.0 for the other two). A stronger constant-velocity baseline could therefore narrow the post-release M4 advantage for that athlete. It has not been run and is not in any E1 claim. The gate design came from examining the evaluation session, so any such comparison needs its own frozen protocol.
- Keep it out of the abstract. It belongs in the repository README as a scoped robustness note.

## 5. Research pipeline: what it does and does not do (verified in code and in the 2026-09-28 local run)

- Stage 07 validates scorecard structure and ranks suggestions; it does not read a manuscript. The repository scanner's `allowed_repo_roots` are `docs/backend/projects`, `api/app`, `api/src/pipelines`, `api/src/airflow_project/dags`, `scripts`, `web/src`, `tests`. **`reports/` is not scanned**, so this paper's abstract and results are invisible to it.
- The local 2026-09-28 run (coverage `partial_governed_seed`) seeds 7 SSAC27 projects, all at result maturity 0–1 of 4. The E1 paper is not one of them. Its "nearest prior work" list is keyword-derived and includes a cricket paper; it lacks Body Shots and the high-resolution shot-capture study, so it supports no novelty claim.
- Adding E1 needs a **narrow, reviewed aggregate-evidence input**, not a wider scan. That is a separate reviewed bundle change and is not a submission prerequisite.
- Not checked: production `/research` serving and any authenticated snapshot.

## 6. Data-licence gate: operator statements recorded

Operator statement, 2026-09-29: **the company is not-for-profit, and the operator is not part of a sports organisation.** This is recorded as the operator's answer to questions 1 and 2 of `SUPPORTING_REPOSITORY_PLAN.md` §1. The repository cannot verify it and this file makes no legal determination.

Still open: question 3 attribution, licence link and change indication; question 4 ShareAlike treatment of aggregate statistics; question 5 link-not-copy (default plan); whether a prize competition counts as commercial use; and the **separate product use** (the admin lab serving MLSE-derived coordinates), which needs its own answers.

## 7. Proposed abstract changes (not applied; need an affected-scope review)

Budget: 468 words by whitespace, 487 if a counter splits hyphenated words, limit under 500.

1. Whole-trial sentence: "constant velocity had the lowest error (150.5 mm); M4 was 8.0 mm worse, within trial-level variation" (about +9 words).
2. Per-athlete near-release: add that the intervals excluded zero for all three athletes (about +7 words).
3. Optional, hand contrast: "detailed hands added 14.2 mm beyond coarse hands" (about +9 words).
4. Offset: drop "Every ridge-model forecast is stored and replays from its fitted model." (−12 words; it is already in the repository plan).

Items 1, 2 and 4 net +4 words. Adding item 3 needs a further trim, which is why it is optional. Do not quote the pooled interval as if it covered athletes.

## 8. Not established here

Not a claim of novelty; not a full-text comparison with Body Shots or the shot-capture study (not read); not a Sloan grade; not an acceptance probability; no independent clean-environment reproduction of the submitted numbers by anyone other than the author of this file; no physical release truth; no model refit; no new data opened (P0004 and P0005 untouched).

## 9. Reproduction

Needs the committed forecast store (sha256 `2a45be1d…`, per `forecast_store_COMPLETE.json`) and SPL Open Data at `a3f9cffbd`. Run once per configuration, giving the checkout of the same commit, the store directory, the SPL data root, the grid, the boundary radii (or `None`) and that configuration's committed `release_stratum_report_*.json`; all six writes to `RESULTS_RAW.txt` come from that loop. The store is per-sample MLSE-derived data and must not be published.
