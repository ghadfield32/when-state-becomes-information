"""OW-RELEASE-STATE-01 Stage 3b — the M4-versus-M3 comparison.

One regularized explicit-state model (closed-form ridge), fitted under matched conditions
for three feature families on IDENTICAL example IDs:

    M3   ball + the 12 core body joints
    M3b  M3 + the coarse hand (thumb, pinky)   <- replaces the proposed wrist ablation,
                                                  which would have duplicated M3 because
                                                  the wrists are already core joints
    M4   M3 + the full finger chain

Everything that could let a family cheat is closed by construction:

* the three families see the SAME rows, so none can look better by dropping hard cases;
* features are prefix-only, formed relative to the decision-sample ball position;
* the target is a DISPLACEMENT, added back afterwards, so no family predicts a coordinate;
* standardisation and alpha selection happen inside the training partition - the held-out
  athlete is never used for selection;
* predictions are stored before any reference is consulted;
* the primary aggregate is the mean of the three ATHLETE means, because overlapping windows
  are not independent and the athletes contribute unequal counts.
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_release_state_dataset import ALLOWED_DIRNAME, build_trial  # noqa: E402
from validate_release_state_protocol import load, validate  # noqa: E402
from forecast_store import RunWriter, digest_bytes  # noqa: E402

FAMILIES = ("M3", "M3b", "M4")


def family_points(config: dict, present: list[str], family: str) -> list[str]:
    """Ordered tracked-point names for a family. M3b and M4 are strict supersets of M3."""
    m3 = [j for j in config["feature_families"]["M3"]["joints"] if j in present]
    if family == "M3":
        return m3
    key = "M3b_hand_coarse" if family == "M3b" else "M4"
    rx = re.compile(config["feature_families"][key]["adds_marker_pattern"])
    return m3 + sorted(n for n in present if rx.search(n) and n not in m3)


def point_series(e: dict, name: str):
    """A tracked point's prefix series, from whichever branch holds it."""
    s = e["prefix"]["m3_joints"].get(name)
    if s is None:
        s = (e["prefix"]["m4_added"] or {}).get(name)
    return s


def features(e: dict, points: list[str]) -> np.ndarray | None:
    """Prefix-only: each point's offset from the decision-sample ball, plus its velocity
    over the final prefix interval. None when any term is unavailable."""
    times = e["prefix"]["times_ms"]
    ball = e["prefix"]["ball_m"]
    if len(times) < 2:
        return None
    dt = times[-1] - times[-2]
    if dt <= 0:
        return None
    origin = np.asarray(ball[-1], dtype=float)
    cols: list[float] = []
    cols.extend(((origin - np.asarray(ball[-2], dtype=float)) / dt).tolist())  # ball velocity
    for name in points:
        s = point_series(e, name)
        if s is None:
            return None
        last = np.asarray(s[-1], dtype=float)
        prev = np.asarray(s[-2], dtype=float)
        cols.extend((last - origin).tolist())
        cols.extend(((last - prev) / dt).tolist())
    return np.asarray(cols, dtype=float)


def ridge_fit(X: np.ndarray, Y: np.ndarray, alpha: float) -> np.ndarray:
    """Closed-form ridge with an unpenalised intercept."""
    n, d = X.shape
    Xb = np.hstack([np.ones((n, 1)), X])
    A = np.eye(d + 1) * alpha
    A[0, 0] = 0.0
    return np.linalg.solve(Xb.T @ Xb + A, Xb.T @ Y)


def ridge_predict(W: np.ndarray, X: np.ndarray) -> np.ndarray:
    return np.hstack([np.ones((X.shape[0], 1)), X]) @ W


def standardise(train: np.ndarray):
    mu = train.mean(axis=0)
    sd = train.std(axis=0)
    sd[sd < 1e-12] = 1.0
    return mu, sd


