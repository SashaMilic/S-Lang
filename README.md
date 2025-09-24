![CI](https://github.com/<you>/S-Lang/actions/workflows/ci.yml/badge.svg)

# S-Lang
A quantum-native programming language where the unit of computation is a state in a Hilbert space (a superposition), not a bitstring. It operates on states and subspaces using linear operators, with measurement treated as an explicit effect.

# Quick use Makefile

## install just tests extra (so pytest exists)
```bash
make install-dev
```
## run your script wrapper
```bash
make sanity
```
## or run individual steps
```bash
make transpile
make metrics
make test
```

# S-Lang (toy quantum DSL) – repo scaffold

This repository contains a small quantum domain-specific language ("S‑Lang"):
- A **parser** for a compact gate-level DSL,
- A **statevector interpreter** for quick simulations,
- A **QASM 3 transpiler** with accurate-ish metrics (depth, two‑qubit depth, T‑count, T‑depth),
- Optional **routing** on a coupling map (inserts SWAPs),
- A **QASM→Qiskit metrics loader** for parity.

> Educational prototype; not a drop‑in replacement for production toolchains.

## Quick start

python -m venv ./env          # Create python virtual environment (venv)
brew install python3          # Install python over homebrew
source ./env/bin/activate     # Activate virtual environment (venv)
deactivate                    # Deactivate virtual environment (venv)

```bash
python -m slang.cli transpile examples/bool_if_inline.slang --ancilla-budget 0 -o out/bool_if_inline.qasm
python tools/qasm_to_qiskit_metrics.py out/bool_if_inline.qasm
```

Optional: install Qiskit to run the parity tools.
```bash
pip install qiskit>=1.0
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

## Content

slang/          # package (parser, interpreter, transpiler, CLI)
tools/          # qasm_to_qiskit_metrics.py
examples/       # demo programs
tests/          # pytest smoke
README.md
requirements.txt

## License

MIT (prototype).

## Novelty

What exists today
-----------------

- Qiskit, Cirq, PyQuil, and other quantum SDKs provide quantum circuit construction, simulation, transpilation, and metrics.
- QASM 2.0 and 3.0 are standard quantum assembly languages for circuit description.
- Qiskit and others have transpilers that output QASM and track metrics like depth, T-count, etc.
- Some DSLs exist for quantum programming (Silq, Quipper, etc.), but most are either embedded in a host language or focus on high-level algorithmic constructs.

What you are doing
------------------

- S-Lang is a small, **quantum-native DSL** where the unit of computation is a *state* (in a Hilbert space), not a classical bitstring.
- It operates directly on states and subspaces using linear operators, with measurement as an explicit effect.
- The repo provides:
  - A **parser** for a compact, gate-level DSL.
  - A **statevector interpreter** for quick simulations.
  - A **QASM 3 transpiler** with accurate-ish metrics (depth, two-qubit depth, T-count, T-depth).
  - Optional **routing** on a coupling map (inserts SWAPs).
  - A **QASM→Qiskit metrics loader** for parity.
- The language supports control flow (if/elif/else), "loop sugar," and measurement as first-class constructs.
- The prototype is designed for educational use and to explore "quantum-native" language design, not as a production toolchain.

So, does it already exist?
--------------------------

- No existing tool combines all these aspects in this form:
  - A minimal, standalone DSL focused on quantum states as the primitive, with explicit measurement and subspace manipulation.
  - A parser/interpreter/transpiler pipeline with routing, metrics, and QASM3 emission, all in a small educational package.
- Existing frameworks are either much larger, embedded in Python, or do not focus on the "state as primitive" approach.
- This project is novel as a compact, self-contained, quantum-native language and toolchain prototype.


# Roadmap (pragmatic, developer-oriented)
##	Language ergonomics
  •	Modules & imports, namespacing, standard library packaging.
  •	Functions with return values, integer/float params, expression grammar.
  •	Debuggability: TRACE, DUMPSTATE, PROBS, ASSERT (runtime checks).
  •	Structured errors (line/col, callsite context).
##	Core IR + passes
  •	Lower parser → SSA-like quantum IR (qubit sets, effects, classical blocks).
  •	Pass framework: const-fold, canonicalize, decompose, route, schedule, cost.
  •	Deterministic pass pipeline with dump points.
##	Backends
  •	QASM3 (we have), QIR stub, Qiskit builder parity.
  •	Simulators: statevector (we have), density matrix & noise channels.
  •	Optional pulse hooks (future).
##	Algorithms & tooling
  •	Stdlib: Grover (done), QFT/IQFT (done), VQE (optimizer + grouping), QPE, phase kickback helpers.
  •	Measurement grouping: commutation classes, greedy & exact clique partitioning.
  •	Small optimizer suite: COBYLA, Nelder–Mead, SPSA (shot-frugal), plus seed control.
##	HW realism
  •	Coupling/routing (we have), swap depth model, simple scheduling, T-depth (we track), calibrations (uture).
##	DX
  •	scli rich CLI: run, transpile, metrics, visualize, diff IR, explain cost.
  •	Jupyter-friendly API, VSCode syntax, docs site.
