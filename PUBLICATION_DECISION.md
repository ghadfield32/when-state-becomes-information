# Publication decision — E1

status: REPOSITORY_PUBLIC_UNDER_OPERATOR_AUTHORIZATION
public_remote: https://github.com/ghadfield32/ssac27-release-conditioned-forecasting
approved_by: Geoffrey Hadfield
approved_at: 2026-10-01
scientific_tag: e1-2026-10-01
scientific_commit: 9f4b38df3e1ffc577d670463ee5b74d4fbba7255
submission_tag: null
sloan_submitted: false

E1's repository was already public before this file existed. This file records
that state rather than gating it.

## The distinction that matters here

Unlike a repository that bundles its data, E1 publishes:

- MIT-licensed original code;
- a pinned acquisition manifest and a deterministic downloader;
- frozen aggregate reports and figures;
- licence and attribution documents carried unchanged.

It publishes **no participant archives and no per-sample tracking data**. The 396
admitted source files are fetched on demand from the pinned upstream revision and
hash-verified. See `RIGHTS.md` and `DATA_INVENTORY.json`.

## What is cleared, and what is not

| Item | State |
|---|---|
| Original code under MIT | cleared by the authors; it is theirs |
| Governance wrapper | published, and **not yet independently reviewed** |
| SPL data redistribution | **not asserted**. Upstream terms are preserved, not cleared |
| Venue interpretation of the data requirement | **open** (gate E1-G1) |
| Sloan submission | **not made**; no receipt exists |

## The one decision that remains

Sloan asks for the research data in the open repository. This package supplies a
deterministic, hash-verified acquisition route instead of bundling third-party
participant archives.

If the venue requires bundled data, the correct response is an explicit operator
decision — **not** copying SPL archives into a public repository at the deadline.
Bundling would change the rights position materially and would require its own
review.

## What must not happen

- No movement of the `e1-2026-10-01` tag. It is the reviewed scientific identity.
- No absorption of the five-athlete, direction, hand-ablation, or challenger work
  into this submission. Those belong to a separate full-paper extension.
- No claim of a Sloan submission or receipt until one actually exists.
