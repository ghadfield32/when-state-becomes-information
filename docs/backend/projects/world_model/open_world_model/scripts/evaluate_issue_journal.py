"""OW-R6L-CAUSAL-ISSUANCE-01: evaluate an issue journal LATER, against references matched by the declared policy, and
write the coordinate-free aggregate report.

Usage:
  python scripts/evaluate_issue_journal.py --config configs/experiments/causal_issuance_v1.json \
      --journal-dir <issue run dir> --data-root <SPL-Open-Data checkout> --out <new dir> --report <new report path> \
      [--expect-journal-sha256 <sha>] [--e1-config configs/experiments/release_state_v1_2.json]

Before any record is evaluated, the journal is verified: the manifest digest (and, with --expect-journal-sha256, a
digest pinned from outside the run directory), the hash chain, the seal, the total and per-trial record counts, and
the issuance config. Every source is re-hashed against the issuance manifest. <out>/evaluation.jsonl holds one
outcome per record; it is MLSE-derived and stays outside git. The report holds counts and error summaries only.

With --e1-config the report adds an E1 parity section. E1's own constant-velocity rows are joined to the journal by
(session/trial, decision time). Where E1 had a decision, the causal path must reproduce it exactly. Causal forecasts
E1 never held are listed under E1's OWN refusal reason for that decision. The reason comes from a mirror of the
builder's per-decision checks, and the mirror refuses to run if it disagrees with `build_trial` on any trial.

The builder stops at the FIRST failing check, so a decision refused for its target never reaches E1's later finger
population rule. The mirror therefore also records whether the prefix's finger markers were complete (`m4_complete`)
for every decision that got that far. A future-refused decision is then counted as "future-dependent only" only if
E1's past-only population would have kept it.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

LAB = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LAB / "src"))
sys.path.insert(0, str(LAB / "scripts"))
from wms.issuance import evaluation, stream  # noqa: E402
from wms.issuance.journal import canonical, read_journal  # noqa: E402

CONFIG_SCHEMA = "wms.causal_issuance_config.v1"
# E1's refusal reasons, by what they read. Only the target checks look at a later sample.
E1_PAST_ONLY = ("prefix_before_trial_start", "prefix_ball_incomplete", "prefix_body_incomplete",
                "eligible_m4_unavailable")
E1_FUTURE_DEPENDENT = ("no_target_within_tolerance", "target_not_strictly_after_decision", "target_ball_missing")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def summary(values: list[float]) -> dict:
    v = sorted(values)
    return {"n": len(v), "mean_m": statistics.fmean(v), "median_m": statistics.median(v),
            "p90_m": v[int(0.9 * (len(v) - 1))], "p95_m": v[int(0.95 * (len(v) - 1))]}


def max_abs_difference(values: list[float]) -> float | None:
    """None when nothing was compared; a refusal, never a silent 0.0, when any difference is not finite."""
    if not values:
        return None
    arr = np.asarray(values, dtype=float)
    if not np.all(np.isfinite(arr)):
        raise ValueError("e1_parity_non_finite_difference")
    return float(np.max(np.abs(arr)))


def coverage(outcomes: list[dict]) -> dict:
    kinds = Counter(o["outcome"] for o in outcomes)
    reasons = {k: dict(sorted(Counter(o["reason"] for o in outcomes if o["outcome"] == k).items()))
               for k in ("abstained", "pending", "unscoreable")}
    issued = kinds["scored"] + kinds["pending"] + kinds["unscoreable"]
    return {"opportunities": len(outcomes), "issued": issued, "abstained": kinds["abstained"],
            "scored": kinds["scored"], "pending": kinds["pending"], "unscoreable": kinds["unscoreable"],
            "reasons": reasons}


def error_section(outcomes: list[dict]) -> dict:
    by_athlete = defaultdict(list)
    for o in outcomes:
        if o["outcome"] == "scored":
            by_athlete[o["athlete"]].append(o["error_norm_m"])
    athletes = {a: summary(v) for a, v in sorted(by_athlete.items())}
    pooled = [e for v in by_athlete.values() for e in v]
    return {"by_athlete": athletes,
            "equal_athlete_mean_m": statistics.fmean(s["mean_m"] for s in athletes.values()) if athletes else None,
            "pooled": summary(pooled) if pooled else None}


def e1_decision_reasons(path: Path, config: dict) -> dict:
    """E1's own outcome for every decision of one trial, keyed by decision time: {"reason", "m4_complete"}.
    `reason` is 'eligible', 'eligible_m4_unavailable' (the builder kept it, E1's finger population did not) or the
    builder's refusal reason. `m4_complete` is whether every finger marker was finite over the prefix, or None when
    the builder refused before that is evaluated. The checks run in the builder's order with the builder's own
    helpers, and the result is checked against `build_trial` itself; any disagreement refuses."""
    import build_release_state_dataset as builder
    tracking = json.loads(path.read_text(encoding="utf-8"))["tracking"]
    times = [f["time"] for f in tracking]
    balls = [builder.to_metres(f["data"].get("ball")) for f in tracking]
    players = [{j: builder.to_metres(v) for j, v in f["data"].get("player", {}).items()} for f in tracking]
    m3_joints, m4_added = builder.marker_sets(config, sorted(players[0].keys()) if players else [])
    if config["prefix"].get("selection") != builder.SELECTION_TIMESTAMP:
        raise ValueError("e1_mirror_supports_the_timestamp_prefix_only")
    horizon = config["target_matching"]["requested_horizon_ms"]
    tol = config["target_matching"]["tolerance_ms"]
    out = {}
    for d in range(0, len(tracking), builder.samples_for(times, config["decision_policy"]["cadence_ms"])):
        win = builder.history_window(times, d, config["prefix"]["length_ms"])
        if win is None:
            out[times[d]] = {"reason": "prefix_before_trial_start", "m4_complete": None}
            continue
        idx = win[0]
        if not all(builder.finite3(balls[i]) for i in idx):
            out[times[d]] = {"reason": "prefix_ball_incomplete", "m4_complete": None}
            continue
        if not all(builder.finite3(players[i].get(j)) for i in idx for j in m3_joints):
            out[times[d]] = {"reason": "prefix_body_incomplete", "m4_complete": None}
            continue
        m4_ok = bool(m4_added) and all(builder.finite3(players[i].get(j)) for i in idx for j in m4_added)
        want = times[d] + horizon
        cands = [(abs(times[k] - want), k) for k in range(d + 1, len(times)) if abs(times[k] - want) <= tol]
        if not cands:
            out[times[d]] = {"reason": "no_target_within_tolerance", "m4_complete": m4_ok}
            continue
        t_idx = min(cands)[1]
        if times[t_idx] <= times[d]:
            out[times[d]] = {"reason": "target_not_strictly_after_decision", "m4_complete": m4_ok}
            continue
        if not builder.finite3(balls[t_idx]):
            out[times[d]] = {"reason": "target_ball_missing", "m4_complete": m4_ok}
            continue
        out[times[d]] = {"reason": "eligible" if m4_ok else "eligible_m4_unavailable", "m4_complete": m4_ok}
    examples, refusals = builder.build_trial(path, config)
    mirrored = dict(Counter(v["reason"] for v in out.values() if not v["reason"].startswith("eligible")))
    kept = {t for t, v in out.items() if v["reason"].startswith("eligible")}
    if mirrored != refusals or kept != {e["decision"]["time_ms"] for e in examples}:
        raise ValueError(f"e1_mirror_disagrees_with_build_trial: {path}")
    return out


def e1_parity(e1_config: Path, data_root: Path, manifest: dict, records: list[dict], outcomes: list[dict]) -> dict:
    from run_release_state_experiment import collect           # E1's own row builder, read-only
    from validate_release_state_protocol import load
    config = load(e1_config)
    rows, tally = collect(config, data_root)
    issue_at = {(r["trial"], r["opportunity"]["time_ms"]): r for r in records}
    outcome_of = {o["issue_id"]: o for o in outcomes}
    joined = off_clock = abstained = not_scored = 0
    forecast_diffs, error_diffs = [], []
    e1_err, causal_err = defaultdict(list), defaultdict(list)
    e1_keys, e1_trials = set(), set()
    for row in rows:
        key = (f'{row["session"]}/{row["trial"]}', row["decision_time_ms"])
        e1_keys.add(key)
        e1_trials.add(key[0])
        e1_cv = row["origin"] + np.asarray(row["feats"]["M3"][:3], dtype=float) * (row["target_time_ms"]
                                                                                 - row["decision_time_ms"])
        e1_error = float(np.linalg.norm(e1_cv - row["ref"]))
        e1_err[row["group"]].append(e1_error)
        record = issue_at.get(key)
        if record is None:
            off_clock += 1
            continue
        joined += 1
        if record["forecast"] is None:
            abstained += 1
            continue
        forecast_diffs.extend((np.asarray(record["forecast"]["ball_m"], dtype=float) - e1_cv).tolist())
        outcome = outcome_of[record["issue_id"]]
        if outcome["outcome"] != "scored":
            not_scored += 1
            continue
        causal_err[row["group"]].append(outcome["error_norm_m"])
        error_diffs.append(outcome["error_norm_m"] - e1_error)

    source_of = {t["trial"]: data_root / t["source_path"] for t in manifest["trials"]}
    reasons_of = {trial: e1_decision_reasons(source_of[trial], config) for trial in sorted(e1_trials)}
    by_reason, by_reason_and_outcome, groups = Counter(), Counter(), Counter()
    for r in records:
        key = (r["trial"], r["opportunity"]["time_ms"])
        if r["trial"] not in e1_trials or r["forecast"] is None or key in e1_keys:
            continue
        e1 = reasons_of[r["trial"]].get(key[1], {"reason": "not_an_e1_decision_time", "m4_complete": None})
        reason = e1["reason"]
        m4 = {True: "m4 complete", False: "m4 unavailable", None: "m4 not evaluated"}[e1["m4_complete"]]
        o = outcome_of[r["issue_id"]]
        later = o["outcome"] if o["outcome"] == "scored" else f'{o["outcome"]}:{o["reason"]}'
        by_reason[f"{reason} ({m4})"] += 1
        by_reason_and_outcome[f"{reason} ({m4}) | {later}"] += 1
        if reason in E1_FUTURE_DEPENDENT:
            groups["future_dependent_only" if e1["m4_complete"] else "future_dependent_and_m4_unavailable"] += 1
        elif reason in E1_PAST_ONLY:
            groups["past_only"] += 1
        else:
            groups["other"] += 1

    def means(d):
        return {a: statistics.fmean(v) for a, v in sorted(d.items())}

    return {
        "e1_rows": len(rows), "e1_funnel": tally, "e1_trials": len(e1_trials),
        "joined_on_causal_clock": joined, "e1_rows_off_causal_clock": off_clock,
        "joined_but_causally_abstained": abstained, "joined_but_not_scored": not_scored,
        "max_abs_forecast_difference_m": max_abs_difference(forecast_diffs),
        "max_abs_error_difference_m": max_abs_difference(error_diffs),
        "e1_cv_mean_m_by_athlete": means(e1_err), "causal_cv_mean_m_by_athlete_on_e1_rows": means(causal_err),
        "e1_cv_equal_athlete_mean_m": statistics.fmean(means(e1_err).values()) if e1_err else None,
        "causal_forecasts_in_e1_trials_not_in_e1": {
            "count": sum(by_reason.values()),
            "by_e1_refusal_reason": dict(sorted(by_reason.items())),
            "by_e1_reason_and_later_outcome": dict(sorted(by_reason_and_outcome.items())),
            **{g: groups[g] for g in ("past_only", "future_dependent_only", "future_dependent_and_m4_unavailable",
                                      "other")}},
        "reading": ("Each causal forecast E1 never held is listed under E1's OWN first refusal reason for that "
                    "decision (mirrored from the builder and checked against build_trial per trial), with the prefix's "
                    "finger completeness, and by what later happened to it. 'future_dependent_only' means a check "
                    "that reads a later sample refused it AND E1's past-only finger population would have kept it."),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", type=Path, required=True)
    ap.add_argument("--journal-dir", type=Path, required=True)
    ap.add_argument("--data-root", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True, help="new directory; refused if it exists")
    ap.add_argument("--report", type=Path, required=True, help="new aggregate report file; refused if it exists")
    ap.add_argument("--expect-journal-sha256", default=None,
                    help="journal digest pinned outside the run directory (e.g. from a committed report)")
    ap.add_argument("--e1-config", type=Path, default=None)
    args = ap.parse_args(argv)

    if args.out.exists():
        raise SystemExit("evaluate_output_exists")
    if args.report.exists():
        raise SystemExit("evaluate_report_exists")
    config_bytes = args.config.read_bytes()
    config = json.loads(config_bytes)
    if config.get("schema") != CONFIG_SCHEMA:
        raise SystemExit(f"evaluate_config_schema_mismatch: {config.get('schema')!r}")
    manifest = json.loads((args.journal_dir / "manifest.json").read_bytes())
    if manifest["config_sha256"] != sha256_bytes(config_bytes):
        raise SystemExit("evaluate_config_not_the_issuance_config")
    journal_path = args.journal_dir / "journal.jsonl"
    journal_sha = sha256_bytes(journal_path.read_bytes())
    if journal_sha != manifest["journal_sha256"]:
        raise SystemExit("evaluate_journal_digest_mismatch")
    if args.expect_journal_sha256 is not None and journal_sha != args.expect_journal_sha256:
        raise SystemExit(f"evaluate_journal_not_the_expected_journal: {journal_sha}")
    records = read_journal(journal_path)                      # hash chain + seal, or a named refusal
    if len(records) != manifest["records"]:
        raise SystemExit("evaluate_record_count_mismatch")

    tolerance = config["evaluation"]["tolerance_ms"]
    latency = config["availability"]["declared_latency_ms"]
    by_trial = defaultdict(list)
    for r in records:
        by_trial[r["trial"]].append(r)
    if set(by_trial) - {t["trial"] for t in manifest["trials"]}:
        raise SystemExit("evaluate_journal_holds_an_undeclared_trial")
    for t in manifest["trials"]:
        if len(by_trial.get(t["trial"], [])) != t["records"]:
            raise SystemExit(f"evaluate_trial_record_count_mismatch: {t['trial']}")

    outcomes: list[dict] = []
    for t in manifest["trials"]:
        raw = (args.data_root / t["source_path"]).read_bytes()
        if sha256_bytes(raw) != t["source_sha256"]:
            raise SystemExit(f"evaluate_source_digest_mismatch: {t['source_path']}")
        log = stream.ball_stream_from_bytes(raw, latency)
        trial_outcomes, _ = evaluation.evaluate(by_trial[t["trial"]], log, tolerance, log.close_ms, latency)
        outcomes.extend({**o, "athlete": t["athlete"], "session": t["session"]} for o in trial_outcomes)

    args.out.mkdir(parents=True)
    lines = b"".join(canonical(o) + b"\n" for o in outcomes)
    (args.out / "evaluation.jsonl").write_bytes(lines)
    report = {
        "packet": config["packet"],
        "status": "COMPLETE_CAUSAL_ISSUANCE_EVALUATION",
        "identity": {"journal_sha256": manifest["journal_sha256"], "config_sha256": manifest["config_sha256"],
                     "issuance_code_sha256": manifest["issuance_code_sha256"],
                     "data_revision": manifest["data_revision"], "evaluation_sha256": sha256_bytes(lines)},
        "evaluation_policy": config["evaluation"],
        "coverage": coverage(outcomes),
        "coverage_by_athlete": {a: coverage([o for o in outcomes if o["athlete"] == a])
                                for a in sorted({o["athlete"] for o in outcomes})},
        "coverage_by_session": {s: coverage([o for o in outcomes if o["session"] == s])
                                for s in sorted({o["session"] for o in outcomes})},
        "error": error_section(outcomes),
        "reference_offset_ms_counts": {str(k): v for k, v in sorted(Counter(
            o["reference_offset_ms"] for o in outcomes if o["outcome"] == "scored").items())},
        "not_claimed": config["not_claimed"],
    }
    if args.e1_config is not None:
        report["e1_parity"] = e1_parity(args.e1_config, args.data_root, manifest, records, outcomes)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    with open(args.report, "xb") as fh:
        fh.write((json.dumps(report, sort_keys=True, indent=1, allow_nan=False) + "\n").encode("utf-8"))
    (args.out / "manifest.json").write_bytes((json.dumps(
        {"journal_sha256": manifest["journal_sha256"], "evaluation_sha256": sha256_bytes(lines),
         "report_sha256": sha256_bytes(args.report.read_bytes()), "coverage": report["coverage"]},
        sort_keys=True, indent=1) + "\n").encode("utf-8"))
    parity = report.get("e1_parity")
    print(json.dumps({"status": "OK", "coverage": report["coverage"], "error": report["error"]["equal_athlete_mean_m"],
                      "e1_parity": None if parity is None else {
                          k: parity[k] for k in ("e1_rows", "joined_on_causal_clock", "e1_rows_off_causal_clock",
                                                 "max_abs_forecast_difference_m", "max_abs_error_difference_m",
                                                 "causal_forecasts_in_e1_trials_not_in_e1")}}, indent=1))
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
