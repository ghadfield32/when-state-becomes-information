"""OW-RELEASE-STATE-01 — the protocol gate.

Stage 1 of the release-state study is a *contract*, not a document: this module refuses a
configuration that would make the M4-versus-M3 comparison unreadable. It reads the frozen
config and returns located refusals; it fits nothing and opens no source data.

The refusals exist because each one has a concrete way of producing a wrong answer:

* **Future flight.** An input taken at or after the decision time makes the "forecast" a
  lookup. Targets must be strictly after, inputs at or before.
* **Mismatched population.** Finger availability is perfectly confounded with session
  (2024-08-28: 125 trials, no fingers; 2025-12-18: 271 trials, all fingers). Scoring M4 on
  the finger subset and M3 on everything attributes a SESSION difference to hands.
* **Protected participants.** P0004/P0005 must never appear.
* **A moved goalpost.** The primary contrast, target, population, horizon and tolerance are
  frozen before fitting; widening the tolerance is how an infeasible horizon gets rescued.
* **Zero-filled missingness.** A missing marker that becomes a zero coordinate is a
  fabricated observation.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

PROTECTED = ("P0004", "P0005")
REQUIRED_TOP = (
    "packet", "participants", "not_opened", "native_timing", "coverage_audit_2026_09_21",
    "primary_comparison", "decision_policy", "target_matching", "splits", "missingness",
    "metrics", "stop_rules", "not_claimed", "prefix", "feature_families",
    "numerical_validity", "amendments", "protocol_identity",
)

# A decision anchored on the release event is retrospective: the system did not know it.
EVENT_ANCHORS = ("release", "event", "apex", "peak", "outcome")


# The keys that define the EXPERIMENT. Changing any of them changes the science, so the
# digest below covers exactly these and nothing else: prose and metrics may be improved
# without re-approval.
# `units` is scientific: an error in metres and the same error in feet are different
# claims. V16-U1 shipped precisely because the digest covered every choice EXCEPT the
# one that decides what the numbers mean. A config without `units` still digests as
# before, so the superseded v1 contract continues to validate unchanged.
SCIENTIFIC_KEYS = ("primary_comparison", "target_matching", "decision_policy", "prefix",
                   "feature_families", "splits", "missingness", "participants", "native_timing",
                   "model", "aggregation", "units")


def scientific_digest(config: dict) -> str:
    """sha256 over a canonical serialisation of the scientific keys."""
    subset = {k: config[k] for k in SCIENTIFIC_KEYS if k in config}
    return hashlib.sha256(json.dumps(subset, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def validate(config: dict) -> list[str]:
    """Return a list of refusals. An empty list means the protocol may be executed."""
    out: list[str] = []

    for key in REQUIRED_TOP:
        if key not in config:
            out.append(f"missing_required_section:{key}")
    if out:
        return out

    # --- the approved experiment is bound by digest, not by the word "immutable" ---
    ident = config["protocol_identity"]
    recorded = ident.get("scientific_digest")
    actual = scientific_digest(config)
    if not recorded:
        out.append("protocol_scientific_digest_absent")
    elif recorded != actual:
        out.append(
            f"protocol_scientific_digest_mismatch:recorded {recorded[:12]}... but the scientific "
            f"keys hash to {actual[:12]}...; a horizon, tolerance, cadence, prefix, feature set, "
            "split, missingness, participant list, timing value, MODEL BUDGET or aggregation rule "
            "was changed after approval"
        )

    # --- protected participants -------------------------------------------------
    for p in PROTECTED:
        if p in config["participants"]:
            out.append(f"protected_participant_in_scope:{p}")
        if p not in config["not_opened"]:
            out.append(f"protected_participant_not_declared_closed:{p}")

    # --- the primary comparison is frozen ---------------------------------------
    pc = config["primary_comparison"]
    if not pc.get("declared_before_results"):
        out.append("primary_comparison_not_declared_before_results")
    if not pc.get("immutable"):
        out.append("primary_comparison_not_marked_immutable")

    # --- M3 and M4 must be scored on the SAME population -------------------------
    audit = config["coverage_audit_2026_09_21"]
    if pc.get("population") != "finger_available":
        out.append(
            "population_mismatch:M4 requires fingers, so M3 must be scored on the same "
            f"finger-available subset ({audit.get('finger_available_trials')} of "
            f"{audit.get('trials_P0001_to_P0003')} trials); otherwise the contrast "
            "confounds hands with session"
        )

    # --- no future flight --------------------------------------------------------
    dp = config["decision_policy"]
    if dp.get("mode") != "fixed_cadence":
        out.append("decision_policy_not_fixed_cadence")
    if dp.get("inputs_available_strictly_at_or_before") != "decision_time_ms":
        out.append("inputs_not_bounded_by_decision_time")
    if dp.get("targets_strictly_after") != "decision_time_ms":
        out.append("targets_not_strictly_after_decision_time")

    # --- the cadence must be SPECIFIED, not merely named -------------------------
    # Without it two implementers build different datasets from the same "frozen" config.
    if dp.get("cadence_samples") is not None:
        out.append("cadence_declared_in_samples:the corpus is mixed-rate, so a sample count means a "
                   "different duration per session; declare cadence_ms instead")
    if dp.get("cadence_ms") is None:
        out.append("decision_cadence_unspecified:fixed_cadence names a mode but not the cadence")
    anchor = str(dp.get("anchor", "")).lower()
    if not anchor:
        out.append("decision_anchor_unspecified")
    elif any(e in anchor for e in EVENT_ANCHORS):
        out.append(f"decision_anchor_is_retrospective:{anchor}; a cadence anchored on a detected "
                   "event smuggles future knowledge into the choice of decision times")

    # --- the prefix must be specified --------------------------------------------
    pf = config["prefix"]
    if pf.get("length_samples") is not None:
        out.append("prefix_declared_in_samples:mixed-rate corpus; declare length_ms instead")
    if not pf.get("length_ms"):
        out.append("prefix_length_unspecified")
    if pf.get("min_finite_fraction") is None:
        out.append("prefix_min_finite_fraction_unspecified")

    # --- M4 must be a strict superset of M3 ---------------------------------------
    # Otherwise a difference could come from REMOVING an M3 input rather than adding hands.
    ff = config["feature_families"]
    if not ff.get("superset_required"):
        out.append("feature_families_do_not_require_M4_superset_of_M3")
    if not ff.get("M3", {}).get("joints"):
        out.append("M3_joint_set_unspecified")
    if not ff.get("M4", {}).get("adds_marker_pattern"):
        out.append("M4_added_markers_unspecified")

    # --- target matching must be feasible on the NATIVE grid ---------------------
    nt = config["native_timing"]
    tm = config["target_matching"]
    # The tolerance must be feasible on the PRIMARY population, not on whichever session
    # happened to be inspected first. v1 failed exactly here (amendment RS-A1).
    measured = nt.get("measured_2026_09_21") or {}
    primary = nt.get("primary_population_session")
    if not measured or not primary:
        out.append("native_timing_not_measured_per_session")
    elif primary not in measured:
        out.append(f"primary_population_session_not_measured:{primary}")
    interval = nt.get("primary_population_dt_ms")
    if not interval:
        out.append("primary_population_interval_absent")
    else:
        tol = tm.get("tolerance_ms")
        if tol is None:
            out.append("target_tolerance_absent")
        elif tol > interval / 2:
            out.append(
                f"target_tolerance_exceeds_native_interval:{tol} > half of {interval:.1f} ms; "
                "above half an interval TWO different samples can satisfy the same horizon, so "
                "the match is ambiguous and a horizon can be rescued by widening the window"
            )
        horizon = tm.get("requested_horizon_ms")
        if horizon is None or horizon <= 0:
            out.append("requested_horizon_absent_or_not_future")

    # --- missingness --------------------------------------------------------------
    mi = config["missingness"]
    if "forbidden" not in mi or "zero" not in mi["forbidden"].lower():
        out.append("missingness_does_not_forbid_zero_filling")

    # --- splits -------------------------------------------------------------------
    sp = config["splits"]
    if sp.get("grouping") != "athlete":
        out.append("splits_not_grouped_by_athlete")
    if sp.get("model_selection") != "inside the training partition only":
        out.append("model_selection_not_confined_to_training_partition")

    # --- claims -------------------------------------------------------------------
    claims = " ".join(config["not_claimed"]).lower()
    for term in ("spin", "contact", "causal"):
        if term not in claims:
            out.append(f"not_claimed_missing_term:{term}")

    return out


def load(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    import argparse
    import sys

    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("config", type=Path)
    args = ap.parse_args(argv)
    refusals = validate(load(args.config))
    print(json.dumps({"status": "PASS" if not refusals else "REFUSED", "refusals": refusals}, indent=1))
    return 0 if not refusals else 1


if __name__ == "__main__":
    raise SystemExit(main())
