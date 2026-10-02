"""OW-CONTEXT-22 negative controls: closed-form endpoint candidates, support audit, reproduction, freeze, cohort, retention."""
from __future__ import annotations

import gzip
import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

LAB = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LAB / "scripts"))
sys.path.insert(0, str(LAB / "tests"))
import run_context_at_release as study  # noqa: E402
from test_event_release_feasibility import _write_trial, shot  # noqa: E402

HZ = 60.0
NAMES = ["RIGHT_SECOND_FINGER_DISTAL", "RIGHT_THUMB_DISTAL", "RIGHT_WRIST", "NOSE"]
A_BALL, A_FINGER, A_THUMB = 6.0, 2.0, 2.5  # upward accelerations from rest at t = 1 s (m/s^2)
OFFSET_FINGER, OFFSET_THUMB = 0.15, 0.16  # vertical offsets below the ball centre at rest (m)


@pytest.fixture(scope="module")
def config():
    return study.default_config()


@pytest.fixture(scope="module")
def task_configs(config):
    _, event_config, rule_config = study.load_task_configs(config)
    return event_config, rule_config


def diverging(end_s=2.0):
    """Ball and two contact keypoints on exact quadratics that separate smoothly; the wrist never touches."""
    t_ms = np.floor(np.arange(int(end_s * HZ) + 1) * 1000.0 / HZ + 1e-9).astype(np.int64)
    s = np.maximum(t_ms / 1000.0 - 1.0, 0.0)
    ball = np.column_stack((np.zeros_like(s), np.zeros_like(s), 1.5 + 0.5 * A_BALL * s ** 2))
    player = np.full((len(s), len(NAMES), 3), np.nan)
    player[:, 0] = np.column_stack((np.zeros_like(s), np.zeros_like(s), 1.5 - OFFSET_FINGER + 0.5 * A_FINGER * s ** 2))
    player[:, 1] = np.column_stack((np.zeros_like(s), np.zeros_like(s), 1.5 - OFFSET_THUMB + 0.5 * A_THUMB * s ** 2))
    player[:, 2] = np.column_stack((np.zeros_like(s), np.full_like(s, 0.3), 1.2 + 0.5 * A_THUMB * s ** 2))
    player[:, 3] = ball + 0.05  # a non-hand keypoint glued to the ball must never count as contact
    return t_ms, ball, player


def test_config_pins_match_the_files_and_evidence_they_name(config):
    assert hashlib.sha256((LAB / config["task"]["config"]["path"]).read_bytes()).hexdigest() == config["task"]["config"]["sha256"]
    assert set(config["participants"]) == {"P0001", "P0002", "P0003"} and set(config["not_opened"]) == {"P0004", "P0005"}
    assert {c for pair in config["contrasts"] for c in pair} <= set(study.CANDIDATES)


@pytest.mark.private_evidence
def test_config_pins_match_private_retained_evidence(config):
    policy = json.loads((study.REPO / "reports/world_model/v1_2/event21/retained/RETENTION.json").read_text(encoding="utf-8"))
    for key, name in (("manifest", "run_manifest.json"), ("frozen_predictions", "frozen_predictions.json")):
        assert config["event21_reproduction"][key]["original_sha256"] == policy["files"][name]["original_sha256"]


def test_quadratic_endpoint_recovers_exact_state_at_the_cutoff():
    t = np.floor(np.arange(0, 181) * 1000.0 / HZ + 1e-9) / 1000.0
    p0, v0, a = np.array([1.0, -2.0, 3.0]), np.array([0.5, 1.5, 4.0]), np.array([0.0, 0.2, -9.81])
    tau = t - 2.0
    series = p0 + np.outer(tau, v0) + 0.5 * np.outer(tau ** 2, a)
    position, velocity, n = study.quadratic_endpoint(t, series, HZ)
    assert np.allclose(position, p0, atol=1e-9) and np.allclose(velocity, v0, atol=1e-9) and n == 13


