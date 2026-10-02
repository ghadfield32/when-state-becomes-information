# OW-R6L-CAUSAL-ISSUANCE-01 — causal constant-velocity issuance, evaluated later

`issuance_report.json` is the coordinate-free aggregate of one issue run and its delayed evaluation. The journal
and the per-record evaluation hold MLSE-derived coordinates, so they are never committed to this repository — they
are written to a local, gitignored data root outside the checkout:

- `<DATA_ROOT>/r6l_issuance/run_02/` holds `journal.jsonl` and `manifest.json`.
  It is byte-identical to `run_01` (journal `afa6a1d2…`).
- `run_02_eval_r2/` holds `evaluation.jsonl` and `manifest.json`: this report's evaluation.

## Identity

| | |
|---|---|
| config | `configs/experiments/causal_issuance_v1.json`, sha256 `65e4d8ad0188ffaee30c8027dc744dc1b12782a937e825f7bfab8c8bd2069c1c` (the abstention list was completed after `run_01`'s `757d95ad…`; no issued value depends on that list) |
| data | SPL Open Data `a3f9cffbde917b1e1747cedd6ec25dfab18c6051`, clean; P0001–P0003, both sessions, 396 trials; P0004/P0005 never opened |
| journal | `wms.issue_journal.v1`, 20,840 records + seal, sha256 `afa6a1d2394bc6e04b2e192fec30419f5012711b54bf9b4a0b37a5203931ef27`. It was re-issued byte-identically as `run_02` after the config's abstention list was completed (review D7); this report evaluates `run_02` with that digest pinned (`--expect-journal-sha256`) |
| evaluation | sha256 in the report's `identity`; the per-record outcomes are unchanged from `run_01`'s evaluation |
| code | sha256 of each issuance module, recorded in the report's `identity` |

## Commands

```
PYTHONPATH=src python scripts/issue_causal_forecasts.py --config configs/experiments/causal_issuance_v1.json \
    --data-root <SPL-Open-Data> --out <DATA_ROOT>/r6l_issuance/run_02
PYTHONPATH=src python scripts/evaluate_issue_journal.py --config configs/experiments/causal_issuance_v1.json \
    --journal-dir <DATA_ROOT>/r6l_issuance/run_02 --data-root <SPL-Open-Data> \
    --out <DATA_ROOT>/r6l_issuance/run_02_eval_r2 \
    --report reports/world_model/v1_2/r6l_causal_issuance/issuance_report.json \
    --expect-journal-sha256 afa6a1d2394bc6e04b2e192fec30419f5012711b54bf9b4a0b37a5203931ef27 \
    --e1-config configs/experiments/release_state_v1_2.json
```

Both commands exited 0.

## Result

| | all trials | 2025-12-18 (E1's session) | 2024-08-28 |
|---|---:|---:|---:|
| opportunities (clock, every 100 ms) | 20,840 | 10,840 | 10,000 |
| issued | 14,998 | 9,897 | 5,101 |
| abstained (named: incomplete 267 ms prefix, or too early in the stream) | 5,842 | 943 | 4,899 |
| scored | 14,594 | 9,619 | 4,975 |
| pending at stream close (reference never arrived) | 246 | 246 | 0 |
| unscoreable (reference ball missing) | 158 | 32 | 126 |

Every scored reference lay exactly at the requested time (offset 0 ms, 14,594 of 14,594).

**E1 parity.** All 9,619 E1 rows join a causal opportunity at the same time (0 are off the clock). The causal
forecast equals E1's constant velocity to **0.0 m**, and so does its error. E1's per-athlete means are reproduced
exactly from the journal (239.90 / 109.12 / 102.53 mm, equal-athlete 150.52 mm).

**What E1's retrospective selection removed.** In E1's 271 trials, a causal system issues 278 forecasts that E1 does
not hold. Each one is listed under E1's own refusal reason for that decision. The reasons come from a mirror of the
builder's per-decision checks, verified against `build_trial` for every trial (it refuses on any disagreement):

| E1's first refusal | reads | finger markers in the prefix | forecasts | later causal outcome |
|---|---|---|---:|---|
| `no_target_within_tolerance` | a later sample | complete | 245 | pending: the reference never arrived |
| `target_ball_missing` | a later sample | complete | 32 | unscoreable: reference ball missing |
| `prefix_body_incomplete` | the past only | not evaluated | 1 | pending |

- The builder stops at its first failing check. So for each target-refused decision, the mirror also records
  whether E1's later, past-only finger-population rule would have kept it. All 277 had complete finger markers.
- So **277** decisions passed every past-only check E1 applies (prefix, body and fingers) and were dropped only
  because their reference was unusable. That is 2.8% of the 9,896 that passed those checks.
- One more decision was excluded by E1's past-only body rule.
- These numbers were corrected twice. A first reading of the outcomes alone said "all 278 future-dependent". The
  boundary review's D1 asked for E1's own reasons, which gave 277 + 1. The focused review's NEW-1 asked for the
  finger status of the 277, which confirmed it.

## Reading

- The constant-velocity numbers in the release-state paper are what a causal issuer produces on the same decisions.
  The matched-timestamp extrapolation found in the leakage audit is latent: every offset is 0 ms.
- The paper's retrospective selection is now counted: 277 decisions (2.8% of those passing every past-only check)
  were kept out of E1 only because a later reference was unusable.
- One refusal reads the whole stream, and it fails closed: a malformed later timestamp refuses the whole trial at load
  (`stream.py`). It never changes an issued record.
- This is the same forecaster, issued causally. It does not claim live latency; availability is declared at zero
  latency, not measured. It makes no accuracy claim and involves no phase model: `prefix_phase_v1` is declared but
  missing.
