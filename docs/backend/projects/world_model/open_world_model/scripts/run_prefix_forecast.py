"""Exploratory native ball-track continuation; never a release/free-flight claim.

Inputs are immutable SPL development observations in feet/milliseconds. State is
fit using only the fixed observation prefix. Future rows supply scoring targets
only. No learned model, interpolation, hyperparameter search or promotion.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess
import sys

import numpy as np

CUTOFF = 2.0
HISTORY = 0.2
HORIZONS = (0.05, 0.1, 0.2)
REVISION = "a3f9cffbde917b1e1747cedd6ec25dfab18c6051"
PARTICIPANTS = {"P0001", "P0002", "P0003", "P0004"}
PARAMETERS = {"cutoff_s": CUTOFF, "history_s": HISTORY,
              "horizons_s": HORIZONS, "minimum_samples": 3,
              "maximum_gap_frames": 1.6, "target": "first_native_at_or_after",
              "units": "metres_seconds", "candidates": ["persistence", "velocity"]}


def fit_prefix(t, xyz, hz):
    """Construct state from finite observations in [1.8, 2.0] seconds only."""
    t, xyz = np.asarray(t, dtype=float), np.asarray(xyz, dtype=float)
    if t.ndim != 1 or xyz.shape != (len(t), 3) or not np.isfinite(hz) or hz <= 0:
        raise ValueError("invalid_shape_or_rate")
    observed = np.isfinite(t) & (t >= CUTOFF - HISTORY) & (t <= CUTOFF)
    pt, px = t[observed], xyz[observed]
    if np.any(np.diff(pt) <= 0):
        raise ValueError("nonmonotone_prefix")
    valid = np.isfinite(px).all(axis=1)
    pt, px = pt[valid], px[valid]
    if len(pt) < 3:
        raise ValueError("insufficient_history")
    # Missing samples remain missing. No interpolation or stale-prefix fallback.
    if (np.any(np.diff(pt) > 1.6 / hz) or CUTOFF - pt[-1] > 1.6 / hz
            or pt[0] - (CUTOFF - HISTORY) > 1.6 / hz):
        raise ValueError("history_gap")
    design = np.column_stack((np.ones(len(pt)), pt - CUTOFF))
    coefficients = np.linalg.lstsq(design, px, rcond=None)[0]
    return {"position": px[-1].copy(), "intercept": coefficients[0], "velocity": coefficients[1]}


def predict(state, target_time, candidate):
    """Persistence holds the last observed position; velocity extrapolates OLS."""
    if candidate == "persistence":
        return state["position"].copy()
    if candidate == "velocity":
        return state["intercept"] + (target_time - CUTOFF) * state["velocity"]
    raise ValueError("unknown_candidate")


def target_index(t, xyz, hz, horizon):
    """Score an actual native reference; do not skip a missing first target."""
    desired = CUTOFF + horizon
    indices = np.flatnonzero(t >= desired)
    if not len(indices) or t[indices[0]] - desired > 1 / hz:
        raise ValueError("target_unavailable")
    j = int(indices[0])
    if not np.isfinite(xyz[j]).all():
        raise ValueError("target_missing")
    return j


def validate_inventory(inventory):
    rows = inventory.get("per_trial", [])
    if not rows:
        raise ValueError("empty_inventory")
    seen, hashes = set(), set()
    for row in rows:
        path = PurePosixPath(row["path"])
        parts = path.parts
        if (row.get("participant") not in PARTICIPANTS or len(parts) != 6
                or parts[:3] != ("basketball", "freethrow", "data")
                or parts[4] != row.get("participant") or ".." in parts):
            raise ValueError("development_only_path_required")
        if parts[3] != row.get("session") or path.suffix != ".json":
            raise ValueError("invalid_inventory_path")
        if row["path"] in seen:
            raise ValueError("duplicate_inventory_path")
        seen.add(row["path"])
        digest = row.get("sha256", "")
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise ValueError("invalid_input_digest")
        if digest in hashes:
            raise ValueError("duplicate_input_digest")
        hashes.add(digest)
    return rows


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def summarize(scores):
    summaries = []
    for split in ("development", "validation"):
        for horizon in HORIZONS:
            for candidate in PARAMETERS["candidates"]:
                chosen = [s for s in scores if s["split"] == split and s["horizon_s"] == horizon]
                if not chosen:
                    raise ValueError(f"empty_cohort:{split}:{horizon}")
                groups = {"all": chosen}
                for s in chosen:
                    groups.setdefault(s["session"] + "/" + s["participant"], []).append(s)
                for group, items in groups.items():
                    errors = [s[candidate + "_error_m"] for s in items]
                    summaries.append({"split": split, "horizon_s": horizon, "candidate": candidate,
                                      "group": group, "n": len(errors), "mean_error_m": float(np.mean(errors)),
                                      "median_error_m": float(np.median(errors))})
    return summaries


def run(args, report):
    source_root = Path(__file__).resolve().parents[1]
    source_paths = [Path(__file__).resolve(), source_root / "tests/test_prefix_forecast.py",
                    source_root / "uv.lock", source_root / "pyproject.toml"]
    source_before = {str(p.relative_to(source_root)): digest(p) for p in source_paths}
    report.update(parameters=PARAMETERS, source_sha256=source_before, numpy=np.__version__, python=sys.version)
    inventory_bytes = args.inventory.read_bytes()
    inventory_hash = hashlib.sha256(inventory_bytes).hexdigest()
    if inventory_hash != args.inventory_sha256:
        raise ValueError("inventory_hash_mismatch")
    inventory = json.loads(inventory_bytes)
    if inventory.get("source_revision") != REVISION:
        raise ValueError("wrong_inventory_revision")
    rows = validate_inventory(inventory)
    if len(rows) != 485:
        raise ValueError("expected_485_development_trials")
    revision = subprocess.check_output(["git", "-C", str(args.data_root), "rev-parse", "HEAD"], text=True).strip()
    if revision != REVISION:
        raise ValueError("wrong_data_revision")
    report.update(data_revision=revision, inventory_sha256=inventory_hash, protected_P0005_opened=False)
    root = args.data_root.resolve()
    scores, rejected, verified, trial_ids = [], [], [], set()
    # Retain partial coverage evidence on a fail-closed malformed-input refusal.
    report.update(scores=scores, rejected=rejected, input_sha256=verified)
    for row in rows:
        path = (root / row["path"]).resolve()
        if not path.is_relative_to(root):
            raise ValueError("input_path_escape")
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != row["sha256"]:
            raise ValueError("input_hash_mismatch:" + row["path"])
        trial = json.loads(raw)
        if trial["participant_id"] != row["participant"]:
            raise ValueError("participant_identity_mismatch")
        trial_key = (row["session"], row["participant"], trial["trial_id"])
        if trial_key in trial_ids:
            raise ValueError("duplicate_trial_identity")
        trial_ids.add(trial_key)
        tracking = trial["tracking"]
        times = np.asarray([r["time"] for r in tracking], dtype=float) / 1000
        if not len(times) or not np.isfinite(times).all() or np.any(np.diff(times) <= 0):
            raise ValueError("invalid_native_time_axis:" + row["path"])
        times = times - times[0]
        xyz = np.asarray([r["data"]["ball"] for r in tracking], dtype=float) * 0.3048
        hz = float(trial["sampling_rate"])
        identity = {"path": row["path"], "participant": row["participant"], "session": row["session"],
                    "split": "validation" if row["participant"] == "P0004" else "development"}
        try:
            state = fit_prefix(times, xyz, hz)
        except ValueError as exc:
            rejected.append({**identity, "reason": str(exc), "horizon_s": None})
        else:
            for horizon in HORIZONS:
                try:
                    j = target_index(times, xyz, hz, horizon)
                except ValueError as exc:
                    rejected.append({**identity, "reason": str(exc), "horizon_s": horizon})
                    continue
                score = {**identity, "horizon_s": horizon, "native_target_time_s": float(times[j]),
                         "reference_m": xyz[j].tolist()}
                for candidate in PARAMETERS["candidates"]:
                    forecast = predict(state, times[j], candidate)
                    score[candidate + "_prediction_m"] = forecast.tolist()
                    score[candidate + "_error_m"] = float(np.linalg.norm(forecast - xyz[j]))
                scores.append(score)
        if digest(path) != row["sha256"]:
            raise ValueError("input_changed_during_read")
        verified.append({"path": row["path"], "sha256": row["sha256"]})
    # Whole-run postcheck catches changes after a trial's individual read.
    if any(digest(root / r["path"]) != r["sha256"] for r in rows):
        raise ValueError("input_changed_during_run")
    if source_before != {str(p.relative_to(source_root)): digest(p) for p in source_paths}:
        raise ValueError("source_changed_during_run")
    if digest(args.inventory) != inventory_hash:
        raise ValueError("inventory_changed_during_run")
    report.update(trials=len(rows), input_and_source_unchanged=True,
                  cohort_sizes=dict(Counter(r["session"] + "/" + r["participant"] for r in rows)))
    report.update(status="COMPLETE_EXPLORATORY_BASELINE", summary=summarize(scores), scores=scores,
                  rejected=rejected, input_sha256=verified, trials=len(rows), input_and_source_unchanged=True,
                  cohort_sizes=dict(Counter(r["session"] + "/" + r["participant"] for r in rows)),
                  limitation="Supplied track continuation only; source tracking may be processed noncausally. No release, free-flight, live sensing or promotion claim.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--inventory-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    validate_output(args.output, args.data_root, Path(__file__).resolve().parents[1])
    args.output.mkdir(parents=True, exist_ok=False)
    report = {"status": "BLOCKED", "command": sys.argv}
    code = 0
    try:
        run(args, report)
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
        code = 2
    path = args.output / "run_manifest.json"
    path.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    (args.output / "SHA256.json").write_text(json.dumps({path.name: digest(path)}, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("status", "trials", "error") if k in report}))
    return code


def validate_output(output, data_root, source_root):
    """Require external, Git-ignored scratch before creating a directory."""
    destination = output.resolve()
    if any(destination.is_relative_to(p.resolve()) for p in (data_root, source_root)):
        raise ValueError("output_inside_protected_tree")
    existing = destination.parent
    while not existing.exists():
        existing = existing.parent
    result = subprocess.run(["git", "-C", str(existing), "check-ignore", "-q", str(destination)], check=False)
    if result.returncode != 0:
        raise ValueError("output_must_be_git_ignored_scratch")


if __name__ == "__main__":
    raise SystemExit(main())
