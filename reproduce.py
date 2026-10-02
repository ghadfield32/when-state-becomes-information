"""Regenerate every number in the E1 abstract, end to end, with one command.

Runs, in order: the protocol check, the dataset build, the baselines, the ridge experiment
(writes a forecast store), the forecast-store replay check, the six stratum reports, the figures,
and the post hoc trial-cluster interval analysis. Every step must exit 0. Outputs go to
outputs/ (gitignored). Then it compares every regenerated result with the committed reports
and exits non-zero on any mismatch. About 15-20 minutes on a laptop.

    python unpack_data.py      # once
    python reproduce.py
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LAB = ROOT / "docs/backend/projects/world_model/open_world_model"
SPL = LAB / "data/external/SPL-Open-Data"
OUT = ROOT / "outputs"
REP = ROOT / "reports/world_model/v1_2/releasestate01_v1_2"
CFG = "configs/experiments/release_state_v1_2.json"
PY = sys.executable
CONFIGS = [("preregistered", None), ("preregistered", "1.5"), ("preregistered", "3.0"),
           ("amended_RS_A2", None), ("amended_RS_A2", "1.5"), ("amended_RS_A2", "3.0")]

if not (SPL / "basketball/freethrow/data").exists():
    sys.exit("run `python unpack_data.py` first")
OUT.mkdir(exist_ok=True)


def run(args, cwd=LAB, capture=False):
    print("+", " ".join(str(a) for a in args), flush=True)
    r = subprocess.run([PY, *map(str, args)], cwd=cwd, capture_output=capture, text=True, encoding="utf-8")
    if r.returncode != 0:
        if capture:
            print(r.stdout[-2000:], r.stderr[-2000:])
        sys.exit(f"FAILED (exit {r.returncode})")
    return r.stdout if capture else None


store = OUT / "forecast_store"
run(["scripts/validate_release_state_protocol.py", CFG])
run(["scripts/build_release_state_dataset.py", "--config", CFG, "--data-root", SPL, "--out", OUT / "dataset"])
run(["scripts/run_release_state_baselines.py", "--config", CFG, "--data-root", SPL, "--out", OUT / "baselines"])
run(["scripts/run_release_state_experiment.py", "--config", CFG, "--data-root", SPL, "--out", OUT / "experiment", "--store", store])
run(["scripts/verify_release_state_forecasts.py", "--store", store, "--config", CFG, "--data-root", SPL,
     "--report", OUT / "experiment/experiment_report.json", "--tolerance-m", "1e-9"])
for grid, radii in CONFIGS:
    extra = ["--contact-radii", radii] if radii else []
    run(["scripts/stratify_release_state.py", "--store", store, "--config", CFG, "--data-root", SPL,
         "--grid", grid, "--out", OUT / "stratum", *extra])
run(["scripts/plot_release_stratum_figures.py", "--reports", OUT / "stratum", "--out", OUT / "figures"])

raw = []
for grid, radii in CONFIGS:
    tag = "" if radii is None else f"_r{float(radii):g}"
    committed = REP / f"release_stratum_report_{grid}_near100{tag}.json"
    raw.append(run([REP / "interval_analysis/trial_cluster_intervals.py", LAB, store, SPL, grid,
                    radii or "None", committed], cwd=ROOT, capture=True))
(OUT / "RESULTS_RAW.txt").write_text("\n".join(raw), encoding="utf-8")

# compare regenerated numerical results with the committed reports
failures = []


def strip(d):
    """Drop fields that legitimately differ between machines (paths and path-derived digests)."""
    if isinstance(d, dict):
        return {k: strip(v) for k, v in d.items()
                if k not in ("store", "data_root", "store_manifest_sha256", "analysis_identity", "generated_at")}
    if isinstance(d, list):
        return [strip(x) for x in d]
    return d


for name in ("experiment_report.json", "baselines_report.json"):
    sub = "experiment" if name.startswith("experiment") else "baselines"
    if strip(json.loads((OUT / sub / name).read_text(encoding="utf-8"))) != strip(json.loads((REP / name).read_text(encoding="utf-8"))):
        failures.append(name)
for grid, radii in CONFIGS:
    tag = "" if radii is None else f"_r{float(radii):g}"
    name = f"release_stratum_report_{grid}_near100{tag}.json"
    if strip(json.loads((OUT / "stratum" / name).read_text(encoding="utf-8"))["by_stratum"]) != \
            strip(json.loads((REP / name).read_text(encoding="utf-8"))["by_stratum"]):
        failures.append(name)
committed_raw = (REP / "interval_analysis/RESULTS_RAW.txt").read_text(encoding="utf-8").replace("\r\n", "\n").strip()
if (OUT / "RESULTS_RAW.txt").read_text(encoding="utf-8").replace("\r\n", "\n").strip() != committed_raw:
    failures.append("interval_analysis/RESULTS_RAW.txt")

print()
if failures:
    print("FAILED: regenerated results differ from committed:", ", ".join(failures))
    sys.exit(1)
print("OK: experiment, baselines, six stratum reports and the interval analysis all match the committed results")
