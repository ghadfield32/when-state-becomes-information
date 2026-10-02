"""OW-RELEASE-STATE-01 V16-S1 - the two publication evidence figures.

Figure 1: equal-athlete error by stratum, every candidate, both grids.
Figure 2: per-athlete near-release contrasts (M4 - constant velocity, M4 - M3) under both
grids AND every declared release-proxy boundary.

Figure 2 exists because the aggregate hides a counterexample: P0003 is worse under M4 than
under constant velocity at every proxy and grid. A figure that showed only the aggregate
would make the paper's strongest number look universal, which it is not.

It reads the stratum reports and draws them. It computes nothing new, so a figure cannot
disagree with the report it came from - and it refuses a report whose contract differs.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

STRATA = ("pre_release_far", "pre_release_near", "post_release")
STRATUM_LABEL = {"pre_release_far": ">100 ms before", "pre_release_near": "≤100 ms before",
                 "post_release": "at/after"}
CANDIDATES = ("constant_velocity", "M3", "M3b", "M4")
ATHLETES = ("P0001", "P0002", "P0003")
GRIDS = ("preregistered", "amended_RS_A2")
RADII = ("1.5", "2.0", "3.0")


def report(folder: Path, grid: str, radii: str) -> dict:
    tag = "" if radii == "2.0" else f"_r{float(radii):g}"
    return json.loads((folder / f"release_stratum_report_{grid}_near100{tag}.json")
                      .read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--reports", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)

    reps = {(g, r): report(args.reports, g, r) for g in GRIDS for r in RADII}
    digests = {rep["protocol_scientific_digest"] for rep in reps.values()}
    if len(digests) != 1:
        print(json.dumps({"status": "REFUSED", "reason": "reports span contracts",
                          "digests": sorted(digests)}, indent=1))
        return 2

    args.out.mkdir(parents=True, exist_ok=True)

    # ---- Figure 1: candidates across strata (primary proxy) ----
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.6), sharey=True)
    width = 0.2
    for ax, g in zip(axes, GRIDS):
        rep = reps[(g, "2.0")]
        for k, cand in enumerate(CANDIDATES):
            vals = [rep["by_stratum"][s][cand]["equal_athlete_mean_m"] * 1000 for s in STRATA]
            xs = [i + (k - 1.5) * width for i in range(len(STRATA))]
            ax.bar(xs, vals, width, label=cand.replace("_", " "))
        ax.set_xticks(range(len(STRATA)))
        ax.set_xticklabels([f"{STRATUM_LABEL[s]}\n(n={rep['coverage'][s]['decisions']:,})"
                            for s in STRATA], fontsize=8)
        ax.set_title(f"{g.replace('_', ' ')} grid", fontsize=9)
        ax.grid(axis="y", alpha=0.3)
    axes[0].set_ylabel("equal-athlete mean endpoint error (mm)")
    axes[1].legend(fontsize=8, frameon=False)
    fig.suptitle("Forecast error at 100 ms by position relative to the retrospective "
                 "release proxy", fontsize=10)
    fig.text(0.5, -0.04, "Strata group already-issued forecasts; the release label is "
             "retrospective and never selected or routed a forecast.",
             ha="center", fontsize=7, style="italic")
    fig.tight_layout()
    fig.savefig(args.out / "fig1_error_by_stratum.png", dpi=200, bbox_inches="tight")
    plt.close(fig)

    # ---- Figure 2: per-athlete near-release contrasts, every grid and proxy ----
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.6))
    contrasts = (("constant_velocity", "M4 − constant velocity"), ("M3", "M4 − M3 (hand contrast)"))
    markers = {"1.5": "v", "2.0": "o", "3.0": "^"}
    colors = {"preregistered": "C0", "amended_RS_A2": "C3"}
    for ax, (ref, title) in zip(axes, contrasts):
        for gi, g in enumerate(GRIDS):
            for ri, r in enumerate(RADII):
                b = reps[(g, r)]["by_stratum"]["pre_release_near"]
                ys = [(b["M4"]["by_athlete"][a]["mean_m"] - b[ref]["by_athlete"][a]["mean_m"])
                      * 1000 for a in ATHLETES]
                xs = [i + (gi - 0.5) * 0.3 + (ri - 1) * 0.08 for i in range(len(ATHLETES))]
                ax.scatter(xs, ys, marker=markers[r], color=colors[g], s=28,
                           label=f"{g.replace('_', ' ')}, {r}r" if ref == "M3" else None)
        ax.axhline(0, color="k", lw=0.8)
        ax.set_xticks(range(len(ATHLETES)))
        ax.set_xticklabels(ATHLETES)
        ax.set_title(title, fontsize=9)
        ax.set_ylabel("difference (mm); below 0 favours M4")
        ax.grid(axis="y", alpha=0.3)
    axes[1].legend(fontsize=6.5, frameon=False, ncol=2)
    fig.suptitle("Near release (≤100 ms before the proxy): per-athlete contrasts under both "
                 "grids and every declared proxy boundary", fontsize=10)
    fig.text(0.5, -0.04, "P0003 is worse under M4 than under constant velocity at every grid "
             "and proxy; the aggregate advantage rests on P0001 and P0002.",
             ha="center", fontsize=7, style="italic")
    fig.tight_layout()
    fig.savefig(args.out / "fig2_per_athlete_near_release.png", dpi=200, bbox_inches="tight")
    plt.close(fig)

    print(json.dumps({"status": "COMPLETE", "contract": digests.pop(),
                      "figures": ["fig1_error_by_stratum.png",
                                  "fig2_per_athlete_near_release.png"]}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