def test_endpoint_candidates_match_closed_form_with_contact_keypoints_only(config, task_configs):
    event_config, rule_config = task_configs
    t_ms, ball, player = diverging()
    frozen = study.freeze_row(t_ms, ball, player, NAMES, HZ, event_config, rule_config)
    assert frozen["event"] == "event" and frozen["arm"]["prefix"] == "eligible"
    te = frozen["event_time_s"]
    boundary = event_config["contact_boundary_radii"] * study.event20.ball_radius_m(event_config)
    s = np.maximum(t_ms / 1000.0 - 1.0, 0.0)
    distance = np.minimum(OFFSET_FINGER + 0.5 * (A_BALL - A_FINGER) * s ** 2, OFFSET_THUMB + 0.5 * (A_BALL - A_THUMB) * s ** 2)
    expected = int(np.flatnonzero(distance > boundary)[0])
    assert round(te * 1000) == t_ms[expected]
    ctx = frozen["context"]
    assert ctx["support"]["status"] == "stable" and ctx["support"]["contact_keypoints"] == sorted(NAMES[:2])
    se = te - 1.0
    assert np.allclose(ctx["ball_endpoint"]["velocity_m_s"], [0, 0, A_BALL * se], atol=1e-9)
    assert np.allclose(ctx["hand"]["velocity_m_s"], [0, 0, 0.5 * (A_FINGER + A_THUMB) * se], atol=1e-9)
    p_e = np.array([0.0, 0.0, 1.5 + 0.5 * A_BALL * se ** 2])
    g = rule_config["gravity_m_s2"]
    for horizon, target in frozen["arm"]["targets"].items():
        tau = target["native_time_s"] - 2.0
        preds = ctx["predictions_m"][horizon]
        v_ball, v_hand = A_BALL * se, 0.5 * (A_FINGER + A_THUMB) * se
        assert np.allclose(preds["ball_endpoint_velocity"], p_e + [0, 0, v_ball * tau], atol=1e-9)
        assert np.allclose(preds["ball_endpoint_ballistic"], p_e + [0, 0, v_ball * tau - 0.5 * g * tau ** 2], atol=1e-9)
        assert np.allclose(preds["hand_endpoint_velocity"], p_e + [0, 0, v_hand * tau], atol=1e-9)
        assert np.allclose(preds["hand_endpoint_ballistic"], p_e + [0, 0, v_hand * tau - 0.5 * g * tau ** 2], atol=1e-9)


def test_a_contact_keypoint_failing_admission_is_recorded_and_excluded(config, task_configs):
    event_config, rule_config = task_configs
    t_ms, ball, player = diverging()
    frozen = study.freeze_row(t_ms, ball, player, NAMES, HZ, event_config, rule_config)
    e = int(np.flatnonzero(t_ms == round(frozen["event_time_s"] * 1000))[0])
    player[e - 8:e - 4, 1] = np.nan  # the thumb loses 4 prefix samples: a gap beyond 1.6 frames
    gapped = study.freeze_row(t_ms, ball, player, NAMES, HZ, event_config, rule_config)
    assert gapped["context"]["hand"]["rejected"] == {"RIGHT_THUMB_DISTAL": "history_gap"}
    se = gapped["event_time_s"] - 1.0
    assert np.allclose(gapped["context"]["hand"]["velocity_m_s"], [0, 0, A_FINGER * se], atol=1e-9)
    t_ms, ball, player = diverging()
    player[: e - 1, :2] = np.nan  # finger and thumb first seen one sample before the event: 2 prefix samples each
    lone = study.freeze_row(t_ms, ball, player, NAMES, HZ, event_config, rule_config)
    assert lone["event_time_s"] == frozen["event_time_s"] and lone["arm"]["prefix"] == "eligible"
    assert lone["context"]["hand"] == {"status": "no_admitted_contact_keypoint", "admitted": {}, "velocity_m_s": None,
                                       "rejected": {"RIGHT_SECOND_FINGER_DISTAL": "insufficient_history",
                                                    "RIGHT_THUMB_DISTAL": "insufficient_history"}}
    assert all(set(p) == set(study.BALL) for p in lone["context"]["predictions_m"].values())


