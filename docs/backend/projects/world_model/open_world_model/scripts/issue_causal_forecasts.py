"""OW-R6L-CAUSAL-ISSUANCE-01: issue causal constant-velocity forecasts for SPL free-throw trials into an immutable
journal. The journal holds MLSE-derived coordinates: write it outside git.

Usage:
  python scripts/issue_causal_forecasts.py --config configs/experiments/causal_issuance_v1.json \
      --data-root <SPL-Open-Data checkout> --out <new dir>

Writes <out>/journal.jsonl (wms.issue_journal.v1, sealed) and <out>/manifest.json: config sha256, the sha256 of every
issuance module, the data revision, each trial's source path + sha256 + record count, and the journal sha256.
Refuses a protected participant, a dirty or wrong-revision data root, an existing output and a config it does not
recognise. Only the ball stream is read; no reference is looked at here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

LAB = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LAB / "src"))
from wms.issuance import issuer, stream  # noqa: E402
from wms.issuance.journal import JournalWriter  # noqa: E402

CONFIG_SCHEMA = "wms.causal_issuance_config.v1"
PROTECTED = ("P0004", "P0005")
ISSUANCE_CODE = ("src/wms/issuance/stream.py", "src/wms/issuance/causal_state.py", "src/wms/issuance/issuer.py",
                 "src/wms/issuance/journal.py")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git_revision(root: Path) -> tuple[str, bool]:
    head = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], check=True, capture_output=True,
                          text=True).stdout.strip()
    dirty = bool(subprocess.run(["git", "-C", str(root), "status", "--porcelain"], check=True, capture_output=True,
                                text=True).stdout.strip())
    return head, dirty


def trial_paths(data_root: Path, participants: list[str]) -> list[Path]:
    """Development participants only, by directory name. The glob does enumerate a protected participant's directory,
    but its files are filtered out here and never opened."""
    allowed = re.compile("^(" + "|".join(re.escape(p) for p in participants) + ")$")
    root = data_root / "basketball" / "freethrow" / "data"
    return sorted(p for p in root.glob("*/*/*.json") if allowed.match(p.parent.name))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", type=Path, required=True)
    ap.add_argument("--data-root", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True, help="new directory; refused if it exists")
    ap.add_argument("--limit-trials", type=int, default=None, help="first N trials only (smoke runs)")
    args = ap.parse_args(argv)

    config_bytes = args.config.read_bytes()
    config = json.loads(config_bytes)
    if config.get("schema") != CONFIG_SCHEMA:
        raise SystemExit(f"issue_config_schema_mismatch: {config.get('schema')!r}")
    participants = config["source"]["participants"]
    if any(p in PROTECTED for p in participants):
        raise SystemExit(f"issue_protected_participant_in_config: {participants}")
    if args.out.exists():
        raise SystemExit("issue_output_exists")
    revision, dirty = git_revision(args.data_root)
    if dirty:
        raise SystemExit("issue_data_root_not_clean")
    if not revision.startswith(config["source"]["data_revision"]):
        raise SystemExit(f"issue_data_revision_mismatch: {revision} does not start with "
                         f"{config['source']['data_revision']}")

    paths = trial_paths(args.data_root, participants)
    if args.limit_trials:
        paths = paths[: args.limit_trials]
    if not paths:
        raise SystemExit("issue_no_trials")
    cadence = config["opportunities"]["cadence_ms"]
    window = config["state_estimators"]["causal_velocity_v1"]["minimum_history"]["window_ms"]
    horizon = config["target"]["horizon_ms"]
    latency = config["availability"]["declared_latency_ms"]

    args.out.mkdir(parents=True)
    writer = JournalWriter(args.out / "journal.jsonl")
    trials, reasons = [], Counter()
    for path in paths:
        rel = path.relative_to(args.data_root).as_posix()
        if any(p in rel for p in PROTECTED):
            raise SystemExit(f"issue_protected_participant: {rel}")
        raw = path.read_bytes()
        log = stream.ball_stream_from_bytes(raw, latency)
        trial = f"{path.parent.parent.name}/{path.stem}"          # session/trial: stems repeat across sessions
        records = issuer.issue_trial(log, trial, cadence, window, horizon)
        for record in records:
            writer.append(record)
            if record["abstention"] is not None:
                reasons[record["abstention"]["reason"]] += 1
        trials.append({"trial": trial, "athlete": path.parent.name, "session": path.parent.parent.name,
                       "source_path": rel, "source_sha256": sha256_bytes(raw), "records": len(records),
                       "issued": sum(1 for r in records if r["forecast"] is not None),
                       "first_time_ms": log.first_time_ms, "close_ms": log.close_ms})
    writer.seal()

    journal_bytes = (args.out / "journal.jsonl").read_bytes()
    manifest = {
        "packet": config["packet"],
        "journal_schema": "wms.issue_journal.v1",
        "config_sha256": sha256_bytes(config_bytes),
        "issuance_code_sha256": {name: sha256_bytes((LAB / name).read_bytes()) for name in ISSUANCE_CODE},
        "data_revision": revision,
        "forecaster": issuer.FORECASTER_ID,
        "trials": trials,
        "records": sum(t["records"] for t in trials),
        "journal_sha256": sha256_bytes(journal_bytes),
    }
    (args.out / "manifest.json").write_bytes((json.dumps(manifest, sort_keys=True, indent=1) + "\n").encode("utf-8"))
    print(json.dumps({"status": "OK", "out": str(args.out), "trials": len(trials), "records": manifest["records"],
                      "issued": sum(t["issued"] for t in trials), "abstained_by_reason": dict(sorted(reasons.items())),
                      "journal_sha256": manifest["journal_sha256"]}, indent=1))
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
