"""Descriptive trial-cluster intervals for the E1 release-stratum contrasts.

STATUS: post-hoc, descriptive, added after the E1 reports and their independent review.
It refits nothing and changes no forecast. It reuses the committed stratifier's own join and
constant-velocity reconstruction, and it first REPRODUCES the committed report's per-stratum
equal-athlete means (refusing to continue if any differs by more than 1e-5 m).

Resampling unit: whole TRIALS within each athlete (the pre-registration convention used by
OW-ROBUST-VELOCITY-01), 10,000 resamples, numpy default_rng seed 20260929, percentile
interval by sorted order statistic at int(0.025 R) and int(0.975 R). The equal-athlete
interval resamples each athlete independently and averages the three athlete means. It is
CONDITIONAL on these three athletes and says nothing about future athletes.

usage:
  python trial_cluster_intervals.py <lab_dir> <store_dir> <spl_data_root> <grid> <radii|None> <that configuration's committed release_stratum_report.json>
  <lab_dir> is the open_world_model directory of a checkout of the same commit as the store.
"""
import json
import statistics
import sys
from pathlib import Path

import numpy as np

LAB, STORE, DATA = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
GRID = sys.argv[4]
RADII = None if sys.argv[5] == "None" else float(sys.argv[5])
COMMITTED = json.loads(Path(sys.argv[6]).read_text(encoding="utf-8"))
R, SEED = 10000, 20260929
ALL = ("pre_release_far", "pre_release_near", "post_release")

sys.path.insert(0, str(LAB / "scripts"))
sys.stdout.reconfigure(encoding="utf-8")
import stratify_release_state as S  # noqa: E402
from forecast_store import load_run  # noqa: E402
from run_release_state_experiment import collect  # noqa: E402
from validate_release_state_protocol import load  # noqa: E402

config_path = LAB / "configs" / "experiments" / "release_state_v1_2.json"
config = load(config_path)
det = json.loads((config_path.parent / S.DETECTOR_CONFIG).read_text(encoding="utf-8"))
run = load_run(STORE, expect_config_digest=config["protocol_identity"]["scientific_digest"])
rel, _ = S.release_times(DATA, det, RADII)

per = {}
for f in run["forecasts"]:
    if f["grid"] != GRID:
        continue
    session, trial = f["example_id"].split("#", 1)[0].split("/", 1)
    if (session, trial) not in rel:
        continue
    key = (S.stratum_for(f["decision_time_ms"] - rel[(session, trial)], 100.0), f["family"])
    per.setdefault(key, {}).setdefault(f["group"], {})[f["example_id"]] = np.asarray(
        f["prediction_m"], float)

rows, _ = collect(config, DATA)
ref = {r["id"]: r["ref"] for r in rows}
cv = {r["id"]: r["origin"] + np.asarray(r["feats"]["M3"][:3], float)
      * (r["target_time_ms"] - r["decision_time_ms"]) for r in rows}


def pred(st, fam, g, i):
    return cv[i] if fam == "constant_velocity" else per[(st, fam)][g][i]


def err(p, i):
    return float(np.linalg.norm(p - ref[i]))


def reproduce_committed():
    """Every configuration is checked against ITS OWN committed report."""
    worst = 0.0
    for st in ALL:
        for fam in ("constant_velocity", "M3", "M3b", "M4"):
            mine = statistics.fmean([
                statistics.fmean([err(pred(st, fam, g, i), i) for i in per[(st, "M3")][g]])
                for g in sorted(per[(st, "M3")])])
            worst = max(worst, abs(mine - COMMITTED["by_stratum"][st][fam]["equal_athlete_mean_m"]))
    if worst > 1e-5:
        raise SystemExit(f"REFUSED: does not reproduce the committed report (max diff {worst:.2e} m)")
    print(f"reproduces committed equal-athlete means: max abs diff {worst:.2e} m")


def boot(strata, a, b):
    """Paired difference a - b in mm, resampling whole trials within each athlete."""
    groups = sorted(per[(strata[0], "M3")])
    diffs = {}
    for g in groups:
        by_trial = {}
        for st in strata:
            for i in per[(st, "M3")][g]:
                by_trial.setdefault(i.split("#", 1)[0], []).append(
                    err(pred(st, a, g, i), i) - err(pred(st, b, g, i), i))
        diffs[g] = list(by_trial.values())
    rng = np.random.default_rng(SEED)
    boots = {g: np.empty(R) for g in groups}
    for r in range(R):
        for g in groups:
            idx = rng.integers(0, len(diffs[g]), len(diffs[g]))
            pool = [d for k in idx for d in diffs[g][k]]
            boots[g][r] = sum(pool) / len(pool)
    out = {}
    for g in groups:
        pt = statistics.fmean([d for t in diffs[g] for d in t])
        s = np.sort(boots[g])
        out[g] = (pt * 1000, s[int(0.025 * R)] * 1000, s[int(0.975 * R)] * 1000)
    eq = np.sort(sum(boots[g] for g in groups) / len(groups))
    out["EQUAL"] = (statistics.fmean([statistics.fmean([d for t in diffs[g] for d in t])
                                      for g in groups]) * 1000,
                    eq[int(0.025 * R)] * 1000, eq[int(0.975 * R)] * 1000)
    return out


reproduce_committed()
print(f"grid={GRID} release_proxy_radii={'primary' if RADII is None else RADII} "
      f"resamples={R} seed={SEED} unit=trial-within-athlete (mm; negative = first model better)")
jobs = [("near", ("pre_release_near",), a, b) for a, b in
        (("M4", "constant_velocity"), ("M4", "M3"), ("M4", "M3b"), ("M3b", "M3"))]
jobs += [("whole", ALL, "M4", "constant_velocity"),
         ("far", ("pre_release_far",), "M4", "constant_velocity"),
         ("post", ("post_release",), "M4", "constant_velocity")]
for label, strata, a, b in jobs:
    o = boot(strata, a, b)
    print(f"{label:5s} {a}-{b}: " + " | ".join(
        f"{g} {v[0]:+.1f} [{v[1]:+.1f},{v[2]:+.1f}]" for g, v in o.items()), flush=True)
