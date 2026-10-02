"""OW-CONTEXT-22: does hand context at the release event reduce the ball-only undershoot? (development)

Development participants only (P0001-P0003); P0004 and P0005 are never opened. On OW-EVENT-21's
release-anchored task (unchanged event arm, reproduced exactly), four candidates are added without
any new parameter: continuations from the ball's end-of-prefix state, with the velocity taken from
the ball itself or from the hand keypoints that were touching it, with and without gravity. A
support audit (PREP-VIS-01) records whether each event's separation is visible on the keypoints
seen at both samples. Predictions are frozen before scoring; labels are descriptive.
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
import run_event_anchored_forecast as event21  # noqa: E402
import run_event_release_feasibility as event20  # noqa: E402
import run_prefix_forecast as baseline  # noqa: E402
import run_regime_stratified_forecast as regime18  # noqa: E402

CONFIG = LAB / "configs/experiments/context_at_release_v1.json"
STATUS = "COMPLETE_DEVELOPMENT_CONTEXT_AT_RELEASE"
BASE = ("persistence", "velocity", "gravity")
BALL = ("ball_endpoint_velocity", "ball_endpoint_ballistic")
HAND = ("hand_endpoint_velocity", "hand_endpoint_ballistic")
CANDIDATES = BASE + BALL + HAND
VIEWS = ("common", "support_stable")
EXAMPLE_WINDOW_S = (0.25, 0.25)


def default_config():
    return json.loads(CONFIG.read_text(encoding="utf-8"))


def check_frozen(path, sha):
    if baseline.digest(Path(path)) != sha or json.loads(Path(path).read_text(encoding="utf-8")) != default_config():
        raise ValueError("frozen_config_mismatch")


def contrast_names(config):
    return [f"{a}_minus_{b}" for a, b in config["contrasts"]]


def load_task_configs(config):
    task = event21.load_pinned_config(config["task"]["config"], "event21_config_changed")
    return (task, event21.load_pinned_config(task["event_detector"]["config"], "event20_config_changed"),
            event21.load_pinned_config(task["candidates"]["config"], "regime18_config_changed"))


def quadratic_endpoint(times, series, hz):
    """Position and velocity at the cutoff from a quadratic fit to exactly the samples the baseline admits."""
    state = baseline.fit_prefix(times, series, hz)  # raises with the baseline reason
    pt, px = regime18.admitted_prefix(times, series)
    if not len(pt) or not np.array_equal(px[-1], state["position"]):
        raise ValueError("prefix_selection_mismatch")
    tau = pt - baseline.CUTOFF
    coefficients = np.linalg.lstsq(np.column_stack((np.ones_like(tau), tau, tau ** 2)), px, rcond=None)[0]
    return coefficients[0], coefficients[1], int(len(pt))


def support_audit(ball, player, names, idx, event_index, boundary):
    """PREP-VIS-01: is the separation visible on the keypoints finite at both the previous sample and the event?"""
    distance = event20.ball_hand_distance(ball, player, idx)
    previous = int(np.flatnonzero(np.isfinite(distance[:event_index]))[-1])
    per = {names[j]: np.linalg.norm(player[:, j, :] - ball, axis=1) for j in idx}
    s_prev = sorted(n for n, d in per.items() if np.isfinite(d[previous]))
    s_event = sorted(n for n, d in per.items() if np.isfinite(d[event_index]))
    common = sorted(set(s_prev) & set(s_event))
    nearest_prev = min(s_prev, key=lambda n: (per[n][previous], n))
    out = {"previous_index": previous, "support_previous": s_prev, "support_event": s_event, "common_support": common,
           "nearest_previous": nearest_prev, "nearest_previous_missing_at_event": nearest_prev not in s_event,
           "support_changed": s_prev != s_event, "common_distance_previous_m": None, "common_distance_event_m": None,
           "contact_keypoints": sorted(n for n in s_prev if per[n][previous] <= boundary)}
    if not common:
        out["status"] = "no_common_support"
        return out
    before, after = min(per[n][previous] for n in common), min(per[n][event_index] for n in common)
    out.update(common_distance_previous_m=float(before), common_distance_event_m=float(after),
               status="stable" if before <= boundary < after else "visibility_ambiguous")
    return out


def freeze_row(times_ms, ball, player, names, hz, event_config, rule_config):
    """Event arm (OW-EVENT-21, unchanged) plus the context candidates. Never computes an error."""
    status, event_time, shifted = event21.event_axis(times_ms, ball, player, names, hz, event_config)
    if shifted is None:
        return {"event": status, "event_time_s": None, "arm": {"prefix": status, "targets": {}}, "context": None}
    arm = regime18.freeze_trial(shifted, ball, hz, rule_config)
    out = {"event": status, "event_time_s": event_time, "arm": arm, "context": None}
    if arm["prefix"] != "eligible":
        return out
    event_index = int(np.flatnonzero(times_ms == round(event_time * 1000))[0])
    idx = event20.hand_indices(names)
    boundary = event_config["contact_boundary_radii"] * event20.ball_radius_m(event_config)
    audit = support_audit(ball, player, names, idx, event_index, boundary)
    position, ball_velocity, n_ball = quadratic_endpoint(shifted, ball, hz)
    admitted, rejected = {}, {}
    for name in audit["contact_keypoints"]:
        try:
            _, velocity, n = quadratic_endpoint(shifted, player[:, names.index(name), :], hz)
        except ValueError as exc:
            rejected[name] = str(exc)
        else:
            admitted[name] = {"velocity_m_s": velocity.tolist(), "n_prefix_samples": n}
    hand_velocity = np.mean([v["velocity_m_s"] for v in admitted.values()], axis=0) if admitted else None
    gravity, axis = rule_config["gravity_m_s2"], rule_config["vertical_axis_index"]

    def continue_from(velocity, tau, ballistic):
        p = position + velocity * tau
        if ballistic:
            p = p.copy()
            p[axis] -= 0.5 * gravity * tau ** 2
        return p.tolist()

    predictions = {}
    for horizon, target in arm["targets"].items():
        if target["status"] != "available":
            continue
        tau = target["native_time_s"] - baseline.CUTOFF
        predictions[horizon] = {"ball_endpoint_velocity": continue_from(ball_velocity, tau, False),
                                "ball_endpoint_ballistic": continue_from(ball_velocity, tau, True)}
        if hand_velocity is not None:
            predictions[horizon].update(hand_endpoint_velocity=continue_from(hand_velocity, tau, False),
                                        hand_endpoint_ballistic=continue_from(hand_velocity, tau, True))
    out["context"] = {"support": audit, "ball_endpoint": {"position_m": position.tolist(), "velocity_m_s": ball_velocity.tolist(),
                                                          "n_prefix_samples": n_ball},
                      "hand": {"status": "available" if admitted else "no_admitted_contact_keypoint", "admitted": admitted,
                               "rejected": rejected, "velocity_m_s": None if hand_velocity is None else hand_velocity.tolist()},
                      "predictions_m": predictions}
    return out


def candidate_predictions(frozen, horizon):
    target = frozen["arm"]["targets"][horizon]
    return {**{c: target["predictions_m"][c] for c in BASE}, **frozen["context"]["predictions_m"][horizon]}


def score_row(frozen, reference_for):
    """Errors for every available frozen target; reference_for(horizon, index) supplies the supplied position."""
    if frozen["context"] is None:
        return {}
    scores = {}
    for horizon, target in frozen["arm"]["targets"].items():
        if target["status"] != "available":
            continue
        reference = np.asarray(reference_for(horizon, target["index"]), dtype=float)
        predictions = candidate_predictions(frozen, horizon)
        errors = {c: float(np.linalg.norm(np.asarray(p) - reference)) for c, p in predictions.items()}
        scores[horizon] = {"reference_m": reference.tolist(), "errors_m": errors,
                           "signed_vertical_m": {c: float(p[2] - reference[2]) for c, p in predictions.items()}}
    return scores


def availability(frozen, horizon, config):
    """None when the trial enters the common view at this horizon, otherwise the exact reason."""
    if frozen["context"] is None:
        return frozen["arm"]["prefix"]
    status = frozen["arm"]["targets"][horizon]["status"]
    if status != "available":
        return status
    return None if frozen["context"]["hand"]["status"] == "available" else frozen["context"]["hand"]["status"]


def _signed(values):
    values = np.asarray(values, dtype=float)
    if not values.size:
        return {"n": 0, "mean": None, "median": None, "fraction_below": None}
    return {"n": int(values.size), "mean": float(values.mean()), "median": float(np.median(values)),
            "fraction_below": float(np.mean(values < 0))}


def summarize(rows, config):
    horizons = [str(h) for h in config["horizons_s"]]
    groups = ["all"] + config["groups"]

    def members(group):
        return [r for r in rows if group == "all" or f"{r['session']}/{r['participant']}" == group]

    summary = {"trials": len(rows), "event": dict(Counter(r["frozen"]["event"] for r in rows)),
               "prefix": dict(Counter(r["frozen"]["arm"]["prefix"] for r in rows)),
               "coverage": {g: {"hand": dict(Counter(r["frozen"]["context"]["hand"]["status"] for r in members(g) if r["frozen"]["context"])),
                                "support": dict(Counter(r["frozen"]["context"]["support"]["status"] for r in members(g) if r["frozen"]["context"])),
                                "nearest_previous_missing_at_event": sum(r["frozen"]["context"]["support"]["nearest_previous_missing_at_event"]
                                                                         for r in members(g) if r["frozen"]["context"])}
                            for g in groups}}
    for view in VIEWS:
        cells, labels = {}, {}
        for horizon in horizons:
            chosen_rows = [r for r in rows if availability(r["frozen"], horizon, config) is None
                           and (view == "common" or r["frozen"]["context"]["support"]["status"] == "stable")]
            per_group = {}
            for group in groups:
                chosen = [r for r in chosen_rows if group == "all" or f"{r['session']}/{r['participant']}" == group]
                cell = {"n": len(chosen),
                        "errors_m": {c: regime18._stats([r["scores"][horizon]["errors_m"][c] for r in chosen]) for c in CANDIDATES},
                        "signed_vertical_m": {c: _signed([r["scores"][horizon]["signed_vertical_m"][c] for r in chosen]) for c in CANDIDATES},
                        "paired_m": {}}
                for a, b in config["contrasts"]:
                    values = [r["scores"][horizon]["errors_m"][a] - r["scores"][horizon]["errors_m"][b] for r in chosen]
                    boot = event21.bootstrap_mean(values, config)
                    cell["paired_m"][f"{a}_minus_{b}"] = {**regime18._stats(values), "bootstrap": boot, "label": event21.label(boot)}
                per_group[group] = cell
            cells[horizon] = per_group
            labels[horizon] = {}
            for name in contrast_names(config):
                by_group = {g: per_group[g]["paired_m"][name]["label"] for g in config["groups"]}
                labels[horizon][name] = {"labels_by_group": by_group, "consistency": event21.consistency(by_group)}
        summary[view] = {"horizons": cells, "consistency": labels}
    summary["decision"] = decide(summary)
    return summary


def decide(summary):
    key, control = "hand_endpoint_ballistic_minus_ball_endpoint_ballistic", "ball_endpoint_ballistic_minus_velocity"

    def all_a_lower(view, name):
        entry = summary[view]["consistency"]["0.2"][name]
        return entry["consistency"] == "consistent" and set(entry["labels_by_group"].values()) == {"a_lower"}

    if all_a_lower("common", key) and all_a_lower("support_stable", key):
        label = "hand_context_adds_information"
    elif all_a_lower("common", control):
        label = "ball_endpoint_suffices"
    else:
        label = "mixed"
    return {"label": label, "key": {v: summary[v]["consistency"]["0.2"][key] for v in VIEWS},
            "lag_control": summary["common"]["consistency"]["0.2"][control]}


def cohort_accounting(rows, config):
    out = {}
    for horizon in (str(h) for h in config["horizons_s"]):
        reasons = {r["path"]: availability(r["frozen"], horizon, config) for r in rows}
        for r in rows:
            if (reasons[r["path"]] is None) != (horizon in r["scores"] and set(r["scores"][horizon]["errors_m"]) == set(CANDIDATES)):
                raise ValueError(f"score_availability_mismatch:{r['path']}:{horizon}")
        out[horizon] = reconcile_cohort([r["path"] for r in rows], [p for p, why in reasons.items() if why is None],
                                        [(p, why) for p, why in reasons.items() if why is not None]).as_dict()
    return out


def check_event21_reproduction(rows, frozen_retained, manifest_retained):
    frozen = {r["path"]: r["frozen"]["arms"]["event"] for r in frozen_retained}
    results = {r["path"]: r["scores"]["event"] for r in manifest_retained["results"]}
    reproduced = 0
    for row in rows:
        if row["path"] not in frozen or row["path"] not in results:
            raise ValueError("event21_row_missing:" + row["path"])
        if json.loads(json.dumps(row["frozen"]["arm"])) != frozen[row["path"]]:
            raise ValueError("event21_frozen_arm_not_reproduced:" + row["path"])
        old = results[row["path"]]
        if set(old) != set(row["scores"]):
            raise ValueError("event21_scored_horizons_not_reproduced:" + row["path"])
        for horizon, score in old.items():
            if {c: row["scores"][horizon]["errors_m"][c] for c in BASE} != {c: score["errors_m"][c] for c in BASE}:
                raise ValueError(f"event21_errors_not_reproduced:{row['path']}:{horizon}")
            reproduced += len(BASE)
    return reproduced


def select_examples(rows, inputs, config):
    examples = []
    for group in config["groups"]:
        chosen = sorted((r for r in rows if f"{r['session']}/{r['participant']}" == group and availability(r["frozen"], "0.2", config) is None),
                        key=lambda r: (r["scores"]["0.2"]["errors_m"]["hand_endpoint_ballistic"], r["path"]))
        if not chosen:
            continue
        for role, row in (("representative", chosen[(len(chosen) - 1) // 2]), ("failure", chosen[-1])):
            times_ms, ball, player, names = inputs[row["path"]]
            frozen = row["frozen"]
            since = (times_ms - round(frozen["event_time_s"] * 1000)) / 1000.0
            window = (since >= -EXAMPLE_WINDOW_S[0]) & (since <= EXAMPLE_WINDOW_S[1])
            contact = [names.index(n) for n in frozen["context"]["hand"]["admitted"]]
            hand_z = np.nanmean(player[:, contact, 2], axis=1) if contact else np.full(len(times_ms), np.nan)
            examples.append({"role": role, "path": row["path"], "group": group, "event_time_s": frozen["event_time_s"],
                             "support": frozen["context"]["support"]["status"], "contact_keypoints": sorted(frozen["context"]["hand"]["admitted"]),
                             "time_since_event_s": since[window].tolist(),
                             "ball_z_m": [None if not np.isfinite(v) else float(v) for v in ball[window, 2]],
                             "contact_mean_z_m": [None if not np.isfinite(v) else float(v) for v in hand_z[window]],
                             "prefix_first_time_s": frozen["arm"]["fits"]["prefix_first_time_s"] - baseline.CUTOFF,
                             "targets": {h: {"time_since_event_s": frozen["arm"]["targets"][h]["native_time_s"] - baseline.CUTOFF,
                                             "predictions_z_m": {c: candidate_predictions(frozen, h)[c][2] for c in ("velocity", "ball_endpoint_ballistic", "hand_endpoint_ballistic")},
                                             "errors_m": row["scores"][h]["errors_m"]}
                                         for h in row["scores"]}})
    return examples


def plot_examples(examples, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(len(examples), 1, figsize=(8, 2.4 * len(examples)), squeeze=False)
    markers = {"velocity": ("^", "C2"), "ball_endpoint_ballistic": ("o", "C1"), "hand_endpoint_ballistic": ("D", "C4")}
    for ax, ex in zip(axes[:, 0], examples):
        t = np.asarray(ex["time_since_event_s"], dtype=float)
        z = np.asarray([np.nan if v is None else v for v in ex["ball_z_m"]], dtype=float)
        hz = np.asarray([np.nan if v is None else v for v in ex["contact_mean_z_m"]], dtype=float)
        prefix = (t >= ex["prefix_first_time_s"]) & (t <= 0)
        ax.plot(t[prefix], z[prefix], "k.", ms=4, label="admitted ball prefix")
        ax.plot(t[~prefix], z[~prefix], ".", color="0.65", ms=4, label="supplied ball track (reference)")
        ax.plot(t, hz, "-", color="C0", lw=0.8, label="contact keypoints, mean height")
        first = True
        for target in ex["targets"].values():
            for c, (m, color) in markers.items():
                ax.plot(target["time_since_event_s"], target["predictions_z_m"][c], m, mfc="none", color=color, label=c if first else None)
            first = False
        ax.axvline(0.0, color="k", lw=0.6)
        err = ex["targets"].get("0.2", {}).get("errors_m", {})
        ax.set_title(f"{ex['role']} | {ex['group']} | {ex['path'].rsplit('/', 1)[-1]} | support {ex['support']} | 200 ms error vel "
                     f"{err.get('velocity', float('nan')):.2f} ball-end {err.get('ball_endpoint_ballistic', float('nan')):.2f} "
                     f"hand-end {err.get('hand_endpoint_ballistic', float('nan')):.2f} m", fontsize=7)
        ax.set_ylabel("z (m)", fontsize=7)
        ax.tick_params(labelsize=6)
    axes[0, 0].legend(fontsize=6, loc="upper left", ncol=2)
    axes[-1, 0].set_xlabel("time since detected release event (s); markers = predictions at 50/100/200 ms", fontsize=7)
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


def build_rows(rows_in, root, config, event_config, rule_config, opened):
    rows, inputs = [], {}
    for row in rows_in:
        times_ms, ball, player, names, _, hz = event20.open_admitted(root, row, config, opened)
        names = list(names)
        inputs[row["path"]] = (times_ms, ball, player, names)
        rows.append({"path": row["path"], "session": row["session"], "participant": row["participant"], "hz": hz,
                     "frozen": freeze_row(times_ms, ball, player, names, hz, event_config, rule_config)})
    return rows, inputs


def run(args, report, config):
    _, event_config, rule_config = load_task_configs(config)
    sources = [Path(__file__).resolve(), CONFIG, LAB / config["task"]["config"]["path"], Path(event21.__file__).resolve(),
               Path(event20.__file__).resolve(), Path(regime18.__file__).resolve(), Path(baseline.__file__).resolve(),
               LAB / "configs/experiments/event_release_feasibility_v1.json", LAB / "configs/experiments/regime_stratified_forecast_v1.json",
               LAB / "src/wms/data/mlse_spl.py", LAB / "src/wms/physics/free_throw.py", LAB / "src/wms/evaluation/evidence_contracts.py",
               LAB / "tests/test_context_at_release.py", LAB / "uv.lock", LAB / "pyproject.toml"]
    source_sha = {str(p.relative_to(LAB)): baseline.digest(p) for p in sources}
    report.update(config=config, config_sha256=args.config_sha256, source_sha256=source_sha, numpy=np.__version__, python=sys.version)
    manifest21 = event21.load_retained(config["event21_reproduction"]["manifest"], "event21_evidence_mismatch")
    frozen21 = event21.load_retained(config["event21_reproduction"]["frozen_predictions"], "event21_frozen_evidence_mismatch")
    rows_in = event20.admitted_rows(args.inventory, args.data_root, config)
    root, opened = args.data_root.resolve(), []
    report.update(opened=opened)
    rows, inputs = build_rows(rows_in, root, config, event_config, rule_config, opened)
    frozen_path = args.output / "frozen_predictions.json"
    frozen_path.write_bytes((json.dumps([{k: r[k] for k in ("path", "session", "participant", "hz", "frozen")} for r in rows],
                                        indent=1, allow_nan=False) + "\n").encode("utf-8"))
    frozen_sha = baseline.digest(frozen_path)
    for row in rows:  # scoring starts only after the freeze is on disk and hashed
        ball = inputs[row["path"]][1]
        row["scores"] = score_row(row["frozen"], lambda _h, i, ball=ball: ball[i])
    if baseline.digest(frozen_path) != frozen_sha:
        raise ValueError("frozen_predictions_changed_during_scoring")
    reproduced = check_event21_reproduction(rows, frozen21, manifest21)
    cohort = cohort_accounting(rows, config)
    if any(baseline.digest(root / r["path"]) != r["sha256"] for r in rows_in):
        raise ValueError("input_changed_during_run")
    if source_sha != {str(p.relative_to(LAB)): baseline.digest(p) for p in sources}:
        raise ValueError("source_changed_during_run")
    if any(f"/{pid}/" in p for p in opened for pid in config["not_opened"]):
        raise ValueError("protected_participant_opened")
    examples = select_examples(rows, inputs, config)
    plot_examples(examples, args.output / "examples.png")
    report.update(status=STATUS, trials=len(rows), frozen_predictions_sha256=frozen_sha, reproduced={"event21_candidate_errors": reproduced},
                  cohort=cohort, summary=summarize(rows, config), examples=examples,
                  results=[{"path": r["path"], "session": r["session"], "participant": r["participant"], "scores": r["scores"]} for r in rows],
                  protected_participants_opened=False, input_and_source_unchanged=True,
                  limitation="Development participants only (P0001-P0003), which shaped the detector; OW-EVENT-21's undershoot "
                             "motivated this packet. Agreement with supplied, possibly processed ball and pose tracks, not "
                             "physical accuracy; hand velocity is a kinematic estimate, not a measured causal input. Labels "
                             "are descriptive. P0004 not consulted; P0005 locked.")


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
    (retained_dir / "RETENTION.json").write_bytes((json.dumps({"packet": "OW-CONTEXT-22", "policy": "exact_bytes_gzip",
                                                               "files": files}, indent=2) + "\n").encode("utf-8"))


def verify_retained(retained_dir, config, data_root=None, inventory=None):
    """Digests, config replay, freeze hash, every frozen available target re-scored, summary/decision/cohort rebuilt."""
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
        frozen, stored = frozen_row["frozen"], result["scores"]
        available = set() if frozen["context"] is None else {h for h, t in frozen["arm"]["targets"].items() if t["status"] == "available"}
        for horizon in sorted(set(stored) - available):
            failures.append(f"score_without_available_target:{frozen_row['path']}:{horizon}")
        missing = sorted(available - set(stored))
        failures.extend(f"score_missing:{frozen_row['path']}:{h}" for h in missing)
        if missing or set(stored) - available:
            continue
        # Only the reference position is taken from the retained scores; every derived number is rebuilt.
        rebuilt = score_row(frozen, lambda h, _i: stored[h]["reference_m"])
        for horizon in sorted(available):
            if rebuilt[horizon] != stored[horizon]:
                failures.append(f"score_not_recomputable:{frozen_row['path']}:{horizon}")
        rows.append({**frozen_row, "scores": rebuilt})
    if any(f.startswith(("result_missing:", "score_missing:", "score_without_available_target:")) for f in failures):
        return failures  # the rebuilt rows are incomplete, so summary and cohort cannot be replayed from them
    if summarize(rows, config) != manifest["summary"]:
        failures.append("summary_not_recomputable")
    if cohort_accounting(rows, config) != manifest["cohort"]:
        failures.append("cohort_not_recomputable")
    if data_root is not None:
        _, event_config, rule_config = load_task_configs(config)
        rows_in = event20.admitted_rows(inventory, data_root, config)
        rebuilt_rows, inputs = build_rows(rows_in, Path(data_root).resolve(), config, event_config, rule_config, [])
        retained_frozen = {r["path"]: r for r in frozen_rows}
        for row in rebuilt_rows:
            if json.loads(json.dumps({k: row[k] for k in ("path", "session", "participant", "hz", "frozen")})) != retained_frozen.get(row["path"]):
                failures.append("frozen_not_rederivable:" + row["path"])
                continue
            ball = inputs[row["path"]][1]
            for horizon, stored in results[row["path"]]["scores"].items():
                if stored["reference_m"] != ball[row["frozen"]["arm"]["targets"][horizon]["index"]].tolist():
                    failures.append(f"reference_not_rederivable:{row['path']}:{horizon}")
        if len(rebuilt_rows) != len(frozen_rows):
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
