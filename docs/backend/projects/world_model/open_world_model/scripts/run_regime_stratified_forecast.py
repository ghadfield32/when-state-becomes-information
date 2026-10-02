"""OW-REGIME-18: prefix-only gravity-vs-line preference and per-group short-horizon forecasts.

Executes the frozen OW-REGIME-18 task card on development participants P0001-P0003 (P0004 and
P0005 are never opened). The prefix eligibility rule is the unchanged baseline. For each admitted
prefix an OLS line and a gravity-only line (both 6 parameters) are fitted to exactly the admitted
samples; `gravity_consistent` means only that gravity was PREFERRED on that prefix (for noise-free
vertical acceleration a this holds whenever a < -g/2), never a release, contact or physics label.
All fits and predictions at native target times are frozen and hashed before any reference
position is used for scoring. OW-REGIME-17's retained future diagnostics appear only in a separate
retrospective fit-preference agreement table. Prefix-only use of supplied tracks; no causal
live-pipeline, physical-accuracy or uncertainty claim.
"""
from __future__ import annotations

import argparse
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import numpy as np

LAB = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LAB / "src"))
sys.path.insert(0, str(LAB / "scripts"))
from wms.physics.free_throw import fit_gravity_ballistic_segment  # noqa: E402
import run_prefix_forecast as baseline  # noqa: E402
import run_regime_feasibility as regime17  # noqa: E402

CONFIG = LAB / "configs/experiments/regime_stratified_forecast_v1.json"
STATUS = "COMPLETE_DEVELOPMENT_REGIME_STRATIFIED_FORECAST"
CANDIDATES = ("persistence", "velocity", "gravity")
PAIRS = (("velocity", "persistence"), ("gravity", "velocity"), ("gravity", "persistence"))
INDICATORS = ("gravity_consistent", "not_gravity_consistent")


def default_config():
    return json.loads(CONFIG.read_text(encoding="utf-8"))


def check_frozen(path, sha):
    if baseline.digest(Path(path)) != sha or json.loads(Path(path).read_text(encoding="utf-8")) != default_config():
        raise ValueError("frozen_config_mismatch")


def admitted_prefix(times, xyz):
    """The finite samples fit_prefix admits in [cutoff - history, cutoff]; guarded against drift below."""
    observed = np.isfinite(times) & (times >= baseline.CUTOFF - baseline.HISTORY) & (times <= baseline.CUTOFF)
    pt, px = times[observed], xyz[observed]
    valid = np.isfinite(px).all(axis=1)
    return pt[valid], px[valid]


def prefix_fits(times, xyz, hz, config):
    state = baseline.fit_prefix(times, xyz, hz)
    pt, px = admitted_prefix(times, xyz)
    # fit_prefix does not return its samples, so re-derive its own OLS state from ours: any added or
    # dropped admitted sample changes intercept/velocity, not only the last position.
    if not len(pt) or not np.array_equal(px[-1], state["position"]):
        raise ValueError("prefix_selection_mismatch")
    reference = np.linalg.lstsq(np.column_stack((np.ones(len(pt)), pt - baseline.CUTOFF)), px, rcond=None)[0]
    if not (np.allclose(reference[0], state["intercept"], rtol=0, atol=1e-9)
            and np.allclose(reference[1], state["velocity"], rtol=0, atol=1e-9)):
        raise ValueError("prefix_selection_mismatch")
    tau = pt - pt[0]
    design = np.column_stack((np.ones_like(tau), tau))
    line = np.linalg.lstsq(design, px, rcond=None)[0]
    rmse_line = float(np.sqrt(np.mean(np.sum((design @ line - px) ** 2, axis=1))))
    gravity = fit_gravity_ballistic_segment(pt, px, gravity_m_s2=config["gravity_m_s2"])
    indicator = "gravity_consistent" if gravity.rmse_m < rmse_line else "not_gravity_consistent"
    fits = {"n_prefix_samples": int(len(pt)), "prefix_first_time_s": float(pt[0]), "prefix_last_time_s": float(pt[-1]),
            "rmse_line_m": rmse_line, "rmse_gravity_m": float(gravity.rmse_m),
            "rmse_gravity_minus_line_m": float(gravity.rmse_m - rmse_line),
            "line_p0_m": line[0].tolist(), "line_v_m_s": line[1].tolist(),
            "gravity_p0_m": gravity.position_m.tolist(), "gravity_v_m_s": gravity.velocity_m_s.tolist()}
    return state, gravity, fits, indicator


