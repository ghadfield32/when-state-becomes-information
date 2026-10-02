# Rights and data disposition — E1

**Status: the code and the reproduction route are publishable; the SPL data is not
the authors' to license.**

This file is the single in-package authority for the rights position. It records
what is asserted and what is not. It does **not** grant permission, and it does
**not** claim a legal pass.

## What is asserted

| Material | Position |
|---|---|
| Original WMS code (`fetch_data.py`, `reproduce.py`, `docs/.../scripts`, `docs/.../src`, `tests`) | MIT. See `LICENSE`. Covers original code only |
| SPL motion-capture data | Governed by **upstream terms**, not MIT. See `THIRD_PARTY_NOTICES.md` and `spl_data/SPL_LICENSE.txt` |
| Raw SPL trials, participant archives, per-sample coordinates | **Not bundled.** Fetched from the pinned upstream revision on demand |
| Data-derived aggregate reports and figures | Distributed under CC BY-NC-SA 4.0 with the upstream additional exclusion preserved |

## What is not asserted

- That the authors hold a licence to redistribute SPL data.
- That academic intent, a public GitHub URL, or the MIT code licence grants
  third-party data rights.
- That any user satisfies the upstream eligibility terms. **They must determine
  that themselves.**
- That this repository has been legally reviewed.

## The upstream terms, unchanged

SPL Open Data states **CC BY-NC-SA 4.0** plus an additional exclusion: employees,
contractors, associated persons and significant shareholders of professional
sports organizations or financial-analysis firms require a specific written
commercial (paid) licence for any use. That clause is preserved verbatim in
`spl_data/SPL_LICENSE.txt`. It is not waived, narrowed, or reinterpreted here.

## Why this package is cleaner than a bundled-data release

- It **bundles no participant archives and no per-sample tracking data.**
- It pins an exact upstream revision (`a3f9cffb…`) and enumerates exactly **396**
  admitted files across four directories.
- Every file's original SHA-256 is pinned and independently verified after fetch.
- The downloader fetches only those literal directories; it does not clone, crawl,
  or request directory listings.
- The upstream licence and README are carried unchanged.

## The venue-interpretation caveat (stated, not resolved)

Sloan asks for an open supporting repository containing the research data.
Deterministic linked acquisition from a pinned upstream revision is the supplied
reproduction route here. **Whether the venue accepts linked acquisition as
satisfying "data in the repo" is a venue-interpretation question, and this package
does not answer it.**

If the venue requires bundled data, the correct response is a decision by the
operator, not a silent copy of SPL archives into a public repository at the
submission deadline. Bundling would also change the rights position materially.

## Operator decision on record

The repository is public under explicit operator authorization, with the SPL
terms documented rather than cleared. If this is later judged impermissible, the
remedy is to remove the derived reports and figures, not to claim a retroactive
permission.
