# Independent review record

This file is a public summary of the independent reviews performed against the release-state
analysis (`reports/world_model/v1_2/releasestate01_v1_2/`) before its numbers were used in the
SSAC27 abstract. It replaces the raw review transcripts, which recorded local machine paths and
unrelated local tool configuration and are not published. This is a historical review record, not approval of the 2026-10-01 source-only extraction.
Every defect below was closed in the
committed reports and code before the corresponding review approved; that historical approval is limited to its stated scope and does not close later
measurement, access, population-generalization or public-release findings.

Three review passes are on record. All three were independent, read-only sessions that did not
author the work under review.

## Round 1 -- initial review

**Scope reviewed:** the abstract and its claim map
(`reports/world_model/v1_2/releasestate01_v1_2/SSAC27_ABSTRACT_DRAFT.md`), the analysis report
(`RELEASE_STRATUM_V16_S1.md`), the evidence it rests on (the six `release_stratum_report_*.json`
files, `experiment_report.json`, `baselines_report.json`, `forecast_store_COMPLETE.json`,
`forecast_replay_verification.json`, `figures/`), and the analysis code
(`stratify_release_state.py`, `forecast_store.py`, `verify_release_state_forecasts.py`,
`run_release_state_experiment.py`, `build_release_state_dataset.py`, and
`release_state_v1_2.json`).

**Criteria checked:** claim-to-evidence fidelity (every number, count, population and unit in the
abstract matches the committed evidence, with headline numbers independently recomputed); no
leakage (the retrospective release label only groups already-issued forecasts and never selects,
routes or alters one; model selection uses training athletes only); estimand honesty (aggregate
vs. per-athlete, decisions vs. predictions, proxy vs. physical release, and analysis chronology
are stated correctly); internal consistency; reproducibility (replaying the stored forecasts
without refitting); and scope (no claim of hand forecasting, coaching benefit, or novelty).

**Decision: APPROVE.** Zero BLOCKER or MAJOR findings; two MINOR findings.

Independent recomputation from the committed JSON reports confirmed the headline numbers,
including: whole-trial constant-velocity equal-athlete mean 150.5167 mm; whole-trial M4
disadvantage 8.0133 mm; primary near-release constant-velocity/M4 197.2633/124.2695 mm; primary
near-release M4 advantage 72.9939 mm; primary M4-minus-M3 -16.7894 mm; the six-configuration M4
advantage range 21.034-77.174 mm; the P0003 disadvantage range 11.709-71.245 mm; 9,619 decisions
against 57,714 stored forecasts; and 263 decisions from 263 distinct trials near release. The
reviewer replayed all 57,714 stored forecasts without refitting (maximum discrepancy
6.394884621840902e-14 m, all six grid/family reconciliations exact) and independently rebuilt all
six stratum reports.

**Defects found and required changes:**

1. **MINOR (claim-to-evidence, estimand honesty) -- 
   `SSAC27_ABSTRACT_DRAFT.md`.** The sentence "Every forecast is stored and replays from its
   fitted model" overstated the stored population: the store holds only the M3, M3b and M4 ridge
   families (9,619 x 3 x 2 = 57,714 stored forecasts); constant velocity is reconstructed from
   source-derived features at scoring time, not stored. Required change: say "Every ridge-model
   forecast is stored and replays from its fitted model."
2. **MINOR (estimand honesty) -- `stratify_release_state.py` and all six
   `release_stratum_report_*.json`.** A code comment and the generated `post_release` stratum
   definition retained an already-withdrawn physical-flight interpretation ("only pre-release
   forecasts can be issued live"; "ball already in free flight"), contradicting the analysis
   report's own correction of that interpretation. Required change: update the comment and the
   generated stratum definition to describe timing relative to the retrospective release proxy
   only, then regenerate the six reports; the prediction hashes, coverage and numerical summaries
   must not change.

## Round 2 -- focused remediation review

**Scope reviewed:** only the two findings above, the exact code/report delta that closed them,
and the invariants that delta could have affected -- not a re-review of the whole packet.

**Decision: APPROVE.** Both findings **CLOSED**:

1. The abstract now reads "Every ridge-model forecast is stored and replays from its fitted
   model." A fresh replay of the store passed (maximum discrepancy again
   6.394884621840902e-14 m, 6/6 aggregates reconciled).
2. The withdrawn live-issuance/free-flight language is gone from the code comment and from the
   generated stratum definition in all six reports; each report's recorded stratifier-code digest
   matches the corrected script.

The reviewer confirmed that `by_stratum`, `paired_M4_minus_M3_by_stratum`, `coverage`,
`join_checks`, `release_detection` and the stored-forecast digest are **identical** across all six
reports before and after the fix -- the only changed JSON leaves per report were the
`post_release` stratum-definition text, the recorded stratifier-code digest, and a path-only
metadata field, plus the corresponding abstract wording.

**New finding, non-blocking:**

3. **MINOR (estimand honesty) -- `SSAC27_ABSTRACT_DRAFT.md`.** Wording said constant velocity is
   recomputed "from the stored features," but the per-example features are rebuilt from source
   data at scoring time and are never part of the forecast store, which holds only predictions
   and fitted model artifacts. Required change: describe constant-velocity forecasts as
   "reconstructed from source-derived features and are not stored." This is a wording fix with no
   effect on any numerical result. It is closed in the claim map committed in this repository
   (`SSAC27_ABSTRACT_DRAFT.md`'s "ridge forecasts stored and replayable" row).

The reviewer noted its own scope limits: it did not re-run model fitting or hyperparameter
selection, did not run the full test suite, did not assess physical release ground truth, and
(reviewing an extracted, history-free copy) did not independently authenticate the reviewed
commit's identity or diff against a base branch.

## Round 3 -- affected-scope review of the 2026-09-25 abstract revision

A review request is on record for a second, narrower pass, scoped only to the sentences the
2026-09-25 abstract revision changed relative to the already-approved 2026-09-22 text (the new
retrospective-selection disclosure in Methods, the industry framing added to the Introduction and
Conclusion, and several trims), plus any unchanged sentence whose meaning a change alters. Its
criteria were: fidelity of each changed sentence to its cited source; that no previously required
claim was dropped; that no new overclaim was introduced; a word-count check against the SSAC27
rules; and that the claim map still covers every number in the abstract.

**No corresponding decision record for this round is present in the committed evidence this
repository draws on.** Unlike rounds 1 and 2, only the review request for this round exists in
the source material; this repository does not include (and did not receive) a completed verdict
for it. The abstract text in this repository (`SSAC27_ABSTRACT_DRAFT.md`) is the 2026-09-25
revision that this round's request describes, but this summary cannot state a review outcome for
it beyond that the request was made. Treat the 2026-09-25 abstract wording as reviewed only
through rounds 1 and 2's approval of its 2026-09-22 predecessor text, plus whatever independent
reading a reader of this repository chooses to give the current wording directly against the
claim map.
