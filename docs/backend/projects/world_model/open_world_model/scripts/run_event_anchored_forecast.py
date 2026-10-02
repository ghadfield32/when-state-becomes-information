"""OW-EVENT-21: short-horizon forecasts with the cutoff at the causal release event vs the fixed 2.0 s cutoff.

Development participants only (P0001-P0003); P0004 and P0005 are never opened. Two arms freeze the
unchanged OW-REGIME-18 candidates (persistence, OLS velocity, gravity-only continuation) for every
trial: on the OW-EVENT-20 event-shifted time axis, and on the fixed-cutoff axis. Both arms must
reproduce their retained predecessors exactly (OW-EVENT-20 events and prefix status, OW-REGIME-18
fixed-cutoff errors). Predictions are frozen and hashed before scoring. Labels and cross-group
consistency are descriptive; P0001-P0003 shaped the detector, so this is development evidence only.
"""
from __future__ import annotations

import argparse
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

LAB = Path(__file__).resolve().parents[1]
REPO = LAB.parents[4]
sys.path.insert(0, str(LAB / "src"))
sys.path.insert(0, str(LAB / "scripts"))
from wms.evaluation.evidence_contracts import reconcile_cohort  # noqa: E402
import run_event_release_feasibility as event20  # noqa: E402
import run_prefix_forecast as baseline  # noqa: E402
import run_regime_feasibility as regime17  # noqa: E402
import run_regime_stratified_forecast as regime18  # noqa: E402

CONFIG = LAB / "configs/experiments/event_anchored_forecast_v1.json"
STATUS = "COMPLETE_DEVELOPMENT_EVENT_ANCHORED_FORECAST"
ARMS = ("event", "fixed")
VIEWS = ("all", "common")
CANDIDATES = regime18.CANDIDATES
EXAMPLE_WINDOW_S = (0.3, 0.3)


def default_config():
    return json.loads(CONFIG.read_text(encoding="utf-8"))


def check_frozen(path, sha):
    if baseline.digest(Path(path)) != sha or json.loads(Path(path).read_text(encoding="utf-8")) != default_config():
        raise ValueError("frozen_config_mismatch")


def load_pinned_config(entry, reason):
    path = LAB / entry["path"]
    if baseline.digest(path) != entry["sha256"]:
        raise ValueError(reason)
    return json.loads(path.read_text(encoding="utf-8"))


def load_retained(entry, reason):
    raw = gzip.decompress((REPO / entry["path"]).read_bytes())
    if hashlib.sha256(raw).hexdigest() != entry["original_sha256"]:
        raise ValueError(reason)
    return json.loads(raw)


def contrast_names(config):
    return [f"{a}_minus_{b}" for a, b in config["contrasts"]]


def event_axis(times_ms, ball, player, names, hz, event_config):
    """OW-EVENT-20's causal event and the integer-millisecond shifted axis (None when there is no event)."""
    r = event20.ball_radius_m(event_config)
    distance = event20.ball_hand_distance(ball, player, event20.hand_indices(names))
    found = event20.detect_release(times_ms, ball, distance, hz, event_config["contact_boundary_radii"] * r,
                                   event20.history_ms(event_config), event_config["vertical_axis_index"])
    if found["event_index"] is None:
        return found["reason"], None, None
    te = int(times_ms[found["event_index"]])
    return "event", te / 1000.0, (times_ms - te) / 1000.0 + baseline.CUTOFF


def freeze_row(times_ms, fixed_times, ball, player, names, hz, event_config, rule_config):
    """Both arms' fits, target times and predictions. Never computes an error."""
    status, event_time, shifted = event_axis(times_ms, ball, player, names, hz, event_config)
    arms = {"event": regime18.freeze_trial(shifted, ball, hz, rule_config) if shifted is not None
            else {"prefix": status, "targets": {}},
            "fixed": regime18.freeze_trial(fixed_times, ball, hz, rule_config)}
    return {"event": status, "event_time_s": event_time, "arms": arms}


def score_row(frozen, ball):
    return {arm: regime18.score_trial(frozen["arms"][arm], ball) for arm in ARMS}


def rejection_reason(frozen_arm, horizon):
    if frozen_arm["prefix"] != "eligible":
        return frozen_arm["prefix"]
    status = frozen_arm["targets"][horizon]["status"]
    if status == "available":  # an available target is always scored; its absence is a defect, never a rejection
        raise ValueError("available_target_unscored")
    return status


