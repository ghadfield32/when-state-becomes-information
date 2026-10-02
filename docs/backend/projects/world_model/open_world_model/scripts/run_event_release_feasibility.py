"""OW-EVENT-20: a causal, body-referenced release event instead of the fixed 2.0 s cutoff (feasibility).

Development participants only (P0001-P0003); P0004 and P0005 are never opened. The release event is
the first native sample at which the ball leaves contact with the hand (nearest finite hand keypoint
beyond one ball diameter of the ball centre, immediately after a contact sample) while ascending over
the trailing 200 ms. Only samples at or before the event are used. The time axis is then shifted so
the event lands on the baseline cutoff, and OW-REGIME-17's reviewed diagnostics describe the prefix and
the observed post-event interval. Everything after the event is a noncausal DIAGNOSTIC of that
interval, never a label or model input. No forecasting comparison is made here.
"""
from __future__ import annotations

import argparse
from collections import Counter
import gzip
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys

import numpy as np

LAB = Path(__file__).resolve().parents[1]
REPO = LAB.parents[4]
sys.path.insert(0, str(LAB / "src"))
sys.path.insert(0, str(LAB / "scripts"))
from wms.data.mlse_spl import load_spl_free_throw  # noqa: E402
import run_prefix_forecast as baseline  # noqa: E402
import run_regime_feasibility as regime17  # noqa: E402

CONFIG = LAB / "configs/experiments/event_release_feasibility_v1.json"
STATUS = "COMPLETE_DEVELOPMENT_EVENT_RELEASE_FEASIBILITY"
QUANTILES = (0.05, 0.25, 0.5, 0.75, 0.95)
HAND_PARTS = ("WRIST", "THUMB", "PINKY", "FINGER")
EXCLUSIONS = ("time_gap", "descending", "direction_unknown")
TRIAL_NUMERIC = ("first_contact_time_s", "excluded_transitions")
EVENT_NUMERIC = ("event_time_s", "event_minus_fixed_cutoff_s", "hand_distance_at_event_m",
                 "event_shift_at_1_5r_s", "event_shift_at_3r_s", "separation_growth_100ms_m") + regime17.NUMERIC
COMPARED = ("quadratic_vertical_acceleration_m_s2", "gravity_over_constant_velocity_rmse", "rmse_gravity_m",
            "rmse_constant_velocity_m", "release_like_time_minus_cutoff_s")
EXAMPLE_WINDOW_S = 0.6


def default_config():
    return json.loads(CONFIG.read_text(encoding="utf-8"))


def check_frozen(path, sha):
    if baseline.digest(Path(path)) != sha or json.loads(Path(path).read_text(encoding="utf-8")) != default_config():
        raise ValueError("frozen_config_mismatch")


def ball_radius_m(config):
    return config["ball_circumference_in"] / (2.0 * math.pi) * 0.0254


def hand_indices(names):
    return [i for i, n in enumerate(names) if n.startswith(("LEFT_", "RIGHT_")) and any(p in n for p in HAND_PARTS)]


def ball_hand_distance(ball, player, idx):
    """Min distance from the ball centre to any finite hand keypoint; NaN unless the sample is evaluable."""
    distance = np.full(len(ball), np.nan)
    if not idx:
        return distance
    per_keypoint = np.linalg.norm(player[:, idx, :] - ball[:, None, :], axis=2)
    evaluable = np.isfinite(ball).all(axis=1) & np.isfinite(per_keypoint).any(axis=1)
    distance[evaluable] = np.nanmin(per_keypoint[evaluable], axis=1)
    return distance


def ascending(times_ms, ball, i, history_ms, axis):
    """Sign of the OLS vertical velocity over finite ball samples in [t_i - history, t_i]; None if < 3 samples."""
    window = (times_ms >= times_ms[i] - history_ms) & (times_ms <= times_ms[i]) & np.isfinite(ball).all(axis=1)
    if window.sum() < 3:
        return None
    return bool(np.polyfit((times_ms[window] - times_ms[i]) / 1000.0, ball[window, axis], 1)[0] > 0)


