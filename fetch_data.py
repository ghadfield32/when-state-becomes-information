"""Fetch only the 396 hash-pinned historical E1 trials, without cloning SPL.

Use a private destination directory with no concurrent writer. This is an
integrity-checked downloader, not an OS sandbox for hostile concurrent users.
"""
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import tempfile
import time
from urllib.request import HTTPRedirectHandler, build_opener


ROOT = Path(__file__).resolve().parent
DEFAULT_DEST = ROOT / "docs/backend/projects/world_model/open_world_model/data/external/SPL-Open-Data"
DEFAULT_MANIFEST = ROOT / "spl_data/UPSTREAM_FILES.json"
MANIFEST_SHA256 = "22fabc5f536e48cd0d035f1ddde3bf89b68e5754a85359979a9967e85e26a42e"
SOURCE_REPOSITORY = "https://github.com/Sport-Performance-Lab/SPL-Open-Data"
SOURCE_REVISION = "a3f9cffbde917b1e1747cedd6ec25dfab18c6051"
INVENTORY_SHA256 = "acf8238d98c8296af5d7894a329a4f02e14a81c1002821bf0d45d25830a34c47"
BASE_URL = f"https://raw.githubusercontent.com/Sport-Performance-Lab/SPL-Open-Data/{SOURCE_REVISION}/"
ALLOWED_GROUPS = {
    "basketball/freethrow/data/2024-08-28/P0001": 125,
    "basketball/freethrow/data/2025-12-18/P0001": 88,
    "basketball/freethrow/data/2025-12-18/P0002": 93,
    "basketball/freethrow/data/2025-12-18/P0003": 90,
}
# Resource limits, not scientific selection thresholds. No automatic retries.
MAX_MANIFEST_BYTES = 1024 * 1024
MAX_FILE_BYTES = 16 * 1024 * 1024
SOCKET_TIMEOUT_SECONDS = 30
FILE_DEADLINE_SECONDS = 120
CHUNK_BYTES = 64 * 1024


def load_manifest(path=DEFAULT_MANIFEST):
    """Validate the entire frozen set before callers can make any request."""
    with Path(path).open("rb") as source:
        content = source.read(MAX_MANIFEST_BYTES + 1)
    if len(content) > MAX_MANIFEST_BYTES:
        raise ValueError("manifest exceeds size limit")
    if hashlib.sha256(content).hexdigest() != MANIFEST_SHA256:
        raise ValueError("manifest sha256 differs from the downloader's immutable pin")
    manifest = json.loads(content)
    if not isinstance(manifest, dict) or set(manifest) != {
        "schema_version", "source_repository", "source_revision", "inventory_sha256", "files",
    }:
        raise ValueError("invalid manifest schema")
    if (type(manifest["schema_version"]) is not int or manifest["schema_version"] != 1
            or manifest["source_repository"] != SOURCE_REPOSITORY
            or manifest["source_revision"] != SOURCE_REVISION
            or manifest["inventory_sha256"] != INVENTORY_SHA256):
        raise ValueError("invalid manifest schema or source identity")
    rows = manifest["files"]
    if not isinstance(rows, list) or len(rows) != 396:
        raise ValueError("manifest must contain all 396 E1 files")
    seen = set()
    groups = Counter()
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"path", "sha256"}:
            raise ValueError("manifest rows must contain only path and sha256")
        name, digest = row["path"], row["sha256"]
        if (not isinstance(name, str) or "\\" in name or ":" in name
                or any(part in ("", ".", "..") for part in name.split("/"))):
            raise ValueError("unsafe relative source path")
        relative = PurePosixPath(name)
        group = relative.parent.as_posix()
        if relative.is_absolute() or group not in ALLOWED_GROUPS:
            raise ValueError("source path outside the exact E1 directories")
        athlete = relative.parent.name
        if not re.fullmatch(rf"BB_FT_{athlete}_T[0-9]{{4}}\.json", relative.name):
            raise ValueError("unexpected trial filename")
        if name in seen:
            raise ValueError("duplicate source path")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("invalid source sha256")
        seen.add(name)
        groups[group] += 1
    if dict(groups) != ALLOWED_GROUPS:
        raise ValueError("manifest directory counts differ from the frozen E1 set")
    return rows


