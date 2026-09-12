# Portable Research Capsule v1

## Purpose

The research-state resolver can derive a dependency-closed profile inside this repository. This capsule layer makes one resolved profile portable enough for another tool, repository, or offline machine to inspect without importing the Matter Transfer source tree.

It deliberately carries evidence, not authority.

## Cross-repo pattern source

This layer adopts one useful pattern observed in `mike-axiom-mir/axm-factual-space-simulator` draft PR #5 at head `bf8e3e92cdf4e7b0b9dbafa0c569a4e0b0036c8f`: a generated capsule should remain verifiable after it has been copied away from its provider repository.

No Factual Space source code is copied. Matter Transfer implements its own smaller research-specific contract using only the Python standard library.

## Build

```bash
python tools/research_capsule.py build observer_game_layer --output /tmp/matter-transfer-observer
```

The capsule contains:

- `manifest.json` — complete byte/hash inventory and authority boundary;
- `resolved-plan.json` — the exact dependency-closed derived assembly;
- `sources/research_state_contract_v1.json` — exact contract bytes used to resolve the plan;
- `sources/current_focus.json` — exact focus bytes used to resolve the plan;
- `sources/organ_registry.json` — exact preserved registry bytes used to resolve the plan;
- `verify.py` — the same dependency-free verifier source, copied so a receiving machine does not need this repository merely to check integrity and lineage.

## Received-capsule verification

After copying the capsule anywhere else:

```bash
cd /some/unrelated/directory
python /path/to/capsule/verify.py verify /path/to/capsule
```

Verification fails closed on:

- manifest digest drift;
- unsafe, duplicate, missing, or undeclared paths;
- symbolic-link substitution;
- byte-count or SHA-256 mismatch;
- malformed or altered resolved-plan identity;
- manifest/profile mismatch;
- source bytes that no longer match the source hashes bound into the resolved plan;
- authority-boundary drift.

The verifier does not need `tools/research_state.py` when used in `verify` mode. Building a new capsule still requires the provider repository because only the provider owns profile resolution.

## Truth and authority boundary

A green verification receipt means the received capsule is internally consistent with the manifest and exact source bytes that produced its resolved plan.

It does **not** prove:

- that the historical source registry is factually correct;
- that any speculative physical mechanism exists;
- that the included plan can or should be executed;
- authorship or identity of whoever supplied the capsule;
- signature authenticity;
- runtime compatibility with an arbitrary consumer;
- merge, promotion, release, or CANON status.

`integrity_and_lineage_evidence_only` is therefore the strongest verification authority emitted by v1.
