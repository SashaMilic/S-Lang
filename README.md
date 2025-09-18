# S-Lang
A quantum-native programming language where the unit of computation is a state in a Hilbert space (a superposition), not a bitstring. It operates on states and subspaces using linear operators, with measurement treated as an explicit effect.


# S-Lang (toy quantum DSL) – repo scaffold

This repository contains a small quantum domain-specific language ("S‑Lang"):
- A **parser** for a compact gate-level DSL,
- A **statevector interpreter** for quick simulations,
- A **QASM 3 transpiler** with accurate-ish metrics (depth, two‑qubit depth, T‑count, T‑depth),
- Optional **routing** on a coupling map (inserts SWAPs),
- A **QASM→Qiskit metrics loader** for parity.

> Educational prototype; not a drop‑in replacement for production toolchains.

## Quick start

```bash
python -m slang.cli transpile examples/bool_if_inline.slang --ancilla-budget 0 -o out/bool_if_inline.qasm
python tools/qasm_to_qiskit_metrics.py out/bool_if_inline.qasm
```

Optional: install Qiskit to run the parity tools.
```bash
pip install qiskit
```

## Repo layout

```
slang-repo/
  slang/
    __init__.py
    runtime.py        # statevector & gates
    parser.py         # Program + AST
    interpreter.py    # executes a subset of the language
    transpiler.py     # QASM3 emission, metrics, routing, ccx decomposition
    cli.py            # tiny CLI: transpile / run
  tools/
    qasm_to_qiskit_metrics.py  # loads QASM, prints metrics via Qiskit
  examples/
    *.slang           # demo programs
  tests/
    test_smoke.py     # smoke tests for parsing and transpiling
  README.md
  requirements.txt
```

## Features in this snapshot

- Gates: `H, X, Z, RZ theta, CNOT a,b, HADAMARD_LAYER r`
- Stdlib-like: `DIFFUSION r` (toy; exercises MCX/CCX/T patterns)
- Measurement: `MEASURE r[i] AS name`, `MEASURE r SHOTS N`
- Control flow: `IF/ELIF/ELSE` with arithmetic, `&&` / `||` short‑circuit lowering
- Loop sugar: `FOR q IN r { … }` → unrolled over qubits
- **Metrics** (footer in QASM): overall depth, two‑qubit depth, two‑qubit counts/equivalent, T‑count, **global T‑depth** with Clifford commuting
- **Routing**: give a `coupling_map=[(0,1),(1,2),...]` to insert SWAPs for non‑adjacent CX
- **CCX decomposition**: optional 7‑T Clifford+T Toffoli with precise T metrics

## License

MIT (prototype).