def detect_release(times_ms, ball, distance, hz, boundary, history_ms, axis):
    """First qualifying contact->beyond-boundary transition; reads only samples at or before it.

    Integer-millisecond time keeps the sample exactly history_ms before t_i inside the window by rule,
    not by floating-point round-off.
    """
    previous, first_contact, excluded = None, None, Counter()
    for i in np.flatnonzero(np.isfinite(distance)):
        if distance[i] <= boundary and first_contact is None:
            first_contact = int(i)
        if previous is not None and distance[previous] <= boundary < distance[i]:
            direction = ascending(times_ms, ball, i, history_ms, axis)
            if times_ms[i] - times_ms[previous] > 1600.0 / hz:
                excluded["time_gap"] += 1
            elif direction is None:
                excluded["direction_unknown"] += 1
            elif not direction:
                excluded["descending"] += 1
            else:
                return {"event_index": int(i), "reason": "event", "first_contact_index": first_contact, "excluded": excluded}
        previous = i
    return {"event_index": None, "reason": "no_contact" if first_contact is None else "no_ascending_release",
            "first_contact_index": first_contact, "excluded": excluded}


def history_ms(config):
    ms = config["history_s"] * 1000.0
    if ms != round(ms):
        raise ValueError("history_not_whole_milliseconds")
    return int(round(ms))


def trial_record(times_ms, ball, player, names, frames, hz, config, regime17_config):
    r = ball_radius_m(config)
    axis, history = config["vertical_axis_index"], history_ms(config)
    idx = hand_indices(names)
    distance = ball_hand_distance(ball, player, idx)
    out = {name: None for name in TRIAL_NUMERIC + EVENT_NUMERIC}  # missing stays missing (JSON null), never 0
    out.update(hand_keypoints_named=len(idx),
               hand_keypoints_ever_finite=int(np.isfinite(player[:, idx, :]).all(axis=2).any(axis=0).sum()),
               evaluable_samples=int(np.isfinite(distance).sum()))
    event = detect_release(times_ms, ball, distance, hz, config["contact_boundary_radii"] * r, history, axis)
    out.update(event=event["reason"], excluded_by_reason={k: event["excluded"][k] for k in EXCLUSIONS},
               excluded_transitions=float(sum(event["excluded"].values())))
    if event["first_contact_index"] is not None:
        out["first_contact_time_s"] = times_ms[event["first_contact_index"]] / 1000.0
    if event["event_index"] is None:
        out.update(prefix=None, targets={}, future_fits=None, release_heuristic=None)
        return out
    i = event["event_index"]
    te = int(times_ms[i])
    out.update(event_time_s=te / 1000.0, event_minus_fixed_cutoff_s=te / 1000.0 - baseline.CUTOFF,
               hand_distance_at_event_m=float(distance[i]))
    for key, radii in zip(("event_shift_at_1_5r_s", "event_shift_at_3r_s"), config["sensitivity_boundary_radii"]):
        other = detect_release(times_ms, ball, distance, hz, radii * r, history, axis)["event_index"]
        out[key] = None if other is None else (int(times_ms[other]) - te) / 1000.0
    later = np.flatnonzero((times_ms >= te + 100) & np.isfinite(distance))
    if len(later):
        out["separation_growth_100ms_m"] = float(distance[later[0]] - distance[i])
    shifted = (times_ms - te) / 1000.0 + baseline.CUTOFF  # the event sample lands exactly on the baseline cutoff
    diagnostics = regime17.trial_diagnostics(shifted, ball, frames, hz, regime17_config)
    out.update({key: diagnostics[key] for key in regime17.NUMERIC})
    out.update(prefix=diagnostics["prefix"], targets=diagnostics["targets"], future_fits=diagnostics["future_fits"],
               release_heuristic=diagnostics["release_heuristic"])
    return out


