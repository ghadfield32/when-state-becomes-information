"""OW-RELEASE-STATE-01 Stage 3b — the comparison must be structurally fair.

These assert the properties that make an M4-minus-M3 number mean anything: the families
see the same rows, M4 strictly contains M3, features are prefix-only, and the held-out
athlete never reaches model selection.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

LAB = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LAB / "scripts"))

from run_release_state_experiment import (  # noqa: E402
    FAMILIES, family_points, features, ridge_fit, ridge_predict, standardise,
)
from validate_release_state_protocol import load  # noqa: E402

CONFIG = load(LAB / "configs" / "experiments" / "release_state_v1.json")
PRESENT = (CONFIG["feature_families"]["M3"]["joints"]
           + ["LEFT_THUMB", "RIGHT_THUMB", "LEFT_PINKY", "RIGHT_PINKY",
              "RIGHT_SECOND_FINGER_DISTAL", "RIGHT_THIRD_FINGER_DIP"])


def example(extra=None, target=(9.0, 9.0, 9.0)):
    names = CONFIG["feature_families"]["M3"]["joints"]
    m3 = {n: [[0.1, 0.2, 0.3], [0.11, 0.2, 0.3]] for n in names}
    added = {n: [[0.5, 0.6, 0.7], [0.52, 0.6, 0.7]] for n in
             ["LEFT_THUMB", "RIGHT_THUMB", "LEFT_PINKY", "RIGHT_PINKY",
              "RIGHT_SECOND_FINGER_DISTAL", "RIGHT_THIRD_FINGER_DIP"]}
    if extra:
        added.update(extra)
    return {"prefix": {"times_ms": [0.0, 17.0], "ball_m": [[1.0, 1.0, 1.0], [1.2, 1.0, 1.0]],
                       "m3_joints": m3, "m4_added": added},
            "target": {"ball_m": list(target)}}


# --- M4 strictly contains M3 --------------------------------------------------------

def test_each_family_is_a_strict_superset_of_the_previous():
    m3 = family_points(CONFIG, PRESENT, "M3")
    m3b = family_points(CONFIG, PRESENT, "M3b")
    m4 = family_points(CONFIG, PRESENT, "M4")
    assert set(m3) < set(m3b) < set(m4)
    assert m3b[:len(m3)] == m3 and m4[:len(m3)] == m3  # ordering preserved


def test_the_coarse_hand_is_thumb_and_pinky_not_the_wrists():
    """The proposed wrist-only ablation would have duplicated M3: the wrists are already
    core joints, so adding them adds nothing."""
    added = set(family_points(CONFIG, PRESENT, "M3b")) - set(family_points(CONFIG, PRESENT, "M3"))
    assert added == {"LEFT_THUMB", "RIGHT_THUMB", "LEFT_PINKY", "RIGHT_PINKY"}
    assert "LEFT_WRIST" in CONFIG["feature_families"]["M3"]["joints"]
    assert not any("WRIST" in a for a in added)


def test_a_richer_family_has_a_larger_feature_vector():
    e = example()
    dims = {f: features(e, family_points(CONFIG, PRESENT, f)).shape[0] for f in FAMILIES}
    assert dims["M3"] < dims["M3b"] < dims["M4"]


def test_the_shared_prefix_of_a_richer_vector_is_identical():
    """M4 must not perturb an M3 term, or a difference could come from the change itself."""
    e = example()
    a = features(e, family_points(CONFIG, PRESENT, "M3"))
    b = features(e, family_points(CONFIG, PRESENT, "M4"))
    assert np.allclose(b[: a.shape[0]], a)


# --- prefix-only ---------------------------------------------------------------------

def test_features_never_read_the_target():
    a = features(example(target=(0, 0, 0)), family_points(CONFIG, PRESENT, "M4"))
    b = features(example(target=(500, -500, 42)), family_points(CONFIG, PRESENT, "M4"))
    assert np.allclose(a, b)


def test_features_are_expressed_relative_to_the_decision_sample_ball():
    e = example()
    f = features(e, family_points(CONFIG, PRESENT, "M3"))
    # first three entries are the ball velocity over the final interval
    assert np.allclose(f[:3], [(1.2 - 1.0) / 17.0, 0.0, 0.0])


def test_a_missing_point_refuses_the_whole_vector_rather_than_zero_filling():
    e = example()
    del e["prefix"]["m4_added"]["RIGHT_THUMB"]
    assert features(e, family_points(CONFIG, PRESENT, "M3b")) is None


def test_a_nonpositive_interval_is_refused():
    e = example()
    e["prefix"]["times_ms"] = [5.0, 5.0]
    assert features(e, family_points(CONFIG, PRESENT, "M3")) is None


# --- the model itself ----------------------------------------------------------------

def test_ridge_recovers_a_known_linear_map_at_low_alpha():
    rng = np.random.default_rng(CONFIG["model"]["seed"])
    X = rng.normal(size=(400, 5))
    true = rng.normal(size=(5, 3))
    Y = X @ true + 0.5
    W = ridge_fit(X, Y, 1e-8)
    assert np.allclose(W[1:], true, atol=1e-4)
    assert np.allclose(ridge_predict(W, X), Y, atol=1e-4)


def test_more_regularisation_shrinks_the_coefficients():
    rng = np.random.default_rng(1)
    X = rng.normal(size=(200, 4))
    Y = X @ rng.normal(size=(4, 3))
    small = np.abs(ridge_fit(X, Y, 1e-6)[1:]).sum()
    large = np.abs(ridge_fit(X, Y, 1e3)[1:]).sum()
    assert large < small


def test_the_intercept_is_not_penalised():
    X = np.zeros((50, 3))
    Y = np.full((50, 3), 7.0)
    W = ridge_fit(X, Y, 1e6)
    assert np.allclose(W[0], 7.0, atol=1e-6)


def test_standardisation_statistics_come_only_from_the_training_rows():
    train = np.array([[0.0, 10.0], [2.0, 10.0]])
    mu, sd = standardise(train)
    assert np.allclose(mu, [1.0, 10.0])
    assert sd[1] == 1.0  # a constant column is not divided by zero


# --- the declared budget --------------------------------------------------------------

def test_the_selection_budget_is_declared_and_identical_for_every_family():
    sel = CONFIG["model"]["selection"]
    assert len(sel["grid"]) == 7
    assert "identical for M3, M3b and M4" in sel["budget"]
    assert "never used for selection" in sel["inner_scheme"]


def test_the_primary_aggregate_is_per_athlete_not_per_window():
    agg = CONFIG["aggregation"]
    assert "MEAN OF THE THREE ATHLETE MEANS" in agg["primary_aggregate"]
    assert "not independent" in agg["why"]


# --- RS-A2: the budget is covered by the digest, and both grids are reported ---------

def test_the_model_budget_is_inside_the_digest_covered_set():
    """A selection budget changed after seeing results is the same failure as a changed
    horizon, so it must move the digest rather than slip through."""
    assert "model" in CONFIG["protocol_identity"]["covers"]
    assert "aggregation" in CONFIG["protocol_identity"]["covers"]


def test_both_grids_are_declared_and_the_preregistered_one_is_kept():
    sel = CONFIG["model"]["selection"]
    assert sel["grid_as_preregistered"] == [1e-4, 1e-3, 1e-2, 1e-1, 1.0, 10.0, 100.0]
    assert sel["grid_amended_RS_A2"][:7] == sel["grid_as_preregistered"]
    assert len(sel["grid_amended_RS_A2"]) > len(sel["grid_as_preregistered"])
    assert "never replaced" in sel["reporting"]


def test_the_amendment_declares_itself_post_hoc():
    a = next(x for x in CONFIG["amendments"] if x["id"] == "RS-A2")
    assert "POST-HOC" in a["status"]
    assert "pre-registered result stands" in a["status"]
    assert "NOT replace" in a["honesty_constraint"] or "does NOT replace" in a["honesty_constraint"]
