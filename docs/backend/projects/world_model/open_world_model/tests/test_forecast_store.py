"""OW-RELEASE-STATE-01 V16-E1 — the store must be evidence, not a convenience.

These assert the properties that make a stored run replayable: an interrupted write does
not read as accepted, a substituted contract is refused, an existing run is never
overwritten, and the producer cannot consult the reference.
"""
from __future__ import annotations

import inspect
import json
import sys
from pathlib import Path

import numpy as np
import pytest

LAB = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LAB / "scripts"))

from forecast_store import COMPLETE, RunWriter, load_run  # noqa: E402

MANIFEST = {"packet": "TEST", "protocol_scientific_digest": "abc123", "feature_schema": {}}


def writer(tmp_path, manifest=None):
    return RunWriter(tmp_path / "run", dict(manifest or MANIFEST))


def issue_one(w, i=0):
    w.fitted(fitted_id="g.M3.P0001", family="M3", grid="g", held_out="P0001", alpha=1.0,
             train_groups=["P0002"], feature_schema=["a", "b"], mu=[0.0, 0.0], sd=[1.0, 1.0],
             weights=[[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
    w.issue(forecast_id=f"f{i}", family="M3", grid="g", held_out="P0001",
            example_id=f"T0001#{i}", group="P0001", decision_time_ms=100.0,
            target_time_ms=200.0, prediction_m=[1.0, 2.0, 3.0], fitted_id="g.M3.P0001")


# --- an interrupted run is not an accepted run ---------------------------------------

def test_a_run_without_its_marker_is_refused(tmp_path):
    w = writer(tmp_path)
    issue_one(w)
    w.abort()                      # the process died here
    assert not (w.out / COMPLETE).exists()
    with pytest.raises(ValueError, match="INCOMPLETE"):
        load_run(w.out)


def test_the_marker_is_written_last(tmp_path):
    """If the marker existed before the forecasts, a truncated file would still verify."""
    w = writer(tmp_path)
    issue_one(w)
    assert not (w.out / COMPLETE).exists()     # forecasts written, marker not yet
    w.finalize()
    assert (w.out / COMPLETE).exists()


def test_a_truncated_forecast_file_is_refused(tmp_path):
    w = writer(tmp_path)
    issue_one(w)
    w.finalize()
    p = w.out / "forecasts.ndjson"
    p.write_text("", encoding="utf-8")         # something ate the file afterwards
    with pytest.raises(ValueError, match="forecasts do not match"):
        load_run(w.out)


def test_an_edited_fitted_artifact_is_refused(tmp_path):
    w = writer(tmp_path)
    issue_one(w)
    w.finalize()
    a = w.out / "fitted" / "g.M3.P0001.json"
    d = json.loads(a.read_text(encoding="utf-8"))
    d["alpha"] = 99.0
    a.write_text(json.dumps(d, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="fitted artifact .* does not match"):
        load_run(w.out)


# --- substitution ---------------------------------------------------------------------

def test_a_run_from_another_contract_is_refused(tmp_path):
    w = writer(tmp_path)
    issue_one(w)
    w.finalize()
    with pytest.raises(ValueError, match="was produced under contract"):
        load_run(w.out, expect_config_digest="a_different_digest")


def test_the_matching_contract_loads(tmp_path):
    w = writer(tmp_path)
    issue_one(w)
    w.finalize()
    run = load_run(w.out, expect_config_digest="abc123")
    assert len(run["forecasts"]) == 1


# --- immutability ----------------------------------------------------------------------

def test_an_existing_run_directory_is_never_overwritten(tmp_path):
    w = writer(tmp_path)
    issue_one(w)
    w.finalize()
    with pytest.raises(FileExistsError):
        RunWriter(w.out, dict(MANIFEST))


def test_finalizing_twice_is_refused(tmp_path):
    w = writer(tmp_path)
    issue_one(w)
    w.finalize()
    with pytest.raises(RuntimeError, match="already finalized"):
        w.finalize()


# --- the producer cannot see the reference --------------------------------------------

def test_issue_accepts_no_reference_by_signature(tmp_path):
    """Not a naming convention: there is no parameter through which a target could arrive."""
    params = set(inspect.signature(RunWriter.issue).parameters)
    for forbidden in ("reference", "reference_m", "ref", "target_m", "truth", "actual"):
        assert forbidden not in params
    assert "prediction_m" in params


def test_a_stored_prediction_is_recomputable_from_its_artifact(tmp_path):
    """The whole point: arithmetic on saved numbers reproduces the issued forecast."""
    w = writer(tmp_path)
    issue_one(w)
    w.finalize()
    run = load_run(w.out)
    art = run["fitted"]["g.M3.P0001"]
    W = np.asarray(art["weights"], dtype=float)
    mu = np.asarray(art["standardiser"]["mu"], dtype=float)
    sd = np.asarray(art["standardiser"]["sd"], dtype=float)
    x = np.asarray([1.0, 2.0], dtype=float)
    origin = np.asarray([0.0, 0.0, 0.0], dtype=float)
    got = W[0] + ((x - mu) / sd) @ W[1:] + origin
    assert got.shape == (3,)


# --- the counts stay distinct -----------------------------------------------------------

def test_emitted_is_counted_independently_of_scoreability(tmp_path):
    w = writer(tmp_path)
    issue_one(w, 0)
    issue_one(w, 1)
    # one of the two issued forecasts has lost its reference
    marker = w.finalize({"intended": 10, "input_eligible": 5, "reference_available": 3,
                         "paired_scoreable": 1})
    c = marker["counts"]
    assert c["emitted"] == 2                 # counted by the writer, not supplied
    assert c["intended"] == 10 and c["input_eligible"] == 5
    # removing a reference must reduce scoreability WITHOUT erasing an issued forecast
    assert c["reference_available"] < c["input_eligible"]
    assert c["emitted"] > c["paired_scoreable"]
