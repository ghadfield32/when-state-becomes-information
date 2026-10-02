"""R6-L: state estimators that read ONLY a view of the samples available by the cutoff.

causal_velocity_v1      secant over the two most recent available ball samples, m/ms. Minimum history: the most
                        recent sample at or before (cutoff - window_ms) must exist, and every ball sample from it
                        through the latest one must be finite. This is E1's complete-prefix rule, applied at the
                        cutoff instead of at a decision sample chosen with knowledge of the whole trial.
causal_acceleration_v1  second divided difference over the three most recent available ball samples, m/ms^2.
prefix_phase_v1         DECLARED, NOT IMPLEMENTED: it needs a causal phase model (R6-M M6). It is never replaced by
                        the retrospective release proxy.

Each estimator returns (state, None) or (None, reason). An abstention is a named outcome, never a default value.
"""
from __future__ import annotations

import numpy as np

PREFIX_PHASE_V1_STATUS = "MISSING: requires a causal phase model (R6-M M6); not implemented and not faked"


def causal_velocity_v1(view, cutoff_ms: float, window_ms: float):
    if not view:
        return None, "no_sample_at_or_before_cutoff"
    start = cutoff_ms - window_ms
    lo = None
    for i in range(len(view) - 1, -1, -1):
        if view[i].time_ms <= start:
            lo = i
            break
    if lo is None:
        return None, "prefix_before_stream_start"
    if any(view[i].ball_m is None for i in range(lo, len(view))):
        return None, "prefix_ball_incomplete"
    if len(view) - lo < 2:
        # the latest available sample is itself older than the window start: a stream gap, not a velocity
        return None, "prefix_too_few_samples"
    last, prev = view[-1], view[-2]
    dt = last.time_ms - prev.time_ms
    origin = np.asarray(last.ball_m, dtype=float)
    velocity = (origin - np.asarray(prev.ball_m, dtype=float)) / dt
    return {"estimator": "causal_velocity_v1",
            "state_time_ms": last.time_ms,
            "ball_m": [float(c) for c in origin],
            "velocity_m_per_ms": [float(c) for c in velocity],
            "window_first_sample_ms": view[lo].time_ms,
            "window_samples": len(view) - lo}, None


def causal_acceleration_v1(view):
    if len(view) < 3:
        return None, "acceleration_too_few_samples"
    s1, s2, s3 = view[-3], view[-2], view[-1]
    if s1.ball_m is None or s2.ball_m is None or s3.ball_m is None:
        return None, "acceleration_ball_incomplete"
    p1, p2, p3 = (np.asarray(s.ball_m, dtype=float) for s in (s1, s2, s3))
    v12 = (p2 - p1) / (s2.time_ms - s1.time_ms)
    v23 = (p3 - p2) / (s3.time_ms - s2.time_ms)
    accel = 2.0 * (v23 - v12) / (s3.time_ms - s1.time_ms)
    return {"estimator": "causal_acceleration_v1", "state_time_ms": s3.time_ms,
            "acceleration_m_per_ms2": [float(c) for c in accel]}, None