def _stats(values):
    finite = np.asarray([np.nan if v is None else v for v in values], dtype=float)
    finite = finite[np.isfinite(finite)]
    return {"n_finite": int(finite.size), "n_missing": int(len(values) - finite.size),
            "quantiles": dict(zip([str(q) for q in QUANTILES], np.quantile(finite, QUANTILES).tolist())) if finite.size else None}


def summarize(rows):
    groups = {"all": rows}
    for row in rows:
        groups.setdefault(f"{row['session']}/{row['participant']}", []).append(row)
    summary = {}
    for name, items in groups.items():
        events = [row for row in items if row["event"] == "event"]
        summary[name] = {
            "trials": len(items), "event": dict(Counter(row["event"] for row in items)),
            "excluded_by_reason": {k: sum(row["excluded_by_reason"][k] for row in items) for k in EXCLUSIONS},
            "post_event_prefix": dict(Counter(row["prefix"] for row in events)),
            "post_event_future_fits": dict(Counter(row["future_fits"] for row in events)),
            "post_event_release_heuristic": dict(Counter(row["release_heuristic"] for row in events)),
            "post_event_targets": {h: dict(Counter(row["targets"][h] for row in events if h in row["targets"]))
                                   for h in sorted({h for row in events for h in row["targets"]})},
            "all_trials": {key: _stats([row[key] for row in items]) for key in TRIAL_NUMERIC},
            "events": {key: _stats([row[key] for row in events]) for key in EVENT_NUMERIC},
            "post_event_prefix_eligible": {key: _stats([row[key] for row in events if row["prefix"] == "eligible"])
                                           for key in COMPARED},
        }
    return summary


def fixed_cutoff_reference(path, config):
    raw = gzip.decompress(Path(path).read_bytes())
    if hashlib.sha256(raw).hexdigest() != config["regime17_retained_manifest"]["original_sha256"]:
        raise ValueError("regime17_evidence_mismatch")
    summary = json.loads(raw)["summary"]
    return {group: {"future_fits": entry["future_fits"], "release_heuristic": entry["release_heuristic"],
                    **{subset: {key: entry[subset][key] for key in COMPARED} for subset in ("all_trials", "prefix_eligible")}}
            for group, entry in summary.items()}


def load_inputs(path, participant):
    """Ball input identical to OW-REGIME-17 plus hand keypoints from the lab loader, cross-checked."""
    trial, _, ball, frames = regime17.load_trial(path)
    stamps = np.asarray([row["time"] for row in trial["tracking"]], dtype=float)
    if not np.all(stamps == np.round(stamps)):
        raise ValueError("non_millisecond_time_axis:" + str(path))
    times_ms = (stamps - stamps[0]).astype(np.int64)
    spl = load_spl_free_throw(path)
    if trial["participant_id"] != participant or spl.participant_id != participant:
        raise ValueError("participant_identity_mismatch")
    if not np.array_equal(spl.ball_xyz_m, ball, equal_nan=True) or not np.array_equal(spl.frame_index, frames):
        raise ValueError("loader_ball_disagreement:" + str(path))
    return times_ms, ball, spl.player_xyz_m, spl.keypoint_names, frames, float(trial["sampling_rate"])