def _check_path(path, *, regular_file=False):
    """Refuse symlinks, Windows reparse points, hardlinks and wrong file types."""
    path = Path(os.path.abspath(path))
    for component in (*reversed(path.parents), path):
        try:
            info = component.lstat()
        except FileNotFoundError:
            continue
        if (stat.S_ISLNK(info.st_mode)
                or getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)):
            raise ValueError(f"refused link or reparse point: {component}")
        if component == path and regular_file:
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise ValueError(f"refused nonregular or hardlinked file: {component}")
        elif not stat.S_ISDIR(info.st_mode):
            raise ValueError(f"refused nondirectory ancestor: {component}")
    return path


def _verify_file(path, expected):
    _check_path(path, regular_file=True)
    digest = hashlib.sha256()
    total = 0
    with path.open("rb") as source:
        while chunk := source.read(CHUNK_BYTES):
            total += len(chunk)
            if total > MAX_FILE_BYTES:
                raise ValueError(f"file exceeds size limit: {path}")
            digest.update(chunk)
    if digest.hexdigest() != expected:
        raise ValueError(f"existing file sha256 mismatch: {path}")


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("redirect refused; only pinned raw source URLs are allowed")


def _open_source(url):
    return build_opener(_NoRedirect()).open(url, timeout=SOCKET_TIMEOUT_SECONDS)


def _download_file(path, source_path, expected):
    _check_path(path, regular_file=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    _check_path(path, regular_file=True)
    temporary = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(prefix=".e1-", suffix=".part", dir=path.parent)
        temporary = Path(temporary_name)
        digest = hashlib.sha256()
        total = 0
        started = time.monotonic()
        with os.fdopen(descriptor, "wb") as target:
            with _open_source(BASE_URL + source_path) as response:
                while chunk := response.read(CHUNK_BYTES):
                    total += len(chunk)
                    if total > MAX_FILE_BYTES:
                        raise ValueError(f"download exceeds size limit: {source_path}")
                    if time.monotonic() - started > FILE_DEADLINE_SECONDS:
                        raise ValueError(f"download exceeds time limit: {source_path}")
                    digest.update(chunk)
                    target.write(chunk)
            if time.monotonic() - started > FILE_DEADLINE_SECONDS:
                raise ValueError(f"download exceeds time limit: {source_path}")
            if digest.hexdigest() != expected:
                raise ValueError(f"download sha256 mismatch: {source_path}")
            target.flush()
            os.fsync(target.fileno())
        _check_path(path, regular_file=True)
        # Atomic publication without replacing a file another writer created.
        # This requires hardlink support (NTFS and ordinary POSIX filesystems).
        os.link(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink()


def acquire(destination=DEFAULT_DEST, *, manifest_path=DEFAULT_MANIFEST, verify_only=False):
    """Preflight all paths/old bytes; then fetch missing files or verify offline."""
    rows = load_manifest(manifest_path)
    destination = _check_path(destination)
    pending = []
    verified = 0
    for row in rows:
        path = _check_path(destination / row["path"], regular_file=True)
        if path.exists():
            _verify_file(path, row["sha256"])
            verified += 1
        else:
            pending.append((path, row))
    if verify_only and pending:
        raise ValueError(f"missing {len(pending)} of 396 E1 files; verify-only never fetches")
    for path, row in pending:
        _download_file(path, row["path"], row["sha256"])
    return {"downloaded": len(pending), "verified": verified}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dest", type=Path, default=DEFAULT_DEST,
                        help="SPL root destination; default is the unchanged reproducer's data root")
    parser.add_argument("--verify-only", action="store_true", help="offline check; refuse missing files")
    args = parser.parse_args()
    try:
        result = acquire(args.dest, verify_only=args.verify_only)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"REFUSED: {exc}\n")
    print(f"OK: {result['downloaded']} downloaded, {result['verified']} existing files verified; 396 E1 files")


if __name__ == "__main__":
    main()
