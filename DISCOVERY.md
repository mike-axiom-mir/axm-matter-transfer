# Public capability discovery

This repository explicitly opts one bounded executable capability into AXM public discovery:

`axm.matter-transfer.ellis-wormhole.experiment/v1`

The declaration points to the deterministic single-file Ellis toy-geometry runner introduced by the portable experiment lane. Discovery is a way to locate and inspect that capability; it is **not** permission to execute it and it does not strengthen the scientific claim.

## Generate or verify

```bash
python tools/generate_public_capabilities.py --check
```

The committed registry is generated from the actual portable builder and experiment bytes. The generator builds the portable artifact in memory, inspects its embedded `AXM_PORTABLE.json`, verifies the example fixture contract, checks the Apache-2.0 license marker, and binds provider inputs by Git blob identity.

Generated files:

- `registry/capabilities.jsonl`
- `registry/capabilities.receipt.json`

The public marker is `.axm/discovery-public.json`.

## Cross-repository compatibility

The discovery shape is adapted from the proven AXM public-capability pattern in `mike-axiom-mir/axm-casual-loop` at `f561a8a325444be30ad0b4fee412b3958aa1f1ee`. Runtime/scientific implementation code was not copied.

CI pins Discovery Buddy at `565c38ecf93a9d563b02211258d8d36fcb1162b5`, builds its deterministic one-file zipapp, deletes the Discovery Buddy source checkout, then uses only that portable artifact to scan, verify, and query this repository.

## Truth boundary

The discoverable record preserves the existing claim ceiling:

`NO_PHYSICAL_MACROSCOPIC_MATTER_TRANSFER_MECHANISM_ESTABLISHED`

A discovery match proves only that the admitted repository snapshot contains the declared source-backed capability record. It does not authenticate authorship, prove physical feasibility, establish stability or usable stress-energy, demonstrate matter transfer, select/install/execute the provider, grant engineering authority, merge anything, or declare CANON.

The capability maturity field is intentionally `null` because the portable provider contract does not declare a maturity status. Mike remains the merge/CANON authority.
