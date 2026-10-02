"""OW-RELEASE-STATE-01 V16-S1 - the release stratum.

The study issues forecasts at a FIXED CADENCE across the whole trial. That is not a
release-only experiment, and calling it one would be the single largest unsupported claim
available to this paper. This stratifies the ALREADY-ISSUED forecasts by when they fall
relative to the source-supported release event, so the release question can be asked
without changing what was issued.

Two disciplines the design turns on:

* **The stratum is retrospective, and only groups results.** `detect_release` scans the
  whole trial, so the event is known only afterwards. It therefore may NOT decide which
  decisions were issued, only how their errors are reported. A label that selected
  issuance would be an advance-known trigger the system does not have.
* **Nothing is refitted.** Predictions come from the V16-E1 store; this joins a stratum
  label and re-aggregates. A forecast's value cannot change because we grouped it.

The detector is OW-EVENT-21's reviewed rule and its frozen config, reused rather than
reinvented: first evaluable contact -> beyond-boundary transition with ascending vertical
ball velocity, reading only samples at or before the transition.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
from collections import Counter
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_release_state_dataset import ALLOWED_DIRNAME, to_metres  # noqa: E402
from forecast_store import load_run  # noqa: E402
from run_event_release_feasibility import (  # noqa: E402
    ball_hand_distance, ball_radius_m, detect_release, hand_indices, history_ms,
)
from run_release_state_experiment import collect  # noqa: E402
from validate_release_state_protocol import load  # noqa: E402

DETECTOR_CONFIG = "event_release_feasibility_v1.json"

# Strata are named for WHERE THE DECISION SITS relative to the retrospective release proxy,
# not for what we hope to find. They are timing groups only: a live system may forecast at
# any time, but it never has this label in advance, and the proxy certifies neither a held
# ball before it nor uninterrupted flight after it.
STRATA = ("pre_release_far", "pre_release_near", "post_release")
NEAR_MS = 100.0   # "near" is one decision cadence before release


def digest_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def analysis_identity(config_path: Path, det_path: Path, store: Path, args) -> dict:
    """Everything a future session needs to reproduce THIS analysis.

    A detector filename is not an identity: the file can change. The digests of the
    detector config, the detector code and this script are recorded, alongside the store's
    own completion marker, so a changed rule cannot masquerade as the same analysis.
    """
    # this script lives in scripts/, so the detector code sits beside it
    det_code = Path(__file__).resolve().parent / "run_event_release_feasibility.py"
    marker = json.loads((store / "COMPLETE.json").read_text(encoding="utf-8"))
    return {
        "config": config_path.name,
        "config_sha256": digest_bytes(config_path.read_bytes()),
        "detector_config": det_path.name,
        "detector_config_sha256": digest_bytes(det_path.read_bytes()),
        "detector_code_sha256": digest_bytes(det_code.read_bytes()),
        "stratifier_code_sha256": digest_bytes(Path(__file__).read_bytes()),
        "store_forecasts_sha256": marker["forecasts_sha256"],
        "store_manifest_sha256": marker["manifest_sha256"],
        "store_counts": marker["counts"],
        "near_ms": args.near_ms,
        "grid": args.grid,
    }


def enforce_join(per: dict, ref: dict) -> dict:
    """Refuse a silently-intersected join.

    Every family must cover the SAME examples in a stratum. Quietly intersecting them
    would compare families on different rows and call the difference an effect.
    """
    checks = {}
    for stratum in sorted({k[0] for k in per}):
        fams = {k[1] for k in per if k[0] == stratum}
        ids = {}
        for fam in fams:
            flat = [i for g in per[(stratum, fam)] for i, _p in per[(stratum, fam)][g]]
            if len(flat) != len(set(flat)):
                dupes = [i for i in set(flat) if flat.count(i) > 1][:3]
                raise ValueError(f"duplicate forecasts in {stratum}/{fam}: {dupes}")
            ids[fam] = set(flat)
        sizes = {f: len(v) for f, v in ids.items()}
        if len({frozenset(v) for v in ids.values()}) != 1:
            raise ValueError(f"families do not cover identical examples in {stratum}: {sizes}")
        orphans = set().union(*ids.values()) - set(ref)
        if orphans:
            raise ValueError(f"{len(orphans)} forecasts in {stratum} have no source example, "
                             f"e.g. {sorted(orphans)[:3]}")
        checks[stratum] = {"families": sorted(fams), "examples": sizes[sorted(fams)[0]],
                           "duplicates": 0, "orphans": 0}
    return checks


def stratum_for(offset_ms: float, near_ms: float = NEAR_MS) -> str:
    """offset = decision_time - release_time. Negative means the decision precedes release."""
    if offset_ms >= 0.0:
        return "post_release"
    return "pre_release_near" if offset_ms >= -near_ms else "pre_release_far"


def trial_release_time(tracking: list, det: dict,
                       radii: float | None = None) -> tuple[float | None, str]:
    """Release time in ms for one trial, or (None, reason). Missing stays missing."""
    times = np.asarray([f["time"] for f in tracking], dtype=float)
    if len(times) < 2:
        return None, "too_few_samples"
    nan3 = [float("nan")] * 3
    # the SAME unit boundary as the dataset builder (V16-U1): the source publishes feet
    ball = np.asarray([to_metres(f["data"].get("ball")) or nan3 for f in tracking],
                      dtype=float)
    names = sorted(tracking[0]["data"].get("player", {}).keys())
    player = np.asarray(
        [[to_metres(f["data"].get("player", {}).get(n)) or nan3 for n in names]
         for f in tracking], dtype=float)
    deltas = [times[i + 1] - times[i] for i in range(len(times) - 1)]
    hz = 1000.0 / statistics.median(deltas)
    dist = ball_hand_distance(ball, player, hand_indices(names))
    ev = detect_release(times, ball, dist, hz,
                        (det["contact_boundary_radii"] if radii is None else radii)
                        * ball_radius_m(det),
                        history_ms(det), det["vertical_axis_index"])
    if ev["event_index"] is None:
        return None, ev["reason"]
    return float(times[ev["event_index"]]), "event"


def release_times(data_root: Path, det: dict,
                  radii: float | None = None) -> tuple[dict, Counter]:
    """Release time per (session, trial).

    Keyed by SESSION AND TRIAL: 88 of the 396 trial filenames occur in both sessions, so a
    stem-keyed map silently held one session's event under the other's name.
    """
    root = data_root / "basketball" / "freethrow" / "data"
    trials = sorted(p for p in root.glob("*/*/*.json") if ALLOWED_DIRNAME.match(p.parent.name))
    out, reasons = {}, Counter()
    for t in trials:
        tracking = json.loads(t.read_text(encoding="utf-8"))["tracking"]
        ms, reason = trial_release_time(tracking, det, radii)
        reasons[reason] += 1
        if ms is not None:
            out[(t.parent.parent.name, t.stem)] = ms
    return out, reasons


def summarise(values: list[float]) -> dict:
    v = sorted(values)
    return {"n": len(v), "mean_m": round(statistics.fmean(v), 6),
            "median_m": round(statistics.median(v), 6),
            "p90_m": round(v[int(0.9 * (len(v) - 1))], 6)}


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--store", type=Path, required=True)
    ap.add_argument("--config", type=Path, required=True)
    ap.add_argument("--data-root", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--grid", default="preregistered")
    # The near/far boundary is a CHOICE, so it is an argument and its sensitivity is
    # reported rather than a constant buried in the module.
    ap.add_argument("--near-ms", type=float, default=NEAR_MS)
    # Proxy-timing sensitivity. Only the boundaries the detector's REVIEWED config already
    # declares are accepted - its primary and its `sensitivity_boundary_radii` - so the
    # release proxy can be stressed but never tuned toward a favourable result.
    ap.add_argument("--contact-radii", type=float, default=None,
                    help="release-proxy contact boundary in ball radii (declared values only)")
    ap.add_argument("--overwrite", action="store_true",
                    help="deliberately replace an existing report for this grid/boundary")
    args = ap.parse_args(argv)

    config = load(args.config)
    det = json.loads((args.config.parent / DETECTOR_CONFIG).read_text(encoding="utf-8"))

    # Argument refusals come FIRST, before any store or source I/O, so each guard is
    # exercised on its own and cannot be masked by a later failure.
    allowed = [det["contact_boundary_radii"], *det["sensitivity_boundary_radii"]]
    if args.contact_radii is not None and args.contact_radii not in allowed:
        print(json.dumps({"status": "REFUSED",
                          "reason": f"contact radii {args.contact_radii} is not declared by "
                                    f"the detector config; allowed {allowed}"}, indent=1))
        return 2
    radii = det["contact_boundary_radii"] if args.contact_radii is None else args.contact_radii
    tag = "" if radii == det["contact_boundary_radii"] else f"_r{radii:g}"
    dest = args.out / f"release_stratum_report_{args.grid}_near{int(args.near_ms)}{tag}.json"
    # Release evidence: a second grid or boundary must not overwrite the first silently.
    if dest.exists() and not args.overwrite:
        print(json.dumps({"status": "REFUSED", "reason": "output already exists",
                          "path": str(dest),
                          "remedy": "choose another --out, or pass --overwrite deliberately"},
                         indent=1))
        return 2
    run = load_run(args.store,
                   expect_config_digest=config["protocol_identity"]["scientific_digest"])

    rel, reasons = release_times(args.data_root, det, radii)

    per: dict = {}
    unlabelled: Counter = Counter()
    offsets: list[float] = []
    for f in run["forecasts"]:
        if f["grid"] != args.grid:
            continue
        # example_id is "<session>/<trial>#<decision>" - unambiguous by construction
        session, trial = f["example_id"].split("#", 1)[0].split("/", 1)
        if (session, trial) not in rel:
            unlabelled[f["family"]] += 1
            continue
        off = f["decision_time_ms"] - rel[(session, trial)]
        offsets.append(off)
        key = (stratum_for(off, args.near_ms), f["family"])
        per.setdefault(key, {}).setdefault(f["group"], []).append(
            (f["example_id"], np.asarray(f["prediction_m"], dtype=float)))

    # references are joined ONLY now, and only to score - never to choose a stratum
    rows, _tally = collect(config, args.data_root)
    ref = {r["id"]: r["ref"] for r in rows}

    # The baseline belongs in EVERY stratum. Comparing M4 with M3 alone repeats the error
    # this study already made once: a within-family gain means nothing while a transparent
    # baseline beats both. Constant velocity is reconstructed exactly from the stored
    # features - the first three columns ARE the final-interval ball velocity in m/ms, and
    # `origin` is the decision-sample ball - so this is the same definition as
    # `run_release_state_baselines.velocity`, not a re-derivation.
    cv = {}
    for r in rows:
        v = r["feats"]["M3"][:3]
        horizon = r["target_time_ms"] - r["decision_time_ms"]
        cv[r["id"]] = r["origin"] + np.asarray(v, dtype=float) * horizon

    # constant velocity, scored on exactly the rows each stratum contains
    for stratum in sorted({k[0] for k in per}):
        anchor = per[(stratum, "M3")]
        per[(stratum, "constant_velocity")] = {
            g: [(i, cv[i]) for i, _p in v] for g, v in anchor.items()}

    join_checks = enforce_join(per, ref)

    # Coverage the reader needs to judge the smallest stratum: rows are not independent,
    # so the number of distinct TRIALS behind them is reported too.
    coverage = {}
    for stratum in sorted({k[0] for k in per}):
        ids = [i for g in per[(stratum, "M3")] for i, _p in per[(stratum, "M3")][g]]
        coverage[stratum] = {
            "decisions": len(ids),
            "unique_trials": len({i.split("#", 1)[0] for i in ids}),
            "decisions_by_athlete": {g: len(v) for g, v in sorted(per[(stratum, "M3")].items())},
            "unique_trials_by_athlete": {
                g: len({i.split("#", 1)[0] for i, _p in v})
                for g, v in sorted(per[(stratum, "M3")].items())},
        }

    table: dict = {}
    for (stratum, fam), by_group in sorted(per.items()):
        errs = {g: [float(np.linalg.norm(p - ref[i])) for i, p in v]
                for g, v in by_group.items()}
        table.setdefault(stratum, {})[fam] = {
            "pooled": summarise([e for g in errs for e in errs[g]]),
            "by_athlete": {g: summarise(errs[g]) for g in sorted(errs)},
            "equal_athlete_mean_m": round(
                statistics.fmean([statistics.fmean(errs[g]) for g in sorted(errs)]), 6),
        }

    paired: dict = {}
    for stratum in table:
        if not {"M3", "M4"} <= set(table[stratum]):
            continue
        per_group = {}
        groups = sorted(set(per.get((stratum, "M3"), {})) & set(per.get((stratum, "M4"), {})))
        for g in groups:
            m3 = dict(per[(stratum, "M3")][g])
            m4 = dict(per[(stratum, "M4")][g])
            ids = sorted(set(m3) & set(m4))
            if not ids:
                continue
            vals = [float(np.linalg.norm(m4[i] - ref[i]))
                    - float(np.linalg.norm(m3[i] - ref[i])) for i in ids]
            per_group[g] = {"n": len(vals), "mean_m": round(statistics.fmean(vals), 6),
                            "share_improved": round(sum(1 for x in vals if x < 0) / len(vals), 4)}
        if per_group:
            paired[stratum] = dict(
                per_group,
                equal_athlete_mean_m=round(
                    statistics.fmean([v["mean_m"] for v in per_group.values()]), 6))

    report = {
        "status": "COMPLETE_RELEASE_STRATUM",
        "packet": config["packet"] + "-S1",
        "grid": args.grid,
        "protocol_scientific_digest": config["protocol_identity"]["scientific_digest"],
        "store": str(args.store),
        "refitted": False,
        "chronology": (
            "The release event is RETROSPECTIVE: OW-EVENT-21's detector scans the whole "
            "trial. It is used ONLY to group already-issued forecasts. It did not select "
            "which decisions were issued and is not available in advance to a live system."),
        "detector": {"config": DETECTOR_CONFIG, "rule": det["event_rule"],
                     "contact_boundary_radii": det["contact_boundary_radii"],
                     "history_s": det["history_s"]},
        "near_ms": args.near_ms,
        "strata_definition": {
            "pre_release_far": f"decision more than {args.near_ms:.0f} ms before release",
            "pre_release_near": f"decision within {args.near_ms:.0f} ms before release",
            "post_release": "decision at or after the retrospective release proxy",
        },
        "analysis_identity": analysis_identity(args.config, args.config.parent / DETECTOR_CONFIG,
                                               args.store, args),
        "release_proxy": {"contact_boundary_radii": radii,
                          "is_primary": radii == det["contact_boundary_radii"],
                          "role": ("primary event definition" if radii == det["contact_boundary_radii"]
                                   else "declared sensitivity boundary - stresses the proxy, "
                                        "never replaces the primary event")},
        "join_checks": join_checks,
        "coverage": coverage,
        "release_detection": {"trials_with_event": len(rel), "reasons": dict(reasons)},
        "forecasts_unlabelled_no_event": dict(unlabelled),
        "decision_offset_ms": (
            {"n": len(offsets), "min": round(min(offsets), 1), "max": round(max(offsets), 1),
             "median": round(statistics.median(offsets), 1)} if offsets else None),
        "by_stratum": table,
        "paired_M4_minus_M3_by_stratum": paired,
        "boundary_sensitivity_note": (
            "Boundaries REUSE overlapping observations - a wider window contains a "
            "narrower one - so varying near_ms is a sensitivity check, never independent "
            "replication."),
        "detector_coverage_note": (
            "396/396 means a qualifying transition was found in every trial. It does NOT "
            "establish the instant of final fingertip contact: the rule is a geometric "
            "ball-hand boundary plus upward velocity."),
        "live_use_note": (
            "A live system may forecast before or after release. What it cannot have in "
            "advance is this retrospective LABEL; it belongs to evaluation, never to "
            "inference-time selection or routing."),
        "not_claimed": (
            "A stratum difference is an association within this corpus, not a mechanism. "
            "Per-athlete results must be read beside any aggregate: an equal-athlete mean "
            "can favour a model that loses for an individual athlete."),
    }
    args.out.mkdir(parents=True, exist_ok=True)
    dest.write_text(
        json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps({k: report[k] for k in
                      ("status", "release_detection", "decision_offset_ms",
                       "paired_M4_minus_M3_by_stratum")}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
