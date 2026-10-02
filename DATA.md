# Data acquisition, provenance and rights

## Source and terms

This package contains no participant archives or per-sample tracking data.
Code is MIT licensed; those permissions do not license SPL data or the
data-derived reports and figures. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

Source: [SPL Open Data](https://github.com/Sport-Performance-Lab/SPL-Open-Data),
Maple Leaf Sports & Entertainment (MLSE), Sport Performance Lab, Toronto.
Pinned revision: `a3f9cffbde917b1e1747cedd6ec25dfab18c6051`.
The preserved upstream README uses the earlier `mlsedigital/SPL-Open-Data` URL.
Read the unchanged [source licence](spl_data/SPL_LICENSE.txt) and
[source README](spl_data/SPL_README.md) before acquisition.

The source terms state [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/)
and an additional exclusion for employees, contractors, associated persons
and significant shareholders of professional sports organizations or financial
analysis firms, who need the stated specific written commercial (paid) licence
for any use. That exclusion is retained unchanged in `SPL_LICENSE.txt`.
Availability on GitHub and the MIT code licence grant no blanket commercial
clearance. Each user must establish that their affiliation and intended use
satisfy the source terms; this package does not make that factual determination.

## Public input setup for the unchanged reproducer

From the standalone repository root, use the activated Python 3.12 environment:

```sh
python fetch_data.py
python fetch_data.py --verify-only
python reproduce.py
```

`fetch_data.py` uses only the Python standard library. Its default destination
is `docs/backend/projects/world_model/open_world_model/data/external/SPL-Open-Data`,
the unchanged reproducer's expected SPL root. It fetches individual JSON files
from `raw.githubusercontent.com/Sport-Performance-Lab/SPL-Open-Data/` at the
pinned commit. It does not clone, crawl, request directory listings, or fetch
any participant outside the four literal directories below.

| Directory below `basketball/freethrow/data/` | Files | Historical role |
|---|---:|---|
| `2024-08-28/P0001/` | 125 | Development session; fine fingers unavailable |
| `2025-12-18/P0001/` | 88 | Evaluation athlete P0001 |
| `2025-12-18/P0002/` | 93 | Evaluation athlete P0002 |
| `2025-12-18/P0003/` | 90 | Evaluation athlete P0003 |
| Total | 396 | Historical E1 inputs |

[UPSTREAM_FILES.json](spl_data/UPSTREAM_FILES.json) contains only each admitted
file's relative path and original SHA256, plus schema and source provenance.
Its exact byte SHA256 is
`22fabc5f536e48cd0d035f1ddde3bf89b68e5754a85359979a9967e85e26a42e`,
independently pinned in `fetch_data.py`. It was derived by filtering metadata
to these four exact directories before export from the retained observation
inventory, whose SHA256 is
`acf8238d98c8296af5d7894a329a4f02e14a81c1002821bf0d45d25830a34c47`.
No observations, coordinates, other participants' rows, or fitted outputs are
included in that public manifest.

Before making any network request or creating a destination, the downloader
validates the complete manifest, byte pin, source revision, unique safe paths,
hash syntax, all four counts, destination path components and every existing
manifest file. Changed existing bytes cause refusal; verified files are skipped.
Each missing file is streamed to a temporary file, size- and time-bounded,
hashed, flushed, then published atomically without overwriting an existing file.
Redirects are refused. Transport and digest failures stop the command and
remove its temporary file; rerunning verifies completed files before resuming.

The per-file resource limits are 16 MiB, a 30-second socket timeout and a
120-second elapsed deadline, checked between reads and at response completion.
A blocked read can last up to the socket timeout before the elapsed check.
There are no automatic retries. Publication requires filesystem hardlink
support (including NTFS and ordinary POSIX filesystems); unsupported filesystems
fail instead of falling back to a weaker overwrite method.

Use a fresh private destination with no concurrent writer. Existing symlinks,
Windows reparse points, hardlinks and wrong file types on manifest paths are
refused. This utility is not an OS sandbox against a hostile process mutating
directories concurrently, and does not enumerate unrelated existing files.
`--dest PATH` selects another SPL root for standalone verification. The
unchanged `reproduce.py` uses its default root. `--verify-only` performs the full
offline manifest/file check and refuses missing files without downloading.

## Existing archive alternative

Previously authorized exact archives may still be placed in ignored `spl_data/`:
`2024-08-28_P0001.tar.gz`, `2025-12-18_P0001.tar.gz`,
`2025-12-18_P0002.tar.gz`, and `2025-12-18_P0003.tar.gz`.
Run `python unpack_data.py`, then `python fetch_data.py --verify-only`.
The historical archive checksums in `spl_data/SHA256SUMS` are unchanged. They
identify those archives, not independently recompressed upstream files; do
not change them to accept a different archive. The public file downloader
bypasses archive acquisition while preserving the original trial bytes.

## Interpretation and publication

P0004/P0005 remain outside historical E1. Prior exposure in other research does
not become a fresh holdout by renaming an identifier. Older-session missing
fingers are ineligible for detailed-hand models, never zero-filled. The source
loader converts positions from feet to metres; timestamps retain their
documented time units. Acquisition makes no scientific transformation.

Included aggregate reports and figures are conservatively distributed under
CC BY-NC-SA 4.0 with the upstream additional exclusion preserved. These are
derived research summaries and visualizations; the raw trials, forecast stores
and per-example arrays are omitted. Attribution does not imply SPL endorsement.

An independently usable linked source route is a reproducibility aid. It does
not itself establish that the submission venue accepts linked data as satisfying
its requirement to provide the data used. Venue acceptance, actual author/use
eligibility, and full clean-environment reproduction remain separate release
checks. Software tests do not settle those checks or establish conference
submission.
