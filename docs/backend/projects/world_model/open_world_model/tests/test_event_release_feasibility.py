"""OW-EVENT-20 negative controls: known-geometry synthetic trials, causality, exclusions and protected participants."""
from __future__ import annotations

import gzip
import hashlib
import json
import math
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

LAB = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LAB / "scripts"))
import run_event_release_feasibility as study  # noqa: E402

G = 9.81
HZ = 60.0
NAMES = ("NOSE", "RIGHT_WRIST", "RIGHT_SECOND_FINGER_DISTAL", "LEFT_THUMB_DISTAL", "LEFT_ELBOW")
HELD = np.array([0.0, 0.0, 0.15])  # ball centre 0.15 m above the hand while held: inside one diameter (0.2385 m)


@pytest.fixture(scope="module")
def config():
    return study.default_config()


@pytest.fixture(scope="module")
def regime17_config(config):
    return study.load_regime17_config(config)


def shot(end_s=3.0, release_s=1.9, v=(0.0, 1.0, 4.0), dribble=False, pass_in=False, far=False):
    """Hand at rest, then lifting; the ball rides 0.15 m above it until release, then free flight.

    The clock is integer milliseconds floored from the frame period, like the SPL stamps (0, 16, 33, 50, ...).
    """
    t_ms = np.floor(np.arange(int(end_s * HZ) + 1) * 1000.0 / HZ + 1e-9).astype(np.int64)
    t = t_ms / 1000.0
    hand = np.empty((len(t), 3))
    for i, ti in enumerate(t):
        lift = min(max(ti - 1.0, 0.0), release_s - 1.0)  # the hand stops where the ball left it
        hand[i] = np.array([0.0, 0.3 * lift, 1.2 + 1.5 * lift])
    ball = hand + HELD
    for i, ti in enumerate(t):
        if ti > release_s:
            tau = ti - release_s
            ball[i] = hand[i] + HELD + np.asarray(v) * tau + np.array([0.0, 0.0, -0.5 * G * tau ** 2])
        if dribble and 0.3 < ti < 0.7:
            ball[i, 2] -= 3.0 * (min(ti, 0.5) - 0.3) - 3.0 * max(ti - 0.5, 0.0)  # down 0.6 m and back into the hand
        if pass_in and ti < 0.25:
            ball[i, 1] += -3.0 + 12.0 * ti  # arrives from 3 m away
    if far:
        ball[:, 1] += 5.0
    player = np.full((len(t), len(NAMES), 3), np.nan)
    player[:, 1] = hand
    player[:, 2] = hand + np.array([0.0, 0.05, 0.02])
    player[:, 3] = hand + np.array([0.0, -0.05, 0.02])
    player[:, 4] = hand - np.array([0.0, 0.0, 0.3])  # elbow: close enough to matter if it were counted as a hand
    player[:, 0] = hand + np.array([0.0, 0.0, 0.5])
    return t_ms, ball, player, NAMES, np.arange(len(t)), HZ


def boundary(config, radii=None):
    return (config["contact_boundary_radii"] if radii is None else radii) * study.ball_radius_m(config)


def independent_event(t, ball, player, config):
    """The event recomputed directly from geometry for a clean, gap-free, ascending synthetic release."""
    hands = player[:, [1, 2, 3]]
    d = np.linalg.norm(hands - ball[:, None, :], axis=2).min(axis=1)
    b = boundary(config)
    return next(i for i in range(1, len(t)) if d[i - 1] <= b < d[i] and t[i] > 1000)


def test_ball_radius_and_boundaries_are_derived_from_the_circumference(config):
    r = 29.5 / (2 * math.pi) * 0.0254
    assert study.ball_radius_m(config) == pytest.approx(r, rel=1e-15)
    assert config["contact_boundary_radii"] * r == pytest.approx(2 * r)
    low, high = config["sensitivity_boundary_radii"]
    assert low < config["contact_boundary_radii"] < high


def test_only_left_right_wrist_thumb_pinky_finger_keypoints_are_hands():
    names = ("NOSE", "LEFT_WRIST", "RIGHT_PINKY_KNUCKLE", "LEFT_ELBOW", "RIGHT_THUMB_DISTAL", "MID_HIP",
             "RIGHT_FOURTH_FINGER_DISTAL", "WRIST", "LEFT_HEEL")
    assert [names[i] for i in study.hand_indices(names)] == ["LEFT_WRIST", "RIGHT_PINKY_KNUCKLE", "RIGHT_THUMB_DISTAL",
                                                             "RIGHT_FOURTH_FINGER_DISTAL"]


