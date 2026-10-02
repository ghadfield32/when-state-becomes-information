"""OW-RELEASE-STATE-01 Stage 3a — the baselines must be honest floors.

They use only the prefix, they refuse rather than guess, and none of them is a
gravity model.
"""
from __future__ import annotations

import copy
import json
import math
import sys
from pathlib import Path

import pytest

LAB = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LAB / "scripts"))

from run_release_state_baselines import BASELINES, predict, quadratic, velocity  # noqa: E402
from validate_release_state_protocol import load, scientific_digest, validate  # noqa: E402

CONFIG = load(LAB / "configs" / "experiments" / "release_state_v1.json")


def example(times, pts, target_t, target=(9.9, 9.9, 9.9)):
    return {"prefix": {"times_ms": list(times), "ball_m": [list(p) for p in pts]},
            "target": {"time_ms": target_t, "ball_m": list(target)}}


# --- the baselines use only the prefix ---------------------------------------------

def test_held_position_is_exactly_the_last_prefix_sample():
    e = example([0, 17, 34], [[1, 2, 3], [1.1, 2, 3], [1.2, 2, 3]], 134)
    assert predict(e)["held_position"] == [1.2, 2, 3]


def test_constant_velocity_extrapolates_the_last_prefix_velocity():
    e = example([0, 17, 34], [[0, 0, 0], [1, 0, 0], [2, 0, 0]], 134)  # 1 m per 17 ms in x
    got = predict(e)["constant_velocity"]
    assert got == pytest.approx([2 + (100 / 17), 0, 0], abs=1e-9)


def test_a_baseline_never_reads_the_target_value():
    """Changing the target must not change any prediction."""
    a = example([0, 17, 34], [[0, 0, 0], [1, 0, 0], [2, 0, 0]], 134, target=(0, 0, 0))
    b = example([0, 17, 34], [[0, 0, 0], [1, 0, 0], [2, 0, 0]], 134, target=(500, -500, 42))
    assert predict(a) == predict(b)


def test_a_later_prefix_sample_changes_the_prediction():
    a = predict(example([0, 17, 34], [[0, 0, 0], [1, 0, 0], [2, 0, 0]], 134))
    b = predict(example([0, 17, 34], [[0, 0, 0], [1, 0, 0], [9, 0, 0]], 134))
    assert a["held_position"] != b["held_position"]


# --- refusal rather than a guess ----------------------------------------------------

def test_velocity_refuses_a_single_sample_and_a_nonpositive_interval():
    assert velocity([0], [[1, 1, 1]]) is None
    assert velocity([10, 10], [[1, 1, 1], [2, 2, 2]]) is None


def test_quadratic_refuses_fewer_than_three_samples():
    assert quadratic([0, 17], [[0, 0, 0], [1, 0, 0]], 100) is None


def test_an_unavailable_baseline_is_None_not_a_substituted_value():
    e = example([0], [[1, 2, 3]], 100)
    p = predict(e)
    assert p["constant_velocity"] is None
    assert p["quadratic_prefix"] is None
    assert p["held_position"] == [1, 2, 3]  # this one is always available


# --- the quadratic is NOT a gravity model -------------------------------------------

def test_the_quadratic_recovers_a_curvature_that_is_not_gravity():
    """A ball still accelerated by the hand is not in free flight, so the curvature is
    ESTIMATED. Feed it an upward acceleration gravity could never produce."""
    a = +30.0 / 1e6  # m per ms^2, upward
    times = [0, 17, 34, 51]
    pts = [[0, 0, 0.5 * a * t * t] for t in times]
    got = quadratic(times, pts, 151)
    assert got is not None
    assert got[2] == pytest.approx(0.5 * a * 151 ** 2, rel=1e-6)
    assert got[2] > 0  # gravity-only would pull this down


def test_every_declared_baseline_is_implemented():
    e = example([0, 17, 34], [[0, 0, 0], [1, 0, 0], [2, 0, 0]], 134)
    assert set(predict(e)) == set(BASELINES)


# --- finding 4: the approved experiment is bound by digest ---------------------------

def test_the_recorded_digest_matches_the_scientific_keys():
    assert CONFIG["protocol_identity"]["scientific_digest"] == scientific_digest(CONFIG)
    assert validate(CONFIG) == []


@pytest.mark.parametrize("path,value", [
    (("target_matching", "requested_horizon_ms"), 50),
    (("target_matching", "tolerance_ms"), 4),
    (("decision_policy", "cadence_ms"), 200),
    (("prefix", "length_ms"), 500),
    (("primary_comparison", "population"), "all_trials"),
    (("splits", "grouping"), "trial"),
])
def test_changing_any_scientific_value_is_refused_by_the_digest(path, value):
    """'Immutable' was prose. Prose does not refuse an easier horizon."""
    bad = copy.deepcopy(CONFIG)
    node = bad
    for k in path[:-1]:
        node = node[k]
    node[path[-1]] = value
    refusals = validate(bad)
    assert any(r.startswith("protocol_scientific_digest_mismatch") for r in refusals), refusals


def test_prose_may_be_improved_without_breaking_the_digest():
    ok = copy.deepcopy(CONFIG)
    ok["question"] = ok["question"] + " (clarified wording)"
    ok["metrics"]["cost"].append("notes")
    assert not any(r.startswith("protocol_scientific_digest") for r in validate(ok))
