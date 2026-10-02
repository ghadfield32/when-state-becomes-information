# SSAC27 abstract — draft for operator review

**Status:** DRAFT, revised 2026-09-25: adds the retrospective-selection disclosure and the industry question
and takeaway that the SSAC27 rules require, and trims the text to 468 words. The 2026-09-22 text passed
independent review (initial and focused remediation both APPROVE); the 2026-09-25 changes carry their own
affected-scope review. Records are in `review/`. Not submitted. Submission and data-permission confirmation
are operator gates. Every number below is traced to a committed report in the claim map at the end of this
file; the abstract itself stops at the horizontal rule.

---

## When Richer State Helps: Release-Conditioned Basketball Forecasting

**Introduction.** Motion capture now records basketball players down to finger joints, but
teams deciding what to capture have little public evidence on when that detail improves
prediction. We ask whether richer body and hand state improves a 100 ms ball forecast, and
whether that depends on timing within the shooting motion.

**Methods.** We used SPL Open Data free-throw motion capture (MLSE Sport Performance Lab, CC
BY-NC-SA 4.0): three athletes at 60 Hz and 9,619 forecast decisions, one every 100 ms.
Decisions required a fully observed preceding 267 ms and a reference sample within 8 ms of the
100 ms target, a retrospective selection: this benchmark is not a live-forecasting test. We
compared constant-velocity extrapolation with three ridge models of increasing state, each
using final positions and final-interval velocities: ball and core body (M3), plus coarse hand
(M3b), plus detailed hand and finger markers (M4). Models were trained leave-one-athlete-out,
with regularisation chosen within training athletes only. We report the mean of per-athlete
errors under the pre-registered tuning grid, with a wider grid as sensitivity analysis. After
the whole-trial result existed, we grouped the already-issued forecasts by timing relative to a
retrospectively detected release, a label used only for evaluation, never to select or route a
forecast. Every ridge-model forecast is stored and replays from its fitted model.

**Results.** Across whole trials, constant velocity was best (150.5 mm error), with M4 8.0 mm
worse. Grouping by release timing changes this (Table 1). More than 100 ms before release,
constant velocity was best (66 mm), as it was after release (210 mm). In the final 100 ms
before release, constant velocity erred by 197 mm and M4 by 124 mm, 73 mm better; this window
holds one decision from each of 263 trials, all from the same three athletes. The advantage
kept its sign across the detector's declared alternative release boundaries and both tuning
grids, but ranged from 21 to 77 mm. It came from two athletes (−116 and −118 mm); for the
third, M4 was worse than constant velocity in every configuration (+12 to +71 mm). Near
release, detailed hands improved on M3 by 16.8 mm under the pre-registered grid, but that gain
reversed for the third athlete under the wider grid.

**Conclusion.** Which forecaster is best depends on when it is evaluated. Over whole trials the
richer models did not improve on constant velocity; just before release they were markedly
better on average. The hand-specific gain holds in aggregate but not across every athlete or
tuning budget, and three athletes cannot establish how it generalises. Teams weighing
hand-level capture should judge it by phase and athlete, not whole-trial averages. These are
forecast errors against supplied motion capture, not tracking accuracy, and a live system would
have to estimate the release phase itself.

**Table 1.** Mean per-athlete endpoint error (mm), pre-registered grid.

| Decision timing | Decisions | Constant velocity | M3 | M4 |
|---|---:|---:|---:|---:|
| More than 100 ms before release | 4,382 | **66** | 79 | 83 |
| Within 100 ms before release | 263 | 197 | 141 | **124** |
| At or after release | 4,974 | **210** | 222 | 220 |

---

## Claim map (not part of the abstract)

All paths under `reports/world_model/v1_2/releasestate01_v1_2/`. Contract
`release_state_v1_2.json`, scientific digest `b0a8399d…`.