def test_support_audit_classifies_visibility_driven_and_unsupported_transitions(config, task_configs):
    event_config, _ = task_configs
    boundary = event_config["contact_boundary_radii"] * study.event20.ball_radius_m(event_config)
    ball = np.column_stack((np.zeros(4), np.zeros(4), np.linspace(1.0, 1.1, 4)))
    player = np.full((4, 2, 3), np.nan)
    player[:, 0] = ball - [0, 0, 0.10]  # finger in contact throughout...
    player[:, 1] = ball - [0, 0, 0.30]  # ...wrist never in contact
    player[3, 0] = np.nan  # PREP-VIS-01: only the finger disappears at the "event"
    names = ["RIGHT_SECOND_FINGER_DISTAL", "RIGHT_WRIST"]
    audit = study.support_audit(ball, player, names, [0, 1], 3, boundary)
    assert audit["status"] == "visibility_ambiguous" and audit["nearest_previous_missing_at_event"]
    assert audit["common_support"] == ["RIGHT_WRIST"] and audit["contact_keypoints"] == ["RIGHT_SECOND_FINGER_DISTAL"]
    swapped = player.copy()
    swapped[3, 0] = np.nan
    swapped[2, 1] = np.nan
    swapped[3, 1] = ball[3] - [0, 0, 0.30]
    assert study.support_audit(ball, swapped, names, [0, 1], 3, boundary)["status"] == "no_common_support"
    moving = player.copy()
    moving[3, 0] = ball[3] - [0, 0, 0.30]  # the finger is still seen, and has really moved away
    assert study.support_audit(ball, moving, names, [0, 1], 3, boundary)["status"] == "stable"


def test_context_predictions_ignore_everything_after_the_event(config, task_configs):
    event_config, rule_config = task_configs
    t_ms, ball, player = diverging()
    frozen = study.freeze_row(t_ms, ball, player, NAMES, HZ, event_config, rule_config)
    e = int(np.flatnonzero(t_ms == round(frozen["event_time_s"] * 1000))[0])
    moved_ball, moved_player = ball.copy(), player.copy()
    moved_ball[e + 1:] += 5.0
    moved_player[e + 1:] -= 5.0
    moved = study.freeze_row(t_ms, moved_ball, moved_player, NAMES, HZ, event_config, rule_config)
    assert moved == frozen
    scores = study.score_row(frozen, lambda _h, i: ball[i])
    moved_scores = study.score_row(moved, lambda _h, i: moved_ball[i])
    assert scores != moved_scores, "control did not move the references"


def _decision_summary(key_common, key_stable, control):
    def view(key_labels, control_labels):
        return {"consistency": {"0.2": {
            "hand_endpoint_ballistic_minus_ball_endpoint_ballistic": {"labels_by_group": key_labels, "consistency": study.event21.consistency(key_labels)},
            "ball_endpoint_ballistic_minus_velocity": {"labels_by_group": control_labels, "consistency": study.event21.consistency(control_labels)}}}}
    return {"common": view(key_common, control), "support_stable": view(key_stable, control)}


@pytest.mark.parametrize("key_common, key_stable, control, expected", [
    ({"a": "a_lower", "b": "a_lower"}, {"a": "a_lower", "b": "a_lower"}, {"a": "b_lower", "b": "b_lower"}, "hand_context_adds_information"),
    ({"a": "a_lower", "b": "a_lower"}, {"a": "a_lower", "b": "not_separated"}, {"a": "a_lower", "b": "a_lower"}, "ball_endpoint_suffices"),
    ({"a": "b_lower", "b": "b_lower"}, {"a": "b_lower", "b": "b_lower"}, {"a": "b_lower", "b": "b_lower"}, "mixed"),
    ({"a": "b_lower", "b": "b_lower"}, {"a": "undefined", "b": "undefined"}, {"a": "a_lower", "b": "undefined"}, "mixed"),
])
def test_decision_rule(key_common, key_stable, control, expected):
    assert study.decide(_decision_summary(key_common, key_stable, control))["label"] == expected


