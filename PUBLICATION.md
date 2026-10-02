# Publication and clean-clone checklist

## What to publish

Use this `e1` directory as the root of a new repository. Do not initialize or
push the enclosing Betts repository. This package intentionally has no nested
Git history or data submodule. Review `SOURCE_MANIFEST.json` and `SHA256SUMS`
before copying it. The manifest records original bytes; the checksums record
the final package bytes, excluding the checksum file itself.

1. Review the exact abstract, author metadata and source/data rights. The
   code's MIT licence does not override the SPL licence. `DATA.md` describes
   the separate data boundary.
2. Extract the provided `e1-source.zip` to an empty directory outside the private
   monorepo, or copy only paths listed in `SHA256SUMS` plus `SHA256SUMS` itself.
   Do not copy caches created by local runs. `.gitattributes` disables text
   normalization so Git preserves the exact checksummed historical bytes.
3. Run the source-only checks in `TESTING.md` and the checksum verification
   below. Inspect `git status` before staging. No participant archives,
   outputs, local environments or access authorizations belong in the payload.
4. Initialize the new repository locally with `git init -b main`. Stage only
   the reviewed package paths. Review the staged diff and a secret scan.
5. Under the operator's explicit publication authorization, create the public
   remote and publish that reviewed commit.
   No remote URL is invented by this package.
6. Clone anonymously into a new directory. Repeat environment setup and
   source-only tests. Read the source terms, then run `fetch_data.py`,
   `fetch_data.py --verify-only`, and `reproduce.py`. Retain the exact commit, input
   hashes, environment versions, command, exit status and comparison output.
7. Inspect the public URL anonymously, then supply it in the Sloan portal.
   Record the submitted abstract bytes, author fields, timestamp and receipt.

## Verify the package

From this directory on a platform with `sha256sum`:

```sh
sha256sum --check SHA256SUMS
```

Portable Python equivalent:

```sh
python -c "import hashlib,pathlib; r=pathlib.Path('.'); rows=[x.split('  ',1) for x in (r/'SHA256SUMS').read_text().splitlines()]; bad=[p for h,p in rows if not (r/p).is_file() or hashlib.sha256((r/p).read_bytes()).hexdigest()!=h]; print('PASS' if not bad else bad); raise SystemExit(bool(bad))"
```

Checksums detect changes to listed files; also inspect all extra/untracked
files before publication. Checksums and ignore rules are not a rights review
or a security sandbox.

## Conference boundary

The official [SSAC research competition page](https://www.sloansportsconference.com/research-paper-competition)
states an October 1, 2026, 11:59 p.m. Eastern abstract deadline and requires a
repository with the data used in the research; model code is encouraged.
This package supplies code, aggregates and a verified pinned public input
route. Raw trial files remain upstream under their separate terms. That
arrangement must not be represented as explicit venue approval. Invited full
papers are due December 4.
Observed October 1, 2026. Check the live rules and portal before submission;
this file does not establish acceptance or submission.
