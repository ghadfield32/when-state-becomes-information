"""OW-REGIME-17: what motion regime does the fixed-cutoff MLSE baseline's 200 ms future occupy?

Development participants only (P0001-P0003). P0004 and P0005 rows are never opened. The
prefix eligibility rule is the unchanged baseline (`run_prefix_forecast.fit_prefix` and
`target_index`). Future-window fits and the whole-trajectory release heuristic are
noncausal DIAGNOSTICS used to decide which dynamics are physically admissible; they are
never labels, model inputs or evaluation references. No thresholds are applied: the report
is counts, reasons and quantiles.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import numpy as np

LAB = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LAB / "src"))
sys.path.insert(0, str(LAB / "scripts"))
from wms.physics.free_throw import fit_gravity_ballistic_segment, select_ballistic_window  # noqa: E402
import run_prefix_forecast as baseline  # noqa: E402

CONFIG = LAB / "configs/experiments/regime_feasibility_v1.json"
STATUS = "COMPLETE_DEVELOPMENT_REGIME_FEASIBILITY"
QUANTILES = (0.05, 0.25, 0.5, 0.75, 0.95)
NUMERIC = ("z_at_cutoff_m", "vz_at_cutoff_m_s", "speed_at_cutoff_m_s", "future_samples",
           "rmse_constant_velocity_m", "rmse_gravity_m", "rmse_quadratic_m",
           "gravity_over_constant_velocity_rmse", "quadratic_vertical_acceleration_m_s2",
           "tracking_tail_s", "release_like_time_minus_cutoff_s")


def default_config():
    return json.loads(CONFIG.read_text(encoding="utf-8"))


def check_frozen(path, sha):
    if baseline.digest(Path(path)) != sha or json.loads(Path(path).read_text(encoding="utf-8")) != default_config():
        raise ValueError("frozen_config_mismatch")


def _rmse(pred, observed):
    return float(np.sqrt(np.mean(np.sum((pred - observed) ** 2, axis=1))))


def trial_diagnostics(times, xyz, frames, hz, config):
    """Per-trial eligibility (baseline rule) plus noncausal regime diagnostics. Missing stays NaN."""
    cutoff, window = baseline.CUTOFF, config["future_window_s"]
    out = {name: None for name in NUMERIC}  # missing stays missing (JSON null), never 0
    out["targets"] = {}
    try:
        state = baseline.fit_prefix(times, xyz, hz)
    except ValueError as exc:
        out["prefix"] = str(exc)
    else:
        out["prefix"] = "eligible"
        velocity = np.asarray(state["velocity"], dtype=float)
        out.update(z_at_cutoff_m=float(state["position"][config["vertical_axis_index"]]),
                   vz_at_cutoff_m_s=float(velocity[config["vertical_axis_index"]]),
                   speed_at_cutoff_m_s=float(np.linalg.norm(velocity)))
        for horizon in config["horizons_s"]:
            try:
                j = baseline.target_index(times, xyz, hz, horizon)
            except ValueError as exc:
                out["targets"][str(horizon)] = str(exc)
            else:
                out["targets"][str(horizon)] = "available"
                out.setdefault("target_time_offsets_s", {})[str(horizon)] = float(times[j] - cutoff - horizon)
    finite = np.isfinite(times) & np.isfinite(xyz).all(axis=1)
    future = finite & (times > cutoff) & (times <= cutoff + window)
    out["future_samples"] = float(future.sum())
    if future.sum() >= config["minimum_future_samples_for_fits"]:
        tau, observed = times[future] - cutoff, xyz[future]
        linear = np.column_stack((np.ones_like(tau), tau))
        quadratic = np.column_stack((linear, tau ** 2))
        cv = linear @ np.linalg.lstsq(linear, observed, rcond=None)[0]
        coefficients = np.linalg.lstsq(quadratic, observed, rcond=None)[0]
        gravity = fit_gravity_ballistic_segment(times[future], observed, gravity_m_s2=config["gravity_m_s2"])
        out.update(rmse_constant_velocity_m=_rmse(cv, observed), rmse_gravity_m=gravity.rmse_m,
                   rmse_quadratic_m=_rmse(quadratic @ coefficients, observed),
                   quadratic_vertical_acceleration_m_s2=float(2.0 * coefficients[2, config["vertical_axis_index"]]))
        if out["rmse_constant_velocity_m"] > 0:  # a zero denominator leaves the ratio missing
            out["gravity_over_constant_velocity_rmse"] = out["rmse_gravity_m"] / out["rmse_constant_velocity_m"]
        out["future_fits"] = "fitted"
    else:
        out["future_fits"] = "insufficient_future_samples"
    if finite.any():
        out["tracking_tail_s"] = float(times[finite][-1] - cutoff)
    try:
        release = select_ballistic_window(times, xyz, frame_indices=frames, sampling_rate_hz=hz,
                                          gravity_m_s2=config["gravity_m_s2"])
    except ValueError:
        out["release_heuristic"] = "none_found"
    else:
        delta = release.reference_time_s - cutoff
        out["release_like_time_minus_cutoff_s"] = float(delta)
        out["release_heuristic"] = ("before_history" if delta < -baseline.HISTORY else "in_history" if delta <= 0
                                    else "in_future_window" if delta <= window else "after_future_window")
    return out


def summarize(rows):
    groups = {"all": rows}
    for r in rows:
        groups.setdefault(f"{r['session']}/{r['participant']}", []).append(r)
    summary = {}
    for name, items in groups.items():
        entry = {"trials": len(items), "prefix": dict(Counter(r["prefix"] for r in items)),
                 "future_fits": dict(Counter(r["future_fits"] for r in items)),
                 "release_heuristic": dict(Counter(r["release_heuristic"] for r in items)),
                 "targets": {h: dict(Counter(r["targets"][h] for r in items if h in r["targets"]))
                             for h in sorted({h for r in items for h in r["targets"]})}}
        for subset, chosen in (("all_trials", items), ("prefix_eligible", [r for r in items if r["prefix"] == "eligible"])):
            stats = {}
            for key in NUMERIC:
                values = np.asarray([r[key] for r in chosen], dtype=float)
                values = values[np.isfinite(values)]
                stats[key] = {"n_finite": int(values.size), "n_missing": int(len(chosen) - values.size),
                              "quantiles": dict(zip([str(q) for q in QUANTILES], np.quantile(values, QUANTILES).tolist()))
                              if values.size else None}
            entry[subset] = stats
        summary[name] = entry
    return summary


def load_trial(path):
    trial = json.loads(path.read_bytes())
    tracking = trial["tracking"]
    times = np.asarray([r["time"] for r in tracking], dtype=float) / 1000
    if not len(times) or not np.isfinite(times).all() or np.any(np.diff(times) <= 0):
        raise ValueError("invalid_native_time_axis:" + str(path))
    xyz = np.asarray([r["data"]["ball"] if r["data"]["ball"] is not None else [np.nan] * 3 for r in tracking],
                     dtype=float) * 0.3048
    frames = np.asarray([r["frame"] for r in tracking])
    return trial, times - times[0], xyz, frames


def run(args, report, config):
    source_paths = [Path(__file__).resolve(), Path(baseline.__file__).resolve(), CONFIG,
                    LAB / "src/wms/physics/free_throw.py", LAB / "tests/test_regime_feasibility.py",
                    LAB / "uv.lock", LAB / "pyproject.toml"]
    sources = {str(p.relative_to(LAB)): baseline.digest(p) for p in source_paths}
    report.update(config=config, config_sha256=args.config_sha256, source_sha256=sources,
                  numpy=np.__version__, python=sys.version)
    if baseline.digest(args.inventory) != config["inventory_sha256"]:
        raise ValueError("inventory_hash_mismatch")
    inventory = json.loads(args.inventory.read_bytes())
    if inventory.get("source_revision") != config["data_revision"]:
        raise ValueError("wrong_inventory_revision")
    revision = subprocess.check_output(["git", "-C", str(args.data_root), "rev-parse", "HEAD"], text=True).strip()
    if revision != config["data_revision"]:
        raise ValueError("wrong_data_revision")
    rows = [r for r in baseline.validate_inventory(inventory) if r["participant"] in config["participants"]]
    if len(rows) != config["expected_trials"]:
        raise ValueError("expected_trial_count_mismatch")
    root = args.data_root.resolve()
    results, opened = [], []
    report.update(results=results, opened=opened)
    for row in rows:
        path = (root / row["path"]).resolve()
        if not path.is_relative_to(root) or row["participant"] not in config["participants"]:
            raise ValueError("input_outside_admitted_participants")
        if baseline.digest(path) != row["sha256"]:
            raise ValueError("input_hash_mismatch:" + row["path"])
        trial, times, xyz, frames = load_trial(path)
        if trial["participant_id"] != row["participant"]:
            raise ValueError("participant_identity_mismatch")
        opened.append(row["path"])
        results.append({"path": row["path"], "session": row["session"], "participant": row["participant"],
                        "hz": float(trial["sampling_rate"]),
                        **trial_diagnostics(times, xyz, frames, float(trial["sampling_rate"]), config)})
    if any(baseline.digest(root / r["path"]) != r["sha256"] for r in rows):
        raise ValueError("input_changed_during_run")
    if sources != {str(p.relative_to(LAB)): baseline.digest(p) for p in source_paths}:
        raise ValueError("source_changed_during_run")
    forbidden = [p for p in opened if any(f"/{pid}/" in p for pid in config["not_opened"])]
    if forbidden:
        raise ValueError("protected_participant_opened")
    report.update(status=STATUS, trials=len(results), summary=summarize(results),
                  protected_participants_opened=False, input_and_source_unchanged=True,
                  limitation="Development participants only. Future-window fits and the release heuristic are "
                             "noncausal diagnostics on supplied processed tracks; they decide admissible dynamics "
                             "for the next task card and are not labels, references or evaluation results.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
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
    manifest.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    (args.output / "SHA256.json").write_text(json.dumps({manifest.name: baseline.digest(manifest)}, indent=2) + "\n",
                                             encoding="utf-8")
    print(json.dumps({k: report.get(k) for k in ("status", "trials", "error")}))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