def _rows(config, task_configs):
    event_config, rule_config = task_configs
    rows = []
    t_ms, ball, player = diverging()
    frozen = study.freeze_row(t_ms, ball, player, NAMES, HZ, event_config, rule_config)
    rows.append({"path": "p0", "session": "2025-12-18", "participant": "P0001", "frozen": frozen,
                 "scores": study.score_row(frozen, lambda _h, i: ball[i])})
    t2, b2, p2, n2, _, _ = shot(far=True)
    far = study.freeze_row(t2, b2, p2, list(n2), HZ, event_config, rule_config)
    rows.append({"path": "p1", "session": "2025-12-18", "participant": "P0002", "frozen": far, "scores": study.score_row(far, lambda _h, i: b2[i])})
    return rows


def test_summary_and_cohort_account_for_every_trial_and_keep_empty_cells_null(config, task_configs):
    rows = _rows(config, task_configs)
    ambiguous = json.loads(json.dumps(rows[0]))
    ambiguous.update(path="p2", participant="P0003")
    ambiguous["frozen"]["context"]["support"]["status"] = "visibility_ambiguous"
    summary = study.summarize(rows + [ambiguous], config)
    assert summary["common"]["horizons"]["0.2"]["all"]["n"] == 2 and summary["support_stable"]["horizons"]["0.2"]["all"]["n"] == 1
    assert summary["coverage"]["2025-12-18/P0003"]["support"] == {"visibility_ambiguous": 1}
    summary = study.summarize(rows, config)
    assert summary["common"]["horizons"]["0.2"]["all"]["n"] == 1 and summary["support_stable"]["horizons"]["0.2"]["all"]["n"] == 1
    empty = summary["common"]["horizons"]["0.2"]["2025-12-18/P0003"]
    assert empty["n"] == 0 and empty["errors_m"]["hand_endpoint_ballistic"]["mean"] is None
    assert empty["signed_vertical_m"]["velocity"]["fraction_below"] is None
    assert summary["decision"]["label"] == "mixed"  # empty groups can never make a consistent label
    cohort = study.cohort_accounting(rows, config)
    assert cohort["0.2"] == {"expected_count": 2, "accepted_count": 1, "rejected_count": 1,
                             "rejection_reasons": {"no_contact": 1}, "status": "complete"}
    del rows[0]["scores"]["0.2"]
    with pytest.raises(ValueError, match="score_availability_mismatch"):
        study.cohort_accounting(rows, config)


def test_event21_reproduction_refuses_any_difference(config, task_configs):
    rows = _rows(config, task_configs)
    frozen = [{"path": r["path"], "frozen": {"arms": {"event": json.loads(json.dumps(r["frozen"]["arm"]))}}} for r in rows]
    manifest = {"results": [{"path": r["path"], "scores": {"event": {h: {"errors_m": {c: s["errors_m"][c] for c in study.BASE}}
                                                                    for h, s in r["scores"].items()}}} for r in rows]}
    assert study.check_event21_reproduction(rows, frozen, manifest) == 3 * 3
    edited = json.loads(json.dumps(manifest))
    edited["results"][0]["scores"]["event"]["0.1"]["errors_m"]["velocity"] += 1e-12
    with pytest.raises(ValueError, match="event21_errors_not_reproduced"):
        study.check_event21_reproduction(rows, frozen, edited)
    arm = json.loads(json.dumps(frozen))
    arm[0]["frozen"]["arms"]["event"]["fits"]["rmse_line_m"] += 1.0
    with pytest.raises(ValueError, match="event21_frozen_arm_not_reproduced"):
        study.check_event21_reproduction(rows, arm, manifest)
    dropped = json.loads(json.dumps(manifest))
    del dropped["results"][0]["scores"]["event"]["0.05"]
    with pytest.raises(ValueError, match="event21_scored_horizons_not_reproduced"):
        study.check_event21_reproduction(rows, frozen, dropped)
    with pytest.raises(ValueError, match="event21_row_missing"):
        study.check_event21_reproduction(rows, frozen[1:], manifest)


