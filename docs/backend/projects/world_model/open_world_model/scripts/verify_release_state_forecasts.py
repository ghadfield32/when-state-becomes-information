"""OW-RELEASE-STATE-01 V16-E1 — replay a stored run without refitting.

Traverses the chain the evidence exists to support:

    original prefix -> fitted artifact -> issued prediction -> later reference -> metric

It refits NOTHING. Each stored forecast is recomputed by applying its own fitted
artifact's standardiser and weights to features rebuilt from the pinned source, and
compared with the prediction that was actually issued. Then the references are joined -
only now - and the aggregate is compared with the accepted report.

A run without its COMPLETE marker, or produced under a different contract digest, is
refused rather than silently verified.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from forecast_store import load_run  # noqa: E402
from run_release_state_experiment import (  # noqa: E402
    FAMILIES, collect, feature_schema,
)
from validate_release_state_protocol import load  # noqa: E402


def recompute(artifact: dict, x: np.ndarray, origin: np.ndarray) -> np.ndarray:
    """Apply a stored artifact. This is arithmetic on saved numbers - no fitting."""
    mu = np.asarray(artifact["standardiser"]["mu"], dtype=float)
    sd = np.asarray(artifact["standardiser"]["sd"], dtype=float)
    W = np.asarray(artifact["weights"], dtype=float)
    z = (x - mu) / sd
    return W[0] + z @ W[1:] + origin


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--store", type=Path, required=True)
    ap.add_argument("--config", type=Path, required=True)
    ap.add_argument("--data-root", type=Path, required=True)
    ap.add_argument("--report", type=Path, default=None,
                    help="an accepted experiment_report.json to reconcile the metric against")
    ap.add_argument("--tolerance-m", type=float, default=1e-9)
    args = ap.parse_args(argv)

    config = load(args.config)
    run = load_run(args.store,
                   expect_config_digest=config["protocol_identity"]["scientific_digest"])

    rows, _tally = collect(config, args.data_root)
    by_id = {r["id"]: r for r in rows}
    schema = feature_schema(config, rows)

    # the ordered schema in the manifest must be the one the features are built in
    for fam in FAMILIES:
        if run["manifest"]["feature_schema"][fam] != schema[fam]:
            print(json.dumps({"status": "REFUSED",
                              "reason": f"feature schema for {fam} differs from the run"}, indent=1))
            return 2

    worst = 0.0
    checked = 0
    err = {}
    for f in run["forecasts"]:
        art = run["fitted"][f["fitted_id"]]
        r = by_id.get(f["example_id"])
        if r is None:
            print(json.dumps({"status": "REFUSED",
                              "reason": f"stored forecast {f['forecast_id']} has no source example"},
                             indent=1))
            return 2
        got = recompute(art, r["feats"][f["family"]], r["origin"])
        d = float(np.max(np.abs(got - np.asarray(f["prediction_m"], dtype=float))))
        worst = max(worst, d)
        checked += 1
        # references joined ONLY now
        err.setdefault((f["grid"], f["family"]), {}).setdefault(f["group"], []).append(
            float(np.linalg.norm(np.asarray(f["prediction_m"], dtype=float) - r["ref"])))

    agg = {f"{g}.{fam}": round(statistics.fmean(
        [statistics.fmean(v) for v in err[(g, fam)].values()]), 5)
        for (g, fam) in sorted(err)}

    out = {
        "status": "REPLAYED" if worst <= args.tolerance_m else "MISMATCH",
        "store": str(args.store),
        "contract_digest": run["manifest"]["protocol_scientific_digest"],
        "forecasts_checked": checked,
        "max_abs_difference_m": worst,
        "tolerance_m": args.tolerance_m,
        "refitted": False,
        "aggregate_mean_of_athlete_means_m_from_store": agg,
        "counts": run["marker"]["counts"],
    }

    if args.report and args.report.exists():
        rep = json.loads(args.report.read_text(encoding="utf-8"))
        want = {"preregistered": rep["PRIMARY_preregistered_grid"],
                "amended_RS_A2": rep["amended_RS_A2_grid_reported_alongside"]}
        recon = {}
        for gname, block in want.items():
            for fam, v in block["aggregate_mean_of_athlete_means_m"].items():
                recon[f"{gname}.{fam}"] = {"report": v, "from_store": agg[f"{gname}.{fam}"],
                                           "equal": v == agg[f"{gname}.{fam}"]}
        out["reconciliation_with_accepted_report"] = recon
        out["reconciles"] = all(x["equal"] for x in recon.values())
        if not out["reconciles"]:
            out["status"] = "MISMATCH"

    print(json.dumps(out, indent=1))
    return 0 if out["status"] == "REPLAYED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