def test_distance_uses_finite_hand_keypoints_and_stays_missing_otherwise():
    ball = np.array([[0.0, 0.0, 1.0], [np.nan, 0.0, 1.0], [0.0, 0.0, 1.0]])
    player = np.full((3, 2, 3), np.nan)
    player[0, 0] = [0.0, 0.0, 0.7]
    player[0, 1] = [0.0, 0.0, 0.9]
    player[1, 0] = [0.0, 0.0, 0.9]
    distance = study.ball_hand_distance(ball, player, [0, 1])
    assert distance[0] == pytest.approx(0.1)
    assert np.isnan(distance[1]) and np.isnan(distance[2])  # ball missing; every hand keypoint missing
    assert np.isnan(study.ball_hand_distance(ball, player, [])).all()


def test_release_is_the_first_ascending_separation_and_post_event_flight_is_gravity(config, regime17_config):
    t, ball, player, names, frames, hz = shot()
    out = study.trial_record(t, ball, player, names, frames, hz, config, regime17_config)
    i = independent_event(t, ball, player, config)
    assert out["event"] == "event" and out["event_time_s"] == t[i] / 1000
    assert out["excluded_transitions"] == 0 and out["first_contact_time_s"] == 0.0
    assert out["hand_keypoints_named"] == 3 and out["hand_keypoints_ever_finite"] == 3
    # The event sample lands exactly on the baseline cutoff, so the prefix state is read at the event.
    assert out["prefix"] == "eligible" and out["z_at_cutoff_m"] == ball[i, 2]
    assert out["future_fits"] == "fitted"
    assert out["quadratic_vertical_acceleration_m_s2"] == pytest.approx(-G, abs=1e-6)
    assert out["separation_growth_100ms_m"] > 0
    assert out["event_shift_at_1_5r_s"] <= 0 <= out["event_shift_at_3r_s"]


def test_event_ignores_everything_after_it(config, regime17_config):
    t, ball, player, names, frames, hz = shot()
    base = study.trial_record(t, ball, player, names, frames, hz, config, regime17_config)
    i = independent_event(t, ball, player, config)
    moved_ball, moved_player = ball.copy(), player.copy()
    moved_ball[i + 1:] = player[i + 1:, 1] + HELD  # the future puts the ball straight back in the hand
    moved_player[i + 1:] += 7.0
    moved = study.trial_record(t, moved_ball, moved_player, names, frames, hz, config, regime17_config)
    for key in ("event", "event_time_s", "hand_distance_at_event_m", "first_contact_time_s", "excluded_transitions",
                "prefix", "z_at_cutoff_m", "vz_at_cutoff_m_s", "event_shift_at_1_5r_s"):
        assert moved[key] == base[key], key
    assert moved["quadratic_vertical_acceleration_m_s2"] != base["quadratic_vertical_acceleration_m_s2"], "control did not move the future"


def test_event_is_tied_to_motion_not_to_the_wall_clock(config, regime17_config):
    t, ball, player, names, frames, hz = shot()
    base = study.trial_record(t, ball, player, names, frames, hz, config, regime17_config)
    late = study.trial_record(t + 1000, ball, player, names, frames, hz, config, regime17_config)
    assert late["event_time_s"] == pytest.approx(base["event_time_s"] + 1.0)
    assert late["event_minus_fixed_cutoff_s"] == pytest.approx(base["event_minus_fixed_cutoff_s"] + 1.0)
    # Integer-millisecond shifting makes the event-anchored window bit-identical whatever the clock offset.
    clock = {"event_time_s", "event_minus_fixed_cutoff_s", "first_contact_time_s"}
    for key in set(base) - clock:
        assert late[key] == base[key], key


def test_the_sample_exactly_one_history_before_the_event_is_inside_the_window():
    times_ms = np.array([1000, 1100, 1200], dtype=np.int64)
    ball = np.array([[0.0, 0.0, 1.0], [0.0, 0.0, 1.1], [0.0, 0.0, 1.2]])
    assert study.ascending(times_ms, ball, 2, 200, 2) is True
    assert study.ascending(times_ms, ball, 2, 199, 2) is None
    with pytest.raises(ValueError, match="history_not_whole_milliseconds"):
        study.history_ms({"history_s": 0.2005})


