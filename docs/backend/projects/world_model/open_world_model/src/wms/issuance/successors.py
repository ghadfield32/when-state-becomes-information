"""R6-M: causal successor forecasters (M1 least-squares/Theil-Sen velocity, M2 gravity-aware) that share M0's
issuance path, journal shape and eligibility gate (OW-R6M-M1M2-01).

What this is: three families of `wms.issuance.issuer.Forecaster`, each built on the SAME view every opportunity
already receives (`log.available_at(cutoff_ms)`) and gated by M0's own minimum-history rule
(`wms.issuance.causal_state.causal_velocity_v1`'s complete-prefix check, called with the SAME window_ms the caller
passes for M0). Because every candidate shares that one gate and nothing else decides whether to abstain, all of
them issue on EXACTLY the same opportunities with the same abstention reasons; only what happens AFTER the gate
passes differs between candidates.

- M1 least-squares (`causal_ls.v1:w<ms>`): per-axis ordinary least-squares slope of ball position against native
  time, fit over the window from the most recent sample at or before (cutoff - w) through the latest sample at or
  before the cutoff -- the SAME timestamp-bound search the prefix rule uses, re-applied with the candidate's own w
  instead of the shared gate's window. The forecast anchors at the true last observed position, never the fit's own
  intercept: p_last + slope * (target_requested - t_last).
- M1 Theil-Sen (`causal_ts.v1:w<ms>`): the median of every pairwise per-axis slope over the same window, anchored
  the same way. Robust to a single gross outlier inside the window; least-squares is not.
- M2 gravity (`causal_grav.v1`): M0's own final-interval secant (v_sec, p_last, taken verbatim from the shared
  gate's state) plus a constant-acceleration correction: p_last + v_sec*h + 1/2*a*h*(h + delta), h = target_requested
  - t_last, delta = t_last - t_prev, and a is a 3-vector in m/ms^2 declared by the CALLER (the experiment config),
  never hardcoded here. Applied at every issued opportunity -- there is no phase gate and no release proxy as an
  input, so this also applies while the ball is still held. It needs nothing beyond what the shared gate already
  verified finite, so it has no window of its own.

What this is NOT: a replacement for M0, a phase-aware estimator (that is R6-M M6, declared but not implemented
anywhere in this packet), or a source of NEW abstention reasons -- a candidate here either reproduces the shared
gate's outcome or raises loudly, it never invents a private refusal that would break the "same opportunities, same
abstentions" contract every candidate is built to satisfy.
"""
from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from wms.issuance.causal_state import causal_velocity_v1
from wms.issuance.issuer import Forecaster

LS_ESTIMATOR_ID = "causal_ls.v1"
TS_ESTIMATOR_ID = "causal_ts.v1"
GRAV_ESTIMATOR_ID = "causal_grav.v1"


def _forecaster_id(base: str, window_ms: float) -> str:
    return f"{base}:w{int(window_ms)}"


def _window_lo(view, cutoff_ms: float, window_ms: float) -> int:
    """The prefix rule's own backward search for 'the most recent sample at or before (cutoff - window_ms)',
    re-applied at a candidate's own window_ms. Callers reach this only after the shared gate (`causal_velocity_v1`,
    called with a window at least as large as this one) has already passed, so a sample satisfying `time_ms <=
    cutoff_ms - window_ms` is guaranteed to exist: the gate's own qualifying sample already satisfies the weaker
    (larger) threshold this search uses whenever window_ms is no larger than the gate's window."""
    start = cutoff_ms - window_ms
    for i in range(len(view) - 1, -1, -1):
        if view[i].time_ms <= start:
            return i
    raise AssertionError(f"successor_window_before_stream_start_after_gate_passed: window_ms={window_ms}, "
                         f"cutoff_ms={cutoff_ms}")


def _slope_predict(state: dict, target_ms: float) -> np.ndarray:
    """Shared by every velocity-only successor (LS and TS alike): anchor at the true last observed position, never
    at the fit's own intercept."""
    origin = np.asarray(state["ball_m"], dtype=float)
    velocity = np.asarray(state["velocity_m_per_ms"], dtype=float)
    return origin + velocity * (target_ms - state["state_time_ms"])


def _least_squares_slope(t: np.ndarray, p: np.ndarray) -> np.ndarray:
    """Per-axis ordinary least-squares slope of `p` (>=2 rows) against `t`. Mean-centring only changes
    floating-point conditioning, never the slope itself; the caller supplies samples with strictly increasing,
    distinct native times, so the denominator is always > 0."""
    dt = t - t.mean()
    denom = float(np.dot(dt, dt))
    dp = p - p.mean(axis=0)
    return (dt @ dp) / denom


def _theil_sen_slope(t: np.ndarray, p: np.ndarray) -> np.ndarray:
    """Per-axis Theil-Sen slope: the median of every pairwise slope i<j. `t` is strictly increasing, so every pair
    spans a nonzero interval."""
    n = len(t)
    out = np.empty(p.shape[1], dtype=float)
    for axis in range(p.shape[1]):
        pairwise = [(p[j, axis] - p[i, axis]) / (t[j] - t[i]) for i in range(n) for j in range(i + 1, n)]
        out[axis] = float(np.median(pairwise))
    return out


