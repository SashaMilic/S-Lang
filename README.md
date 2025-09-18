# S-Lang
A quantum-native programming language where the unit of computation is a state in a Hilbert space (a superposition), not a bitstring. It operates on states and subspaces using linear operators, with measurement treated as an explicit effect.

# Content

slang-repo/
  README.md
  requirements.txt
  slang/
    __init__.py
    runtime.py        # statevector + basic gates
    parser.py         # S-Lang parser & AST
    interpreter.py    # toy statevector interpreter (IF/ELIF/ELSE, FOR-IN, DIFFUSION)
    transpiler.py     # OpenQASM 3 emitter + metrics + routing + CCX decomposition
    cli.py            # CLI: transpile / run
  tools/
    qasm_to_qiskit_metrics.py   # QASM→Qiskit loader that prints the same metrics
  examples/
    bool_if_inline.slang
    loop_sugar.slang
    diffusion_anc0.slang
    routed_line_cx.slang
  tests/
    test_smoke.py


# Quick start

## transpile to QASM (prints to stdout)
python -m slang.cli transpile examples/bool_if_inline.slang

## transpile with routing & CCX decomposition -> file
python -m slang.cli transpile examples/routed_line_cx.slang \
  --coupling '[[0,1],[1,2],[2,3],[3,4],[4,5]]' \
  --ancilla-budget 0 \
  -o out/routed.qasm

## analyze QASM with Qiskit-based parity tool
python tools/qasm_to_qiskit_metrics.py out/routed.qasm

# Notes

	•	The transpiler includes:
	•	T-depth with Clifford commuting (global stage count),
	•	Two-qubit depth and counts (and ccx as 2× equiv),
	•	Optional SWAP routing on a coupling map (adds realistic CX overhead),
	•	7-T Toffoli decomposition when decompose_ccx=True (on by default).
	•	The interpreter is intentionally small; it runs H/X/Z/RZ/CNOT/HADAMARD_LAYER/DIFFUSION, IF/ELIF/ELSE, FOR-IN and simple measurements.
