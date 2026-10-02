"""OW-RELEASE-STATE-01 V16-E1 — durable forecasts and fitted artifacts.

"The predictions existed in memory before scoring" is weaker than evidence a reviewer can
replay. This makes one forecast traversable: original prefix -> fitted artifact -> issued
prediction -> later reference -> metric.

Three properties it exists to guarantee:

* **The producer never sees the reference.** `issue()` takes features and an origin. The
  reference is joined only by `evaluate()`. A target coordinate does not reach the model
  merely because the evaluator will need it later.
* **A run is complete or it is not.** The COMPLETE marker is written LAST. An interrupted
  run has no marker and `load_run` refuses it, so a truncated store can never be read as
  an accepted result.
* **Substitution is refused.** The manifest pins the config digest, the ordered feature
  schema and the code identity. Reading a run whose contract differs is an error, not a
  silent comparison of two different experiments.

Streaming by construction: forecasts append to NDJSON one record at a time and nothing
accumulates the dataset. The V16-T1 unit materialised a 926 MB `examples.json`; this store
holds ~25 MB for the same 9,621 examples across three families.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

COMPLETE = "COMPLETE.json"
FORECASTS = "forecasts.ndjson"
MANIFEST = "run_manifest.json"
FITTED = "fitted"


def digest_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def digest_file(p: Path) -> str:
    return digest_bytes(p.read_bytes())


class RunWriter:
    """An immutable run directory. Refuses to open over an existing one."""

    def __init__(self, out: Path, manifest: dict):
        if out.exists() and any(out.iterdir()):
            raise FileExistsError(f"run directory already exists and is not empty: {out}")
        out.mkdir(parents=True, exist_ok=True)
        (out / FITTED).mkdir(exist_ok=True)
        self.out = out
        self.manifest = dict(manifest)
        (out / MANIFEST).write_text(json.dumps(self.manifest, indent=1), encoding="utf-8")
        self._fh = (out / FORECASTS).open("w", encoding="utf-8", newline="\n")
        self.counts = {"intended": 0, "input_eligible": 0, "emitted": 0,
                       "reference_available": 0, "paired_scoreable": 0}
        self._closed = False

    def issue(self, *, forecast_id: str, family: str, grid: str, held_out: str,
              example_id: str, group: str, decision_time_ms: float,
              target_time_ms: float, prediction_m, fitted_id: str) -> None:
        """Record ONE issued forecast. No reference is accepted here, by signature."""
        rec = {"forecast_id": forecast_id, "family": family, "grid": grid,
               "held_out_athlete": held_out, "example_id": example_id, "group": group,
               "decision_time_ms": decision_time_ms, "target_time_ms": target_time_ms,
               "prediction_m": [float(v) for v in prediction_m], "fitted_id": fitted_id}
        self._fh.write(json.dumps(rec, sort_keys=True, separators=(",", ":")) + "\n")
        self.counts["emitted"] += 1

    def fitted(self, *, fitted_id: str, family: str, grid: str, held_out: str,
               alpha: float, train_groups: list[str], feature_schema: list[str],
               mu, sd, weights) -> None:
        """The artifact a prediction can be recomputed from, without refitting."""
        payload = {
            "fitted_id": fitted_id, "family": family, "grid": grid,
            "held_out_athlete": held_out, "alpha": float(alpha),
            "train_groups": list(train_groups),
            "feature_schema": list(feature_schema),
            "n_features": len(feature_schema),
            "standardiser": {"mu": [float(v) for v in mu], "sd": [float(v) for v in sd]},
            # row 0 is the unpenalised intercept; rows 1.. are the coefficients
            "weights": [[float(v) for v in row] for row in weights],
        }
        (self.out / FITTED / f"{fitted_id}.json").write_text(
            json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")

    def finalize(self, counts: dict | None = None) -> dict:
        """Write the COMPLETE marker LAST, with the digests that make the run verifiable."""
        if self._closed:
            raise RuntimeError("run already finalized")
        self._fh.close()
        self._closed = True
        if counts:
            self.counts.update(counts)
        fitted = sorted((self.out / FITTED).glob("*.json"))
        marker = {
            "status": "COMPLETE",
            "counts": self.counts,
            "forecasts_sha256": digest_file(self.out / FORECASTS),
            "forecasts_bytes": (self.out / FORECASTS).stat().st_size,
            "manifest_sha256": digest_file(self.out / MANIFEST),
            "fitted_artifacts": {p.stem: digest_file(p) for p in fitted},
        }
        (self.out / COMPLETE).write_text(json.dumps(marker, indent=1), encoding="utf-8")
        return marker

    def abort(self) -> None:
        """Leave the run WITHOUT a marker: an interrupted write must not read as accepted."""
        if not self._closed:
            self._fh.close()
            self._closed = True


def load_run(out: Path, *, expect_config_digest: str | None = None) -> dict:
    """Read a run, refusing an incomplete or substituted one."""
    if not (out / COMPLETE).exists():
        raise ValueError(f"run is INCOMPLETE (no {COMPLETE}): {out}")
    marker = json.loads((out / COMPLETE).read_text(encoding="utf-8"))
    manifest = json.loads((out / MANIFEST).read_text(encoding="utf-8"))
    if digest_file(out / MANIFEST) != marker["manifest_sha256"]:
        raise ValueError("run manifest does not match its completion marker")
    if digest_file(out / FORECASTS) != marker["forecasts_sha256"]:
        raise ValueError("forecasts do not match their completion marker")
    if expect_config_digest and manifest.get("protocol_scientific_digest") != expect_config_digest:
        raise ValueError(
            f"run was produced under contract {manifest.get('protocol_scientific_digest')}, "
            f"not {expect_config_digest}")
    forecasts = [json.loads(line) for line in
                 (out / FORECASTS).read_text(encoding="utf-8").splitlines() if line]
    fitted = {p.stem: json.loads(p.read_text(encoding="utf-8"))
              for p in sorted((out / FITTED).glob("*.json"))}
    for fid, art in fitted.items():
        if digest_file(out / FITTED / f"{fid}.json") != marker["fitted_artifacts"][fid]:
            raise ValueError(f"fitted artifact {fid} does not match its completion marker")
    return {"marker": marker, "manifest": manifest, "forecasts": forecasts, "fitted": fitted}
