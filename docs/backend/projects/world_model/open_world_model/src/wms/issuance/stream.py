"""R6-L: an observation stream that can only be read up to a cutoff.

What this is: the ball-centre observations of one trial, each with its native timestamp and the time it became
AVAILABLE. `available_at(cutoff)` is the only read path an issuer gets, so a forecast built from that view cannot
reach a later sample.

What this is NOT: a live transport. Offline motion capture records no arrival times, so availability is the native
timestamp plus a DECLARED latency (zero in causal_issuance_v1). A live source must replace it with measured
availability.

Missing stays missing: a ball that is absent or not three finite real numbers is `None`, never a zero coordinate.

One refusal reads the whole stream, and it is declared here: the clock check (strictly increasing time,
availability not before occurrence) runs over the entire trial at load. A malformed LATER timestamp therefore refuses
the whole trial, including records whose prefix was well formed. That fails closed; it never changes the content of
a record that is issued.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

from wms.data.mlse_spl import FEET_TO_METERS


@dataclass(frozen=True)
class Sample:
    time_ms: float
    available_ms: float
    ball_m: tuple[float, float, float] | None


def ball_metres(value) -> tuple[float, float, float] | None:
    """Source feet -> metres once, component by component (the same arithmetic as E1's builder). Anything that is not
    three finite real numbers is MISSING. `bool` is refused even though it is an `int`."""
    if not (isinstance(value, (list, tuple)) and len(value) == 3):
        return None
    if not all(isinstance(c, (int, float)) and not isinstance(c, bool) and math.isfinite(c) for c in value):
        return None
    return tuple(c * FEET_TO_METERS for c in value)


class ObservationLog:
    """An immutable, time-ordered stream. Refuses non-increasing native time and availability before occurrence."""

    def __init__(self, samples):
        samples = tuple(samples)
        if not samples:
            raise ValueError("stream_empty")
        for a, b in zip(samples, samples[1:]):
            if not b.time_ms > a.time_ms:
                raise ValueError(f"stream_time_not_strictly_increasing: {a.time_ms} -> {b.time_ms}")
        for s in samples:
            if s.available_ms < s.time_ms:
                raise ValueError(f"stream_available_before_time: {s.time_ms}")
        self._samples = samples

    @property
    def first_time_ms(self) -> float:
        """Known when the stream starts: the anchor of the opportunity clock."""
        return self._samples[0].time_ms

    @property
    def close_ms(self) -> float:
        """The last availability time: where an offline replay's clock stops."""
        return max(s.available_ms for s in self._samples)

    def available_at(self, cutoff_ms: float) -> tuple[Sample, ...]:
        """Every sample available at or before the cutoff, in native-time order. Nothing later exists in the view."""
        return tuple(s for s in self._samples if s.available_ms <= cutoff_ms)


def ball_stream_from_bytes(raw: bytes, latency_ms: float = 0) -> ObservationLog:
    """One SPL free-throw trial's ball stream from the exact bytes a caller digested; availability = native time +
    the declared latency."""
    tracking = json.loads(raw)["tracking"]
    return ObservationLog(Sample(f["time"], f["time"] + latency_ms, ball_metres(f["data"].get("ball")))
                          for f in tracking)


def load_spl_ball_stream(path: Path, latency_ms: float = 0) -> ObservationLog:
    return ball_stream_from_bytes(Path(path).read_bytes(), latency_ms)
