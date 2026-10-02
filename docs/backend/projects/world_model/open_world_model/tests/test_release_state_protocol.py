"""OW-RELEASE-STATE-01 — the protocol gate must refuse the configurations that would
produce an unreadable M4-versus-M3 result.

Each test names the wrong answer the refusal prevents, not just the field it checks.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

LAB = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LAB / "scripts"))

from validate_release_state_protocol import load, validate  # noqa: E402

CONFIG_PATH = LAB / "configs" / "experiments" / "release_state_v1.json"


@pytest.fixture
def cfg() -> dict:
    return load(CONFIG_PATH)


def test_the_frozen_config_passes_its_own_gate(cfg):
    assert validate(cfg) == []


def test_the_frozen_config_is_valid_json_and_names_its_packet(cfg):
    assert cfg["packet"] == "OW-RELEASE-STATE-01"
    assert json.dumps(cfg)  # round-trips


# --- protected participants ------------------------------------------------------

@pytest.mark.parametrize("protected", ["P0004", "P0005"])
def test_refuses_a_protected_participant_in_scope(cfg, protected):
    bad = copy.deepcopy(cfg)
    bad["participants"].append(protected)
    assert any(f"protected_participant_in_scope:{protected}" in r for r in validate(bad))


# --- the confound this study exists to avoid -------------------------------------

def test_refuses_scoring_M3_and_M4_on_different_populations(cfg):
    """Finger availability IS session availability. Scoring M4 on the 271 finger trials
    and M3 on all 396 would report a session difference as a hand benefit."""
    bad = copy.deepcopy(cfg)
    bad["primary_comparison"]["population"] = "all_trials"
    refusals = validate(bad)
    assert any(r.startswith("population_mismatch") for r in refusals)
    assert any("confounds hands with session" in r for r in refusals)


def test_the_recorded_audit_matches_the_measured_confound(cfg):
    a = cfg["coverage_audit_2026_09_21"]
    assert a["trials_P0001_to_P0003"] == 396
    assert a["finger_available_trials"] == 271
    assert a["finger_absent_trials"] == 125
    assert a["finger_available_trials"] + a["finger_absent_trials"] == a["trials_P0001_to_P0003"]
    assert "CONFOUNDED WITH SESSION" in a["finding"]


# --- future flight ----------------------------------------------------------------

def test_refuses_inputs_that_are_not_bounded_by_the_decision_time(cfg):
    bad = copy.deepcopy(cfg)
    bad["decision_policy"]["inputs_available_strictly_at_or_before"] = "trial_end"
    assert "inputs_not_bounded_by_decision_time" in validate(bad)


def test_refuses_targets_that_are_not_strictly_after_the_decision(cfg):
    bad = copy.deepcopy(cfg)
    bad["decision_policy"]["targets_strictly_after"] = "trial_start"
    assert "targets_not_strictly_after_decision_time" in validate(bad)


def test_refuses_an_event_triggered_decision_dressed_as_known_in_advance(cfg):
    bad = copy.deepcopy(cfg)
    bad["decision_policy"]["mode"] = "release_triggered"
    assert "decision_policy_not_fixed_cadence" in validate(bad)


# --- target matching on the real 30 Hz grid ---------------------------------------

def test_refuses_a_tolerance_wider_than_one_native_sample(cfg):
    """33.3 ms native. A tolerance above that lets a DIFFERENT sample satisfy the
    horizon, which is how an infeasible horizon gets rescued after the fact."""
    bad = copy.deepcopy(cfg)
    bad["target_matching"]["tolerance_ms"] = 50
    assert any(r.startswith("target_tolerance_exceeds_native_interval") for r in validate(bad))


def test_the_frozen_tolerance_is_within_the_PRIMARY_populations_interval(cfg):
    assert cfg["target_matching"]["tolerance_ms"] <= cfg["native_timing"]["primary_population_dt_ms"]


def test_refuses_a_non_future_horizon(cfg):
    bad = copy.deepcopy(cfg)
    bad["target_matching"]["requested_horizon_ms"] = 0
    assert "requested_horizon_absent_or_not_future" in validate(bad)


# --- moved goalposts ---------------------------------------------------------------

def test_refuses_a_comparison_not_declared_before_results(cfg):
    bad = copy.deepcopy(cfg)
    bad["primary_comparison"]["declared_before_results"] = False
    assert "primary_comparison_not_declared_before_results" in validate(bad)


def test_refuses_a_mutable_primary_comparison(cfg):
    bad = copy.deepcopy(cfg)
    del bad["primary_comparison"]["immutable"]
    assert "primary_comparison_not_marked_immutable" in validate(bad)


# --- missingness and splits --------------------------------------------------------

def test_refuses_a_policy_that_does_not_forbid_zero_filling(cfg):
    bad = copy.deepcopy(cfg)
    bad["missingness"]["forbidden"] = "nothing in particular"
    assert "missingness_does_not_forbid_zero_filling" in validate(bad)


def test_refuses_splits_not_grouped_by_athlete(cfg):
    bad = copy.deepcopy(cfg)
    bad["splits"]["grouping"] = "shot"
    assert "splits_not_grouped_by_athlete" in validate(bad)


def test_refuses_model_selection_outside_the_training_partition(cfg):
    bad = copy.deepcopy(cfg)
    bad["splits"]["model_selection"] = "on the held-out athlete"
    assert "model_selection_not_confined_to_training_partition" in validate(bad)


# --- claims -------------------------------------------------------------------------

@pytest.mark.parametrize("term", ["spin", "contact", "causal"])
def test_requires_the_unclaimed_terms_to_stay_unclaimed(cfg, term):
    bad = copy.deepcopy(cfg)
    bad["not_claimed"] = [c for c in bad["not_claimed"] if term not in c.lower()]
    assert f"not_claimed_missing_term:{term}" in validate(bad)


def test_gravity_is_not_a_release_window_baseline(cfg):
    """A ball still being accelerated by the hand is not in free flight."""
    assert "gravity" not in " ".join(cfg["baselines_before_learning"]).lower()
    assert "not" in cfg["baseline_note"].lower() and "gravity" in cfg["baseline_note"].lower()


def test_a_missing_section_is_refused_rather_than_defaulted(cfg):
    bad = copy.deepcopy(cfg)
    del bad["target_matching"]
    assert "missing_required_section:target_matching" in validate(bad)


# --- the gap found while building Stage 2 ------------------------------------------

def test_refuses_a_cadence_that_is_named_but_not_specified(cfg):
    """'fixed_cadence' names a MODE. Without cadence_ms two implementers build
    different datasets from the same 'frozen' config."""
    bad = copy.deepcopy(cfg)
    del bad["decision_policy"]["cadence_ms"]
    assert any(r.startswith("decision_cadence_unspecified") for r in validate(bad))


def test_refuses_a_cadence_anchored_on_a_detected_event(cfg):
    bad = copy.deepcopy(cfg)
    bad["decision_policy"]["anchor"] = "release_event"
    assert any(r.startswith("decision_anchor_is_retrospective") for r in validate(bad))


def test_refuses_an_unspecified_prefix(cfg):
    bad = copy.deepcopy(cfg)
    del bad["prefix"]["length_ms"]
    assert "prefix_length_unspecified" in validate(bad)


def test_refuses_an_unspecified_missing_data_threshold(cfg):
    bad = copy.deepcopy(cfg)
    del bad["prefix"]["min_finite_fraction"]
    assert "prefix_min_finite_fraction_unspecified" in validate(bad)


def test_refuses_feature_families_that_do_not_require_M4_to_be_a_superset(cfg):
    """If M4 could DROP an M3 input, a difference might come from the loss, not the hands."""
    bad = copy.deepcopy(cfg)
    bad["feature_families"]["superset_required"] = False
    assert "feature_families_do_not_require_M4_superset_of_M3" in validate(bad)


def test_refuses_an_unspecified_M3_joint_set(cfg):
    bad = copy.deepcopy(cfg)
    bad["feature_families"]["M3"]["joints"] = []
    assert "M3_joint_set_unspecified" in validate(bad)


# --- RS-A1: the mixed-rate corpus (the defect this amendment corrects) --------------

def test_the_corpus_is_recorded_as_mixed_rate(cfg):
    m = cfg["native_timing"]["measured_2026_09_21"]
    assert m["2024-08-28"]["measured_median_dt_ms"] == 33.0
    assert m["2025-12-18"]["measured_median_dt_ms"] == 17.0
    assert cfg["native_timing"]["primary_population_session"] == "2025-12-18"


def test_refuses_a_cadence_declared_in_SAMPLES_on_a_mixed_rate_corpus(cfg):
    """A sample count means 51 ms at 60 Hz and 100 ms at 30 Hz. That is exactly how v1
    declared 100 ms and delivered 51 ms on the scored population."""
    bad = copy.deepcopy(cfg)
    bad["decision_policy"]["cadence_samples"] = 3
    assert any(r.startswith("cadence_declared_in_samples") for r in validate(bad))


def test_refuses_a_prefix_declared_in_SAMPLES(cfg):
    bad = copy.deepcopy(cfg)
    bad["prefix"]["length_samples"] = 8
    assert any(r.startswith("prefix_declared_in_samples") for r in validate(bad))


def test_refuses_the_v1_tolerance_against_the_real_primary_interval(cfg):
    """v1's 17 ms tolerance EXCEEDS the 60 Hz interval. It passed only because the config
    declared the wrong rate."""
    bad = copy.deepcopy(cfg)
    bad["target_matching"]["tolerance_ms"] = 17
    assert any(r.startswith("target_tolerance_exceeds_native_interval") for r in validate(bad))


def test_refuses_timing_that_was_not_measured_per_session(cfg):
    bad = copy.deepcopy(cfg)
    del bad["native_timing"]["measured_2026_09_21"]
    assert "native_timing_not_measured_per_session" in validate(bad)


def test_the_amendment_is_recorded_as_pre_fit(cfg):
    a = next(x for x in cfg["amendments"] if x["id"] == "RS-A1")
    assert "pre-fit" in a["status"]
    assert "not changed" in a["unchanged"].lower() or "NOT changed" in a["unchanged"]
