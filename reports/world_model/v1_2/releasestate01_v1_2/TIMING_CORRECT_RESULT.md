# The timing-correct release-state result (v1_2)

**Date:** 2026-09-22 · **Contract:** `release_state_v1_2.json`, digest `b0a8399d…`
**Authorised by:** the merge of #1786, which approved the RS-A3 timing amendment.
**Evidence:** every forecast persisted and replayed (V16-E1).

Prefix history is now genuinely **267.0 ms on 100%** of examples, against a uniform
250.0 ms under v1_1. Scored examples 9,621 → **9,619**.

## Result, in metres (equal-athlete weighting throughout)

| candidate / contrast | pre-registered | RS-A2 sensitivity |
|---|---:|---:|
| constant velocity (equal-athlete) | **0.15052** | 0.15052 |
| M3 — ball + core body | 0.15986 | 0.16138 |
| M3b — M3 + coarse hand | 0.15949 | 0.16171 |
| M4 — M3 + detailed hands/fingers | **0.15853** | **0.16076** |
| **M4 − M3** | **−1.337 mm** | **−0.618 mm** |
| P0003: M4 − M3 | −0.241 mm | **+6.548 mm** |

Baselines on the same 9,619 examples, equal-athlete: held_position 0.27893,
**constant_velocity 0.15052**, quadratic_prefix 0.20893.

## What the timing correction changed

Almost nothing, and that is now **measured rather than predicted**:

| quantity | v1_1 (250 ms) | v1_2 (267 ms) | delta |
|---|---:|---:|---:|
| M3 / M3b / M4 | 0.15990 / 0.15951 / 0.15854 | 0.15986 / 0.15949 / 0.15853 | ≤ **0.04 mm** |
| M4 − M3, pre-registered | −1.354 mm | −1.337 mm | 0.017 mm |
| M4 − M3, RS-A2 | −0.623 mm | −0.618 mm | 0.005 mm |
| alpha at grid maximum | 9/9 and 0/9 | 9/9 and 0/9 | unchanged |
| constant velocity | 0.15049 | 0.15052 | +0.03 mm |

**One baseline did move.** `quadratic_prefix` went 0.20662 → **0.20893 (+2.31 mm)**, by far
the largest shift of anything here. That is the expected direction: a second-order fit over
a 6.8% longer window has more curvature leverage, so extrapolating from it is slightly
worse. It is reported because it is the one place the timing correction was not negligible.

## What the result says

**Constant-velocity extrapolation from the prefix (150.5 mm) still beats every learned
family (158.5–161.8 mm)** at the 100 ms horizon — M4 trails it by **8.01 mm** (was 8.05).

The detailed-hand benefit is **≈1.34 mm** pre-registered and **0.62 mm** under the amended
selection budget: an order of magnitude below the gap to the simple baseline, and **not
sign-consistent per athlete** (`consistent_in_every_athlete_under_both_grids: false`) —
P0003 reverses to +6.55 mm under RS-A2.

The aggregate also hides real heterogeneity, which belongs in the result: on
**P0001** M4 beats constant velocity, while **P0002** and **P0003** favour constant velocity.

## Evidence

| check | result |
|---|---:|
| forecasts persisted and replayed | **57,714** |
| max abs difference, stored vs recomputed | **6.4e-14 m** |
| refitted during verification | **false** |
| aggregates reconciled with this report | **6 / 6 exact** |
| funnel | 14,594 intended → 9,619 eligible → 57,714 emitted |

## Not claimed

Forecast-error statistics, not millimetre tracking accuracy. No physical mechanism, causal
effect, spin, contact force or coaching recommendation. Three development athletes do not
establish uncertainty over future athletes. The release **stratum** (V16-S1) is still not
defined: this remains a trial-wide fixed-cadence forecast, not a release-only one, and must
not be described as the latter. Hand-target prediction remains unimplemented.

The v1 and v1_1 configs and reports are preserved unchanged.