def bootstrap_mean(values, config):
    values = np.asarray(values, dtype=float)
    if not values.size:
        return {"n": 0, "mean": None, "ci95": None}
    idx = np.random.default_rng(config["bootstrap_seed"]).integers(0, values.size, size=(config["bootstrap_resamples"], values.size))
    means = values[idx].mean(axis=1)
    return {"n": int(values.size), "mean": float(values.mean()),
            "ci95": [float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))]}


def label(boot):
    if boot["ci95"] is None:
        return "undefined"
    return "a_lower" if boot["ci95"][1] < 0 else "b_lower" if boot["ci95"][0] > 0 else "not_separated"


def consistency(labels):
    values = list(labels.values())
    return "consistent" if values and "undefined" not in values and len(set(values)) == 1 else "inconsistent"


def summarize(rows, config):
    horizons = [str(h) for h in config["horizons_s"]]
    summary = {"trials": len(rows), "event": dict(Counter(r["frozen"]["event"] for r in rows)),
               "prefix": {arm: dict(Counter(r["frozen"]["arms"][arm]["prefix"] for r in rows)) for arm in ARMS}}
    for arm in ARMS:
        for view in VIEWS:
            cells, labels_by = {}, {}
            for horizon in horizons:
                scored = [r for r in rows if horizon in r["scores"][arm]
                          and (view == "all" or all(horizon in r["scores"][a] for a in ARMS))]
                per_group = {}
                for group in ["all"] + config["groups"]:
                    chosen = [r for r in scored if group == "all" or f"{r['session']}/{r['participant']}" == group]
                    cell = {"n": len(chosen),
                            "errors_m": {c: regime18._stats([r["scores"][arm][horizon]["errors_m"][c] for r in chosen])
                                         for c in CANDIDATES},
                            "paired_m": {}}
                    for name in contrast_names(config):
                        values = [r["scores"][arm][horizon]["paired_m"][name] for r in chosen]
                        boot = bootstrap_mean(values, config)
                        cell["paired_m"][name] = {**regime18._stats(values), "bootstrap": boot, "label": label(boot)}
                    if view == "all":
                        members = [r for r in rows if group == "all" or f"{r['session']}/{r['participant']}" == group]
                        cell["unscored"] = dict(Counter(rejection_reason(r["frozen"]["arms"][arm], horizon)
                                                        for r in members if horizon not in r["scores"][arm]))
                    per_group[group] = cell
                cells[horizon] = per_group
                labels_by[horizon] = {name: {"labels_by_group": {g: per_group[g]["paired_m"][name]["label"] for g in config["groups"]}}
                                      for name in contrast_names(config)}
                for entry in labels_by[horizon].values():
                    entry["consistency"] = consistency(entry["labels_by_group"])
            summary[f"{arm}_{view}"] = {"horizons": cells, "consistency": labels_by}
    summary["key"] = {arm: {"view": "common", "horizon_s": "0.2", "contrast": "gravity_minus_velocity",
                            **summary[f"{arm}_common"]["consistency"]["0.2"]["gravity_minus_velocity"],
                            "by_group": {g: summary[f"{arm}_common"]["horizons"]["0.2"][g]["paired_m"]["gravity_minus_velocity"]["bootstrap"]
                                         for g in ["all"] + config["groups"]}}
                      for arm in ARMS}
    return summary


def cohort_accounting(rows, config):
    expected = [r["path"] for r in rows]
    out = {}
    for arm in ARMS:
        for horizon in (str(h) for h in config["horizons_s"]):
            accepted = [r["path"] for r in rows if horizon in r["scores"][arm]]
            rejected = [(r["path"], rejection_reason(r["frozen"]["arms"][arm], horizon))
                        for r in rows if horizon not in r["scores"][arm]]
            out[f"{arm}/{horizon}"] = reconcile_cohort(expected, accepted, rejected).as_dict()
    return out


def check_event20_reproduction(rows, retained):
    stored = {r["path"]: r for r in retained["results"]}
    for row in rows:
        old = stored.get(row["path"])
        if old is None:
            raise ValueError("event20_row_missing:" + row["path"])
        expected_prefix = old["prefix"] if old["event"] == "event" else old["event"]
        if (row["frozen"]["event"], row["frozen"]["event_time_s"], row["frozen"]["arms"]["event"]["prefix"]) != (old["event"], old["event_time_s"], expected_prefix):
            raise ValueError("event20_not_reproduced:" + row["path"])
    return len(rows)


