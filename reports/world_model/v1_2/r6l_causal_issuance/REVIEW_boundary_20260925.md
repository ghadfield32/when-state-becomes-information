# OW-R6L-CAUSAL-ISSUANCE-01: boundary review and remediation (2026-09-25/26)

## Review

- Reviewed #1879 at head `b043a6e809a5` (merged as `e1d1c1d31`).
- Reviewer: a fresh read-only session. It is the same model family as
  the author, so independence is reduced; this is disclosed.
- Recorded as a `cc-review-record` on #1879.
- Mode: initial review at the milestone boundary, against the contract frozen in the RUNDOC (#1873).

**Decision: APPROVE.** No BLOCKER or MAJOR findings; 5 MINOR and 4 NIT.

The reviewer confirmed:

- **Causality by construction.** The issuer reads only `available_at(t)`. The clock is anchored on the first sample.
  `close_ms` only bounds the loop. The target is exactly cutoff + horizon. The window is anchored on the cutoff.
  The view is latency-correct.
- **Journal integrity.** All tamper classes are refused.
- **E1-consistent matching.** Nearest reference within ±8 ms, ties to the earlier sample, strictly after the issue,
  and no fallback when the reference ball is missing.
- **Counts reconcile**, overall and for E1's session.
- **Parity.** The join key and the constant-velocity rebuild are identical to `stratify_release_state.py:243-246`.
- **Refusals and contract honesty.** Refusals behave as specified, and the contract is honestly covered.

## Findings and disposition (fixed in the follow-up PR, packet `OW-R6L-CAUSAL-ISSUANCE-01-R1`)

| ID | Severity | Finding | Disposition |
|---|---|---|---|
| D1 | MINOR | "None were excluded by a past-only rule" was inferred from later outcomes, not measured from E1's own refusal reasons | **Measured.** `e1_decision_reasons` mirrors the builder's per-decision checks and refuses unless it equals `build_trial` on every trial. Result: 277 future-dependent (245 no target, 32 target ball missing), plus **1 past-only** (body incomplete). The README is corrected; a test proves the mirror refuses on disagreement |
| D2 | MINOR | The invariance cut sat 17–33 ms after the last opportunity, so a short look-ahead could pass; no mutant targeted `available_at` or the window anchor | The cut now sits exactly on an opportunity, and the rewritten future starts 1 ms later. A new test pins the window to the cutoff. Look-ahead mutants of 1 ms and 17 ms and a latest-sample-anchor mutant are all killed |
| D3 | MINOR | `pending` ignored the declared latency | Pending now lasts until target + tolerance + latency. Test: a reference still in transit is pending, not unscoreable |
| D4 | MINOR | `max(0.0, nan)` would print as exact parity; 0.0 read as parity when nothing was joined | `max_abs_difference` refuses non-finite values and returns None when nothing was compared. Tested |
| D5 | MINOR | The manifest beside the journal is unauthenticated; per-trial counts were unchecked | `--expect-journal-sha256` pins a digest from outside the run directory, and per-trial record counts are checked. Test: a consistent rewrite of journal plus manifest is refused |
| D6 | NIT | Whole-stream clock validation reads the future (it fails closed) | Declared in `stream.py` and in the README |
| D7 | NIT | The config's abstention list omitted two reasons | Completed. `run_02` was re-issued under the new config and is byte-identical to `run_01` (`afa6a1d2…`) |
| D8 | NIT | A non-object line, or a record without a payload, raised a bare AttributeError or KeyError | Now named `JournalError`s (`journal_line_not_an_object`, `journal_record_missing_payload`). Tested |
| D9 | NIT | The docstring said the protected directory was "never listed" | It now says the directory is enumerated but its files are never opened |

The remediation's mutation set has 14 mutants: the original six plus D2's three and five guard removals (NaN
masking, the pinned digest, per-trial counts, the mirror self-check, and latency). Every one is killed, and the
suite passes (38) before and after.

## Focused remediation review (#1880 at `87aff904a`)

A fresh read-only session (same family, reduced independence disclosed) returned **APPROVE**.
D1–D9 are all CLOSED in code. It confirmed that `issuer.py` and `causal_state.py` are untouched, that their digests
in the report are unchanged, and that the journal is unchanged (`afa6a1d2…`). It found two new items:

| ID | Severity | Finding | Disposition |
|---|---|---|---|
| NEW-1 | MINOR | "277 passed every past-only check" was not measured. The mirror recorded only the builder's FIRST failing check, and E1's finger-population rule comes after the target check | **Measured.** The mirror now records `m4_complete` for every decision that reached the target checks. All 277 had complete fingers, so the report splits them as `future_dependent_only` 277, `future_dependent_and_m4_unavailable` 0, `past_only` 1 and `other` 0 |
| NEW-2 | NIT | The README still cited `run_01`'s config digest and commands | The README cites config `65e4d8ad…`, `run_02`, `run_02_eval_r2` and the pinned `--expect-journal-sha256` |
| D2 NIT | NIT | Nothing asserted that the record at the cut is issued | Asserted in the invariance test |

After these changes the 14 mutants are all killed again, and 38 tests pass. Because they are MINOR/NIT
corrections, a further review round is not required.
