# E1 abstract: revision draft for review, revision 5 (2026-09-29)

**Status:** reviewed candidate; **not submitted** (no submission receipt exists yet). The reviews cited below were fresh read-only sessions of the same model family as the author (reduced independence); operator sign-off is still required.
- It revises `reports/world_model/v1_2/releasestate01_v1_2/SSAC27_ABSTRACT_DRAFT.md`, which was independently reviewed on 09-22 and 09-25.
- Revision 2 addressed the independent review of `36da6b8c7` (MAJOR 1–2, MINOR 3–7).
- Every new number comes from `EVIDENCE_DOSSIER_20260929.md`, `interval_analysis/RESULTS_RAW.txt` (post hoc) or `release_stratum_report_preregistered_near100.json` (9,619 / 14,594 and the M3b column).
- Revision 4 ("pooled 73 mm" became "73 mm equal-athlete mean gain") was APPROVED in the affected-scope review of #2120. Revision 5 shortened the Introduction and dropped the Conclusion's opening sentence (no result or caveat removed); it was APPROVED in the affected-scope review of #2129 (head `12961ea7b`). All reviews were fresh read-only sessions of the same model family as the author (reduced independence). This is a submission candidate; no receipt is recorded. The canonical title was updated on 2026-10-01 without changing scientific text or values; affected-scope review is separate from the historical reviews above.

**Summary of changes (see the word diff for the complete record):**
1. Whole trial: "constant velocity was best" is now "had the lowest error … within trial-level variation", with an interval.
2. Near release: trial-level intervals and per-athlete sign statements are added.
3. Hand result: restated as detailed vs coarse hands (M4 − M3b), scoped to the final 100 ms, with its interval and its boundary-dependent exception.
4. Attribution: a sentence now says that constant velocity → M3 changes the estimator and is not attributed to body information. The Conclusion states the hand gain as about 14 mm.
5. Population: now states that hand and finger markers were required (9,619 of 14,594 scheduled decisions).
6. Table 1: an M3b column is added.
7. **Removed:**
   - "Every ridge-model forecast is stored and replays from its fitted model."
   - "using final positions and final-interval velocities"
   - "never to select or route a forecast"; the remaining phrase is "used only for evaluation".
   - "all from the same three athletes"; the generalisation limit is restated in the Conclusion.
8. **Kept or restored:** the live-system caveat ("a live system would have to estimate the release phase itself");
   - the grid definition (pre-registered grid, wider grid as sensitivity);
   - "three athletes cannot establish how it generalises".

---

## When State Becomes Information: Release-Conditioned Basketball Forecasting

**Introduction.** Teams have little public evidence on when finger-level motion capture improves prediction. We ask whether richer body and hand state improves a 100 ms ball forecast, and whether that depends on timing within the shot.

**Methods.** We used SPL Open Data free-throw motion capture (MLSE Sport Performance Lab, CC BY-NC-SA 4.0) from three athletes at 60 Hz. There were 9,619 forecast decisions, one every 100 ms, out of 14,594 scheduled. Each needed a fully observed preceding 267 ms, including hand and finger markers, plus a reference sample within 8 ms of the target. This is a retrospective selection, not a live test. We compared constant-velocity extrapolation with three ridge models of increasing state: ball and core body (M3), plus coarse hand (M3b), plus detailed hand and finger markers (M4). Models were trained leave-one-athlete-out, with regularisation chosen within training athletes, under a pre-registered tuning grid and a wider grid as sensitivity. After the whole-trial result existed, we grouped forecasts by timing relative to a retrospectively detected release, used only for evaluation. Post hoc intervals resample whole trials within each athlete.

**Results.** Across whole trials, constant velocity had the lowest error (150.5 mm); M4 was 8.0 mm worse, within trial-level variation (95% interval −18.7 to +23.8). More than 100 ms before release, M4 was worse on average for every athlete. In the final 100 ms, M4 erred by 124 mm against constant velocity's 197 mm (trial-level interval 66–79 mm better, 263 trials; Table 1). The advantage held across declared release boundaries and both grids (21–77 mm). It came from two athletes (−116, −118 mm); for the third, M4 was worse in every configuration (+12 to +71 mm). Of the 73 mm equal-athlete mean gain, 56 mm arises at the step from extrapolation to the fitted ball-and-body model, which changes estimator and inputs together. In the final 100 ms, detailed hands improved on coarse hands by 14.2 mm (12.4–16.1), except for the third athlete under the wider grid at two of three boundaries.

**Conclusion.** Just before release, fitted models were markedly better for two of three athletes; detailed hand markers added about 14 mm beyond coarse hands. Teams weighing hand-level capture should judge it by phase and athlete, not whole-trial averages. Three athletes cannot establish how this generalises. These are forecast errors against supplied motion capture, not tracking accuracy, and a live system would have to estimate the release phase itself.

**Table 1.** Mean per-athlete endpoint error (mm), pre-registered grid.

| Decision timing | Decisions | Constant velocity | M3 | M3b | M4 |
|---|---:|---:|---:|---:|---:|
| More than 100 ms before release | 4,382 | **66** | 79 | 80 | 83 |
| Within 100 ms before release | 263 | 197 | 141 | 138 | **124** |
| At or after release | 4,974 | **210** | 222 | 221 | 220 |

---

**Claim bindings for new text:**

| Claim | Source |
|---|---|
| 9,619 of 14,594 scheduled | stratum report `analysis_identity.store_counts`: intended 14,594, input_eligible 9,619, m4_unavailable 4,975 |
| Whole trial +8.0 [−18.7, +23.8] | `RESULTS_RAW.txt` pre-registered/primary `whole` |
| Worse on average before release | `far`: +10.9 [−1.7, +21.6], +23.4, +15.6 |
| Trial-level 66–79 | `near M4-constant_velocity` EQUAL [−79.4, −66.2] |
| Mostly fitted vs extrapolation | CV→M3 −56.2 of −73.0 (dossier §2) |
| 14.2 [12.4, 16.1], final 100 ms | `near M4-M3b` EQUAL |
| Third athlete, wider grid, 2 of 3 boundaries | `amended_RS_A2` primary +3.7 and 1.5 +3.8 (worse); 3.0 −5.2 (better) |
| M3b column 80 / 138 / 221 | stratum report `M3b.equal_athlete_mean_m` 0.0803 / 0.1385 / 0.2212 |