def _velocity_estimate(estimator_id: str, window_ms: float, slope_fn):
    """Build a `Forecaster.estimate` closure: share M0's gate for the abstention decision, then re-window to
    `window_ms` and fit `slope_fn` over exactly that window."""

    def estimate(view, cutoff_ms, gate_window_ms):
        _gate_state, reason = causal_velocity_v1(view, cutoff_ms, gate_window_ms)
        if reason is not None:
            return None, reason
        lo = _window_lo(view, cutoff_ms, window_ms)
        samples = view[lo:]
        if len(samples) < 2:
            # Reachable: the shared gate only requires 2 samples spanning gate_window_ms; it does not require the
            # LATEST sample to be close to the cutoff. If a native time gap wider than this candidate's own
            # window_ms sits just before the cutoff while the gate still passes (using older, more widely spaced
            # samples), the latest available sample can itself already be stale by more than window_ms, leaving
            # this candidate's own re-window with only that one sample. When that happens the run aborts loudly by
            # design, rather than inventing a private abstention reason or silently degrading the forecast -- see
            # tests/test_r6m_successors.py::test_a_stream_gap_that_would_desync_a_smaller_window_from_the_shared_gate
            # _raises_loudly_never_silently, which constructs exactly this case. On the 396-trial P0001-P0003
            # dataset this has been checked and never occurs: 0 of 20,840 opportunities, across all four window
            # sizes, ever reach this branch.
            raise AssertionError(f"successor_window_too_few_samples_after_gate_passed: estimator={estimator_id}, "
                                 f"window_ms={window_ms}, cutoff_ms={cutoff_ms}, samples_in_window={len(samples)}")
        t = np.asarray([s.time_ms for s in samples], dtype=float)
        p = np.asarray([s.ball_m for s in samples], dtype=float)
        slope = slope_fn(t, p)
        last = samples[-1]
        return {"estimator": estimator_id, "window_ms": window_ms, "state_time_ms": last.time_ms,
                "ball_m": [float(c) for c in last.ball_m], "velocity_m_per_ms": [float(c) for c in slope],
                "window_first_sample_ms": samples[0].time_ms, "window_samples": len(samples)}, None

    return estimate


def make_least_squares_forecaster(window_ms: float) -> Forecaster:
    """M1-LS-w: per-axis OLS slope over the most recent window_ms of the shared, gate-passed view."""
    return Forecaster(_forecaster_id(LS_ESTIMATOR_ID, window_ms),
                      _velocity_estimate(LS_ESTIMATOR_ID, window_ms, _least_squares_slope), _slope_predict)


def make_theil_sen_forecaster(window_ms: float) -> Forecaster:
    """M1-TS-w: per-axis Theil-Sen slope over the most recent window_ms of the shared, gate-passed view."""
    return Forecaster(_forecaster_id(TS_ESTIMATOR_ID, window_ms),
                      _velocity_estimate(TS_ESTIMATOR_ID, window_ms, _theil_sen_slope), _slope_predict)


def _grav_estimate(gravity_m_per_ms2: tuple[float, float, float]):
    def estimate(view, cutoff_ms, gate_window_ms):
        gate_state, reason = causal_velocity_v1(view, cutoff_ms, gate_window_ms)
        if reason is not None:
            return None, reason
        last, prev = view[-1], view[-2]
        return {"estimator": GRAV_ESTIMATOR_ID, "state_time_ms": last.time_ms,
                "ball_m": list(gate_state["ball_m"]), "velocity_m_per_ms": list(gate_state["velocity_m_per_ms"]),
                "delta_ms": last.time_ms - prev.time_ms, "gravity_m_per_ms2": list(gravity_m_per_ms2)}, None

    return estimate


def _grav_predict(state: dict, target_ms: float) -> np.ndarray:
    origin = np.asarray(state["ball_m"], dtype=float)
    velocity = np.asarray(state["velocity_m_per_ms"], dtype=float)
    a = np.asarray(state["gravity_m_per_ms2"], dtype=float)
    h = target_ms - state["state_time_ms"]
    delta = state["delta_ms"]
    return origin + velocity * h + 0.5 * a * h * (h + delta)


def make_gravity_forecaster(gravity_m_per_ms2: Sequence[float]) -> Forecaster:
    """M2: gravity_m_per_ms2 is a 3-vector in m/ms^2 (e.g. (0.0, 0.0, -9.81e-6) in a frame whose z axis is up),
    declared by the caller (the experiment config) and never hardcoded here. v_sec and p_last are M0's own gate
    state, reused verbatim; the only new input is delta_ms = t_last - t_prev, read from the same two samples the
    gate already verified finite."""
    return Forecaster(GRAV_ESTIMATOR_ID, _grav_estimate(tuple(float(c) for c in gravity_m_per_ms2)), _grav_predict)
