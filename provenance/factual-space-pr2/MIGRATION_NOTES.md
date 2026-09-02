# Migration Notes — Factual Space PR #2

**Migration date:** 2026-09-02  
**Destination:** `mike-axiom-mir/axm-matter-transfer`  
**Source repository:** `mike-axiom-mir/axm-factual-space-simulator`  
**Source PR:** https://github.com/mike-axiom-mir/axm-factual-space-simulator/pull/2  
**Source branch:** `automation/matter-transfer-geometry-state-v0-1`  
**Source head:** `1fa76ef579272b4bcfcd1d054977b90a3d596e23`  
**Source PR status at migration:** open draft; not merged; original merge gate = HOLD AS DRAFT.

## Why copy it

The matter-transfer work was originally placed in Factual Space because that repository already had evidence-bounded physics, source registries, claim ceilings, and a verification lane. A dedicated `axm-matter-transfer` repository now exists, so the research is copied here without deleting or rewriting the original branch.

The original Factual Space PR remains useful provenance. This migration does not retroactively make that PR canonical or merged.

## Source files

| Source path | Source blob SHA | Migration treatment |
|---|---|---|
| `docs/research/MATTER_TRANSFER_GEOMETRY_STATE_ARCHITECTURE_v0_1.md` | `fea7ac02886a7f6e08ee0c947017c8626c567fa7` | copied as human-readable provenance |
| `docs/research/FACEBOOK_LIGHT_GEOMETRY_INTAKE_2026_08_16.md` | `8ed68ee7597f57132e418b89054a181d59784084` | copied as human-readable provenance |
| `docs/ACTION_REPORT_MATTER_TRANSFER_GEOMETRY_STATE_v0_1.md` | `3fa6ea2042ff52002dfabfd8a54c2a8237033e10` | copied as human-readable provenance |
| `data/matter_transfer_organ_registry_v0_1.json` | `766067f7816f332e0d30b915f518d5982d393d5d` | semantically migrated; source SHA retained because cross-repository Git blob reuse was rejected by GitHub |

## Important integrity note

The three Markdown files above were migrated from their source text without intentionally changing the research claims.

The JSON registry is a semantic migration, not claimed byte-identical. GitHub rejected direct reuse of the source repository's blob SHA in the new repository. The source PR and blob SHA above remain the authoritative byte-level provenance reference.

No source file in `axm-factual-space-simulator` was deleted, closed, merged, or rewritten during this migration.

## Current interpretation must stay separate

The August 16 material considered multiple transfer families, including scan/reconstruction and spacetime-shortcut models. The September 2 research discussion narrowed the main speculative target:

> **continuous transfer of the same matter through an altered effective adjacency or path geometry, rather than destroy/scan/reconstruct.**

That newer interpretation lives in the destination repo's current research files. It does not silently rewrite this preserved older checkpoint.
