# Lane — deterministic research-state and assembly resolver

**Branch:** `automation/systems-state-profile-resolver-2026-09-09-0526`  
**Created:** 2026-09-09  
**Perspective:** AXM Systems & State Architect

## Scope

- preserve the migrated organ registry as historical source material;
- add one versioned contract for the current focus and registry invariants;
- validate truth boundaries, mode classes, state-summary derivation, references, and dependency acyclicity;
- resolve assembly-profile roots into deterministic dependency-closed execution plans;
- bind every receipt and plan to the exact source bytes with SHA-256;
- run the contract, mutation tests, and all profile resolutions in CI.

## Authority boundary

The organ registry remains the preserved source. Resolved plans are derived projections and identify themselves as such. They cannot overwrite the registry or promote a research claim. A new physical-status combination intentionally fails until a reviewed contract version defines its wording.

## Stop condition

This lane ends when the baseline validates, malformed dependency/state fixtures fail closed, all four profiles resolve deterministically, and CI covers those claims. It does not implement a simulator, change the historical research, merge itself, or declare CANON.