def _fake_run(tmp_path, config, task_configs, monkeypatch):
    event_config, rule_config = task_configs
    data = tmp_path / "data"
    t_ms, ball, player, names, _, _ = shot()
    rows = [_write_trial(data, "2025-12-18", "P0001", "T0001", t_ms, ball, player, names),
            _write_trial(data, "2025-12-18", "P0002", "T0001", t_ms + 5000, ball + 0.01, player + 0.01, names)]
    rows.append({"path": "basketball/freethrow/data/2025-12-18/P0004/BB_FT_P0004_T0001.json",
                 "sha256": "f" * 64, "participant": "P0004", "session": "2025-12-18"})
    inventory = tmp_path / "inventory.json"
    inventory.write_text(json.dumps({"source_revision": config["data_revision"], "per_trial": rows}), encoding="utf-8")
    monkeypatch.setattr(study.event20, "subprocess", SimpleNamespace(
        check_output=lambda *a, **k: config["data_revision"] + "\n"))
    cfg = dict(config, expected_trials=2, inventory_sha256=hashlib.sha256(inventory.read_bytes()).hexdigest())
    built, inputs = study.build_rows(study.event20.admitted_rows(inventory, data, cfg), data.resolve(), cfg, event_config, rule_config, [])
    frozen = [{"path": r["path"], "frozen": {"arms": {"event": r["frozen"]["arm"]}}} for r in built]
    manifest = {"results": [{"path": r["path"], "scores": {"event": {
        h: {"errors_m": {c: s["errors_m"][c] for c in study.BASE}}
        for h, s in study.score_row(r["frozen"], lambda _h, i, b=inputs[r["path"]][1]: b[i]).items()}}} for r in built]}
    reproduction = dict(cfg["event21_reproduction"])
    for key, payload in (("manifest", manifest), ("frozen_predictions", frozen)):
        raw = (json.dumps(payload) + "\n").encode("utf-8")
        path = tmp_path / f"event21_{key}.json.gz"
        path.write_bytes(gzip.compress(raw, mtime=0))
        reproduction[key] = {"path": str(path), "original_sha256": hashlib.sha256(raw).hexdigest()}
    cfg["event21_reproduction"] = reproduction
    output = tmp_path / "run"
    output.mkdir()
    args = type("Args", (), {"data_root": data, "inventory": inventory, "config_sha256": "x", "output": output})()
    return args, cfg, rows


def test_fake_revision_does_not_change_unrelated_subprocess_output(tmp_path, config, task_configs, monkeypatch):
    import subprocess

    _fake_run(tmp_path, config, task_configs, monkeypatch)
    output = subprocess.check_output([sys.executable, "-c", "print('unrelated-process')"])
    assert output.strip() == b"unrelated-process"


def test_run_freezes_before_scoring_reproduces_event21_and_never_opens_protected_rows(tmp_path, config, task_configs, monkeypatch):
    args, cfg, rows = _fake_run(tmp_path, config, task_configs, monkeypatch)
    seen, original = [], study.score_row

    def spy(frozen, reference_for):
        seen.append((args.output / "frozen_predictions.json").is_file())
        return original(frozen, reference_for)

    monkeypatch.setattr(study, "score_row", spy)
    report = {}
    study.run(args, report, cfg)
    assert report["status"] == study.STATUS and report["trials"] == 2 and seen == [True, True]
    assert report["opened"] == [rows[0]["path"], rows[1]["path"]]
    assert report["reproduced"] == {"event21_candidate_errors": 2 * 3 * 3}
    assert report["frozen_predictions_sha256"] == hashlib.sha256((args.output / "frozen_predictions.json").read_bytes()).hexdigest()
    assert (args.output / "examples.png").stat().st_size > 0
    with pytest.raises(ValueError, match="event21_evidence_mismatch"):
        study.run(args, {}, dict(cfg, event21_reproduction=dict(cfg["event21_reproduction"],
                                                                 manifest=dict(cfg["event21_reproduction"]["manifest"], original_sha256="0" * 64))))
    p5 = dict(rows[0], path="basketball/freethrow/data/2025-12-18/P0005/BB_FT_P0005_T0001.json", participant="P0005", sha256="e" * 64)
    args.inventory.write_text(json.dumps({"source_revision": config["data_revision"], "per_trial": rows + [p5]}), encoding="utf-8")
    with pytest.raises(ValueError, match="development_only_path_required"):
        study.run(args, {}, dict(cfg, inventory_sha256=hashlib.sha256(args.inventory.read_bytes()).hexdigest()))


