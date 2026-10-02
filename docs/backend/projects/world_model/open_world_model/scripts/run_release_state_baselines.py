"""OW-RELEASE-STATE-01 Stage 3a — the transparent baselines.

These are the floor the M4-versus-M3 comparison must beat to mean anything. They use
ONLY the prefix, and they are deliberately simple so nothing can hide in them:

* **held_position** — the ball does not move after the decision.
* **constant_velocity** — the prefix's last finite velocity, extrapolated to the target.
* **quadratic_prefix** — a second-order fit to the prefix, extrapolated. This is NOT a
  gravity model: the coefficient is estimated from the prefix, because a ball still being
  accelerated by the hand is not in free flight and a gravity-only equation does not
  describe that interval.

It streams the dataset builder trial by trial rather than materialising the ~900 MB
example file, and it joins references only AFTER every prediction exists.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_release_state_dataset import ALLOWED_DIRNAME, build_trial  # noqa: E402
from validate_release_state_protocol import load, validate  # noqa: E402


def velocity(times: list[float], pts: list[list[float]]) -> list[float] | None:
    """Last finite velocity in the prefix, m/ms. None when it cannot be formed."""
    if len(pts) < 2:
        return None
    dt = times[-1] - times[-2]
    if dt <= 0:
        return None
    return [(pts[-1][k] - pts[-2][k]) / dt for k in range(3)]


def quadratic(times: list[float], pts: list[list[float]], at: float) -> list[float] | None:
    """Second-order least squares per axis over the prefix, evaluated at `at`.

    The curvature term is ESTIMATED, never set to gravity.
    """
    n = len(times)
    if n < 3:
        return None
    t0 = times[-1]
    x = [t - t0 for t in times]
    out = []
    for k in range(3):
        y = [p[k] for p in pts]
        # normal equations for a quadratic; small and explicit
        s = [sum(v ** p for v in x) for p in range(5)]
        b = [sum(y[i] * x[i] ** p for i in range(n)) for p in range(3)]
        m = [[s[0], s[1], s[2]], [s[1], s[2], s[3]], [s[2], s[3], s[4]]]
        det = (m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1])
               - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
               + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0]))
        if abs(det) < 1e-18:
            return None
        def cof(i, j):
            sub = [[m[r][c] for c in range(3) if c != j] for r in range(3) if r != i]
            return ((-1) ** (i + j)) * (sub[0][0] * sub[1][1] - sub[0][1] * sub[1][0])
        inv = [[cof(j, i) / det for j in range(3)] for i in range(3)]
        coef = [sum(inv[i][j] * b[j] for j in range(3)) for i in range(3)]
        d = at - t0
        out.append(coef[0] + coef[1] * d + coef[2] * d * d)
    return out


BASELINES = ("held_position", "constant_velocity", "quadratic_prefix")


def predict(e: dict) -> dict[str, list[float] | None]:
    times, pts = e["prefix"]["times_ms"], e["prefix"]["ball_m"]
    at = e["target"]["time_ms"]
    v = velocity(times, pts)
    return {
        "held_position": list(pts[-1]),
        "constant_velocity": ([pts[-1][k] + v[k] * (at - times[-1]) for k in range(3)] if v else None),
        "quadratic_prefix": quadratic(times, pts, at),
    }


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", type=Path, required=True)
    ap.add_argument("--data-root", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)

    config = load(args.config)
    refusals = validate(config)
    if refusals:
        print(json.dumps({"status": "BLOCKED", "protocol_refusals": refusals}, indent=1))
        return 2

    root = args.data_root / "basketball" / "freethrow" / "data"
    trials = sorted(p for p in root.glob("*/*/*.json") if ALLOWED_DIRNAME.match(p.parent.name))

    # 1) every prediction is made and stored BEFORE any reference is consulted
    preds: list[tuple[str, dict[str, list[float] | None], list[float]]] = []
    unavailable = {b: 0 for b in BASELINES}
    for t in trials:
        ex, _ = build_trial(t, config)
        for e in ex:
            if not e["m4_available"]:
                continue  # the declared scored population
            p = predict(e)
            for b in BASELINES:
                if p[b] is None:
                    unavailable[b] += 1
            preds.append((e["group"], p, e["target"]["ball_m"]))

    # 2) only now join the references and score
    errs = {b: {} for b in BASELINES}
    for group, p, ref in preds:
        for b in BASELINES:
            if p[b] is None:
                continue
            d = math.dist(p[b], ref)
            errs[b].setdefault(group, []).append(d)

    def summary(v: list[float]) -> dict:
        v = sorted(v)
        return {"n": len(v), "mean_m": round(statistics.fmean(v), 5),
                "median_m": round(statistics.median(v), 5),
                "p90_m": round(v[int(0.9 * (len(v) - 1))], 5)}

    report = {
        "status": "COMPLETE_RELEASE_STATE_BASELINES",
        "packet": config["packet"],
        "protocol_scientific_digest": config["protocol_identity"]["scientific_digest"],
        "population": config["primary_comparison"]["population"],
        "horizon_ms": config["target_matching"]["requested_horizon_ms"],
        "scored_examples": len(preds),
        "baselines": {b: {"pooled": summary([d for g in errs[b] for d in errs[b][g]]),
                          "by_athlete": {g: summary(errs[b][g]) for g in sorted(errs[b])},
                          "unavailable": unavailable[b]}
                      for b in BASELINES},
        "note": ("quadratic_prefix estimates its curvature from the prefix; it is NOT a gravity "
                 "model, because a ball still accelerated by the hand is not in free flight."),
        "not_claimed": "No M3/M4 model is fitted here. These are the floor those models must beat.",
    }
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "baselines_report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps(report, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
