# Lane — Factual Space migration provenance freeze

Status: **TEST / review only**

## Why this lane exists

The preserved Factual Space PR #2 migration notes already distinguish two different
truth contracts:

- three Markdown files were copied as human-readable provenance with exact source
  Git blob identities;
- the organ registry was a semantic migration and is explicitly *not* claimed
  byte-identical.

Before this lane, those identities were documentary evidence only. A later edit to
one of the three preserved Markdown copies could silently break the migration
receipt while leaving the notes unchanged.

## Focused change

This lane adds a standard-library verifier that reads the migration table itself,
recomputes Git blob identity from the destination bytes, and fails closed if an
exact-copy row drifts.

The semantic registry remains a different boundary: the verifier checks that it is
present and valid JSON but deliberately does not require its current Git blob SHA
to equal the source SHA.

Unsafe/non-canonical source paths, duplicate rows, malformed source/head hashes,
missing files, and unknown migration treatments also fail closed.

## Lane separation

Open work was inspected before editing.

- PR #3 is Apache-2.0 license metadata.
- PR #4 owns the research-state contract/resolver, its tests, README changes, and
  `research-state.yml`.

This lane changes none of those files. It adds only:

- `tools/verify_migration_provenance.py`
- `tests/test_migration_provenance.py`
- `.github/workflows/provenance-freeze.yml`
- this lane receipt

## Verification target

```text
python3 -m unittest discover -s tests -v
python3 tools/verify_migration_provenance.py --json
```

The focused unit suite includes a known Git blob identity, exact-copy drift,
semantic-migration non-equivalence, and path-traversal rejection.

## Truth boundary

This proves only that the preserved exact-copy files still match the Git blob
identities declared in the migration notes, and that the semantic JSON migration
is still present/parseable.

It does not authenticate the original source repository, prove the historical
research claims, validate physics, prove semantic equivalence of the migrated
registry, merge anything, or make any material CANON.