def collect(config: dict, data_root: Path):
    """Every scored example, with per-family feature vectors on IDENTICAL rows."""
    root = data_root / "basketball" / "freethrow" / "data"
    trials = sorted(p for p in root.glob("*/*/*.json") if ALLOWED_DIRNAME.match(p.parent.name))
    rows = []
    # V16-E1: the funnel is counted, never inferred from the survivors.
    tally = {"intended": 0, "m4_unavailable": 0, "feature_unavailable": 0,
             "input_eligible": 0, "reference_available": 0}
    for t in trials:
        ex, _ = build_trial(t, config)
        for e in ex:
            tally["intended"] += 1
            if not e["m4_available"]:
                tally["m4_unavailable"] += 1
                continue
            present = sorted(list(e["prefix"]["m3_joints"]) + list(e["prefix"]["m4_added"] or {}))
            feats = {}
            ok = True
            for fam in FAMILIES:
                f = features(e, family_points(config, present, fam))
                if f is None:
                    ok = False
                    break
                feats[fam] = f
            if not ok:
                tally["feature_unavailable"] += 1
                continue  # dropped for ALL families together, never for one
            origin = np.asarray(e["prefix"]["ball_m"][-1], dtype=float)
            rows.append({
                # V16-S1: the trial STEM is not unique - 88 of the 396 filenames occur in
                # both the 2024-08-28 and 2025-12-18 sessions. The scored population is
                # single-session today, so the collision is latent rather than active, but
                # an ambiguous example identity is the false-merge hazard, so the session
                # is part of the identity by construction.
                "id": f'{e["source"]["session"]}/{e["source"]["trial"]}#{e["decision"]["index"]}',
                "session": e["source"]["session"],
                "trial": e["source"]["trial"],
                "group": e["group"],
                "present": present,
                "decision_time_ms": e["decision"]["time_ms"],
                "target_time_ms": e["target"]["time_ms"],
                "feats": feats,
                "origin": origin,
                "disp": np.asarray(e["target"]["ball_m"], dtype=float) - origin,
                "ref": np.asarray(e["target"]["ball_m"], dtype=float),
            })
            tally["input_eligible"] += 1
            # A reference exists for every eligible row by construction here; it is counted
            # SEPARATELY so removing a reference later reduces scoreability, not issuance.
            tally["reference_available"] += 1
    return rows, tally


AXES = ("x", "y", "z")


def feature_schema(config: dict, rows: list[dict]) -> dict[str, list[str]]:
    """The ORDERED feature names per family, matching what `features()` actually builds.

    A stored weight vector is meaningless without the order its columns were fitted in, so
    this is written into the run manifest. It is DERIVED from the resolved point set rather
    than restated, and it refuses if the point set is not identical across examples - two
    orderings under one family name would make the artifacts uncomparable.
    """
    if not rows:
        return {fam: [] for fam in FAMILIES}
    present = rows[0]["present"]
    if any(r["present"] != present for r in rows):
        raise ValueError("resolved point set is not identical across examples")
    out = {}
    for fam in FAMILIES:
        names = [f"ball.vel_{a}" for a in AXES]
        for pt in family_points(config, present, fam):
            names += [f"{pt}.off_{a}" for a in AXES] + [f"{pt}.vel_{a}" for a in AXES]
        out[fam] = names
    return out


