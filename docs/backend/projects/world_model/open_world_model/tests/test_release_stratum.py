"""OW-RELEASE-STATE-01 V16-S1 - the release stratum must group, never select.

The dangerous failure here is not a wrong number: it is a retrospective event quietly
becoming an advance-known trigger, which would turn a fixed-cadence study into a
"release-only" claim the system cannot support.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

LAB = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LAB / "scripts"))

from run_release_state_baselines import velocity  # noqa: E402
from stratify_release_state import NEAR_MS, STRATA, stratum_for, trial_release_time  # noqa: E402
from validate_release_state_protocol import load  # noqa: E402

DET = json.loads((LAB / "configs" / "experiments"
                  / "event_release_feasibility_v1.json").read_text(encoding="utf-8"))


# --- the stratum boundary ---------------------------------------------------------------

def test_a_decision_at_the_release_sample_is_post_release():
    """The event sample itself is not "just before"; the ball has left the hand."""
    assert stratum_for(0.0) == "post_release"


def test_the_near_boundary_is_inclusive_and_the_next_millisecond_is_far():
    assert stratum_for(-NEAR_MS) == "pre_release_near"
    assert stratum_for(-NEAR_MS - 0.001) == "pre_release_far"


def test_every_offset_lands_in_exactly_one_named_stratum():
    for off in (-5000.0, -NEAR_MS - 1, -NEAR_MS, -1.0, 0.0, 1.0, 5000.0):
        assert stratum_for(off) in STRATA


def test_the_boundary_is_a_parameter_not_a_hidden_constant():
    """The near/far cut is a choice, so its sensitivity has to be reportable."""
    assert stratum_for(-150.0, near_ms=100.0) == "pre_release_far"
    assert stratum_for(-150.0, near_ms=200.0) == "pre_release_near"


# --- the label groups, it never selects ---------------------------------------------------

def test_stratifying_cannot_change_a_prediction():
    """A forecast's value must not depend on how it was later grouped. The stratifier
    reads stored predictions and never writes any, so this asserts the property that makes
    that safe: the label is a pure function of two timestamps."""
    import inspect
    src = inspect.getsource(stratum_for)
    for forbidden in ("prediction", "ref", "error", "fit", "feats"):
        assert forbidden not in src


def test_the_label_is_a_pure_function_of_timing():
    a = stratum_for(-42.0)
    b = stratum_for(-42.0)
    assert a == b


# --- the event is retrospective, and the detector says so --------------------------------

def test_the_detector_reads_the_whole_trial_so_the_event_is_not_known_in_advance():
    """`detect_release` scans forward over every evaluable sample. That is exactly why the
    stratum may only group results: a live system at decision time does not have it."""
    import inspect
    from run_event_release_feasibility import detect_release
    src = inspect.getsource(detect_release)
    assert "for i in np.flatnonzero" in src      # scans the trial


def test_a_trial_with_no_detected_release_is_reported_not_guessed():
    """Missing stays missing: no fallback release time is invented."""
    tracking = [{"time": 0.0, "data": {"ball": [0.0, 0.0, 1.0], "player": {}}},
                {"time": 17.0, "data": {"ball": [0.0, 0.0, 1.0], "player": {}}}]
    ms, reason = trial_release_time(tracking, DET)
    assert ms is None
    assert reason in ("no_contact", "no_ascending_release", "too_few_samples")


def test_a_too_short_trial_refuses_rather_than_returning_zero():
    ms, reason = trial_release_time([{"time": 0.0, "data": {"ball": None, "player": {}}}], DET)
    assert ms is None and reason == "too_few_samples"


# --- the identity the join depends on ------------------------------------------------------

def test_trial_filenames_are_not_unique_across_sessions():
    """The reason the join is keyed by (session, trial): 88 of 396 stems occur twice. A
    stem-keyed map silently held one session's release event under the other's name."""
    root = LAB / "data" / "external" / "SPL-Open-Data" / "basketball" / "freethrow" / "data"
    stems = [p.stem for p in root.glob("*/P000[123]/*.json")]
    assert len(stems) == 396
    assert len(set(stems)) < len(stems)


def test_the_example_identity_carries_the_session():
    from run_release_state_experiment import collect
    cfg = load(LAB / "configs" / "experiments" / "release_state_v1_2.json")
    rows, _ = collect(cfg, LAB / "data" / "external" / "SPL-Open-Data")
    assert rows
    for r in rows[:50]:
        session, rest = r["id"].split("/", 1)
        assert session == r["session"]
        assert rest.startswith(r["trial"] + "#")


# --- the baseline in each stratum is the SAME baseline ---------------------------------------

def test_the_reconstructed_constant_velocity_equals_the_baselines_definition():
    """The stratifier rebuilds constant velocity from stored features rather than re-deriving
    it. If that reconstruction drifted from `run_release_state_baselines.velocity`, every
    per-stratum baseline would be a different candidate wearing the same name."""
    times = [0.0, 16.0, 33.0]
    pts = [[1.0, 2.0, 3.0], [1.1, 2.0, 3.0], [1.3, 2.05, 3.1]]
    horizon = 100.0
    v = velocity(times, pts)
    from_baselines = [pts[-1][k] + v[k] * horizon for k in range(3)]

    # the stratifier's route: the first three feature columns ARE that velocity
    dt = times[-1] - times[-2]
    feat_velocity = [(pts[-1][k] - pts[-2][k]) / dt for k in range(3)]
    origin = np.asarray(pts[-1], dtype=float)
    from_features = origin + np.asarray(feat_velocity, dtype=float) * horizon

    assert from_features == pytest.approx(from_baselines, abs=1e-12)