def test_non_millisecond_time_stamps_are_refused(tmp_path):
    t, ball, player, names, _, _ = shot()
    row = _write_trial(tmp_path, "2025-12-18", "P0001", "T0001", t, ball, player, names)
    path = tmp_path / row["path"]
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["tracking"][5]["time"] += 0.5
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="non_millisecond_time_axis"):
        study.load_inputs(path, "P0001")


def test_descending_dribble_is_excluded_and_the_shot_is_still_found(config, regime17_config):
    t, ball, player, names, frames, hz = shot(dribble=True)
    out = study.trial_record(t, ball, player, names, frames, hz, config, regime17_config)
    assert out["excluded_by_reason"] == {"time_gap": 0, "descending": 1, "direction_unknown": 0}
    assert out["event"] == "event" and out["event_time_s"] == t[independent_event(t, ball, player, config)] / 1000


def test_incoming_pass_is_not_a_transition(config, regime17_config):
    t, ball, player, names, frames, hz = shot(pass_in=True)
    out = study.trial_record(t, ball, player, names, frames, hz, config, regime17_config)
    assert out["excluded_transitions"] == 0 and out["event"] == "event"
    assert 0.2 < out["first_contact_time_s"] <= 0.25 + 1 / HZ


def test_separation_across_a_tracking_gap_is_excluded(config, regime17_config):
    t, ball, player, names, frames, hz = shot()
    i = independent_event(t, ball, player, config)
    ball[i - 1:i + 2] = np.nan  # the last contact sample before the gap is 2 frames before the next evaluable one
    out = study.trial_record(t, ball, player, names, frames, hz, config, regime17_config)
    assert out["excluded_by_reason"]["time_gap"] == 1
    assert out["event"] == "no_ascending_release" and out["event_time_s"] is None


def test_separation_without_enough_ball_history_is_direction_unknown(config, regime17_config):
    t, ball, player, names, frames, hz = shot()
    i = independent_event(t, ball, player, config)
    ball[i - 13:i - 1] = np.nan  # hands stay finite: only the event sample and its predecessor remain in the window
    out = study.trial_record(t, ball, player, names, frames, hz, config, regime17_config)
    assert out["excluded_by_reason"]["direction_unknown"] == 1
    assert out["event"] == "no_ascending_release"


def test_trial_without_contact_keeps_every_event_value_missing(config, regime17_config):
    t, ball, player, names, frames, hz = shot(far=True)
    out = study.trial_record(t, ball, player, names, frames, hz, config, regime17_config)
    assert out["event"] == "no_contact" and out["first_contact_time_s"] is None
    assert all(out[key] is None for key in study.EVENT_NUMERIC)
    assert out["prefix"] is None and out["targets"] == {} and out["future_fits"] is None


def test_summary_accounts_every_trial_once_and_counts_missing(config, regime17_config):
    rows = []
    for participant, kwargs in (("P0001", {}), ("P0001", {"far": True}), ("P0002", {"dribble": True})):
        t, ball, player, names, frames, hz = shot(**kwargs)
        rows.append({"path": f"p/{participant}/{len(rows)}", "session": "2025-12-18", "participant": participant, "hz": hz,
                     **study.trial_record(t, ball, player, names, frames, hz, config, regime17_config)})
    summary = study.summarize(rows)
    assert summary["all"]["trials"] == 3 and sum(summary["all"]["event"].values()) == 3
    assert summary["all"]["event"] == {"event": 2, "no_contact": 1}
    assert summary["all"]["excluded_by_reason"]["descending"] == 1
    assert summary["all"]["all_trials"]["first_contact_time_s"]["n_missing"] == 1
    assert summary["all"]["events"]["event_time_s"]["n_finite"] == 2
    assert summary["2025-12-18/P0001"]["trials"] == 2 and summary["2025-12-18/P0002"]["trials"] == 1


def test_frozen_config_and_pinned_regime17_inputs_are_enforced(tmp_path, config):
    edited = tmp_path / "c.json"
    edited.write_text(json.dumps(dict(config, contact_boundary_radii=3.0)), encoding="utf-8")
    with pytest.raises(ValueError, match="frozen_config_mismatch"):
        study.check_frozen(edited, hashlib.sha256(edited.read_bytes()).hexdigest())
    with pytest.raises(ValueError, match="regime17_config_changed"):
        study.load_regime17_config(dict(config, regime17_config=dict(config["regime17_config"], sha256="0" * 64)))
    assert set(config["participants"]) == {"P0001", "P0002", "P0003"}
    assert set(config["not_opened"]) == {"P0004", "P0005"}


