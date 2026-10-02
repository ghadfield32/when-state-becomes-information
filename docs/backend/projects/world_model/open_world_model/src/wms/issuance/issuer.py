"""R6-L: issue causal forecasts through a pluggable `Forecaster`, one record per opportunity.

The issuer's whole input for opportunity k is `log.available_at(t_k)`: it cannot read a sample that was not available
by its cutoff. Opportunities run on a clock anchored at the first sample time, so no whole-trial statistic decides
when a forecast is made, and the requested target is exactly t_k + horizon, whatever reference later exists.

A record is either a forecast or a named abstention. It carries no wall-clock time (a replay must be byte-identical)
and no evaluation: scoring lives in `wms.issuance.evaluation` and never writes here.

A `Forecaster` pairs an id with `estimate(view, cutoff_ms, window_ms) -> (state, None) | (None, reason)` and
`predict(state, target_ms) -> sequence[float]` (ball_m, length 3). `issue_record`/`issue_trial` default to
`CAUSAL_CV_V1` when no forecaster is given, reproducing the original hardcoded `causal_cv.v1` behaviour byte for
byte -- passing no forecaster is exactly today's behaviour, unchanged. R6-M's successor forecasters
(`wms.issuance.successors`) are built on this same shape and share this same issuance path.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np

from wms.issuance.causal_state import causal_velocity_v1
from wms.issuance.journal import canonical, sha256_bytes

FORECASTER_ID = "causal_cv.v1"


@dataclass(frozen=True)
class Forecaster:
    id: str
    estimate: Callable
    predict: Callable


def _cv_estimate(view, cutoff_ms, window_ms):
    return causal_velocity_v1(view, cutoff_ms, window_ms)


def _cv_predict(state, target_ms):
    origin = np.asarray(state["ball_m"], dtype=float)
    velocity = np.asarray(state["velocity_m_per_ms"], dtype=float)
    return origin + velocity * (target_ms - state["state_time_ms"])


CAUSAL_CV_V1 = Forecaster(FORECASTER_ID, _cv_estimate, _cv_predict)


def opportunity_times(anchor_ms: float, cadence_ms: float, until_ms: float) -> list[float]:
    """anchor + k * cadence for every k with that time at or before `until_ms` (the stream close in a replay)."""
    out, k = [], 0
    while anchor_ms + k * cadence_ms <= until_ms:
        out.append(anchor_ms + k * cadence_ms)
        k += 1
    return out


def _inputs_digest(view) -> str:
    """sha256 of every sample the issuer could see: the proof object for 'same inputs'."""
    return sha256_bytes(canonical([[s.time_ms, s.available_ms, None if s.ball_m is None else list(s.ball_m)]
                                   for s in view]))


def issue_record(view, trial: str, k: int, cutoff_ms: float, window_ms: float, horizon_ms: float,
                 forecaster: Forecaster | None = None) -> dict:
    forecaster = forecaster if forecaster is not None else CAUSAL_CV_V1
    target = cutoff_ms + horizon_ms
    identity = {"forecaster": forecaster.id, "trial": trial, "k": k, "opportunity_time_ms": cutoff_ms,
                "target_requested_ms": target}
    record = {
        "issue_id": sha256_bytes(canonical(identity))[:32],
        "forecaster": forecaster.id,
        "trial": trial,
        "opportunity": {"k": k, "time_ms": cutoff_ms},
        "information_cutoff_ms": cutoff_ms,
        "target_requested_ms": target,
        "horizon_ms": horizon_ms,
        "inputs": {"available_samples": len(view),
                   "latest_sample_time_ms": view[-1].time_ms if view else None,
                   "inputs_sha256": _inputs_digest(view)},
    }
    state, reason = forecaster.estimate(view, cutoff_ms, window_ms)
    if reason is not None:
        record.update(state=None, state_id=None, forecast=None, abstention={"reason": reason})
        return record
    prediction = forecaster.predict(state, target)
    record.update(state=state, state_id=sha256_bytes(canonical(state)),
                  forecast={"ball_m": [float(c) for c in prediction]}, abstention=None)
    return record


def issue_trial(log, trial: str, cadence_ms: float, window_ms: float, horizon_ms: float,
                forecaster: Forecaster | None = None) -> list[dict]:
    """Every opportunity of one stream, in issue order."""
    return [issue_record(log.available_at(t), trial, k, t, window_ms, horizon_ms, forecaster)
            for k, t in enumerate(opportunity_times(log.first_time_ms, cadence_ms, log.close_ms))]
