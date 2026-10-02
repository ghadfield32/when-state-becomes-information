"""Verify and unpack the included SPL Open Data subset to where the pipeline expects it.

The archives in spl_data/ hold an unmodified subset of SPL Open Data (MLSE Sport Performance
Lab), revision in spl_data/SPL_REVISION.txt, licensed CC BY-NC-SA 4.0 (spl_data/SPL_LICENSE.txt):
the free-throw trials of athletes P0001-P0003 that this study uses. Each archive's sha256 is
checked against spl_data/SHA256SUMS before anything is extracted.

    python unpack_data.py
"""
import hashlib
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "spl_data"
DEST = ROOT / "docs/backend/projects/world_model/open_world_model/data/external/SPL-Open-Data"
TARGET = DEST / "basketball" / "freethrow" / "data"

expected = {}
for line in (SRC / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
    digest, name = line.split(maxsplit=1)
    expected[name.lstrip("*")] = digest

for name, digest in sorted(expected.items()):
    h = hashlib.sha256((SRC / name).read_bytes()).hexdigest()
    if h != digest:
        sys.exit(f"REFUSED: {name} sha256 {h} does not match SHA256SUMS {digest}")
    print(f"verified {name}")

TARGET.mkdir(parents=True, exist_ok=True)
for name in sorted(expected):
    with tarfile.open(SRC / name, "r:gz") as tf:
        for member in tf.getmembers():
            p = Path(member.name)
            if p.is_absolute() or ".." in p.parts or not member.isreg() and not member.isdir():
                sys.exit(f"REFUSED: unsafe archive member {member.name!r} in {name}")
        tf.extractall(TARGET)
for extra in ("SPL_LICENSE.txt", "SPL_README.md"):
    (DEST / extra.replace("SPL_", "")).write_bytes((SRC / extra).read_bytes())
n = sum(1 for _ in TARGET.glob("*/*/*.json"))
print(f"unpacked {n} trial files to {TARGET.relative_to(ROOT).as_posix()}")