def freeze_trial(times, xyz, hz, config):
    """Prefix fits, indicator and every prediction at native target times. Never computes an error.

    Target availability uses the baseline's target_index (native time grid plus finiteness of the
    target sample), exactly as OW-PREFIX-07 did.
    """
    out = {"targets": {}}
    try:
        state, gravity, fits, indicator = prefix_fits(times, xyz, hz, config)
    except ValueError as exc:
        out["prefix"] = str(exc)
        return out
    out.update(prefix="eligible", indicator=indicator, fits=fits,
               gravity_role="candidate" if indicator == "gravity_consistent" else "mismatched_comparator")
    for horizon in config["horizons_s"]:
        try:
            j = baseline.target_index(times, xyz, hz, horizon)
        except ValueError as exc:
            out["targets"][str(horizon)] = {"status": str(exc)}
            continue
        t = float(times[j])
        out["targets"][str(horizon)] = {
            "status": "available", "index": int(j), "requested_time_s": baseline.CUTOFF + horizon, "native_time_s": t,
            "predictions_m": {"persistence": baseline.predict(state, t, "persistence").tolist(),
                              "velocity": baseline.predict(state, t, "velocity").tolist(),
                              "gravity": gravity.predict(t).tolist()}}
    return out


def score_trial(frozen, xyz):
    """Errors against the supplied reference, computed only from frozen predictions."""
    scored = {}
    for horizon, target in frozen["targets"].items():
        if target["status"] != "available":
            continue
        reference = xyz[target["index"]]
        errors = {c: float(np.linalg.norm(np.asarray(target["predictions_m"][c]) - reference)) for c in CANDIDATES}
        scored[horizon] = {"reference_m": reference.tolist(), "errors_m": errors,
                           "paired_m": {f"{a}_minus_{b}": errors[a] - errors[b] for a, b in PAIRS}}
    return scored


def future_preference(row):
    g, line = row.get("rmse_gravity_m"), row.get("rmse_constant_velocity_m")
    if g is None or line is None:
        return "future_undefined"
    return "future_gravity_preferred" if g < line else "future_line_preferred"


def _stats(values):
    values = np.asarray(values, dtype=float)
    if not values.size:
        return {"n": 0, "mean": None, "median": None, "p90": None}
    return {"n": int(values.size), "mean": float(values.mean()), "median": float(np.median(values)),
            "p90": float(np.quantile(values, 0.9))}


def summarize(rows, config):
    eligible = [r for r in rows if r["prefix"] == "eligible"]
    groups = {"all": eligible}
    for r in eligible:
        groups.setdefault(f"{r['session']}/{r['participant']}", []).append(r)
    summary = {}
    for name, items in groups.items():
        entry = {"prefixes": len(items), "indicator": dict(Counter(r["indicator"] for r in items)),
                 "agreement": dict(Counter(f"{r['indicator']}|{r['future_preference']}" for r in items)),
                 "by_indicator": {}}
        for indicator in INDICATORS:
            chosen = [r for r in items if r["indicator"] == indicator]
            per_h = {}
            for horizon in (str(h) for h in config["horizons_s"]):
                scored = [r["scores"][horizon] for r in chosen if horizon in r["scores"]]
                per_h[horizon] = {
                    "unavailable": dict(Counter(r["frozen"]["targets"][horizon]["status"] for r in chosen
                                                if r["frozen"]["targets"][horizon]["status"] != "available")),
                    "errors_m": {c: _stats([s["errors_m"][c] for s in scored]) for c in CANDIDATES},
                    "paired_m": {f"{a}_minus_{b}": _stats([s["paired_m"][f"{a}_minus_{b}"] for s in scored])
                                 for a, b in PAIRS}}
            entry["by_indicator"][indicator] = {"n": len(chosen), "horizons": per_h}
        summary[name] = entry
    return summary


