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

The output path is no-replace. Verification checks the receipt digest and then
re-executes the experiment; changing a result and recalculating its digest is
therefore insufficient.

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
matter transfer, merge authority, or CANON. No biological, destructive,
weapon, confinement, or hardware experiment is included.