def test_frozen_predictions_changed_during_scoring_block_the_run(tmp_path, config, task_configs, monkeypatch):
    args, cfg, _ = _fake_run(tmp_path, config, task_configs, monkeypatch)
    original = study.score_row

    def tamper(frozen, reference_for):
        (args.output / "frozen_predictions.json").write_bytes(b"[]\n")
        return original(frozen, reference_for)

    monkeypatch.setattr(study, "score_row", tamper)
    with pytest.raises(ValueError, match="frozen_predictions_changed_during_scoring"):
        study.run(args, {}, cfg)


def _reseal(retained, name, payload):
    raw = (json.dumps(payload, indent=1) + "\n").encode("utf-8")
    gz = gzip.compress(raw, mtime=0)
    (retained / f"{name}.gz").write_bytes(gz)
    policy = json.loads((retained / "RETENTION.json").read_text(encoding="utf-8"))
    policy["files"][name].update(original_sha256=hashlib.sha256(raw).hexdigest(), retained_sha256=hashlib.sha256(gz).hexdigest())
    (retained / "RETENTION.json").write_text(json.dumps(policy), encoding="utf-8")
    return hashlib.sha256(raw).hexdigest()


def test_retained_bundle_rescores_rederives_and_catches_edits(tmp_path, config, task_configs, monkeypatch):
    args, cfg, _ = _fake_run(tmp_path, config, task_configs, monkeypatch)
    report = {}
    study.run(args, report, cfg)
    (args.output / "run_manifest.json").write_bytes((json.dumps(report, indent=1) + "\n").encode("utf-8"))
    original = json.loads((args.output / "run_manifest.json").read_text(encoding="utf-8"))
    retained = tmp_path / "bundle"
    study.retain(args.output, retained)
    assert study.verify_retained(retained, cfg) == []
    assert study.verify_retained(retained, cfg, args.data_root, args.inventory) == []
    assert study.verify_retained(retained, dict(cfg, bootstrap_seed=1)) == ["config_mismatch"]
    path = original["results"][0]["path"]
    edited = json.loads(json.dumps(original))
    edited["results"][0]["scores"]["0.2"]["reference_m"][2] += 0.5
    _reseal(retained, "run_manifest.json", edited)
    assert f"score_not_recomputable:{path}:0.2" in study.verify_retained(retained, cfg)
    deleted = json.loads(json.dumps(original))
    del deleted["results"][1]["scores"]["0.1"]
    _reseal(retained, "run_manifest.json", deleted)
    assert study.verify_retained(retained, cfg) == [f"score_missing:{original['results'][1]['path']}:0.1"]
    invented = json.loads(json.dumps(original))
    invented["results"][0]["scores"]["0.3"] = invented["results"][0]["scores"]["0.2"]
    _reseal(retained, "run_manifest.json", invented)
    assert study.verify_retained(retained, cfg) == [f"score_without_available_target:{path}:0.3"]
    stale = json.loads(json.dumps(original))
    stale["frozen_predictions_sha256"] = "0" * 64
    _reseal(retained, "run_manifest.json", stale)
    assert study.verify_retained(retained, cfg) == ["frozen_predictions_not_the_scored_freeze"]
    frozen = json.loads(gzip.decompress((retained / "frozen_predictions.json.gz").read_bytes()))
    frozen[0]["frozen"]["context"]["support"]["common_distance_event_m"] += 1.0  # not used for scoring
    resealed = json.loads(json.dumps(original))
    resealed["frozen_predictions_sha256"] = _reseal(retained, "frozen_predictions.json", frozen)
    _reseal(retained, "run_manifest.json", resealed)
    assert study.verify_retained(retained, cfg) == []
    assert study.verify_retained(retained, cfg, args.data_root, args.inventory) == ["frozen_not_rederivable:" + path]
