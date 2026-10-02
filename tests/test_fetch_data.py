"""Downloader boundary tests; all source responses are synthetic and offline."""
import hashlib
import importlib.util
import io
import itertools
import json
import os
from pathlib import Path
import subprocess

import pytest


PACKAGE = Path(__file__).resolve().parents[1]
GROUPS = [
    ("2024-08-28", "P0001", 125),
    ("2025-12-18", "P0001", 88),
    ("2025-12-18", "P0002", 93),
    ("2025-12-18", "P0003", 90),
]
PAYLOAD = b'{"synthetic": true}\n'


@pytest.fixture
def downloader():
    spec = importlib.util.spec_from_file_location("e1_fetch_data", PACKAGE / "fetch_data.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def manifest(tmp_path, downloader, monkeypatch):
    files = [
        {"path": f"basketball/freethrow/data/{session}/{athlete}/BB_FT_{athlete}_T{i:04d}.json",
         "sha256": hashlib.sha256(PAYLOAD).hexdigest()}
        for session, athlete, count in GROUPS for i in range(1, count + 1)
    ]
    data = {"schema_version": 1,
            "source_repository": "https://github.com/Sport-Performance-Lab/SPL-Open-Data",
            "source_revision": "a3f9cffbde917b1e1747cedd6ec25dfab18c6051",
            "inventory_sha256": "acf8238d98c8296af5d7894a329a4f02e14a81c1002821bf0d45d25830a34c47",
            "files": files}
    path = tmp_path / "manifest.json"
    path.write_bytes((json.dumps(data, indent=2) + "\n").encode())
    monkeypatch.setattr(downloader, "MANIFEST_SHA256", hashlib.sha256(path.read_bytes()).hexdigest())
    return path, data


def no_network(*args, **kwargs):
    pytest.fail("network called before refusal/offline verification")


def repin(module, path, data, monkeypatch):
    """Exercise structural validation independently of the immutable byte pin."""
    path.write_bytes((json.dumps(data, indent=2) + "\n").encode())
    monkeypatch.setattr(module, "MANIFEST_SHA256", hashlib.sha256(path.read_bytes()).hexdigest())


def test_shipped_manifest_validates_without_data_or_network(downloader):
    rows = downloader.load_manifest(PACKAGE / "spl_data/UPSTREAM_FILES.json")
    assert len(rows) == 396
    assert all(set(row) == {"path", "sha256"} for row in rows)


@pytest.mark.parametrize("mutation", [
    "missing", "duplicate", "extra", "escape", "absolute", "backslash", "url",
    "wrong_group", "nested", "bad_hash", "wrong_revision", "extra_metadata", "wrong_schema", "wrong_counts",
])
def test_invalid_complete_manifest_refuses_before_network(
    downloader, manifest, tmp_path, monkeypatch, mutation,
):
    path, data = manifest
    if mutation == "missing":
        data["files"].pop()
    elif mutation == "duplicate":
        data["files"][1] = dict(data["files"][0])
    elif mutation == "extra":
        data["files"].append(dict(data["files"][0]))
    elif mutation == "bad_hash":
        data["files"][0]["sha256"] = "z" * 64
    elif mutation == "wrong_revision":
        data["source_revision"] = "0" * 40
    elif mutation == "extra_metadata":
        data["files"][0]["frames"] = 240
    elif mutation == "wrong_schema":
        data["schema_version"] = True
    elif mutation == "wrong_counts":
        data["files"][0]["path"] = "basketball/freethrow/data/2025-12-18/P0001/BB_FT_P0001_T0999.json"
    else:
        paths = {
            "escape": "basketball/freethrow/data/2024-08-28/P0001/../escape.json",
            "absolute": "/basketball/freethrow/data/2024-08-28/P0001/trial.json",
            "backslash": "basketball\\freethrow\\data\\2024-08-28\\P0001\\trial.json",
            "url": "https://example.test/trial.json",
            "wrong_group": "basketball/freethrow/data/2025-12-18/P0004/BB_FT_P0004_T0001.json",
            "nested": "basketball/freethrow/data/2024-08-28/P0001/sub/trial.json",
        }
        data["files"][0]["path"] = paths[mutation]
    repin(downloader, path, data, monkeypatch)
    monkeypatch.setattr(downloader, "_open_source", no_network)
    dest = tmp_path / "source"
    with pytest.raises(ValueError):
        downloader.acquire(dest, manifest_path=path)
    assert not dest.exists()


def test_changed_manifest_pin_refuses_even_structurally_valid_input(
    downloader, manifest, tmp_path, monkeypatch,
):
    path, data = manifest
    data["files"][0]["sha256"] = "0" * 64
    path.write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setattr(downloader, "_open_source", no_network)
    with pytest.raises(ValueError, match="manifest.*sha256"):
        downloader.acquire(tmp_path / "source", manifest_path=path)


def test_download_verifies_bytes_and_second_run_is_offline(
    downloader, manifest, tmp_path, monkeypatch,
):
    path, data = manifest
    requested = []

    def response(url):
        assert url.startswith("https://raw.githubusercontent.com/Sport-Performance-Lab/SPL-Open-Data/a3f9cffbde917b1e1747cedd6ec25dfab18c6051/")
        requested.append(url)
        return io.BytesIO(PAYLOAD)

    monkeypatch.setattr(downloader, "_open_source", response)
    dest = tmp_path / "source"
    assert downloader.acquire(dest, manifest_path=path) == {"downloaded": 396, "verified": 0}
    assert len(requested) == 396
    assert all((dest / row["path"]).read_bytes() == PAYLOAD for row in data["files"])
    monkeypatch.setattr(downloader, "_open_source", no_network)
    assert downloader.acquire(dest, manifest_path=path) == {"downloaded": 0, "verified": 396}
    assert downloader.acquire(dest, manifest_path=path, verify_only=True) == {"downloaded": 0, "verified": 396}


def test_late_wrong_existing_file_refuses_before_any_fetch(
    downloader, manifest, tmp_path, monkeypatch,
):
    path, data = manifest
    dest = tmp_path / "source"
    wrong = dest / data["files"][-1]["path"]
    wrong.parent.mkdir(parents=True)
    wrong.write_bytes(b"wrong existing bytes")
    monkeypatch.setattr(downloader, "_open_source", no_network)
    with pytest.raises(ValueError, match="sha256"):
        downloader.acquire(dest, manifest_path=path)
    assert wrong.read_bytes() == b"wrong existing bytes"
    assert not (dest / data["files"][0]["path"]).exists()


def test_verify_only_missing_files_never_fetches_or_creates_destination(
    downloader, manifest, tmp_path, monkeypatch,
):
    path, _ = manifest
    dest = tmp_path / "source"
    monkeypatch.setattr(downloader, "_open_source", no_network)
    with pytest.raises(ValueError, match="missing"):
        downloader.acquire(dest, manifest_path=path, verify_only=True)
    assert not dest.exists()


@pytest.mark.parametrize("where", ["root", "group", "file"])
def test_symlink_refuses_before_network(downloader, manifest, tmp_path, monkeypatch, where):
    path, data = manifest
    dest = tmp_path / "source"
    external = tmp_path / "outside"
    external.mkdir()
    target = {"root": dest, "group": dest / Path(data["files"][0]["path"]).parent,
              "file": dest / data["files"][0]["path"]}[where]
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        target.symlink_to(external, target_is_directory=True)
    except OSError as exc:
        if os.name != "nt":
            raise
        # NTFS junctions require no symlink privilege and exercise the same
        # reparse-point refusal on this Windows station.
        escaped_target = str(target).replace("'", "''")
        escaped_external = str(external).replace("'", "''")
        subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                        f"$null = New-Item -ItemType Junction -Path '{escaped_target}' -Target '{escaped_external}' -ErrorAction Stop"],
                       check=True, capture_output=True, text=True)
    monkeypatch.setattr(downloader, "_open_source", no_network)
    with pytest.raises(ValueError, match="link|reparse"):
        downloader.acquire(dest, manifest_path=path)
    assert list(external.iterdir()) == []
    # Remove only the link, never recurse into its external target.
    if target.is_symlink():
        target.unlink()
    else:
        target.rmdir()


