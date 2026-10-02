"""R6-L: the append-only issue journal (`wms.issue_journal.v1`).

What this is: JSON lines, one per issued record, written once with exclusive create. Every line is canonical JSON
(sorted keys, compact separators, no NaN) and carries its `seq` and the sha256 of the previous line; the final line
is a seal holding the record count. An edited, reordered, inserted or deleted line breaks the chain or the seal, and
a missing seal is refused, so a truncated journal cannot pass as complete.

What this is NOT: protection against someone rewriting the WHOLE file consistently. The run manifest records the
journal's sha256, and the evaluation records the digest it evaluated; those, not the chain, bind a journal to a run.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

SCHEMA = "wms.issue_journal.v1"
GENESIS = "0" * 64


class JournalError(ValueError):
    pass


def canonical(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class JournalWriter:
    """Exclusive-create writer. `append` records in issue order, then `seal` exactly once."""

    def __init__(self, path: Path):
        self._file = open(path, "xb")      # refuses an existing journal: a journal is never rewritten
        self._prev = GENESIS
        self._seq = 0
        self._sealed = False

    def _write(self, obj: dict) -> str:
        line = canonical(obj)
        self._file.write(line + b"\n")
        self._prev = sha256_bytes(line)
        self._seq += 1
        return self._prev

    def append(self, record: dict) -> str:
        if self._sealed:
            raise JournalError("journal_already_sealed")
        return self._write({"schema": SCHEMA, "seq": self._seq, "prev_sha256": self._prev,
                            "kind": "record", "record": record})

    def seal(self) -> str:
        if self._sealed:
            raise JournalError("journal_already_sealed")
        records = self._seq
        last = self._write({"schema": SCHEMA, "seq": self._seq, "prev_sha256": self._prev,
                            "kind": "seal", "records": records})
        self._sealed = True
        self._file.close()
        return last


def read_journal(path: Path) -> list[dict]:
    """Every record of a sealed journal, or a named refusal. Nothing is returned from a journal that fails a check."""
    data = Path(path).read_bytes()
    if not data.endswith(b"\n"):
        raise JournalError("journal_not_newline_terminated")
    lines = data[:-1].split(b"\n")
    prev = GENESIS
    records: list[dict] = []
    for i, line in enumerate(lines):
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            raise JournalError(f"journal_line_unparseable: line {i}") from exc
        if not isinstance(obj, dict):
            raise JournalError(f"journal_line_not_an_object: line {i}")
        if canonical(obj) != line:
            raise JournalError(f"journal_line_not_canonical: line {i}")
        if obj.get("schema") != SCHEMA or obj.get("seq") != i or obj.get("prev_sha256") != prev:
            raise JournalError(f"journal_chain_broken: line {i}")
        prev = sha256_bytes(line)
        if obj.get("kind") == "seal":
            if i != len(lines) - 1:
                raise JournalError(f"journal_line_after_seal: line {i}")
            if obj.get("records") != len(records):
                raise JournalError("journal_seal_count_mismatch")
            return records
        if obj.get("kind") != "record":
            raise JournalError(f"journal_unknown_kind: line {i}")
        if not isinstance(obj.get("record"), dict):
            raise JournalError(f"journal_record_missing_payload: line {i}")
        records.append(obj["record"])
    raise JournalError("journal_not_sealed")