def select_examples(rows, inputs, config):
    examples = []
    r = ball_radius_m(config)
    for group in sorted({(row["session"], row["participant"]) for row in rows}):
        chosen = sorted((row for row in rows if (row["session"], row["participant"]) == group and row["event"] == "event"),
                        key=lambda row: (row["event_time_s"], row["path"]))
        if not chosen:
            continue
        row = chosen[(len(chosen) - 1) // 2]
        times_ms, ball, player, names = inputs[row["path"]]
        distance = ball_hand_distance(ball, player, hand_indices(names))
        since_event = (times_ms - round(row["event_time_s"] * 1000)) / 1000.0
        window = np.abs(since_event) <= EXAMPLE_WINDOW_S
        examples.append({"path": row["path"], "session": group[0], "participant": group[1],
                         "event_time_s": row["event_time_s"], "future_fits": row["future_fits"],
                         "quadratic_vertical_acceleration_m_s2": row["quadratic_vertical_acceleration_m_s2"],
                         "time_since_event_s": since_event[window].tolist(),
                         "ball_hand_distance_m": [None if not np.isfinite(v) else float(v) for v in distance[window]],
                         "ball_z_m": [None if not np.isfinite(v) else float(v) for v in ball[window, config["vertical_axis_index"]]],
                         "boundaries_m": {"contact": config["contact_boundary_radii"] * r,
                                          "sensitivity": [k * r for k in config["sensitivity_boundary_radii"]]}})
    return examples


def plot_examples(examples, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(len(examples), 1, figsize=(8, 2.6 * len(examples)), squeeze=False)
    for ax, ex in zip(axes[:, 0], examples):
        t = np.asarray(ex["time_since_event_s"], dtype=float)
        d = np.asarray([np.nan if v is None else v for v in ex["ball_hand_distance_m"]], dtype=float)
        z = np.asarray([np.nan if v is None else v for v in ex["ball_z_m"]], dtype=float)
        ax.plot(t, d, "k.-", ms=3, lw=0.6, label="min ball-hand distance (m)")
        ax.plot(t, z, ".", color="C1", ms=3, label="ball height (m)")
        ax.axhline(ex["boundaries_m"]["contact"], color="C3", lw=0.8, label="contact boundary (2r)")
        for b in ex["boundaries_m"]["sensitivity"]:
            ax.axhline(b, color="C3", lw=0.5, ls=":")
        ax.axvline(0.0, color="k", lw=0.6)
        ax.axvline(baseline.CUTOFF - ex["event_time_s"], color="C0", lw=0.8, ls="--", label="fixed 2.0 s cutoff")
        accel = ex["quadratic_vertical_acceleration_m_s2"]
        ax.set_title(f"{ex['session']}/{ex['participant']} | {ex['path'].rsplit('/', 1)[-1]} | event at {ex['event_time_s']:.3f} s | "
                     f"post-event quadratic a_z {'n/a' if accel is None else f'{accel:.1f}'} m/s^2", fontsize=7)
        ax.set_ylim(0, 4)
        ax.tick_params(labelsize=6)
    axes[0, 0].legend(fontsize=6, loc="upper left")
    axes[-1, 0].set_xlabel("time since detected release event (s); dotted = 1.5r and 3r sensitivity boundaries", fontsize=7)
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


def admitted_rows(inventory_path, data_root, config):
    if baseline.digest(Path(inventory_path)) != config["inventory_sha256"]:
        raise ValueError("inventory_hash_mismatch")
    inventory = json.loads(Path(inventory_path).read_bytes())
    if inventory.get("source_revision") != config["data_revision"]:
        raise ValueError("wrong_inventory_revision")
    revision = subprocess.check_output(["git", "-C", str(data_root), "rev-parse", "HEAD"], text=True).strip()
    if revision != config["data_revision"]:
        raise ValueError("wrong_data_revision")
    rows = [r for r in baseline.validate_inventory(inventory) if r["participant"] in config["participants"]]
    if len(rows) != config["expected_trials"]:
        raise ValueError("expected_trial_count_mismatch")
    return rows


def open_admitted(root, row, config, opened):
    path = (root / row["path"]).resolve()
    if not path.is_relative_to(root) or row["participant"] not in config["participants"]:
        raise ValueError("input_outside_admitted_participants")
    opened.append(row["path"])  # recorded before any read of the trial
    if baseline.digest(path) != row["sha256"]:
        raise ValueError("input_hash_mismatch:" + row["path"])
    return load_inputs(path, row["participant"])


def load_regime17_config(config):
    path = LAB / config["regime17_config"]["path"]
    if baseline.digest(path) != config["regime17_config"]["sha256"]:
        raise ValueError("regime17_config_changed")
    return json.loads(path.read_text(encoding="utf-8"))


def run(args, report, config):
    regime17_config = load_regime17_config(config)
    sources = [Path(__file__).resolve(), CONFIG, LAB / config["regime17_config"]["path"], Path(baseline.__file__).resolve(),
               Path(regime17.__file__).resolve(), LAB / "src/wms/data/mlse_spl.py", LAB / "src/wms/physics/free_throw.py",
               LAB / "tests/test_event_release_feasibility.py", LAB / "uv.lock", LAB / "pyproject.toml"]
    source_sha = {str(p.relative_to(LAB)): baseline.digest(p) for p in sources}
    report.update(config=config, config_sha256=args.config_sha256, source_sha256=source_sha, numpy=np.__version__,
                  python=sys.version, ball_radius_m=ball_radius_m(config))
    reference = fixed_cutoff_reference(args.regime17_manifest, config)
    rows_in = admitted_rows(args.inventory, args.data_root, config)
    root = args.data_root.resolve()
    results, inputs, opened = [], {}, []
    report.update(opened=opened)
    for row in rows_in:
        times_ms, ball, player, names, frames, hz = open_admitted(root, row, config, opened)
        inputs[row["path"]] = (times_ms, ball, player, names)
        results.append({"path": row["path"], "session": row["session"], "participant": row["participant"], "hz": hz,
                        **trial_record(times_ms, ball, player, names, frames, hz, config, regime17_config)})
    if any(baseline.digest(root / r["path"]) != r["sha256"] for r in rows_in):
        raise ValueError("input_changed_during_run")
    if source_sha != {str(p.relative_to(LAB)): baseline.digest(p) for p in sources}:
        raise ValueError("source_changed_during_run")
    if any(f"/{pid}/" in p for p in opened for pid in config["not_opened"]):
        raise ValueError("protected_participant_opened")
    examples = select_examples(results, inputs, config)
    plot_examples(examples, args.output / "examples.png")
    report.update(status=STATUS, trials=len(results), results=results, summary=summarize(results),
                  fixed_cutoff_reference=reference, examples=examples, protected_participants_opened=False,
                  input_and_source_unchanged=True,
                  limitation="Development participants only (P0001-P0003); supplied, possibly processed ball and pose "
                             "tracks. The event is a body-referenced detector, not release ground truth. Post-event fits "
                             "are noncausal diagnostics of the observed interval; no forecast comparison is made. P0004 "
                             "not consulted; P0005 locked.")


RETAINED = ("run_manifest.json",)


def retain(run_dir, retained_dir):
    """Retain the run byte-exact: JSON gzip-compressed (mtime 0), the example figure as-is."""
    run_dir, retained_dir = Path(run_dir), Path(retained_dir)
    retained_dir.mkdir(parents=True, exist_ok=False)
    files = {}
    for name in RETAINED:
        raw = (run_dir / name).read_bytes()
        gz = gzip.compress(raw, mtime=0)
        (retained_dir / f"{name}.gz").write_bytes(gz)
        files[name] = {"retained_file": f"{name}.gz", "original_sha256": hashlib.sha256(raw).hexdigest(),
                       "retained_sha256": hashlib.sha256(gz).hexdigest(), "original_bytes": len(raw)}
    png = (run_dir / "examples.png").read_bytes()
    (retained_dir / "examples.png").write_bytes(png)
    files["examples.png"] = {"retained_file": "examples.png", "original_sha256": hashlib.sha256(png).hexdigest()}
    (retained_dir / "RETENTION.json").write_bytes((json.dumps({"packet": "OW-EVENT-20", "policy": "exact_bytes_gzip",
                                                               "files": files}, indent=2) + "\n").encode("utf-8"))


def verify_retained(retained_dir, config, data_root=None, inventory=None):
    """Digests, frozen-config replay, the summary rebuilt from the rows, and (with data) every row re-derived."""
    retained_dir = Path(retained_dir)
    policy = json.loads((retained_dir / "RETENTION.json").read_text(encoding="utf-8"))
    raw = {}
    for name, entry in policy["files"].items():
        path = retained_dir / entry["retained_file"]
        if not path.is_file():
            return [f"missing:{name}"]
        data = path.read_bytes()
        if "retained_sha256" in entry and hashlib.sha256(data).hexdigest() != entry["retained_sha256"]:
            return [f"retained_digest_mismatch:{name}"]
        data = gzip.decompress(data) if entry["retained_file"].endswith(".gz") else data
        if hashlib.sha256(data).hexdigest() != entry["original_sha256"]:
            return [f"digest_mismatch:{name}"]
        raw[name] = data
    manifest = json.loads(raw["run_manifest.json"])
    if manifest.get("config") != config:
        return ["config_mismatch"]  # replay only the frozen rule the run executed
    failures = [] if summarize(manifest["results"]) == manifest["summary"] else ["summary_not_recomputable"]
    # The fixed-cutoff columns are a copy: replay them from REGIME-17's retained manifest (digest-checked).
    reference = fixed_cutoff_reference(REPO / config["regime17_retained_manifest"]["path"], config)
    if reference != manifest["fixed_cutoff_reference"]:
        failures.append("fixed_cutoff_reference_not_reproducible")
    if data_root is not None:
        regime17_config, opened, root = load_regime17_config(config), [], Path(data_root).resolve()
        stored = {r["path"]: r for r in manifest["results"]}
        rows_in = admitted_rows(inventory, data_root, config)
        if sorted(stored) != sorted(r["path"] for r in rows_in):
            failures.append("result_paths_differ_from_admitted_inventory")
        for row in rows_in:
            times_ms, ball, player, names, frames, hz = open_admitted(root, row, config, opened)
            rebuilt = {"path": row["path"], "session": row["session"], "participant": row["participant"], "hz": hz,
                       **trial_record(times_ms, ball, player, names, frames, hz, config, regime17_config)}
            if json.loads(json.dumps(rebuilt, allow_nan=False)) != stored.get(row["path"]):
                failures.append("row_not_rederivable:" + row["path"])
    return failures


def main():
    if len(sys.argv) >= 3 and sys.argv[1] == "verify-retained":
        parser = argparse.ArgumentParser(prog="verify-retained")
        parser.add_argument("retained_dir", type=Path)
        parser.add_argument("--data-root", type=Path)
        parser.add_argument("--inventory", type=Path)
        args = parser.parse_args(sys.argv[2:])
        if (args.data_root is None) != (args.inventory is None):
            parser.error("--data-root and --inventory go together")
        failures = verify_retained(args.retained_dir, default_config(), args.data_root, args.inventory)
        print(json.dumps({"status": "PASS" if not failures else "FAIL", "rows_rederived": args.data_root is not None,
                          "failures": failures}))
        return 0 if not failures else 1
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--regime17-manifest", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--config-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    baseline.validate_output(args.output, args.data_root, LAB)
    args.output.mkdir(parents=True, exist_ok=False)
    report, code = {"status": "BLOCKED", "command": sys.argv}, 0
    try:
        check_frozen(args.config, args.config_sha256)
        run(args, report, default_config())
    except Exception as exc:  # recorded in the manifest and returned as a non-zero exit
        report["status"], report["error"], code = "BLOCKED", f"{type(exc).__name__}: {exc}", 2
    manifest = args.output / "run_manifest.json"
    manifest.write_bytes((json.dumps(report, indent=1, allow_nan=False) + "\n").encode("utf-8"))
    (args.output / "SHA256.json").write_bytes((json.dumps({manifest.name: baseline.digest(manifest)}, indent=2) + "\n").encode("utf-8"))
    print(json.dumps({k: report.get(k) for k in ("status", "trials", "error")}))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
