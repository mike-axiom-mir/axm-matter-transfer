# AXM Matter Transfer

Speculative, evidence-bounded research into whether physically admissible geometry/state configurations could provide a continuous, causally valid, radically shortened path for ordinary matter. No physical macroscopic matter-transfer mechanism is established.

## Canonical and preserved inputs

- `data/current_focus_v0_2.json` is the current research focus.
- `provenance/factual-space-pr2/data/matter_transfer_organ_registry_v0_1.json` is preserved historical source material migrated from Factual Space PR #2.
- `contracts/research_state_contract_v1.json` defines the executable invariants connecting them.

The historical registry is not silently rewritten. Assembly profiles name roots; the resolver computes their full transitive dependency closure as a derived execution plan and records exact source hashes.

## Deterministic checks

Requires Python 3.11+ and no third-party packages.

```bash
python tools/research_state.py validate
python tools/research_state.py resolve-profile observer_game_layer
python -m unittest discover -s tests -v
```

Validation fails closed on broken schemas, missing safety gates, unsupported truth-status combinations, transfer-mode drift, unknown organ references, dependency cycles, or invalid profile roots. Resolution outputs dependency-first organ order, transitive additions, and a deterministic plan hash; it never changes source state or promotes a scientific claim.

## Truth boundary

Mathematical models, deterministic simulations, and internally consistent execution plans are not evidence that nature permits macroscopic matter transfer. Current work is limited to literature mapping, published toy-model reproduction, simulation, causal/path analysis, source and claim registries, contradiction mapping, and falsification design.
