# Lane — migration source witness

Status: review/HOLD. No merge or CANON action.

## Dependency

This lane is intentionally stacked on `axm-matter-transfer` PR #5 at exact head
`7984286ef70b2667f2e30d3857a82113a1a8b796`.

PR #5 proves that the destination still matches the migration notes: three
human-readable files retain their recorded source Git blob identities, while
the JSON registry remains explicitly semantic rather than byte-identical.

This lane proves a different boundary: the recorded source commit and all four
recorded source blobs must actually exist in an explicitly selected local Git
checkout. It consumes PR #5's verified migration receipt instead of replacing
or weakening that gate.

## Improvement

`tools/verify_migration_source.py`:

- never fetches, checks out, writes, commits, pushes, or merges;
- requires PR #5's destination provenance gate to pass first;
- resolves the recorded source head as a Git commit in the caller-selected
  source checkout;
- checks every recorded source path at that exact commit and requires the
  recorded Git blob identity;
- rejects non-regular Git objects such as symlinks at the recorded path;
- can additionally require the selected checkout HEAD and GitHub origin
  metadata to match the migration notes;
- emits an explicit no-authority receipt and never labels Git metadata as
  author authentication.

The CI lane checks out
`mike-axiom-mir/axm-factual-space-simulator@1fa76ef579272b4bcfcd1d054977b90a3d596e23`
and runs both destination and source gates on Python 3.11 and 3.13.

## Truth boundary

A PASS proves that the received destination still satisfies PR #5's migration
contract and that the caller-selected Git source history contains the exact
recorded commit/path/blob identities. Git object identity and remote metadata
are lineage/integrity evidence, not signatures or proof of who authored the
history. This does not validate the physics, prove semantic equivalence of the
migrated registry, grant merge authority, or declare CANON.
