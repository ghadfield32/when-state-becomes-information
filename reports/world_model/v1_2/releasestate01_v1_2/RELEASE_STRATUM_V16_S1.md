# V16-S1 — the release stratum

**Date:** 2026-09-22 · **Contract:** `release_state_v1_2.json`, digest `b0a8399d…`
**Refitted:** nothing. Every number here re-aggregates the V16-E1 stored forecasts.

## What this closes

The study issues forecasts at a **fixed cadence across the whole trial**. That is not a
release-only experiment, and until now "release-state" was a name the evaluation did not
support. This stratifies the **already-issued** forecasts by where each decision falls
relative to the source-supported release event.

The event comes from **OW-EVENT-21's reviewed detector and its frozen config**, reused
rather than reinvented: first evaluable ball–hand contact → beyond-boundary transition with
ascending vertical ball velocity. It fires on **396 / 396 trials**.

**Chronology, stated plainly:** the detector scans the whole trial, so the event is
**retrospective**. It is used only to *group* results, and it did not select which
decisions were issued.

**Corrected (audit, 2026-09-22):** an earlier version of this section said only the
pre-release strata describe a forecast a live system could issue. That was too strong. A
live system can forecast at any time, before or after release. What it cannot have in
advance is the **retrospective label** saying "this decision will fall within 100 ms of
release" — that label belongs to evaluation, never to inference-time selection or routing.

**Coverage is not timing accuracy.** The detector fires on 396/396 trials, which measures
that a qualifying transition was found — not that the instant of final fingertip contact
was located. The rule is a geometric ball–hand boundary plus upward velocity. Equally,
"more than 100 ms before" does not certify a stationary held ball, and "at or after" does
not certify uninterrupted ballistic flight; the offsets run from −2,300 ms to +3,767 ms.

**Analysis chronology.** The tuning grid was pre-registered. The near-release stratum and
the emphasis on it were **not** — they were specified after the trial-wide result existed.
Both facts belong in any write-up of this table.

## The result (pre-registered grid, equal-athlete, metres)

| stratum | n | constant velocity | M3 | M3b | M4 |
|---|---:|---:|---:|---:|---:|
| pre-release far (>100 ms before) | 4,382 | **0.06633** | 0.07911 | 0.08027 | 0.08296 |
| **pre-release near (≤100 ms before)** | 263 | 0.19726 | 0.14106 | 0.13846 | **0.12427** |
| at or after release | 4,974 | **0.20974** | 0.22221 | 0.22123 | 0.21959 |

**The trial-wide average was hiding three different regimes.**

* **More than 100 ms before release**, constant velocity is best (66 mm) and every learned
  family is worse.
* **Within 100 ms before release**, constant velocity errs by 197 mm and **M4 is 73 mm
  better** (124 mm) in the equal-athlete aggregate.
* **At or after release**, constant velocity is best again (210 mm).

*Superseded (audit, 2026-09-22):* an earlier version explained these regimes physically —
the ball "essentially held" before release and "ballistic" after it. The detector does not
certify either state, as the chronology section above says, so those explanations are
withdrawn. The strata are timing groups relative to a retrospective proxy, nothing more.

This reverses the headline. Trial-wide, constant velocity beat every learned family by
~8 mm. **In the window the paper is actually about, the explicit-state models win, and the
detailed-hand model wins by the most.**

## The hand contrast, and where it is not robust

Paired M4 − M3 within `pre_release_near`, equal-athlete:

| grid | M4 − M3 | P0001 | P0002 | P0003 | same sign in all three |
|---|---:|---:|---:|---:|:--:|
| pre-registered | **−16.79 mm** | −16.9 | −13.5 | −19.9 | **yes** |
| amended RS-A2 | −22.05 mm | −16.9 | −63.2 | **+14.0** | **no** |

**Boundary sensitivity** (pre-registered grid) — the near/far cut is a choice, so it is an
argument and its sensitivity is reported:

| near_ms | n | const-vel | M3 | M4 | M4 − M3 | all three same sign |
|---:|---:|---:|---:|---:|---:|:--:|
| 50 | 75 | 0.18000 | 0.16729 | 0.14159 | −25.70 mm | yes |
| 100 | 263 | 0.19726 | 0.14106 | 0.12427 | −16.79 mm | yes |
| 200 | 525 | 0.16731 | 0.14445 | 0.12947 | −14.98 mm | yes |
| 300 | 787 | 0.13594 | 0.14704 | 0.12486 | −22.18 mm | yes |