| claim in the abstract | value | source |
|---|---|---|
| 9,619 forecast decisions, three athletes | 9,619 decisions (3,095 / 3,315 / 3,209); 57,714 model x grid predictions | `experiment_report.json` `scored_examples`, `by_athlete_examples` |
| 267 ms eligibility window, 100 ms cadence and horizon | contract | `release_state_v1_2.json` `prefix`, `decision_policy`, `target_matching` |
| decisions need a fully observed 267 ms prefix and a reference sample within 8 ms of the 100 ms target, a retrospective selection | contract | `release_state_v1_2.json` `prefix.min_finite_fraction` 1.0, `target_matching.tolerance_ms` 8, `decision_policy.eligible_decision_range` ("a complete prefix AND a matchable target"): whether a decision exists depends on a later sample |
| features are final positions and final-interval velocities | code | `run_release_state_experiment.py` `features()` reads samples [-1] and [-2] only |
| whole-trial constant velocity 150.5 mm | 0.15052 m | mean of `baselines_report.json` constant-velocity per-athlete means |
| M4 8.0 mm worse whole-trial | 0.15853 − 0.15052 m | `experiment_report.json` pre-registered aggregate M4 |
| ridge forecasts stored and replayable | 57,714 M3/M3b/M4 forecasts, max 6.4e-14 m, reconciles 6/6; constant-velocity forecasts are reconstructed from source-derived features and are not stored | `forecast_replay_verification.json` |
| strata 66 / 197 / 210 mm and Table 1 | 66.3 / 197.3 / 209.7 mm | `release_stratum_report_preregistered_near100.json` |
| M4 124 mm, 73 mm better | 124.3; −73.0 mm | same |
| one decision per trial, 263 trials | 263 decisions, 263 unique trials, three athletes | same, `coverage.pre_release_near`; reduced redundancy, not independence |
| sign held; 21–77 mm range | −21.0 … −77.2 mm | the six `release_stratum_report_*_near100*.json` (1.5r / 2.0r / 3.0r × two grids) |
| two athletes −116, −118 mm | −115.7, −118.2 mm | pre-registered 2.0r, `by_athlete` |
| third athlete +12 to +71 mm | +11.7 … +71.2 mm | P0003 across the six reports |
| hand gain 16.8 mm; reverses for the third | −16.8 mm; P0003 +14.0 mm under RS-A2 | `paired_M4_minus_M3_by_stratum` in the 2.0r reports |
| label used only for evaluation | analysis design | `stratify_release_state.py` docstring; `RELEASE_STRATUM_V16_S1.md` |
| grouping specified after the whole-trial result | chronology | `RELEASE_STRATUM_V16_S1.md`, "Analysis chronology" |
| "judge it by phase and athlete, not whole-trial averages" | interpretation | follows from Table 1 and the per-athlete rows above; a recommendation about how to evaluate, not a performance claim |
| size of the retrospective selection (not stated in the abstract; supports its disclosure) | 277 of the 9,896 decisions that passed every past-only check (2.8%) were dropped only because the later reference was unusable; 1 more failed a past-only body rule | `reports/world_model/v1_2/r6l_causal_issuance/issuance_report.json` `e1_parity.causal_forecasts_in_e1_trials_not_in_e1` (E1's own per-decision reasons, mirrored from its builder and verified against `build_trial` for every trial) |
| constant-velocity numbers equal a causal forecaster's | a causal issuer requesting exactly t + 100 ms reproduces all 9,619 E1 constant-velocity forecasts to 0.0 m. The matched-timestamp extrapolation in `run_release_state_baselines.py` is latent here: every matched offset is 0 ms | same report, `e1_parity` and `reference_offset_ms_counts` |

**Format check (2026-09-25, against the official rules at
<https://www.sloansportsconference.com/research-paper-competition>).** "Fewer than 500 words, including title and
body": 468 by whitespace tokens, 487 if a counter splits hyphenated words; Table 1's block adds 43. "Up to two tables or figures combined": Table 1, plus
optionally Figure 2. Required sections: Introduction (the question and why it matters to the industry), Methods
(methods and data source), Results (actual results with statistics), Conclusion (takeaway and industry impact),
all present. "A link to the author's GitHub repository or other repository supporting the research will be
required." Deadline: "Oct. 1, 2026 11:59 p.m. EST".

The two figures in `figures/` exist if the submission uses the second figure/table slot:
`fig2_per_athlete_near_release.png` shows the third-athlete counterexample, and it is the
recommended choice because the aggregate alone would make the headline look universal.

## Deliberately left out

- **Hand/finger forecasting.** Not implemented; no hand-target error exists.
- **"Release-only forecasting."** The system forecasts at a fixed cadence across the whole
  trial; release is a retrospective evaluation grouping.
- **Any physical explanation** of why a regime favours a model, including "the ball is held"
  before release — the detector boundary does not certify it.
- **Spin, contact force, tracking accuracy or coaching benefit.**
- **"First basketball world model"** or any novelty claim without a scoped review.

## Operator gates before submission

1. **Done — independent review.** Initial review of candidate `489302f9f` APPROVE with two
   MINOR findings; focused remediation review of `61d040de3` APPROVE, both CLOSED, and its
   one new MINOR (constant-velocity wording) is fixed in the claim map above. The reviewer
   replayed all 57,714 ridge forecasts and rebuilt the six stratum reports without fitting.
   Its recorded scope excludes model refitting, the full test suite, physical release truth,
   licensing and Git authentication of the extracted candidate (`review/`, "Not checked").
   After #1805's squash merge, main is byte-identical to `61d040de3` on every reviewed path.
2. Confirm the SPL Open Data licence permits this use. The pinned `LICENSE`
   (`a3f9cffbd`) is CC BY-NC-SA 4.0 **plus** an added exclusion: anyone employed by,
   contracted to, associated with, or a significant shareholder of a professional sports
   organization or financial analysis firm may not use the data for any purpose. Settle
   that, the attribution wording and any supporting-data link.
3. Format: checked against the official rules on 2026-09-25 (above); re-check on the submission form. If the
   form's counter includes Table 1's text, submit Table 1 as a figure image (the rules allow up to two tables or
   figures combined), since title + body + table would then exceed 500.
4. Supporting repository: the rules require a link to an open-source repository supporting the research.
   `SUPPORTING_REPOSITORY_PLAN.md` lists the 16-file code closure, configs, tests and aggregate reports that would
   reproduce these numbers. It links the upstream SPL data rather than copying it, lists what must never be
   published, and gives a dry-run checklist. Its decisions depend on item 2.
5. Submission itself (official deadline Oct. 1, 2026 11:59 p.m. EST; internal target Sept. 30).
