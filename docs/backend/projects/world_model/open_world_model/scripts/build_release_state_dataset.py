"""OW-RELEASE-STATE-01 Stage 2 — the prefix-only release dataset.

Turns the frozen protocol into examples. It makes NO scientific choice of its own: the
cadence, prefix, horizon, tolerance, population and feature families all come from the
config, and the gate must pass before a single trial is opened.

Three properties it exists to guarantee:

* **Prefix-only.** An input sample is taken at or before the decision time; a target is
  taken strictly after. Nothing downstream of the decision can reach an input.
* **Complete accounting.** Every intended decision is EITHER eligible OR carries an
  explicit refusal reason. Nothing is dropped silently.
* **Missing stays missing.** An incomplete prefix or an unmatched target refuses the
  example. A missing marker never becomes a zero coordinate.

Full-precision native source values only - never the viewer's rounded display arrays.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from validate_release_state_protocol import load, validate  # noqa: E402

from wms.data.mlse_spl import FEET_TO_METERS  # noqa: E402

ALLOWED_DIRNAME = re.compile(r"^P000[123]$")


def to_metres(v):
    """THE unit boundary for this experiment: source feet -> analysis metres, once.

    The SPL source publishes ball and pose coordinates in FEET. Measured on the real
    tree: ball z reaches 13.139 (a free-throw arc peak over a 10 ft rim) and hip z sits
    near 3.296 - 4.0 m and 1.0 m respectively. Read as metres those are absurd.

    Six sibling scripts here already multiply `r["data"]["ball"]` by 0.3048, and
    `wms.data.mlse_spl` defines the constant; this builder was the one consumer of the
    same field that copied feet into fields named `_m`. Every metre-labelled number
    downstream was therefore a foot value.

    Conversion happens HERE and nowhere else, so ball, body and hand coordinates cannot
    diverge. A non-coordinate value is returned unchanged so `finite3` still refuses it
    rather than a fabricated zero appearing in its place.
    """
    if not (isinstance(v, (list, tuple)) and len(v) == 3):
        return v
    return [c * FEET_TO_METERS if isinstance(c, (int, float)) and not isinstance(c, bool)
            else c for c in v]


def finite3(v) -> bool:
    """A coordinate triplet of FINITE REAL numbers.

    `isinstance(c, (int, float))` alone is not enough: NaN and infinity are floats, and
    `bool` is a subclass of `int`, so `True` would pass as a coordinate.
    """
    return (isinstance(v, (list, tuple)) and len(v) == 3
            and all(isinstance(c, (int, float)) and not isinstance(c, bool) and math.isfinite(c)
                    for c in v))


def samples_for(times: list[float], ms: float) -> int:
    """Convert a declared DURATION to samples using this trial's own measured interval.

    The corpus is mixed-rate (33 ms in 2024-08-28, 17 ms in 2025-12-18), so a fixed
    sample count would mean a different duration per session - the defect amendment
    RS-A1 corrects.
    """
    if len(times) < 2:
        return 0
    deltas = sorted(times[i + 1] - times[i] for i in range(len(times) - 1))
    interval = deltas[len(deltas) // 2]
    return max(1, round(ms / interval)) if interval > 0 else 0


SELECTION_SAMPLE_COUNT = "sample_count_from_median_interval"
SELECTION_TIMESTAMP = "timestamp_bound_minimum_history"


def history_window(times: list[float], d: int, length_ms: float):
    """V16-T1: the prefix bound by TIMESTAMPS, not by a sample count.

    A STRIDE of n samples crosses n intervals; a WINDOW of n samples crosses n-1. The
    cadence is a stride, so `samples_for` is correct there. The prefix is a window, so the
    same helper was off by exactly one interval: measured on the real corpus, all 9,621
    scored examples achieved 250.0 ms of history against a declared 267 ms, and none
    reached 267.

    Adding one sample does not fix it. The 60 Hz timestamps are integer-rounded, so the
    intervals alternate 16 and 17 ms; 17 samples span 266.0 ms, still not 267. No sample
    count can enforce a duration on irregular timestamps.

    So this selects the MOST RECENT observation at or before `times[d] - length_ms` and
    keeps every observation through the decision. The achieved span is then always >=
    the declared length, and the overshoot is reported rather than hidden.

    Returns (indices, achieved_span_ms, overshoot_ms), or None when the trial does not
    reach back far enough - an explicit refusal, never a shortened window passed off as a
    full one.
    """
    if d < 0 or d >= len(times):
        return None
    cutoff = times[d] - length_ms
    lo = None
    for i in range(d, -1, -1):
        if times[i] <= cutoff:
            lo = i
            break
    if lo is None:
        return None
    idx = list(range(lo, d + 1))
    achieved = times[d] - times[lo]
    return idx, achieved, achieved - length_ms


def marker_sets(config: dict, present: list[str]) -> tuple[list[str], list[str]]:
    """(M3 joints, markers M4 adds). M4 is M3 plus the pattern; nothing is removed.

    V16-T1: the M3 list used to be INTERSECTED with the first frame's keys, so a declared
    joint missing from frame 0 silently shrank M3 - a different model reported under the
    same family name. Measured across all 396 trials the schema is in fact stable (M3 is
    always the full 12 declared joints and M4 always adds 44 markers), so this has never
    fired and changes no result. It refuses now so it cannot fire unnoticed later.
    """
    declared = config["feature_families"]["M3"]["joints"]
    missing = [j for j in declared if j not in present]
    if missing:
        raise ValueError(f"declared M3 joints absent from the source: {missing}")
    pat = re.compile(config["feature_families"]["M4"]["adds_marker_pattern"])
    added = sorted(n for n in present if pat.search(n) and n not in declared)
    return list(declared), added


def build_trial(path: Path, config: dict) -> tuple[list[dict], dict]:
    """Return (examples, refusal_counts) for one trial. Opens the source read-only."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    tracking = raw["tracking"]
    times = [f["time"] for f in tracking]
    # Converted at the boundary: everything downstream is metres, and the `_m` field
    # names become true. `times` is milliseconds and is NOT a length - never scaled.
    balls = [to_metres(f["data"].get("ball")) for f in tracking]
    players = [{j: to_metres(v) for j, v in f["data"].get("player", {}).items()}
               for f in tracking]
    present = sorted(players[0].keys()) if players else []

    m3_joints, m4_added = marker_sets(config, present)
    prefix_len_ms = config["prefix"]["length_ms"]
    # The rule is declared by the config so an earlier contract stays reproducible: a
    # config with no `selection` is the pre-V16-T1 sample-count rule, byte for byte.
    selection = config["prefix"].get("selection", SELECTION_SAMPLE_COUNT)
    if selection not in (SELECTION_SAMPLE_COUNT, SELECTION_TIMESTAMP):
        raise ValueError(f"unknown prefix.selection {selection!r}")
    prefix_n = samples_for(times, prefix_len_ms)
    # A STRIDE of n samples crosses n intervals, so this one is correct as written.
    cadence = samples_for(times, config["decision_policy"]["cadence_ms"])
    horizon_ms = config["target_matching"]["requested_horizon_ms"]
    tol = config["target_matching"]["tolerance_ms"]

    parts = path.as_posix().split("/")
    session, athlete, trial = parts[-3], parts[-2], path.stem

    examples: list[dict] = []
    refusals: dict[str, int] = {}

    def refuse(reason: str) -> None:
        refusals[reason] = refusals.get(reason, 0) + 1

    for d in range(0, len(tracking), cadence):
        if selection == SELECTION_TIMESTAMP:
            win = history_window(times, d, prefix_len_ms)
            if win is None:
                refuse("prefix_before_trial_start")
                continue
            idx, achieved_span_ms, overshoot_ms = win
        else:
            if d + 1 < prefix_n:
                refuse("prefix_before_trial_start")
                continue
            lo = d + 1 - prefix_n
            idx = list(range(lo, d + 1))
            achieved_span_ms = times[idx[-1]] - times[idx[0]]
            overshoot_ms = achieved_span_ms - prefix_len_ms

        # every input strictly at or before the decision sample
        assert idx[-1] == d

        ball_ok = all(finite3(balls[i]) for i in idx)
        m3_ok = all(finite3(players[i].get(j)) for i in idx for j in m3_joints)
        if not ball_ok:
            refuse("prefix_ball_incomplete")
            continue
        if not m3_ok:
            refuse("prefix_body_incomplete")
            continue
        m4_ok = bool(m4_added) and all(finite3(players[i].get(j)) for i in idx for j in m4_added)

        want = times[d] + horizon_ms
        cands = [(abs(times[k] - want), k) for k in range(d + 1, len(times)) if abs(times[k] - want) <= tol]
        if not cands:
            refuse("no_target_within_tolerance")
            continue
        _, t_idx = min(cands)
        if times[t_idx] <= times[d]:
            refuse("target_not_strictly_after_decision")
            continue
        if not finite3(balls[t_idx]):
            refuse("target_ball_missing")
            continue

        examples.append({
            "source": {"session": session, "athlete": athlete, "trial": trial,
                       "path": path.as_posix().split("SPL-Open-Data/")[-1]},
            "group": athlete,
            "decision": {"index": d, "time_ms": times[d],
                         "last_available_input_time_ms": times[d]},
            "prefix": {"indices": idx, "times_ms": [times[i] for i in idx],
                       # Recorded, not assumed: the declared length is a REQUEST and the
                       # achieved span is what the trial's own timestamps allowed.
                       "declared_length_ms": prefix_len_ms,
                       "achieved_span_ms": achieved_span_ms,
                       "overshoot_ms": overshoot_ms,
                       "selection": selection,
                       "ball_m": [balls[i] for i in idx],
                       "m3_joints": {j: [players[i][j] for i in idx] for j in m3_joints},
                       "m4_added": ({j: [players[i][j] for i in idx] for j in m4_added} if m4_ok else None)},
            "m4_available": m4_ok,
            "target": {"index": t_idx, "time_ms": times[t_idx],
                       "requested_ms": want, "offset_ms": times[t_idx] - want,
                       "ball_m": balls[t_idx],
                       "hand_m": ({j: players[t_idx][j] for j in m4_added
                                   if finite3(players[t_idx].get(j))} if m4_ok else None)},
            "eligible": True,
        })
    return examples, refusals


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", type=Path, required=True)
    ap.add_argument("--data-root", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--limit-trials", type=int, default=None)
    ap.add_argument("--expect-config-sha256", default=None,
                    help="whole-file digest of the approved config; catches an edit that also "
                         "updates the config's own internal scientific digest")
    args = ap.parse_args(argv)

    if args.expect_config_sha256:
        actual = hashlib.sha256(args.config.read_bytes()).hexdigest()
        if actual != args.expect_config_sha256:
            print(json.dumps({"status": "BLOCKED", "protocol_refusals": [
                f"config_file_digest_mismatch:{actual} != expected {args.expect_config_sha256}"]}, indent=1))
            return 2
    config = load(args.config)
    refusals = validate(config)
    if refusals:
        print(json.dumps({"status": "BLOCKED", "protocol_refusals": refusals}, indent=1))
        return 2  # the gate refused; no source is opened

    root = args.data_root / "basketball" / "freethrow" / "data"
    trials = sorted(p for p in root.glob("*/*/*.json") if ALLOWED_DIRNAME.match(p.parent.name))
    if args.limit_trials:
        trials = trials[: args.limit_trials]

    all_ex: list[dict] = []
    agg: dict[str, int] = {}
    per_pop = {"finger_available": 0, "finger_absent": 0}
    for t in trials:
        ex, ref = build_trial(t, config)
        all_ex.extend(ex)
        for k, v in ref.items():
            agg[k] = agg.get(k, 0) + v
        if ex:
            per_pop["finger_available" if ex[0]["m4_available"] else "finger_absent"] += 1

    population = config["primary_comparison"]["population"]
    scored = [e for e in all_ex if e["m4_available"]] if population == "finger_available" else all_ex

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "examples.json").write_text(json.dumps(scored, indent=1), encoding="utf-8")

    report = {
        "status": "COMPLETE_RELEASE_STATE_DATASET",
        "packet": config["packet"],
        "population_scored": population,
        "trials_opened": len(trials),
        "trials_with_fingers": per_pop["finger_available"],
        "trials_without_fingers": per_pop["finger_absent"],
        "examples_total": len(all_ex),
        "examples_scored": len(scored),
        "examples_excluded_by_population": len(all_ex) - len(scored),
        "refusals": dict(sorted(agg.items())),
        "intended_decisions": len(all_ex) + sum(agg.values()),
        "accounting_note": "intended = eligible + refused; every intended decision is one or the other",
        "by_athlete": {a: sum(1 for e in scored if e["group"] == a)
                       for a in sorted({e["group"] for e in scored})},
        "m3_vs_m4_identical_population": True,
        "config_horizon_ms": config["target_matching"]["requested_horizon_ms"],
        "config_tolerance_ms": config["target_matching"]["tolerance_ms"],
        "config_cadence_ms": config["decision_policy"]["cadence_ms"],
        "config_prefix_ms": config["prefix"]["length_ms"],
        "amendments_applied": [a["id"] for a in config.get("amendments", [])],
    }
    (args.out / "coverage_report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps(report, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
