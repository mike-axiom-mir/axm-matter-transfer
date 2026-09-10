# Executable toy-geometry experiments

This directory turns bounded parts of the research program into deterministic,
inspectable software experiments. A passing receipt is evidence about the
declared mathematical model and implementation only.

## Ellis zero-mass wormhole reproduction

The first experiment evaluates the static, spherically symmetric metric

```text
ds² = -dt² + dl² + (l² + a²)dΩ²
```

and its equivalent Morris–Thorne form `Φ(r)=0`, `b(r)=a²/r`. It checks the
throat and flare-out identities, exposes the negative radial null-energy sum
required by this standard-GR description, compares analytic proper distance
with an independent Simpson integration, and evaluates predictions that were
recorded before execution.

Run and independently replay the included fixture:

```bash
python3 experiments/ellis_wormhole.py run \
  --input experiments/fixtures/ellis_zero_mass_v1.json \
  --output /tmp/ellis-receipt.json

python3 experiments/ellis_wormhole.py verify \
  --input experiments/fixtures/ellis_zero_mass_v1.json \
  --receipt /tmp/ellis-receipt.json
```

The output path is created exclusively in one filesystem operation: an existing
file, directory, or symlink—including a dangling symlink—is treated as occupied
and is never followed or replaced. Verification checks the receipt digest and
then re-executes the experiment; changing a result and recalculating its digest
is therefore insufficient.

### Portable single-file runner

The same experiment can be packaged as one deterministic Python zipapp without
copying or rewriting the model by hand:

```bash
python3 tools/build_ellis_zipapp.py build \
  --output /tmp/ellis-wormhole.pyz \
  --receipt /tmp/ellis-wormhole.build.json

python3 tools/build_ellis_zipapp.py verify \
  --artifact /tmp/ellis-wormhole.pyz \
  --receipt /tmp/ellis-wormhole.build.json \
  --source experiments/ellis_wormhole.py
```

The `.pyz` contains the exact current `ellis_wormhole.py` bytes, a minimal
entrypoint, and bounded machine-readable metadata. It needs only Python 3.11+
and the standard library. Copy the `.pyz` plus an input JSON file to another
local directory and run the same `run` / `verify` commands directly against the
artifact; no repository checkout, package install, account, network, or AI
model is required at execution time.

The build receipt binds the artifact and packaged provider source by SHA-256.
The verifier also checks the exact member inventory, stored-member policy,
entrypoint, embedded metadata, and (when supplied) byte equality with the
provider source. Re-sealing an artifact with an extra member therefore does not
make the widened artifact admissible. SHA-256 here is integrity/lineage
evidence, not authorship authentication or a signature.

The pull-request gate also retains the built `.pyz` and build receipt as a
review artifact. Retention is a review/distribution convenience, not a release,
promotion, or claim that the artifact is CANON.

This distribution seam applies the same AXM principle used by verified portable
capsules—carry exact source/evidence with the thing that leaves its checkout—but
it does not copy implementation code from another repository or create a
shared runtime dependency.

### Sources and adaptation

- H. G. Ellis, “Ether flow through a drainhole: A particle model in general
  relativity,” *Journal of Mathematical Physics* 14 (1973),
  <https://doi.org/10.1063/1.1666161>.
- M. S. Morris and K. S. Thorne, “Wormholes in spacetime and their use for
  interstellar travel: A tool for teaching general relativity,” *American
  Journal of Physics* 56 (1988), <https://doi.org/10.1119/1.15620>.

The source papers are references, not copied code. This implementation uses
only equations declared in the receipt and Python’s standard library.

### Truth boundary

`PASS` means the bounded computational reproduction met its declared gates.
It does **not** establish stability, quantum-field compatibility, a source for
the required stress-energy, an actuator, engineering feasibility, physical
matter transfer, merge authority, or CANON. Packaging the experiment changes
none of those claims and grants no automatic execution authority. No
biological, destructive, weapon, confinement, or hardware experiment is
included.