def test_loader_disagreement_on_the_ball_blocks(tmp_path, monkeypatch):
    t, ball, player, names, frames, hz = shot()
    path = _write_trial(tmp_path, "2025-12-18", "P0001", "T0001", t, ball, player, names)["path"]

    class Shifted:
        participant_id, frame_index, player_xyz_m, keypoint_names = "P0001", frames, player, names
        ball_xyz_m = ball + 0.001

    monkeypatch.setattr(study, "load_spl_free_throw", lambda p: Shifted)
    with pytest.raises(ValueError, match="loader_ball_disagreement"):
        study.load_inputs(tmp_path / path, "P0001")


def _write_trial(root, session, participant, trial_id, t, ball, player, names):
    rel = f"basketball/freethrow/data/{session}/{participant}/BB_FT_{participant}_{trial_id}.json"
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)

    def feet(p):
        return None if not np.isfinite(p).all() else (p / 0.3048).tolist()

    rows = [{"frame": i, "time": int(ti),
             "data": {"ball": feet(ball[i]), "player": {n: feet(player[i, j]) for j, n in enumerate(names)}}}
            for i, ti in enumerate(t)]
    path.write_text(json.dumps({"sampling_rate": HZ, "participant_id": participant, "trial_id": trial_id,
                                "tracking": rows}), encoding="utf-8")
    return {"path": rel, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "participant": participant,
            "session": session}


def _fake_run(tmp_path, config, monkeypatch):
    data = tmp_path / "data"
    t, ball, player, names, _, _ = shot()
    # The second trial's clock starts at 5 s: the loader re-zeroes it, and its event is still found by motion.
    rows = [_write_trial(data, "2025-12-18", "P0001", "T0001", t, ball, player, names),
            _write_trial(data, "2025-12-18", "P0002", "T0001", t + 5000, ball + 0.01, player + 0.01, names)]
    # A P0004 row whose file does not exist: opening it would raise, so completion proves it was never read.
    rows.append({"path": "basketball/freethrow/data/2025-12-18/P0004/BB_FT_P0004_T0001.json",
                 "sha256": "f" * 64, "participant": "P0004", "session": "2025-12-18"})
    inventory = tmp_path / "inventory.json"
    inventory.write_text(json.dumps({"source_revision": config["data_revision"], "per_trial": rows}), encoding="utf-8")
    regime17_raw = (json.dumps({"summary": {"all": {
        "future_fits": {"fitted": 1}, "release_heuristic": {"none_found": 1},
        "all_trials": {k: {"n_finite": 0} for k in study.COMPARED},
        "prefix_eligible": {k: {"n_finite": 0} for k in study.COMPARED}}}}) + "\n").encode("utf-8")
    regime17_manifest = tmp_path / "regime17.json.gz"
    regime17_manifest.write_bytes(gzip.compress(regime17_raw, mtime=0))
    cfg = dict(config, expected_trials=2, inventory_sha256=hashlib.sha256(inventory.read_bytes()).hexdigest(),
               regime17_retained_manifest={"path": str(regime17_manifest), "original_sha256": hashlib.sha256(regime17_raw).hexdigest()})
    monkeypatch.setattr(study, "subprocess", SimpleNamespace(
        check_output=lambda *a, **k: config["data_revision"] + "\n"))
    output = tmp_path / "run"
    output.mkdir()
    args = type("Args", (), {"data_root": data, "inventory": inventory, "regime17_manifest": regime17_manifest,
                             "config_sha256": "x", "output": output})()
    return args, cfg, rows


def test_fake_revision_does_not_change_unrelated_subprocess_output(tmp_path, config, monkeypatch):
    import subprocess

    _fake_run(tmp_path, config, monkeypatch)
    output = subprocess.check_output([sys.executable, "-c", "print('unrelated-process')"])
    assert output.strip() == b"unrelated-process"


