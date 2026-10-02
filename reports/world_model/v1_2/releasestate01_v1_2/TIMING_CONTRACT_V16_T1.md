# V16-T1 — the declared 267 ms history was always 250 ms

**Date:** 2026-09-21 · **Packet:** `OW-RELEASE-STATE-01-v1_2` · **Mode:** focused remediation
**Status:** **AWAITING OPERATOR APPROVAL — nothing has been refitted under this contract.**

## The defect

`prefix.length_ms = 267` was converted to a sample count with the trial's median interval,
and the window took that many inclusive observations.

**A STRIDE of n samples crosses n intervals; a WINDOW of n samples crosses n−1.** The
cadence is a stride, so it was correct. The prefix is a window, so it was short by exactly
one interval.

Measured on the pinned corpus, over all 9,621 scored examples:

| | value |
|---|---:|
| declared prefix length | 267 ms |
| achieved span — min / p50 / max | **250.0 / 250.0 / 250.0 ms** |
| examples reaching ≥ 267 ms | **0 (0.00%)** |
| uniform shortfall | **17.0 ms (6.4%)** |
| prefixes containing a gap > 1.6× median interval | 0 |

The cadence was verified in the same pass and is correct: a stride of 6 samples achieves
**100.0 ms** against a declared 100 ms. It is deliberately unchanged.

## Why adding a sample is not the fix

The 60 Hz timestamps are integer-rounded, so intervals alternate 16 and 17 ms
(`{17: 159, 16: 80}` in a representative trial; median 17, mean 16.665). 16 samples span
250.0 ms and **17 span 266.0 ms — still not 267.** No sample count enforces a duration on
irregular timestamps.

## The contract

Select the **most recent observation at or before `decision_time − length_ms`**, and keep
every observation through the decision sample. The achieved span is then always ≥ the
declared length, and the overshoot is recorded per example. A trial that cannot reach back
the full length is **refused**, never silently shortened.

The rule is named in the config (`prefix.selection`). A config with no `selection` key keeps
the legacy sample-count rule, so **v1 and v1_1 stay reproducible** — verified: the v1_1
baselines report regenerates byte-identically after this change.

## What the amendment would change

Measured before any refit, v1_1 (sample count) vs v1_2 (timestamp bound):

| | v1_1 | v1_2 |
|---|---:|---:|
| scored examples | 9,621 | **9,619** |
| retained | — | 9,619 |
| removed / added | — | **2 / 0** |
| retained with an unchanged target index | — | **9,619 / 9,619** |
| achieved span min / p50 / max | 250.0 / 250.0 / 250.0 | **267.0 / 267.0 / 267.0** |
| reaching ≥ 267 ms | 0 | **9,619 (100%)** |
| per athlete | 3097 / 3315 / 3209 | **3095 / 3315 / 3209** |

**The two lost examples are not a reach-back failure.** `prefix_before_trial_start` is
unchanged at 1,188. The driver is the complete-case rule over a genuinely longer window:
`prefix_ball_incomplete` rises 4,613 → 4,654 (+41 across all decisions). Both lost scored
examples are P0001 at decision index 186 (t = 3100 ms, late-trial where tracking thins):
`T0009` is refused for an incomplete ball, and `T0032` loses `m4_available` to a missing
finger marker. Missing stays missing.

## What this does NOT establish

The population changes by 2 examples (0.021%), so the refitted numbers are very likely to
track the v1_1 result closely — but **that is a prediction, not a measurement.** No model
has been refitted under this contract. Unlike the V16-U1 unit correction, this is a
population change and **must not be described as a rescaling**.

RS-A3 is a **post-fit corrective** amendment: it was raised after the v1_1 result existed
and is reported as such, never as pre-registered.

## Also in T1 scope: the frozen feature schema

The M3 list was **intersected with the first frame's keys**, so a declared joint missing
from frame 0 would silently shrink M3 — a smaller model reported under the same family
name. `marker_sets` now refuses instead.

**Measured across all 396 trials, this has never fired:** there is exactly one schema —
M3 is always the full 12 declared joints and M4 always adds 44 markers. So the guard
changes no existing result, and the v1_1 baselines report still regenerates
byte-identically. It exists so a future source change cannot pass unnoticed. The
measurement itself is asserted in the suite rather than remembered.

## Still open

`V16-E1` (persist individual forecasts and fitted artifacts) and `V16-S1` (release-specific
stratum and hand-target outputs) are untouched by this unit.