def run_grid(rows, groups, grid, store=None, grid_name="", schema=None):
    """Fit every family over the outer folds with one alpha grid.

    Returns (predictions, selected alpha) per family. Predictions are produced and stored
    BEFORE any reference is consulted.
    """
    preds = {f: {} for f in FAMILIES}
    chosen = {f: {} for f in FAMILIES}
    for held in groups:
        test = [r for r in rows if r["group"] == held]
        train = [r for r in rows if r["group"] != held]
        inner_groups = sorted({r["group"] for r in train})
        for fam in FAMILIES:
            scores = {}
            for a in grid:
                errs = []
                for vg in inner_groups:  # the held-out athlete never reaches selection
                    itr = [r for r in train if r["group"] != vg]
                    iva = [r for r in train if r["group"] == vg]
                    Xt = np.vstack([r["feats"][fam] for r in itr])
                    Yt = np.vstack([r["disp"] for r in itr])
                    mu, sd = standardise(Xt)
                    W = ridge_fit((Xt - mu) / sd, Yt, a)
                    Xv = (np.vstack([r["feats"][fam] for r in iva]) - mu) / sd
                    P = ridge_predict(W, Xv) + np.vstack([r["origin"] for r in iva])
                    R = np.vstack([r["ref"] for r in iva])
                    errs.append(float(np.mean(np.linalg.norm(P - R, axis=1))))
                scores[a] = statistics.fmean(errs)
            best = min(scores, key=scores.get)
            chosen[fam][held] = best
            Xt = np.vstack([r["feats"][fam] for r in train])
            Yt = np.vstack([r["disp"] for r in train])
            mu, sd = standardise(Xt)
            W = ridge_fit((Xt - mu) / sd, Yt, best)
            Xs = (np.vstack([r["feats"][fam] for r in test]) - mu) / sd
            P = ridge_predict(W, Xs) + np.vstack([r["origin"] for r in test])
            # V16-E1: the fitted artifact is written BEFORE the forecasts it explains, so a
            # forecast can never reference an artifact that was never durably stored.
            fitted_id = f"{grid_name}.{fam}.{held}" if store else ""
            if store is not None:
                store.fitted(fitted_id=fitted_id, family=fam, grid=grid_name, held_out=held,
                             alpha=best, train_groups=sorted({r["group"] for r in train}),
                             feature_schema=(schema or {}).get(fam, []), mu=mu, sd=sd,
                             weights=W)
            for r, pr in zip(test, P):
                preds[fam][r["id"]] = pr
                if store is not None:
                    # Note the signature: no reference is passed. The producer cannot
                    # consult the target even though `r` happens to carry it in memory.
                    store.issue(forecast_id=f"{fitted_id}.{r['id']}", family=fam,
                                grid=grid_name, held_out=held, example_id=r["id"],
                                group=r["group"],
                                decision_time_ms=r["decision_time_ms"],
                                target_time_ms=r["target_time_ms"],
                                prediction_m=pr, fitted_id=fitted_id)
    return preds, chosen


