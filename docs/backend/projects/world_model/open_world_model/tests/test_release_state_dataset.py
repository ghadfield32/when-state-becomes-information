"""OW-RELEASE-STATE-01 Stage 2 — the dataset builder must not leak the future.

The fixture mirrors the REAL SPL shape ({sampling_rate, tracking:[{frame,time,data:{ball,player}}]}),
because a fixture written to the shape the builder assumes would let a nesting bug pass.
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

from build_release_state_dataset import (  # noqa: E402
    build_trial, finite3, history_window, main, marker_sets, samples_for, to_metres,
)
from validate_release_state_protocol import load  # noqa: E402

CONFIG = load(LAB / "configs" / "experiments" / "release_state_v1.json")

JOINTS = CONFIG["feature_families"]["M3"]["joints"]
FINGERS = ["RIGHT_SECOND_FINGER_DISTAL", "RIGHT_THUMB", "RIGHT_PINKY"]


def trial(n_frames: int = 120, fingers: bool = True, dt: float = 17.0):
    frames = []
    for i in range(n_frames):
        player = {j: [0.1 * i, 0.2, 1.0 + 0.01 * i] for j in JOINTS}
        if fingers:
            player.update({f: [0.1 * i + 0.05, 0.21, 1.02 + 0.01 * i] for f in FINGERS})
        frames.append({"frame": i, "time": round(i * dt, 3),
                       "data": {"ball": [0.3 * i, 0.4, 2.0 + 0.02 * i], "player": player}})
    return {"sampling_rate": 30, "tracking": frames}


@pytest.fixture
def path(tmp_path):
    def _write(doc, name="BB_FT_P0001_T0001.json"):
        d = tmp_path / "2025-12-18" / "P0001"
        d.mkdir(parents=True, exist_ok=True)
        p = d / name
        p.write_text(json.dumps(doc), encoding="utf-8")
        return p
    return _write


# --- the decisive property: the future cannot reach an input ----------------------

def test_no_input_sample_is_taken_after_the_decision(path):
    ex, _ = build_trial(path(trial()), CONFIG)
    assert ex
    for e in ex:
        assert max(e["prefix"]["indices"]) == e["decision"]["index"]
        assert all(t <= e["decision"]["time_ms"] for t in e["prefix"]["times_ms"])


def test_mutating_one_decisions_future_leaves_that_decisions_inputs_unchanged(path):
    """Windows OVERLAP, so "the future" is per decision: a sample after decision d is an
    INPUT for a later decision. Mutating every future of every decision at once would
    corrupt later inputs, which is a property of the cadence, not a leak. So this
    perturbs exactly one decision's future and checks that decision."""
    base = trial()
    ex_a, _ = build_trial(path(base), CONFIG)
    target_e = ex_a[len(ex_a) // 2]
    d = target_e["decision"]["index"]

    mutated = copy.deepcopy(base)
    for k in range(d + 1, len(mutated["tracking"])):
        mutated["tracking"][k]["data"]["ball"] = [999.0, -999.0, 42.0]
    ex_b, _ = build_trial(path(mutated, "BB_FT_P0001_T0002.json"), CONFIG)

    after = next(e for e in ex_b if e["decision"]["index"] == d)
    assert after["prefix"] == target_e["prefix"]          # inputs untouched
    # The sentinel is injected into the RAW tracking, which is feet, so it comes back
    # converted. Asserting the raw triplet is what made this test fail once the
    # V16-U1 unit boundary landed - the future still moved, and only the future.
    assert after["target"]["ball_m"] == [c * 0.3048 for c in (999.0, -999.0, 42.0)]


def test_no_earlier_decision_can_see_a_later_perturbation(path):
    base = trial()
    ex_a, _ = build_trial(path(base), CONFIG)
    cut = ex_a[len(ex_a) // 2]["decision"]["index"]

    mutated = copy.deepcopy(base)
    for k in range(cut + 1, len(mutated["tracking"])):
        mutated["tracking"][k]["data"]["ball"] = [999.0, -999.0, 42.0]
    ex_b, _ = build_trial(path(mutated, "BB_FT_P0001_T0004.json"), CONFIG)

    by_d = {e["decision"]["index"]: e for e in ex_b}
    for e in ex_a:
        if e["decision"]["index"] <= cut and e["decision"]["index"] in by_d:
            assert by_d[e["decision"]["index"]]["prefix"] == e["prefix"]


def test_the_target_is_strictly_after_the_decision(path):
    ex, _ = build_trial(path(trial()), CONFIG)
    for e in ex:
        assert e["target"]["time_ms"] > e["decision"]["time_ms"]
        assert e["target"]["index"] > e["decision"]["index"]


# --- target matching respects ACTUAL timestamps ------------------------------------

def test_every_matched_target_is_inside_the_frozen_tolerance(path):
    tol = CONFIG["target_matching"]["tolerance_ms"]
    ex, _ = build_trial(path(trial()), CONFIG)
    for e in ex:
        assert abs(e["target"]["offset_ms"]) <= tol


def test_a_gap_wider_than_the_tolerance_is_refused_not_stretched(path):
    doc = trial()
    # stretch the grid so no sample lands within tolerance of decision+100ms
    for i, f in enumerate(doc["tracking"]):
        f["time"] = round(i * 250.0, 3)
    ex, ref = build_trial(path(doc), CONFIG)
    assert ex == []
    assert ref.get("no_target_within_tolerance", 0) > 0


# --- missing stays missing ----------------------------------------------------------

def test_an_incomplete_prefix_is_refused_and_never_zero_filled(path):
    doc = trial()
    doc["tracking"][10]["data"]["ball"] = None
    ex, ref = build_trial(path(doc), CONFIG)
    assert ref.get("prefix_ball_incomplete", 0) > 0
    for e in ex:
        assert all(finite3(b) for b in e["prefix"]["ball_m"])
        assert all(b != [0, 0, 0] for b in e["prefix"]["ball_m"])


def test_a_missing_target_refuses_the_example_rather_than_imputing_it(path):
    doc = trial()
    for f in doc["tracking"][20:]:
        f["data"]["ball"] = None
    ex, ref = build_trial(path(doc), CONFIG)
    assert ref.get("prefix_ball_incomplete", 0) + ref.get("target_ball_missing", 0) > 0
    for e in ex:
        assert finite3(e["target"]["ball_m"])


def test_a_missing_body_joint_refuses_rather_than_substituting(path):
    doc = trial()
    doc["tracking"][12]["data"]["player"]["RIGHT_ELBOW"] = None
    _, ref = build_trial(path(doc), CONFIG)
    assert ref.get("prefix_body_incomplete", 0) > 0


# --- M4 is a strict superset, on the SAME rows --------------------------------------

def test_M4_adds_markers_without_changing_a_single_M3_input(path):
    with_f, _ = build_trial(path(trial(fingers=True)), CONFIG)
    without_f, _ = build_trial(path(trial(fingers=False), "BB_FT_P0001_T0003.json"), CONFIG)
    assert with_f and without_f
    assert [e["prefix"]["ball_m"] for e in with_f] == [e["prefix"]["ball_m"] for e in without_f]
    assert [e["prefix"]["m3_joints"] for e in with_f] == [e["prefix"]["m3_joints"] for e in without_f]
    assert all(e["m4_available"] for e in with_f)
    assert not any(e["m4_available"] for e in without_f)
    assert all(e["prefix"]["m4_added"] is None for e in without_f)


def test_a_finger_absent_trial_is_flagged_not_zero_filled(path):
    ex, _ = build_trial(path(trial(fingers=False)), CONFIG)
    for e in ex:
        assert e["m4_available"] is False
        assert e["prefix"]["m4_added"] is None
        assert e["target"]["hand_m"] is None


# --- accounting and grouping ---------------------------------------------------------

def test_every_intended_decision_is_eligible_or_refused(path):
    doc = trial()
    doc["tracking"][15]["data"]["ball"] = None
    ex, ref = build_trial(path(doc), CONFIG)
    from build_release_state_dataset import samples_for
    times = [f["time"] for f in doc["tracking"]]
    cadence = samples_for(times, CONFIG["decision_policy"]["cadence_ms"])
    intended = len(range(0, len(doc["tracking"]), cadence))
    assert len(ex) + sum(ref.values()) == intended


def test_every_example_carries_its_athlete_group_for_split_isolation(path):
    ex, _ = build_trial(path(trial()), CONFIG)
    assert {e["group"] for e in ex} == {"P0001"}
    # overlapping windows from one trial all share one group, so they cannot straddle folds
    assert len({e["source"]["trial"] for e in ex}) == 1


def test_every_example_identifies_its_source_and_times(path):
    e = build_trial(path(trial()), CONFIG)[0][0]
    for key in ("session", "athlete", "trial", "path"):
        assert e["source"][key]
    assert e["decision"]["last_available_input_time_ms"] == e["decision"]["time_ms"]


# --- the gate blocks the build --------------------------------------------------------

def test_a_refused_protocol_blocks_the_build_before_any_source_is_opened(tmp_path, capsys):
    bad = copy.deepcopy(CONFIG)
    bad["participants"].append("P0004")
    cfg = tmp_path / "bad.json"
    cfg.write_text(json.dumps(bad), encoding="utf-8")
    rc = main(["--config", str(cfg), "--data-root", str(tmp_path / "nonexistent"),
               "--out", str(tmp_path / "out")])
    assert rc == 2
    assert "BLOCKED" in capsys.readouterr().out
    assert not (tmp_path / "out").exists()  # nothing was written


# --- RS-A1: numerical validity and per-trial rate conversion -------------------------

def test_finite3_rejects_NaN_infinity_and_booleans(path):
    """isinstance(c, (int, float)) alone passes NaN, inf and True - bool subclasses int."""
    assert finite3([1.0, 2.0, 3.0])
    assert not finite3([float("nan"), 1.0, 2.0])
    assert not finite3([float("inf"), 1.0, 2.0])
    assert not finite3([True, 1.0, 2.0])


def test_a_NaN_coordinate_refuses_the_example_rather_than_entering_the_prefix(path):
    doc = trial()
    doc["tracking"][30]["data"]["ball"] = [float("nan"), 1.0, 2.0]
    ex, ref = build_trial(path(doc), CONFIG)
    assert ref.get("prefix_ball_incomplete", 0) > 0
    import math
    for e in ex:
        assert all(all(math.isfinite(c) for c in b) for b in e["prefix"]["ball_m"])


def test_a_declared_duration_converts_per_trial_rate(path):
    from build_release_state_dataset import samples_for
    fast = [i * 17.0 for i in range(120)]   # 2025-12-18, 60 Hz
    slow = [i * 33.0 for i in range(120)]   # 2024-08-28, 30 Hz
    assert samples_for(fast, 100) == 6
    assert samples_for(slow, 100) == 3
    assert samples_for(fast, 267) == 16
    assert samples_for(slow, 267) == 8


def test_the_same_declared_window_spans_the_same_TIME_at_both_rates(path):
    ex_fast, _ = build_trial(path(trial(dt=17.0)), CONFIG)
    ex_slow, _ = build_trial(path(trial(dt=33.0), "BB_FT_P0001_T0009.json"), CONFIG)
    span = lambda e: e["prefix"]["times_ms"][-1] - e["prefix"]["times_ms"][0]
    assert abs(span(ex_fast[0]) - span(ex_slow[0])) <= 35  # within one slow sample


# --- V16-U1: the unit boundary -------------------------------------------------------
#
# The SPL source publishes FEET. This builder copied them into fields named `_m`, so
# every metre-labelled number in the release-state reports was a foot value. These pin
# the conversion at one boundary and refuse the ways a unit bug stays silent.

class TestUnitBoundary:
    def test_the_source_really_is_feet_not_metres(self):
        """Read as metres the source is physically impossible: this is WHY we convert."""
        root = (LAB / "data" / "external" / "SPL-Open-Data" / "basketball" / "freethrow"
                / "data")
        trial = sorted(root.glob("*/P000[123]/*.json"))[0]
        tracking = json.loads(trial.read_text(encoding="utf-8"))["tracking"]
        # Some ball samples are NaN. That is honest missing data, so it is EXCLUDED
        # from the scale check rather than filled - max() over a NaN returns NaN and
        # would have made this assertion meaningless.
        zs = [f["data"]["ball"][2] for f in tracking
              if isinstance(f["data"].get("ball"), list)
              and math.isfinite(f["data"]["ball"][2])]
        peak = max(zs)
        # A free throw peaks above a 10 ft rim: ~13 ft = ~4 m. 13 METRES is absurd,
        # and so is a 4 ft peak, so the scale is unambiguous.
        assert 9.0 < peak < 20.0, peak
        assert 2.5 < peak * 0.3048 < 6.0, peak * 0.3048

    def test_one_foot_becomes_exactly_0_3048_metres(self):
        assert to_metres([1.0, 0.0, 0.0])[0] == 0.3048
        # 3 * 0.3048 is not exactly 0.9144 in binary floating point, so the contract is
        # "the constant, applied once" - not a decimal literal.
        assert to_metres([0.0, 3.0, 0.0])[1] == 3.0 * 0.3048

    def test_the_same_boundary_applies_to_ball_body_and_hands(self):
        """A conversion applied to only one family would silently mix scales, and the
        ball-to-hand distance would be meaningless."""
        cfg = load(LAB / "configs" / "experiments" / "release_state_v1_1.json")
        trial = sorted((LAB / "data" / "external" / "SPL-Open-Data" / "basketball"
                        / "freethrow" / "data").glob("*/P000[123]/*.json"))[0]
        raw = json.loads(trial.read_text(encoding="utf-8"))["tracking"]
        ex, _ = build_trial(trial, cfg)
        assert ex, "expected at least one eligible example"
        e = ex[0]
        i = e["prefix"]["indices"][0]
        assert e["prefix"]["ball_m"][0] == pytest.approx(
            [c * 0.3048 for c in raw[i]["data"]["ball"]], abs=1e-12)
        for joint, series in e["prefix"]["m3_joints"].items():
            assert series[0] == pytest.approx(
                [c * 0.3048 for c in raw[i]["data"]["player"][joint]], abs=1e-12)
        if e["m4_available"]:
            for joint, series in e["prefix"]["m4_added"].items():
                assert series[0] == pytest.approx(
                    [c * 0.3048 for c in raw[i]["data"]["player"][joint]], abs=1e-12)

    def test_timestamps_are_never_scaled(self):
        """`time` is milliseconds. Scaling it would be a unit bug in the other direction
        and would silently move every horizon."""
        cfg = load(LAB / "configs" / "experiments" / "release_state_v1_1.json")
        trial = sorted((LAB / "data" / "external" / "SPL-Open-Data" / "basketball"
                        / "freethrow" / "data").glob("*/P000[123]/*.json"))[0]
        raw = json.loads(trial.read_text(encoding="utf-8"))["tracking"]
        ex, _ = build_trial(trial, cfg)
        e = ex[0]
        assert e["decision"]["time_ms"] == raw[e["decision"]["index"]]["time"]

    def test_a_missing_marker_is_still_refused_not_turned_into_a_number(self):
        """Converting must not resurrect a None as a coordinate."""
        assert to_metres(None) is None
        assert to_metres([1.0, None, 3.0])[1] is None
        assert not finite3(to_metres([1.0, None, 3.0]))

    def test_a_boolean_is_not_a_coordinate_after_conversion_either(self):
        assert not finite3(to_metres([True, 2.0, 3.0]))


# --- V16-T1: the elapsed-time contract -----------------------------------------------
#
# A STRIDE of n samples crosses n intervals; a WINDOW of n samples crosses n-1. The
# cadence is a stride and was right; the prefix is a window and was short by exactly one
# interval. Measured on the real corpus: all 9,621 scored examples achieved 250.0 ms
# against a declared 267 ms, and NONE reached 267.

class TestElapsedTimeContract:
    def test_a_window_of_n_samples_crosses_n_minus_1_intervals(self):
        """The arithmetic the old rule got wrong, stated directly."""
        times = [0.0, 17.0, 34.0, 51.0]
        assert samples_for(times, 51.0) == 3       # 51/17
        # ...but 3 samples span only 2 intervals = 34 ms, not the 51 ms requested.
        assert times[2] - times[0] == 34.0

    def test_adding_one_sample_does_not_fix_the_real_corpus(self):
        """Measured, not constructed: the 60 Hz timestamps are integer-rounded, so the
        intervals alternate 16 and 17 ms. The old rule picks 16 samples (250.0 ms) and
        17 samples spans 266.0 ms - still not 267. No sample COUNT can enforce a
        duration on irregular timestamps, which is why the contract is timestamp-bound.

        An earlier version of this test built its own interval pattern, which happened
        to land on exactly 267.0 and disproved the very claim it was asserting."""
        # The corpus is MIXED-RATE: 2024-08-28 is 30 Hz and 2025-12-18 is 60 Hz, and the
        # entire scored population comes from the 60 Hz session (it is the one carrying
        # finger markers). Pin the session, or this reads the 30 Hz trial and measures a
        # different contract.
        trial = sorted((LAB / "data" / "external" / "SPL-Open-Data" / "basketball"
                        / "freethrow" / "data" / "2025-12-18").glob("P000[123]/*.json"))[0]
        times = [f["time"] for f in
                 json.loads(trial.read_text(encoding="utf-8"))["tracking"]]
        n = samples_for(times, 267.0)
        assert n == 16
        assert times[n - 1] - times[0] == 250.0        # the shipped shortfall
        assert times[n] - times[0] == 266.0            # one more sample is still not 267

    def test_the_window_always_achieves_at_least_the_declared_length(self):
        times = [i * 16.6667 for i in range(60)]
        d = 50
        idx, achieved, overshoot = history_window(times, d, 267.0)
        assert achieved >= 267.0
        assert overshoot == pytest.approx(achieved - 267.0)
        assert idx[-1] == d                      # the decision sample is included
        assert times[d] - times[idx[0]] == achieved

    def test_it_takes_the_most_recent_qualifying_sample_not_an_earlier_one(self):
        """Reaching further back than necessary would silently widen the history."""
        times = [i * 10.0 for i in range(40)]
        idx, achieved, _ = history_window(times, 30, 100.0)
        assert achieved == 100.0                 # exactly, on a regular grid
        assert idx[0] == 20
        # one sample earlier would also satisfy ">= 100 ms" and must NOT be chosen
        assert times[30] - times[19] > 100.0

    def test_the_boundary_sample_is_included_when_it_lands_exactly(self):
        times = [0.0, 100.0, 200.0, 300.0]
        idx, achieved, overshoot = history_window(times, 3, 100.0)
        assert idx[0] == 2 and achieved == 100.0 and overshoot == 0.0

    def test_a_trial_that_does_not_reach_back_far_enough_is_refused(self):
        """A short window must REFUSE, never be passed off as a full one."""
        times = [0.0, 17.0, 34.0]
        assert history_window(times, 2, 267.0) is None

    def test_a_gap_is_absorbed_as_overshoot_and_reported(self):
        """An irregular interval must not silently shorten the history."""
        times = [0.0, 50.0, 300.0, 320.0, 340.0]      # 250 ms gap
        idx, achieved, overshoot = history_window(times, 4, 100.0)
        assert achieved >= 100.0
        assert overshoot > 0.0                         # the gap is visible, not hidden

    def test_duplicate_timestamps_do_not_break_the_boundary(self):
        times = [0.0, 100.0, 100.0, 200.0, 300.0]
        idx, achieved, _ = history_window(times, 4, 100.0)
        assert achieved >= 100.0 and idx[-1] == 4

    def test_a_future_timestamp_cannot_change_an_earlier_window(self):
        """Strict as-of: mutating anything after the decision must not move its history."""
        times = [i * 17.0 for i in range(40)]
        before = history_window(times, 20, 267.0)
        mutated = list(times)
        for k in range(21, len(mutated)):
            mutated[k] = mutated[k] + 9999.0
        assert history_window(mutated, 20, 267.0) == before

    def test_the_cadence_stride_is_left_alone(self):
        """The stride crosses n intervals and was already correct; V16-T1 must not
        'fix' it into a different decision schedule."""
        times = [i * 16.6667 for i in range(60)]
        stride = samples_for(times, 100.0)
        assert times[stride] - times[0] == pytest.approx(100.0, abs=0.1)

    def test_an_unknown_selection_rule_is_refused_not_guessed(self):
        cfg = copy.deepcopy(load(LAB / "configs" / "experiments" / "release_state_v1_1.json"))
        cfg["prefix"]["selection"] = "whatever_seems_reasonable"
        trial = sorted((LAB / "data" / "external" / "SPL-Open-Data" / "basketball"
                        / "freethrow" / "data").glob("*/P000[123]/*.json"))[0]
        with pytest.raises(ValueError, match="unknown prefix.selection"):
            build_trial(trial, cfg)

    def test_a_config_without_a_selection_key_keeps_the_legacy_rule(self):
        """The superseded contract must stay reproducible, so its absence is meaningful."""
        cfg = load(LAB / "configs" / "experiments" / "release_state_v1_1.json")
        assert "selection" not in cfg["prefix"]
        trial = sorted((LAB / "data" / "external" / "SPL-Open-Data" / "basketball"
                        / "freethrow" / "data").glob("*/P000[123]/*.json"))[0]
        ex, _ = build_trial(trial, cfg)
        assert ex and ex[0]["prefix"]["selection"] == "sample_count_from_median_interval"
        # and it reproduces the measured 250 ms shortfall rather than hiding it
        assert ex[0]["prefix"]["achieved_span_ms"] < cfg["prefix"]["length_ms"]


class TestFrozenFeatureSchema:
    """V16-T1: a declared M3 joint missing from the source must REFUSE, not silently
    shrink the family. Measured across all 396 trials the schema is stable - M3 is always
    the full 12 declared joints and M4 always adds 44 markers - so this guard changes no
    existing result. It exists so a future source change cannot report a smaller model
    under the same family name."""

    def test_a_missing_declared_m3_joint_is_refused(self):
        cfg = load(LAB / "configs" / "experiments" / "release_state_v1_2.json")
        present = [j for j in cfg["feature_families"]["M3"]["joints"]][:-1]
        with pytest.raises(ValueError, match="absent from the source"):
            marker_sets(cfg, present)

    def test_the_full_declared_set_is_returned_in_declared_order(self):
        """Feature ORDER is part of the schema: a reordered vector is a different model."""
        cfg = load(LAB / "configs" / "experiments" / "release_state_v1_2.json")
        declared = cfg["feature_families"]["M3"]["joints"]
        m3, _ = marker_sets(cfg, sorted(declared) + ["RIGHT_THUMB"])
        assert m3 == declared

    def test_m4_adds_are_disjoint_from_m3_and_sorted(self):
        cfg = load(LAB / "configs" / "experiments" / "release_state_v1_2.json")
        declared = cfg["feature_families"]["M3"]["joints"]
        m3, added = marker_sets(cfg, list(declared) + ["RIGHT_THUMB", "LEFT_THUMB"])
        assert not set(added) & set(m3)
        assert added == sorted(added)

    def test_the_real_corpus_schema_is_identical_in_every_trial(self):
        """The measurement behind the claim above, asserted rather than remembered."""
        cfg = load(LAB / "configs" / "experiments" / "release_state_v1_2.json")
        root = LAB / "data" / "external" / "SPL-Open-Data" / "basketball" / "freethrow" / "data"
        sigs = set()
        for t in sorted(root.glob("*/P000[123]/*.json")):
            tr = json.loads(t.read_text(encoding="utf-8"))["tracking"]
            present = sorted(tr[0]["data"].get("player", {}).keys())
            m3, added = marker_sets(cfg, present)
            sigs.add((tuple(m3), len(added)))
        assert len(sigs) == 1, sigs
        (m3, n_added), = sigs
        assert len(m3) == 12 and n_added == 44