The four boundaries **reuse overlapping observations** — the 300 ms window contains the
100 ms window — so they are a sensitivity check, not four independent replications.

**Corrected (audit, 2026-09-22): "M4 beats constant velocity" is an equal-athlete
aggregate, and it is not true for every athlete.** An earlier version of this section
called it robust without that qualification, which repeated the aggregate-as-universal
error this study already made once.

Near release, per athlete (mm):

| athlete | n | const-vel | M3 | M4 | **M4 − const-vel** | M4 − M3 |
|---|---:|---:|---:|---:|---:|---:|
| P0001 | 84 | 185.230 | 86.433 | 69.543 | **−115.687** | −16.890 |
| P0002 | 90 | 209.961 | 105.282 | 91.746 | **−118.215** | −13.536 |
| P0003 | 89 | 196.600 | 231.462 | 211.520 | **+14.920** | −19.942 |

Under RS-A2 the same pattern holds and widens for P0003: M4 − const-vel **+24.339 mm**,
and its hand contrast reverses to **+13.987 mm**.

So the aggregate advantage rests on **two of three athletes**. For P0003 the richer model
is worse than the simple extrapolator near release under both grids. The M4-versus-M3 hand
contrast is sign-consistent across athletes at every boundary under the pre-registered
grid, and reverses for P0003 under the amended budget — the same instability the
trial-wide result showed, larger in magnitude rather than resolved.

## Release-proxy sensitivity (audit, 2026-09-22)

The boundary sweep above varies the **width of the window**. This varies the **release
proxy itself**, which is a different question: how much of the result depends on where the
detector places the event?

Only the boundaries the detector's own reviewed config declares are used — its primary
**2.0r** and its `sensitivity_boundary_radii` **1.5r and 3.0r**, whose declared role is to
be "reported descriptively … they never choose the event". Any other value is **refused**,
so the proxy can be stressed but never tuned toward a favourable result. The detector was
not altered.

Near release, mm:

| grid | proxy | n | const-vel | M4 | **M4 − const-vel** | M4 − M3 | P0003 M4 − const-vel |
|---|---:|---:|---:|---:|---:|---:|---:|
| pre-registered | 1.5r | 259 | 201.0 | 123.9 | **−77.2** | −13.4 | +11.7 |
| pre-registered | 2.0r | 263 | 197.3 | 124.3 | **−73.0** | −16.8 | +14.9 |
| pre-registered | 3.0r | 268 | 176.6 | 134.8 | **−41.8** | −25.5 | +44.7 |
| RS-A2 | 1.5r | 259 | 201.0 | 127.8 | **−73.3** | −16.1 | +18.9 |
| RS-A2 | 2.0r | 263 | 197.3 | 133.4 | **−63.9** | −22.0 | +24.3 |
| RS-A2 | 3.0r | 268 | 176.6 | 155.5 | **−21.0** | −32.4 | +71.2 |

**What survives:** the aggregate M4 advantage over constant velocity holds **in sign** at
every declared proxy under both grids.

**What does not:** its **magnitude**. The "73 mm" headline is specific to the primary proxy
and grid; across the declared proxies and both grids it ranges from **21 to 77 mm**, and it
shrinks as the contact boundary widens. Any single number reported without that range would
overstate its precision.

**P0003 never benefits.** M4 is worse than constant velocity for P0003 at all six
configurations (+11.7 to +71.2 mm), and the deficit grows with the boundary.

The hand contrast (M4 − M3) is sign-consistent across athletes at every proxy under the
pre-registered grid. Under RS-A2, P0003 is positive at 1.5r and 2.0r (+14.4, +14.0 mm) and
≈0 at 3.0r (−0.1 mm).

## Figures

`figures/fig1_error_by_stratum.png` — equal-athlete error by stratum, every candidate, both
grids. `figures/fig2_per_athlete_near_release.png` — per-athlete near-release contrasts
under both grids and every declared proxy; P0003 sits above zero on M4 − constant velocity
in all six. The plotting script reads the stratum reports and computes nothing new, and it
refuses reports that span more than one contract, so a figure cannot disagree with the
report it came from.