def score(rows, groups, preds, chosen, grid):
    """Join references only now, and summarise."""
    by_id = {r["id"]: r for r in rows}
    err = {f: {g: [] for g in groups} for f in FAMILIES}
    for fam in FAMILIES:
        for rid, pr in preds[fam].items():
            r = by_id[rid]
            err[fam][r["group"]].append(float(np.linalg.norm(pr - r["ref"])))

    def athlete_means(fam):
        return {g: statistics.fmean(err[fam][g]) for g in groups}

    def paired(a, b):
        out = {}
        for g in groups:
            ids = [r["id"] for r in rows if r["group"] == g]
            d = [float(np.linalg.norm(preds[a][i] - by_id[i]["ref"]))
                 - float(np.linalg.norm(preds[b][i] - by_id[i]["ref"])) for i in ids]
            out[g] = {"n": len(d), "mean_m": round(statistics.fmean(d), 6),
                      "median_m": round(statistics.median(d), 6),
                      "share_improved": round(sum(1 for x in d if x < 0) / len(d), 4)}
        out["aggregate_mean_of_athlete_means_m"] = round(
            statistics.fmean([out[g]["mean_m"] for g in groups]), 6)
        return out

    at_max = sum(1 for f in FAMILIES for g in groups if chosen[f][g] == max(grid))
    return {
        "selected_alpha_by_outer_fold": chosen,
        "fits_with_alpha_at_grid_maximum": f"{at_max}/{len(FAMILIES) * len(groups)}",
        "mean_error_m": {f: {g: round(v, 5) for g, v in athlete_means(f).items()} for f in FAMILIES},
        "aggregate_mean_of_athlete_means_m": {
            f: round(statistics.fmean(list(athlete_means(f).values())), 5) for f in FAMILIES},
        "primary_M4_minus_M3": paired("M4", "M3"),
        "secondary_M4_minus_M3b": paired("M4", "M3b"),
        "secondary_M3b_minus_M3": paired("M3b", "M3"),
    }


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", type=Path, required=True)
    ap.add_argument("--data-root", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    # V16-E1: durable per-forecast evidence. Off by default so the accepted reports
    # regenerate byte-identically; the store adds evidence, it changes no number.
    ap.add_argument("--store", type=Path, default=None,
                    help="immutable run directory for individual forecasts and fitted artifacts")
    args = ap.parse_args(argv)

    config = load(args.config)
    refusals = validate(config)
    if refusals:
        print(json.dumps({"status": "BLOCKED", "protocol_refusals": refusals}, indent=1))
        return 2

    rows, tally = collect(config, args.data_root)
    groups = sorted({r["group"] for r in rows})
    sel = config["model"]["selection"]
    grids = {"preregistered": sel["grid_as_preregistered"],
             "amended_RS_A2": sel["grid_amended_RS_A2"]}

    store = None
    if args.store is not None:
        schema = feature_schema(config, rows)
        store = RunWriter(args.store, {
            "packet": config["packet"],
            "protocol_scientific_digest": config["protocol_identity"]["scientific_digest"],
            "config": args.config.name,
            "data_root": str(args.data_root),
            "code_sha256": digest_bytes(Path(__file__).read_bytes()),
            "builder_sha256": digest_bytes(
                (Path(__file__).parent / "build_release_state_dataset.py").read_bytes()),
            "families": list(FAMILIES),
            "feature_schema": schema,
            "seed": config["model"].get("seed"),
            "note": ("Forecasts are issued WITHOUT the reference; references are joined only "
                     "at evaluation. The COMPLETE marker is written last."),
        })

    per_grid = {}
    try:
        for name, grid in grids.items():
            preds, chosen = run_grid(rows, groups, grid, store=store, grid_name=name,
                                     schema=(schema if store else None))
            per_grid[name] = score(rows, groups, preds, chosen, grid)
    except BaseException:
        if store is not None:
            store.abort()   # no COMPLETE marker: an interrupted run is not an accepted one
        raise

    if store is not None:
        # paired_scoreable is the emitted forecasts that found a reference to score
        # against - equal to emitted here, and counted rather than assumed equal.
        marker = store.finalize({
            "intended": tally["intended"],
            "input_eligible": tally["input_eligible"],
            "reference_available": tally["reference_available"],
            "paired_scoreable": store.counts["emitted"],
            "m4_unavailable": tally["m4_unavailable"],
            "feature_unavailable": tally["feature_unavailable"],
        })
        print(json.dumps({"store": str(args.store), "marker_counts": marker["counts"]}, indent=1))

    pre = per_grid["preregistered"]["primary_M4_minus_M3"]["aggregate_mean_of_athlete_means_m"]
    amd = per_grid["amended_RS_A2"]["primary_M4_minus_M3"]["aggregate_mean_of_athlete_means_m"]
    report = {
        "status": "COMPLETE_RELEASE_STATE_EXPERIMENT",
        "packet": config["packet"],
        "protocol_scientific_digest": config["protocol_identity"]["scientific_digest"],
        "horizon_ms": config["target_matching"]["requested_horizon_ms"],
        "scored_examples": len(rows),
        "by_athlete_examples": {g: sum(1 for r in rows if r["group"] == g) for g in groups},
        "feature_dimension": {f: int(rows[0]["feats"][f].shape[0]) for f in FAMILIES},
        "PRIMARY_preregistered_grid": per_grid["preregistered"],
        "amended_RS_A2_grid_reported_alongside": per_grid["amended_RS_A2"],
        "grid_agreement": {
            "preregistered_M4_minus_M3_m": pre,
            "amended_M4_minus_M3_m": amd,
            "aggregate_same_sign": (pre < 0) == (amd < 0),
            # The aggregate agreeing is NOT enough: the pre-registered claim was that M4
            # helped in EVERY athlete. Per-athlete sign agreement is the load-bearing check.
            "per_athlete_sign": {
                g: {"preregistered": per_grid["preregistered"]["primary_M4_minus_M3"][g]["mean_m"],
                    "amended": per_grid["amended_RS_A2"]["primary_M4_minus_M3"][g]["mean_m"],
                    "same_sign": ((per_grid["preregistered"]["primary_M4_minus_M3"][g]["mean_m"] < 0)
                                  == (per_grid["amended_RS_A2"]["primary_M4_minus_M3"][g]["mean_m"] < 0))}
                for g in groups},
            "consistent_in_every_athlete_under_both_grids": all(
                per_grid[k]["primary_M4_minus_M3"][g]["mean_m"] < 0
                for k in per_grid for g in groups),
            "note": ("The pre-registered result is primary and is NOT replaced. The amended grid is "
                     "reported alongside it. If the two disagree in sign, that instability is the "
                     "finding, not a reason to prefer one."),
        },
        "aggregation_rule": config["aggregation"]["primary_aggregate"],
        "not_claimed": ("Predictive incremental value only. No physical explanation, no causal claim, "
                        "no coaching recommendation. Three development athletes do not establish "
                        "uncertainty over future athletes."),
    }
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "experiment_report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps(report, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