def check_regime18_reproduction(rows, retained):
    stored, reproduced = {r["path"]: r for r in retained["results"]}, 0
    for row in rows:
        old = stored.get(row["path"])
        if old is None:
            raise ValueError("regime18_row_missing:" + row["path"])
        fixed = row["scores"]["fixed"]
        if row["frozen"]["arms"]["fixed"]["prefix"] != old["prefix"] or set(fixed) != set(old["scores"]):
            raise ValueError("regime18_not_reproduced:" + row["path"])
        for horizon, score in old["scores"].items():
            if fixed[horizon]["errors_m"] != {c: score["errors_m"][c] for c in CANDIDATES}:
                raise ValueError(f"regime18_not_reproduced:{row['path']}:{horizon}")
            reproduced += len(CANDIDATES)
    return reproduced


def select_examples(rows, inputs, config):
    examples = []
    for group in config["groups"]:
        chosen = sorted((r for r in rows if f"{r['session']}/{r['participant']}" == group and "0.2" in r["scores"]["event"]),
                        key=lambda r: (r["scores"]["event"]["0.2"]["errors_m"]["velocity"], r["path"]))
        if not chosen:
            continue
        for role, row in (("representative", chosen[(len(chosen) - 1) // 2]), ("failure", chosen[-1])):
            times_ms, ball = inputs[row["path"]]
            since = (times_ms - round(row["frozen"]["event_time_s"] * 1000)) / 1000.0
            window = (since >= -EXAMPLE_WINDOW_S[0]) & (since <= EXAMPLE_WINDOW_S[1])
            frozen = row["frozen"]["arms"]["event"]
            examples.append({"role": role, "path": row["path"], "group": group, "event_time_s": row["frozen"]["event_time_s"],
                             "time_since_event_s": since[window].tolist(),
                             "ball_z_m": [None if not np.isfinite(v) else float(v) for v in ball[window, 2]],
                             "prefix_first_time_s": frozen["fits"]["prefix_first_time_s"] - baseline.CUTOFF,
                             "targets": {h: {"time_since_event_s": t["native_time_s"] - baseline.CUTOFF,
                                             "predictions_z_m": {c: t["predictions_m"][c][2] for c in CANDIDATES},
                                             "errors_m": row["scores"]["event"][h]["errors_m"]}
                                         for h, t in frozen["targets"].items() if t["status"] == "available"}})
    return examples


def plot_examples(examples, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(len(examples), 1, figsize=(8, 2.4 * len(examples)), squeeze=False)
    markers = {"persistence": ("s", "C0"), "velocity": ("^", "C2"), "gravity": ("o", "C3")}
    for ax, ex in zip(axes[:, 0], examples):
        t = np.asarray(ex["time_since_event_s"], dtype=float)
        z = np.asarray([np.nan if v is None else v for v in ex["ball_z_m"]], dtype=float)
        prefix = (t >= ex["prefix_first_time_s"]) & (t <= 0)
        ax.plot(t[prefix], z[prefix], "k.", ms=4, label="admitted prefix")
        ax.plot(t[~prefix], z[~prefix], ".", color="0.65", ms=4, label="supplied track (reference)")
        for target in ex["targets"].values():
            for c, (m, color) in markers.items():
                ax.plot(target["time_since_event_s"], target["predictions_z_m"][c], m, mfc="none", color=color,
                        label=c if target is next(iter(ex["targets"].values())) else None)
        ax.axvline(0.0, color="k", lw=0.6)
        err = ex["targets"].get("0.2", {}).get("errors_m", {})
        ax.set_title(f"{ex['role']} | {ex['group']} | {ex['path'].rsplit('/', 1)[-1]} | 200 ms 3-D error "
                     + " ".join(f"{c[:4]} {err[c]:.2f}" for c in CANDIDATES if c in err) + " m", fontsize=7)
        ax.set_ylabel("ball z (m)", fontsize=7)
        ax.tick_params(labelsize=6)
    axes[0, 0].legend(fontsize=6, loc="upper left", ncol=2)
    axes[-1, 0].set_xlabel("time since detected release event (s); markers = predictions at 50/100/200 ms", fontsize=7)
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


def load_trial_inputs(root, row, config, opened):
    times_ms, ball, player, names, frames, hz = event20.open_admitted(root, row, config, opened)
    _, fixed_times, fixed_ball, _ = regime17.load_trial((root / row["path"]).resolve())
    if not np.array_equal(fixed_ball, ball, equal_nan=True):
        raise ValueError("arm_ball_disagreement:" + row["path"])
    return times_ms, fixed_times, ball, player, names, hz


def build_rows(rows_in, root, config, event_config, rule_config, opened):
    rows, inputs = [], {}
    for row in rows_in:
        times_ms, fixed_times, ball, player, names, hz = load_trial_inputs(root, row, config, opened)
        inputs[row["path"]] = (times_ms, ball)
        rows.append({"path": row["path"], "session": row["session"], "participant": row["participant"], "hz": hz,
                     "frozen": freeze_row(times_ms, fixed_times, ball, player, names, hz, event_config, rule_config)})
    return rows, inputs


def run(args, report, config):
    event_config = load_pinned_config(config["event_detector"]["config"], "event20_config_changed")
    rule_config = load_pinned_config(config["candidates"]["config"], "regime18_config_changed")
    sources = [Path(__file__).resolve(), CONFIG, LAB / config["event_detector"]["config"]["path"],
               LAB / config["candidates"]["config"]["path"], Path(event20.__file__).resolve(), Path(regime18.__file__).resolve(),
               Path(regime17.__file__).resolve(), Path(baseline.__file__).resolve(), LAB / "src/wms/data/mlse_spl.py",
               LAB / "src/wms/physics/free_throw.py", LAB / "src/wms/evaluation/evidence_contracts.py",
               LAB / "tests/test_event_anchored_forecast.py", LAB / "uv.lock", LAB / "pyproject.toml"]
    source_sha = {str(p.relative_to(LAB)): baseline.digest(p) for p in sources}
    report.update(config=config, config_sha256=args.config_sha256, source_sha256=source_sha, numpy=np.__version__, python=sys.version)
    event20_retained = load_retained(config["event20_reproduction"]["manifest"], "event20_evidence_mismatch")
    regime18_retained = load_retained(config["regime18_reproduction"]["manifest"], "regime18_evidence_mismatch")
    rows_in = event20.admitted_rows(args.inventory, args.data_root, config)
    root, opened = args.data_root.resolve(), []
    report.update(opened=opened)
    rows, inputs = build_rows(rows_in, root, config, event_config, rule_config, opened)
    frozen_path = args.output / "frozen_predictions.json"
    frozen_path.write_bytes((json.dumps([{k: r[k] for k in ("path", "session", "participant", "hz", "frozen")} for r in rows],
                                        indent=1, allow_nan=False) + "\n").encode("utf-8"))
    frozen_sha = baseline.digest(frozen_path)
    for row in rows:  # scoring starts only after the freeze is on disk and hashed
        row["scores"] = score_row(row["frozen"], inputs[row["path"]][1])
    if baseline.digest(frozen_path) != frozen_sha:
        raise ValueError("frozen_predictions_changed_during_scoring")
    reproduced = {"event20_trials": check_event20_reproduction(rows, event20_retained),
                  "regime18_candidate_errors": check_regime18_reproduction(rows, regime18_retained)}
    cohort = cohort_accounting(rows, config)
    if any(baseline.digest(root / r["path"]) != r["sha256"] for r in rows_in):
        raise ValueError("input_changed_during_run")
    if source_sha != {str(p.relative_to(LAB)): baseline.digest(p) for p in sources}:
        raise ValueError("source_changed_during_run")
    if any(f"/{pid}/" in p for p in opened for pid in config["not_opened"]):
        raise ValueError("protected_participant_opened")
    examples = select_examples(rows, inputs, config)
    plot_examples(examples, args.output / "examples.png")
    report.update(status=STATUS, trials=len(rows), frozen_predictions_sha256=frozen_sha, reproduced=reproduced, cohort=cohort,
                  summary=summarize(rows, config), examples=examples,
                  results=[{"path": r["path"], "session": r["session"], "participant": r["participant"], "scores": r["scores"]} for r in rows],
                  protected_participants_opened=False, input_and_source_unchanged=True,
                  limitation="Development participants only (P0001-P0003), which shaped the event detector; agreement with "
                             "supplied, possibly processed tracks, not physical accuracy. Labels are descriptive of these "
                             "trials. No uncertainty qualification. P0004 not consulted; P0005 locked.")


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
    (retained_dir / "RETENTION.json").write_bytes((json.dumps({"packet": "OW-EVENT-21", "policy": "exact_bytes_gzip",
                                                               "files": files}, indent=2) + "\n").encode("utf-8"))


def verify_retained(retained_dir, config, data_root=None, inventory=None):
    """Digests, config replay, freeze hash, every score rebuilt from frozen predictions, summary and cohort rebuilt."""
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
    failures = []
    if hashlib.sha256(raw["frozen_predictions.json"]).hexdigest() != manifest["frozen_predictions_sha256"]:
        failures.append("frozen_predictions_not_the_scored_freeze")
    frozen_rows = json.loads(raw["frozen_predictions.json"])
    results = {r["path"]: r for r in manifest["results"]}
    rows = []
    for frozen_row in frozen_rows:
        result = results.get(frozen_row["path"])
        if result is None:
            failures.append("result_missing:" + frozen_row["path"])
            continue
        scores = {}
        for arm in ARMS:
            scores[arm] = {}
            targets = frozen_row["frozen"]["arms"][arm]["targets"]
            available = {h for h, t in targets.items() if t["status"] == "available"}
            for horizon in sorted(set(result["scores"][arm]) - available):
                failures.append(f"score_without_available_target:{frozen_row['path']}:{arm}:{horizon}")
            for horizon in sorted(available):  # every frozen prediction, not only the ones the manifest kept
                stored = result["scores"][arm].get(horizon)
                if stored is None:
                    failures.append(f"score_missing:{frozen_row['path']}:{arm}:{horizon}")
                    continue
                target = targets[horizon]
                # Only the reference position is taken from the retained scores; every derived number is rebuilt.
                scores[arm][horizon] = regime18.score_trial({"targets": {horizon: target}},
                                                            {target["index"]: np.asarray(stored["reference_m"])})[horizon]
                if scores[arm][horizon] != stored:
                    failures.append(f"score_not_recomputable:{frozen_row['path']}:{arm}:{horizon}")
        rows.append({**frozen_row, "scores": scores})
    if any(f.startswith(("score_missing:", "score_without_available_target:")) for f in failures):
        return failures  # the rebuilt rows are incomplete, so summary and cohort cannot be replayed from them
    if summarize(rows, config) != manifest["summary"]:
        failures.append("summary_not_recomputable")
    if cohort_accounting(rows, config) != manifest["cohort"]:
        failures.append("cohort_not_recomputable")
    if data_root is not None:
        event_config = load_pinned_config(config["event_detector"]["config"], "event20_config_changed")
        rule_config = load_pinned_config(config["candidates"]["config"], "regime18_config_changed")
        rows_in = event20.admitted_rows(inventory, data_root, config)
        rebuilt, inputs = build_rows(rows_in, Path(data_root).resolve(), config, event_config, rule_config, [])
        retained_frozen = {r["path"]: r for r in frozen_rows}
        for row in rebuilt:
            if json.loads(json.dumps({k: row[k] for k in ("path", "session", "participant", "hz", "frozen")})) != retained_frozen.get(row["path"]):
                failures.append("frozen_not_rederivable:" + row["path"])
                continue
            for arm, per_h in results[row["path"]]["scores"].items():
                for horizon, stored in per_h.items():
                    if stored["reference_m"] != inputs[row["path"]][1][row["frozen"]["arms"][arm]["targets"][horizon]["index"]].tolist():
                        failures.append(f"reference_not_rederivable:{row['path']}:{arm}:{horizon}")
        if len(rebuilt) != len(frozen_rows):
            failures.append("trial_count_differs")
    return failures


def main():
    sys.stdout.reconfigure(encoding="utf-8")
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
    (args.output / "SHA256.json").write_bytes((json.dumps(
        {p.name: baseline.digest(p) for p in sorted(args.output.iterdir()) if p.is_file() and p.name != "SHA256.json"},
        indent=2) + "\n").encode("utf-8"))
    print(json.dumps({k: report.get(k) for k in ("status", "trials", "error")}))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
