"""R6-L: delayed evaluation of issued records against references matched by a declared policy.

Policy (causal_issuance_v1): the reference for a forecast is the native sample nearest to its REQUESTED target
within ±tolerance_ms, ties to the earlier sample, strictly after the issue time, with a finite ball — the same
matching rule as E1's builder. Matching belongs here, after issuance: a reference that lands at t+99 or t+102 ms
changes the score, never what was requested.

Outcomes: `scored`; `pending` (the evaluation clock has not passed target + tolerance + the declared latency, so a
reference could still arrive or still be in transit); `unscoreable` with a reason (the window has closed without a
usable reference); `abstained` (nothing was issued). Evaluation only reads samples available by its own clock and
never modifies the journal.
"""
from __future__ import annotations

import numpy as np


def evaluate_record(record: dict, log, tolerance_ms: float, evaluated_at_ms: float, latency_ms: float) -> dict:
    out = {"issue_id": record["issue_id"], "trial": record["trial"],
           "opportunity_time_ms": record["opportunity"]["time_ms"]}
    if record["forecast"] is None:
        return {**out, "outcome": "abstained", "reason": record["abstention"]["reason"]}
    target = record["target_requested_ms"]
    # the window closes when every sample timed within tolerance of the target has had time to become available
    if evaluated_at_ms < target + tolerance_ms + latency_ms:
        return {**out, "outcome": "pending", "reason": "reference_window_not_elapsed"}
    view = log.available_at(evaluated_at_ms)
    cutoff = record["information_cutoff_ms"]
    candidates = [(abs(s.time_ms - target), i) for i, s in enumerate(view)
                  if abs(s.time_ms - target) <= tolerance_ms and s.time_ms > cutoff]
    if not candidates:
        return {**out, "outcome": "unscoreable", "reason": "no_reference_within_tolerance"}
    ref = view[min(candidates)[1]]
    if ref.ball_m is None:
        return {**out, "outcome": "unscoreable", "reason": "reference_ball_missing"}
    error = np.asarray(record["forecast"]["ball_m"], dtype=float) - np.asarray(ref.ball_m, dtype=float)
    return {**out, "outcome": "scored", "reference_time_ms": ref.time_ms,
            "reference_offset_ms": ref.time_ms - target,
            "error_m": [float(c) for c in error], "error_norm_m": float(np.linalg.norm(error))}


def evaluate(records: list[dict], log, tolerance_ms: float, evaluated_at_ms: float,
             latency_ms: float) -> tuple[list[dict], dict]:
    """(one outcome per record, reconciled counts). Refuses if the counts do not reconcile."""
    outcomes = [evaluate_record(r, log, tolerance_ms, evaluated_at_ms, latency_ms) for r in records]
    counts = {k: sum(1 for o in outcomes if o["outcome"] == k)
              for k in ("scored", "pending", "unscoreable", "abstained")}
    issued = sum(1 for r in records if r["forecast"] is not None)
    if counts["scored"] + counts["pending"] + counts["unscoreable"] != issued \
            or issued + counts["abstained"] != len(records):
        raise ValueError(f"evaluation_counts_do_not_reconcile: {counts}, issued={issued}, opportunities={len(records)}")
    return outcomes, {"opportunities": len(records), "issued": issued, **counts}
