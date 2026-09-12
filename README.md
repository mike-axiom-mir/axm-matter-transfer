# AXM Matter Transfer

Speculative, evidence-bounded research into whether physically admissible geometry/state configurations could provide a continuous, causally valid, radically shortened path for ordinary matter. No physical macroscopic matter-transfer mechanism is established.

## Canonical and preserved inputs

- `data/current_focus_v0_2.json` is the current research focus.
- `provenance/factual-space-pr2/data/matter_transfer_organ_registry_v0_1.json` is preserved historical source material migrated from Factual Space PR #2.
- `contracts/research_state_contract_v1.json` defines the executable invariants connecting them.

The historical registry is not silently rewritten. Assembly profiles name roots; the resolver computes their full transitive dependency closure as a derived execution plan and records exact source hashes.

## Deterministic research-state checks

Requires Python 3.11+ and no third-party packages.

```bash
python tools/research_state.py validate
python tools/research_state.py resolve-profile observer_game_layer
python -m unittest discover -s tests -v
```

Validation fails closed on broken schemas, missing safety gates, unsupported truth-status combinations, transfer-mode drift, unknown organ references, dependency cycles, or invalid profile roots. Resolution outputs dependency-first organ order, transitive additions, and a deterministic plan hash; it never changes source state or promotes a scientific claim.

## Executable toy-model reproduction

The first executable experiment reproduces a published zero-mass Ellis wormhole toy geometry without promoting it into engineering evidence:

```bash
python3 experiments/ellis_wormhole.py run \
  --input experiments/fixtures/ellis_zero_mass_v1.json
```

See [the executable experiment guide](experiments/README.md) and the current [continuous-adjacency crosscheck](research/2026-09-02-continuous-adjacency-crosscheck.md).

A `PASS` for this experiment means the declared mathematical identities, fixture predictions, and numerical crosscheck were reproduced under the tested contract. It does not establish stability, a physically available stress-energy source, quantum-energy-inequality compatibility, an actuator, engineering feasibility, or macroscopic matter transfer.

## Truth boundary

Mathematical models, deterministic simulations, internally consistent execution plans, and reproducible receipts are not evidence that nature permits macroscopic matter transfer. Current work is limited to literature mapping, published toy-model reproduction, simulation, causal/path analysis, source and claim registries, contradiction mapping, and falsification design.