def test_existing_hardlink_refuses_before_network(downloader, manifest, tmp_path, monkeypatch):
    path, data = manifest
    external = tmp_path / "outside.json"
    external.write_bytes(PAYLOAD)
    target = tmp_path / "source" / data["files"][0]["path"]
    target.parent.mkdir(parents=True)
    os.link(external, target)
    monkeypatch.setattr(downloader, "_open_source", no_network)
    with pytest.raises(ValueError, match="hardlink"):
        downloader.acquire(tmp_path / "source", manifest_path=path)
    assert external.read_bytes() == PAYLOAD


def test_file_created_during_fetch_is_never_overwritten(downloader, manifest, tmp_path, monkeypatch):
    path, data = manifest
    dest = tmp_path / "source"
    target = dest / data["files"][0]["path"]

    def response(url):
        target.write_bytes(b"concurrent writer")
        return io.BytesIO(PAYLOAD)

    monkeypatch.setattr(downloader, "_open_source", response)
    with pytest.raises(FileExistsError):
        downloader.acquire(dest, manifest_path=path)
    assert target.read_bytes() == b"concurrent writer"
    assert list(dest.rglob("*.part")) == []


def test_deadline_applies_to_response_eof(downloader, manifest, tmp_path, monkeypatch):
    path, data = manifest
    times = itertools.chain([0.0, 0.0], itertools.repeat(121.0))
    monkeypatch.setattr(downloader.time, "monotonic", lambda: next(times))
    monkeypatch.setattr(downloader, "_open_source", lambda url: io.BytesIO(PAYLOAD))
    dest = tmp_path / "source"
    with pytest.raises(ValueError, match="time limit"):
        downloader.acquire(dest, manifest_path=path)
    assert not (dest / data["files"][0]["path"]).exists()
    assert list(dest.rglob("*.part")) == []


@pytest.mark.parametrize("failure", ["digest", "oversize", "transport"])
def test_failed_download_leaves_no_committed_or_temporary_file(
    downloader, manifest, tmp_path, monkeypatch, failure,
):
    path, data = manifest
    if failure == "oversize":
        monkeypatch.setattr(downloader, "MAX_FILE_BYTES", len(PAYLOAD) - 1)

    def response(url):
        if failure == "transport":
            raise TimeoutError("synthetic timeout")
        return io.BytesIO(b"digest mismatch" if failure == "digest" else PAYLOAD)

    monkeypatch.setattr(downloader, "_open_source", response)
    dest = tmp_path / "source"
    with pytest.raises((ValueError, TimeoutError)):
        downloader.acquire(dest, manifest_path=path)
    assert not (dest / data["files"][0]["path"]).exists()
    assert list(dest.rglob("*.part")) == []
