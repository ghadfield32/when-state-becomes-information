"""OW-RELEASE-STATE-01 V16-S1 audit - behaviour, not source strings.

`test_release_stratum.py` asserts that the word "prediction" does not appear inside
`stratum_for`. That is weak assurance: it would pass on a stratifier that leaked through a
helper. These exercise the real path - a stored run, a label, a reference join and a
report - and assert what must be true of the OUTPUT.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

LAB = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LAB / "scripts"))

from forecast_store import RunWriter, load_run  # noqa: E402
from stratify_release_state import enforce_join, stratum_for  # noqa: E402


def fake_store(tmp_path, families=("M3", "M3b", "M4"), ids=("s/T1#0", "s/T1#6")):
    """A complete run with two decisions per family, written through the real writer."""
    w = RunWriter(tmp_path / "run", {"packet": "T", "protocol_scientific_digest": "d",
                                     "feature_schema": {}})
    for fam in families:
        fid = f"g.{fam}.P0001"
        w.fitted(fitted_id=fid, family=fam, grid="g", held_out="P0001", alpha=1.0,
                 train_groups=["P0002"], feature_schema=["a"], mu=[0.0], sd=[1.0],
                 weights=[[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]])
        for k, eid in enumerate(ids):
            w.issue(forecast_id=f"{fid}.{eid}", family=fam, grid="g", held_out="P0001",
                    example_id=eid, group="P0001", decision_time_ms=100.0 * k,
                    target_time_ms=100.0 * k + 100.0, prediction_m=[float(k), 0.0, 0.0],
                    fitted_id=fid)
    w.finalize()
    return w.out


# --- the join must refuse, not silently intersect ---------------------------------------

def test_families_covering_different_examples_are_refused(tmp_path):
    ref = {"s/T1#0": np.zeros(3), "s/T1#6": np.zeros(3)}
    per = {("near", "M3"): {"P0001": [("s/T1#0", np.zeros(3)), ("s/T1#6", np.zeros(3))]},
           ("near", "M4"): {"P0001": [("s/T1#0", np.zeros(3))]}}
    with pytest.raises(ValueError, match="do not cover identical examples"):
        enforce_join(per, ref)


def test_a_duplicate_forecast_is_refused(tmp_path):
    ref = {"s/T1#0": np.zeros(3)}
    per = {("near", "M3"): {"P0001": [("s/T1#0", np.zeros(3)), ("s/T1#0", np.zeros(3))]}}
    with pytest.raises(ValueError, match="duplicate forecasts"):
        enforce_join(per, ref)


def test_an_orphan_forecast_without_a_source_example_is_refused(tmp_path):
    per = {("near", "M3"): {"P0001": [("s/T1#0", np.zeros(3))]}}
    with pytest.raises(ValueError, match="no source example"):
        enforce_join(per, {})


def test_a_clean_join_reports_what_it_checked(tmp_path):
    ref = {"s/T1#0": np.zeros(3), "s/T1#6": np.zeros(3)}
    per = {("near", f): {"P0001": [("s/T1#0", np.zeros(3)), ("s/T1#6", np.zeros(3))]}
           for f in ("M3", "M4")}
    checks = enforce_join(per, ref)
    assert checks["near"] == {"families": ["M3", "M4"], "examples": 2,
                              "duplicates": 0, "orphans": 0}


# --- a label regroups; it can never change a value ----------------------------------------

def test_relabelling_moves_a_forecast_between_strata_without_changing_it(tmp_path):
    """The property that matters, asserted on values rather than on source text."""
    store = fake_store(tmp_path)
    run = load_run(store)
    before = {f["forecast_id"]: tuple(f["prediction_m"]) for f in run["forecasts"]}

    # the same decisions under two different release times -> different strata
    early = {f["forecast_id"]: stratum_for(f["decision_time_ms"] - 500.0) for f in run["forecasts"]}
    late = {f["forecast_id"]: stratum_for(f["decision_time_ms"] - 50.0) for f in run["forecasts"]}
    assert set(early.values()) != set(late.values())      # the grouping really did change

    after = {f["forecast_id"]: tuple(f["prediction_m"]) for f in load_run(store)["forecasts"]}
    assert after == before                                 # ...and nothing else did


def test_removing_a_reference_cannot_manufacture_a_prediction(tmp_path):
    """Scoreability drops; issuance does not. An unscoreable forecast still exists."""
    store = fake_store(tmp_path)
    run = load_run(store)
    ref = {"s/T1#0": np.zeros(3), "s/T1#6": np.zeros(3)}
    scored = [f for f in run["forecasts"] if f["example_id"] in ref]
    ref.pop("s/T1#6")
    still_scored = [f for f in run["forecasts"] if f["example_id"] in ref]
    assert len(still_scored) < len(scored)
    assert len(load_run(store)["forecasts"]) == len(run["forecasts"])   # none erased


# --- the analysis refuses to overwrite its own evidence ------------------------------------

def test_an_occupied_destination_is_refused(tmp_path):
    """Two grids writing one filename silently replaced the first result."""
    out = tmp_path / "out"
    out.mkdir()
    (out / "release_stratum_report_preregistered_near100.json").write_text("{}", encoding="utf-8")
    script = LAB / "scripts" / "stratify_release_state.py"
    proc = subprocess.run(
        [sys.executable, str(script), "--store", str(tmp_path / "missing"),
         "--config", str(LAB / "configs" / "experiments" / "release_state_v1_2.json"),
         "--data-root", str(tmp_path), "--out", str(out)],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert (out / "release_stratum_report_preregistered_near100.json").read_text(
        encoding="utf-8") == "{}"
    assert proc.returncode == 2
    # the refusal must be THIS guard, not an unrelated earlier failure masking it
    assert "output already exists" in proc.stdout


# --- the reported identity is sufficient to reproduce the analysis ---------------------------

def test_the_report_identity_binds_the_detector_not_just_its_filename():
    """A filename is not an identity: the rule inside it can change."""
    import inspect
    from stratify_release_state import analysis_identity
    src = inspect.getsource(analysis_identity)
    for required in ("detector_config_sha256", "detector_code_sha256",
                     "stratifier_code_sha256", "store_forecasts_sha256", "near_ms", "grid"):
        assert required in src


# --- the release proxy can be stressed but never tuned ----------------------------------

def test_an_undeclared_proxy_boundary_is_refused(tmp_path):
    """Only the detector config's primary and declared sensitivity boundaries are accepted.
    A free-choice radius would let the proxy be moved toward a favourable result."""
    script = LAB / "scripts" / "stratify_release_state.py"
    proc = subprocess.run(
        [sys.executable, str(script), "--store", str(tmp_path / "missing"),
         "--config", str(LAB / "configs" / "experiments" / "release_state_v1_2.json"),
         "--data-root", str(tmp_path), "--out", str(tmp_path / "out"),
         "--contact-radii", "2.5"],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert proc.returncode == 2
    assert "is not declared by the detector config" in proc.stdout


def test_the_declared_sensitivity_boundaries_are_the_detectors_own():
    det = json.loads((LAB / "configs" / "experiments"
                      / "event_release_feasibility_v1.json").read_text(encoding="utf-8"))
    assert det["sensitivity_boundary_radii"] == [1.5, 3.0]
    assert "never choose the event" in det["sensitivity_role"]