def select_examples(rows, trials):
    examples = []
    eligible = [r for r in rows if r["prefix"] == "eligible" and "0.2" in r["scores"]]
    keys = sorted({(r["session"], r["participant"], r["indicator"]) for r in eligible})
    for session, participant, indicator in keys:
        chosen = sorted((r for r in eligible if (r["session"], r["participant"], r["indicator"])
                         == (session, participant, indicator)),
                        key=lambda r: (r["scores"]["0.2"]["errors_m"]["velocity"], r["path"]))
        for role, row in (("representative", chosen[(len(chosen) - 1) // 2]), ("failure", chosen[-1])):
            times, xyz = trials[row["path"]]
            window = np.isfinite(times) & (times >= baseline.CUTOFF - baseline.HISTORY) & (times <= baseline.CUTOFF + 0.25)
            examples.append({"role": role, "path": row["path"], "session": session, "participant": participant,
                             "indicator": indicator, "gravity_role": row["frozen"]["gravity_role"],
                             "fits": row["frozen"]["fits"], "targets": row["frozen"]["targets"], "scores": row["scores"],
                             "window_time_s": times[window].tolist(),
                             "window_xyz_m": np.where(np.isfinite(xyz[window]), xyz[window], None).tolist()})
    return examples


def plot_examples(examples, path, config):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    z = config["vertical_axis_index"]
    fig, axes = plt.subplots(len(examples), 1, figsize=(8, 2.6 * len(examples)), squeeze=False)
    for ax, ex in zip(axes[:, 0], examples):
        t = np.asarray(ex["window_time_s"], dtype=float)
        xyz = np.asarray([[np.nan if v is None else v for v in row] for row in ex["window_xyz_m"]], dtype=float)
        prefix = t <= baseline.CUTOFF
        ax.plot(t[prefix], xyz[prefix, z], "k.", label="prefix (observed)")
        ax.plot(t[~prefix], xyz[~prefix, z], ".", color="0.6", label="supplied future (reference)")
        f = ex["fits"]
        grid = np.linspace(f["prefix_first_time_s"], baseline.CUTOFF + 0.2, 60)
        tau = grid - f["prefix_first_time_s"]
        ax.plot(grid, f["line_p0_m"][z] + f["line_v_m_s"][z] * tau, "b-", lw=1, label="OLS line fit")
        ax.plot(grid, f["gravity_p0_m"][z] + f["gravity_v_m_s"][z] * tau - 0.5 * config["gravity_m_s2"] * tau ** 2,
                "r-", lw=1, label="gravity fit")
        for h, target in ex["targets"].items():
            if target["status"] == "available":
                for c, marker in (("persistence", "s"), ("velocity", "^"), ("gravity", "o")):
                    ax.plot(target["native_time_s"], target["predictions_m"][c][z], marker, mfc="none", color="C2")
        ax.axvline(baseline.CUTOFF, color="k", lw=0.5)
        err = ex["scores"]["0.2"]["errors_m"]
        ax.set_title(f"{ex['role']} | {ex['session']}/{ex['participant']} | {ex['indicator']} (gravity {ex['gravity_role']}) | "
                     f"200 ms err pers {err['persistence']:.2f} vel {err['velocity']:.2f} grav {err['gravity']:.2f} m",
                     fontsize=7)
        ax.set_ylabel("supplied z (m)", fontsize=7)
        ax.tick_params(labelsize=6)
    axes[0, 0].legend(fontsize=6, loc="best")
    axes[-1, 0].set_xlabel("time since first tracking sample (s); markers = predictions (square pers, triangle vel, circle grav)",
                           fontsize=7)
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


def load_regime17(path, config):
    raw = gzip.decompress(Path(path).read_bytes())
    if hashlib.sha256(raw).hexdigest() != config["retrospective_agreement"]["source_original_sha256"]:
        raise ValueError("regime17_evidence_mismatch")
    return {r["path"]: r for r in json.loads(raw)["results"]}


def run(args, report, config):
    sources = [Path(__file__).resolve(), Path(baseline.__file__).resolve(), Path(regime17.__file__).resolve(), CONFIG,
               LAB / "src/wms/physics/free_throw.py", LAB / "tests/test_regime_stratified_forecast.py",
               LAB / "uv.lock", LAB / "pyproject.toml"]
    source_sha = {str(p.relative_to(LAB)): baseline.digest(p) for p in sources}
    report.update(config=config, config_sha256=args.config_sha256, source_sha256=source_sha,
                  numpy=np.__version__, python=sys.version)
    future = load_regime17(args.regime17_manifest, config)
    if baseline.digest(args.inventory) != config["inventory_sha256"]:
        raise ValueError("inventory_hash_mismatch")
    inventory = json.loads(args.inventory.read_bytes())
    if inventory.get("source_revision") != config["data_revision"]:
        raise ValueError("wrong_inventory_revision")
    revision = subprocess.check_output(["git", "-C", str(args.data_root), "rev-parse", "HEAD"], text=True).strip()
    if revision != config["data_revision"]:
        raise ValueError("wrong_data_revision")
    rows_in = [r for r in baseline.validate_inventory(inventory) if r["participant"] in config["participants"]]
    if len(rows_in) != config["expected_trials"]:
        raise ValueError("expected_trial_count_mismatch")
    root = args.data_root.resolve()
    rows, trials, opened = [], {}, []
    report.update(opened=opened)
    for row in rows_in:
        path = (root / row["path"]).resolve()
        if not path.is_relative_to(root) or row["participant"] not in config["participants"]:
            raise ValueError("input_outside_admitted_participants")
        if baseline.digest(path) != row["sha256"]:
            raise ValueError("input_hash_mismatch:" + row["path"])
        trial, times, xyz, _ = regime17.load_trial(path)
        if trial["participant_id"] != row["participant"]:
            raise ValueError("participant_identity_mismatch")
        opened.append(row["path"])
        trials[row["path"]] = (times, xyz)
        frozen = freeze_trial(times, xyz, float(trial["sampling_rate"]), config)
        rows.append({"path": row["path"], "session": row["session"], "participant": row["participant"],
                     "hz": float(trial["sampling_rate"]), "prefix": frozen.get("prefix"),
                     "indicator": frozen.get("indicator"), "frozen": frozen})
    eligible = [r for r in rows if r["prefix"] == "eligible"]
    if len(eligible) != config["expected_eligible_prefixes"]:
        raise ValueError("expected_eligible_prefix_count_mismatch")
    frozen_path = args.output / "frozen_predictions.json"
    frozen_path.write_text(json.dumps([{k: r[k] for k in ("path", "session", "participant", "hz", "prefix", "frozen")}
                                       for r in rows], indent=1) + "\n", encoding="utf-8")
    frozen_sha = baseline.digest(frozen_path)
    for r in rows:  # scoring starts only after the freeze is on disk and hashed
        r["scores"] = score_trial(r["frozen"], trials[r["path"]][1]) if r["prefix"] == "eligible" else {}
        if r["prefix"] == "eligible":
            if r["path"] not in future:
                raise ValueError("regime17_row_missing:" + r["path"])
            r["future_preference"] = future_preference(future[r["path"]])
    if baseline.digest(frozen_path) != frozen_sha:
        raise ValueError("frozen_predictions_changed_during_scoring")
    if any(baseline.digest(root / r["path"]) != r["sha256"] for r in rows_in):
        raise ValueError("input_changed_during_run")
    if source_sha != {str(p.relative_to(LAB)): baseline.digest(p) for p in sources}:
        raise ValueError("source_changed_during_run")
    if any(f"/{pid}/" in p for p in opened for pid in config["not_opened"]):
        raise ValueError("protected_participant_opened")
    examples = select_examples(rows, trials)
    plot_examples(examples, args.output / "examples.png", config)
    report.update(status=STATUS, trials=len(rows), eligible_prefixes=len(eligible),
                  rejected=dict(Counter(r["prefix"] for r in rows if r["prefix"] != "eligible")),
                  frozen_predictions_sha256=frozen_sha, summary=summarize(rows, config), examples=examples,
                  results=[{k: r.get(k) for k in ("path", "session", "participant", "hz", "prefix", "indicator",
                                                  "future_preference", "scores")}
                           | {"gravity_role": r["frozen"].get("gravity_role")} for r in rows],
                  protected_participants_opened=False, input_and_source_unchanged=True,
                  limitation="Development participants only (P0001-P0003), prefix-only use of supplied, possibly processed "
                             "tracks. gravity_consistent = gravity preferred over the line on the prefix, not a release, "
                             "contact or physics label. Errors are agreement with supplied coordinates, not physical "
                             "accuracy; no uncertainty is qualified. P0004 not consulted; P0005 locked.")


RETAINED = ("run_manifest.json", "frozen_predictions.json")


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
    (retained_dir / "RETENTION.json").write_text(json.dumps({"packet": "OW-REGIME-18", "policy": "exact_bytes_gzip",
                                                             "files": files}, indent=2) + "\n", encoding="utf-8")


def verify_retained(retained_dir, config):
    """Digests, then re-score every frozen prediction against retained references and rebuild the summary."""
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
    failures = []
    manifest = json.loads(raw["run_manifest.json"])
    if manifest.get("config") != config:
        return ["config_mismatch"]  # replay only the frozen rule the run executed
    if hashlib.sha256(raw["frozen_predictions.json"]).hexdigest() != manifest["frozen_predictions_sha256"]:
        failures.append("frozen_predictions_not_the_scored_freeze")
    results = {r["path"]: r for r in manifest["results"]}
    rows = []
    for frozen_row in json.loads(raw["frozen_predictions.json"]):
        result = results.get(frozen_row["path"])
        if result is None:
            failures.append("result_missing:" + frozen_row["path"])
            continue
        frozen, rebuilt = frozen_row["frozen"], {}
        for horizon, stored in result["scores"].items():
            # Only the reference position is taken from the retained scores; every derived number is rebuilt.
            rebuilt[horizon] = score_trial({"targets": {horizon: frozen["targets"][horizon]}},
                                           {frozen["targets"][horizon]["index"]: np.asarray(stored["reference_m"])})[horizon]
            if rebuilt[horizon]["errors_m"] != stored["errors_m"]:
                failures.append(f"error_not_recomputable:{frozen_row['path']}:{horizon}")
            if rebuilt[horizon]["paired_m"] != stored["paired_m"]:
                failures.append(f"paired_not_recomputable:{frozen_row['path']}:{horizon}")
        rows.append({**frozen_row, "indicator": frozen.get("indicator"),
                     "future_preference": result["future_preference"], "scores": rebuilt})
    if summarize(rows, config) != manifest["summary"]:
        failures.append("summary_not_recomputable")
    return failures


def main():
    if len(sys.argv) == 3 and sys.argv[1] == "verify-retained":
        failures = verify_retained(sys.argv[2], default_config())
        print(json.dumps({"status": "PASS" if not failures else "FAIL", "failures": failures}))
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
    manifest.write_text(json.dumps(report, indent=1, allow_nan=False) + "\n", encoding="utf-8")
    (args.output / "SHA256.json").write_text(json.dumps(
        {p.name: baseline.digest(p) for p in sorted(args.output.iterdir()) if p.is_file() and p.name != "SHA256.json"},
        indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: report.get(k) for k in ("status", "trials", "eligible_prefixes", "error")}))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