## What may and may not be claimed

**Supported:** near release, explicit state beats prefix constant-velocity extrapolation
**in the equal-athlete aggregate**, in sign at every declared release proxy and under both
grids, by **21–77 mm** depending on proxy and grid (73 mm at the primary proxy); and richer
hand input is the best of the explicit families under the pre-registered budget.

**Not supported:** that every athlete benefits — **P0003 does not**, under either grid.
That the hand benefit is stable — it is not, under a different and equally defensible
selection budget. Nor is any mechanism: this is an association within this corpus. Nor does
the original trial-wide result become invalid: trial-wide performance and performance
conditional on a later release label answer **different questions**, and both are kept.

**Sample size, corrected (audit, 2026-09-22).** `pre_release_near` holds **263 decisions**
(84 / 90 / 89 per athlete) against 4,382 and 4,974 — but row counts are not comparable
here, because windows within a trial overlap:

| stratum | decisions | unique trials | decisions per trial |
|---|---:|---:|---:|
| pre-release near | 263 | **263** | **1.0** |
| pre-release far | 4,382 | 262 | 16.7 |
| post-release | 4,974 | 271 | 18.4 |

The near-release stratum takes **exactly one decision from each trial**, so it carries far
less within-trial redundancy than the large strata, which hold ~17–18 heavily overlapping
windows per trial. That is **reduced redundancy, not independence**: the 263 trials still
share three athletes, their sessions and acquisition conditions, and possibly correlated
measurement error. The appropriate independent unit depends on the claim — for anything
about future athletes it is the athlete, and there are three.

*Superseded (audit, 2026-09-22):* an earlier version called these observations "close to
independent". That overstated it.

What does remain a hard limit: **three development athletes**, which cannot establish
uncertainty over future athletes, and a per-athlete split where one of the three contradicts
the aggregate.

## Two defects found and fixed while doing this

1. **The example identity was ambiguous.** It was `<trial>#<decision>`, and **88 of the 396
   trial filenames occur in both sessions**. The scored population is single-session, so the
   collision was latent rather than active — but it is the false-merge hazard, so the
   identity is now `<session>/<trial>#<decision>`. Every v1_2 aggregate is unchanged
   (M3 0.15986 / M3b 0.15949 / M4 0.15853), which confirms it was latent.
2. **My first stratification join used that ambiguous key**, and reported 308 trials with a
   release event against 396 detections — one session's event held under the other's name.
   Keyed by `(session, trial)` it now reports 396 / 396.

## Evidence

| check | result |
|---|---|
| release detection | **396 / 396 trials**, reason `event` |
| forecasts stratified | 28,857 per grid, **0 unlabelled** |
| refitted | **false** |
| replay after the identity fix | 57,714 forecasts, 6.4e-14 m, reconciles 6/6 |
| stratum tests | 12 + 8 end-to-end = **20 passed** |
| join enforcement | 4 families cover identical examples in all 3 strata; 0 duplicates, 0 orphans |
| analysis identity | config, detector config, detector code, stratifier code, store forecasts + manifest digests, `near_ms`, grid |
| overwrite guard | a second run at the same grid/boundary is **REFUSED** |

## Audit safeguards added (2026-09-22)

* **Analysis identity is bound by digest**, not by filename: the detector's config *and
  code*, this script, and the store's own forecast/manifest digests are recorded. A changed
  rule cannot masquerade as the same analysis.
* **The join is enforced, not intersected.** Families must cover identical examples in a
  stratum; duplicates, orphans and unequal family sets raise. Silently intersecting them
  would compare families on different rows and call the difference an effect.
* **Reports are per grid and per boundary** and refuse an occupied destination. Previously
  a second grid overwrote the first under one filename.
* **Assurance is behavioural.** The earlier tests asserted that the word "prediction" does
  not appear inside `stratum_for` — which would pass on a stratifier that leaked through a
  helper. The new fixture exercises a real stored run, relabels it, and asserts the
  predictions are unchanged; and that removing a reference reduces scoreability without
  erasing an issued forecast.

## Still open

Hand/finger **targets** remain unimplemented: no model here predicts a hand position, so
there is no hand-target error to report. Additional horizons likewise have no completed
prediction or coverage evidence. Neither should appear in the paper as a result.