def test_run_detects_events_by_motion_and_never_opens_protected_participants(tmp_path, config, monkeypatch):
    args, cfg, rows = _fake_run(tmp_path, config, monkeypatch)
    report = {}
    study.run(args, report, cfg)
    assert report["status"] == study.STATUS and report["trials"] == 2
    assert report["opened"] == [rows[0]["path"], rows[1]["path"]]
    assert [r["event"] for r in report["results"]] == ["event", "event"]
    assert report["results"][0]["event_time_s"] == pytest.approx(report["results"][1]["event_time_s"])
    assert report["fixed_cutoff_reference"]["all"]["future_fits"] == {"fitted": 1}
    assert (args.output / "examples.png").stat().st_size > 0 and len(report["examples"]) == 2
    with pytest.raises(ValueError, match="regime17_evidence_mismatch"):
        study.run(args, {}, dict(cfg, regime17_retained_manifest={"path": "x", "original_sha256": "0" * 64}))
    # A P0005 row cannot enter the run: the inventory contract refuses it before any file is read.
    p5 = dict(rows[0], path="basketball/freethrow/data/2025-12-18/P0005/BB_FT_P0005_T0001.json",
              participant="P0005", sha256="e" * 64)
    args.inventory.write_text(json.dumps({"source_revision": config["data_revision"], "per_trial": rows + [p5]}),
                              encoding="utf-8")
    with pytest.raises(ValueError, match="development_only_path_required"):
        study.run(args, {}, dict(cfg, inventory_sha256=hashlib.sha256(args.inventory.read_bytes()).hexdigest()))


def test_a_protected_row_relabelled_as_development_is_refused_before_it_is_read(tmp_path, config, monkeypatch):
    opened = []
    monkeypatch.setattr(study, "load_inputs", lambda *a: pytest.fail("read a refused row"))
    row = {"path": "basketball/freethrow/data/2025-12-18/P0004/BB_FT_P0004_T0001.json", "participant": "P0004",
           "sha256": "f" * 64, "session": "2025-12-18"}
    with pytest.raises(ValueError, match="input_outside_admitted_participants"):
        study.open_admitted(tmp_path, row, config, opened)
    escaping = dict(row, participant="P0001", path="../outside.json")
    with pytest.raises(ValueError, match="input_outside_admitted_participants"):
        study.open_admitted(tmp_path / "root", escaping, config, opened)
    assert opened == []


def _reseal(retained, report):
    raw = (json.dumps(report, indent=1) + "\n").encode("utf-8")
    gz = gzip.compress(raw, mtime=0)
    (retained / "run_manifest.json.gz").write_bytes(gz)
    policy = json.loads((retained / "RETENTION.json").read_text(encoding="utf-8"))
    policy["files"]["run_manifest.json"].update(original_sha256=hashlib.sha256(raw).hexdigest(),
                                                retained_sha256=hashlib.sha256(gz).hexdigest())
    (retained / "RETENTION.json").write_text(json.dumps(policy), encoding="utf-8")


def test_retained_bundle_recomputes_rederives_rows_and_edits_are_caught(tmp_path, config, monkeypatch):
    args, cfg, _ = _fake_run(tmp_path, config, monkeypatch)
    report = {}
    study.run(args, report, cfg)
    (args.output / "run_manifest.json").write_bytes((json.dumps(report, indent=1) + "\n").encode("utf-8"))
    retained = tmp_path / "bundle"
    study.retain(args.output, retained)
    assert study.verify_retained(retained, cfg) == []
    assert study.verify_retained(retained, cfg, args.data_root, args.inventory) == []
    assert study.verify_retained(retained, dict(cfg, history_s=0.3)) == ["config_mismatch"]
    (retained / "examples.png").write_bytes(b"edited")
    assert study.verify_retained(retained, cfg) == ["digest_mismatch:examples.png"]
    study.retain(args.output, tmp_path / "bundle2")
    retained = tmp_path / "bundle2"
    original = report["results"][0]["event_time_s"]
    report["results"][0]["event_time_s"] = original + 0.5
    _reseal(retained, report)
    assert study.verify_retained(retained, cfg) == ["summary_not_recomputable"]
    report["results"][0]["event_time_s"] = original
    report["results"][0]["hand_keypoints_named"] = 99  # not summarized: only re-deriving the row catches it
    _reseal(retained, report)
    assert study.verify_retained(retained, cfg) == []
    assert study.verify_retained(retained, cfg, args.data_root, args.inventory) == [
        "row_not_rederivable:" + report["results"][0]["path"]]
    report["results"][0]["hand_keypoints_named"] = 3
    report["fixed_cutoff_reference"]["all"]["future_fits"] = {"fitted": 2}  # an edited copy of REGIME-17's numbers
    _reseal(retained, report)
    assert study.verify_retained(retained, cfg) == ["fixed_cutoff_reference_not_reproducible"]


@pytest.mark.private_evidence
def test_real_retained_bundle_replays_its_fixed_cutoff_reference(config):
    """The committed OW-EVENT-20 bundle verifies without data: digests, config, summary and REGIME-17 reference."""
    assert study.verify_retained(study.REPO / "reports/world_model/v1_2/event20/retained", config) == []
