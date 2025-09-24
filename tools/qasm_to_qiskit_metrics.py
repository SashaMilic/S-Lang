# tools/qasm_to_qiskit_metrics.py
import sys
import re
from pathlib import Path

def _first_noncomment_line(text: str) -> str:
    for ln in text.splitlines():
        s = ln.strip()
        if not s or s.startswith("//"):
            continue
        return s
    return ""

def _normalize_qasm3(text: str) -> str:
    # IMPORTANT: Do NOT strip the stdgates include; Qiskit needs it to define gates like h, cx, x, z.
    s = text

    # Fix conditional syntax issues the current emitter can produce.
    # - 'else if' -> 'elif' (OpenQASM 3 supports 'elif')
    s = re.sub(r"\belse\s+if\b", "elif", s, flags=re.MULTILINE)

    # - collapse 'if ((expr' -> 'if (expr' and ')) {' -> ') {'
    s = re.sub(r"\bif\s*\(\s*\(", "if (", s)
    s = re.sub(r"\)\s*\)\s*\{", ") {", s)

    # - also handle 'elif ((expr' -> 'elif (expr'
    s = re.sub(r"\belif\s*\(\s*\(", "elif (", s)

    return s

def load_qasm(text: str):
    """Load QASM2 or QASM3 from a string using Qiskit, normalizing QASM3 quirks."""
    head = _first_noncomment_line(text)
    try:
        if head.startswith("OPENQASM 3"):
            from qiskit.qasm3 import loads as qasm3_loads  # qiskit>=1.0
            q3 = _normalize_qasm3(text)
            return qasm3_loads(q3)
        else:
            # Assume QASM 2
            from qiskit import QuantumCircuit
            return QuantumCircuit.from_qasm_str(text)
    except Exception as e:
        kind = "qasm3" if head.startswith("OPENQASM 3") else "qasm2"
        raise RuntimeError(f"Failed to parse QASM ({kind}): {e}")

def compute_metrics(qc):
    counts = qc.count_ops()
    depth = qc.depth()

    # two-qubit totals (include cp/swap/cz if present)
    twoq_names = {"cx", "cz", "swap", "cp"}
    twoq = sum(counts.get(n, 0) for n in twoq_names)
    ccx = counts.get("ccx", 0)
    twoq_equiv = twoq + 2 * ccx

    # T metrics
    tcount = counts.get("t", 0) + counts.get("tdg", 0)
    # Simple T-depth approximation via DAG layers
    try:
        from qiskit.converters import circuit_to_dag
        dag = circuit_to_dag(qc)
        t_layers = 0
        for layer in dag.layers():
            ops = [nd.op for nd in layer["graph"].op_nodes()]
            if any(getattr(op, "name", "") in ("t", "tdg") for op in ops):
                t_layers += 1
        tdepth = t_layers
    except Exception:
        tdepth = 0

    return {
        "depth": depth,
        "two_qubit_count": twoq,
        "two_qubit_equiv": twoq_equiv,
        "tcount": tcount,
        "tdepth": tdepth,
    }

def main():
    # Keep the original one-arg interface used by `make metrics`.
    if len(sys.argv) != 2:
        print("usage: python tools/qasm_to_qiskit_metrics.py <file.qasm>", file=sys.stderr)
        sys.exit(2)

    path = Path(sys.argv[1])
    if not path.exists():
        print(f"no such file: {path}", file=sys.stderr)
        sys.exit(2)

    text = path.read_text()
    try:
        qc = load_qasm(text)
    except Exception as e:
        print("Failed to parse QASM:", file=sys.stderr)
        print(f"  file: {path}", file=sys.stderr)
        head = _first_noncomment_line(text)
        print(f"  head: {head}", file=sys.stderr)

        preview = "\n".join(text.splitlines()[:50])
        print("  --- preview ---", file=sys.stderr)
        print(preview, file=sys.stderr)
        print("  ---------------", file=sys.stderr)
        raise

    m = compute_metrics(qc)
    print(f"file: {path}")
    print(f"depth: {m['depth']}")
    print(f"two_qubit_count: {m['two_qubit_count']}")
    print(f"two_qubit_equiv: {m['two_qubit_equiv']}")
    print(f"tcount: {m['tcount']}")
    print(f"tdepth: {m['tdepth']}")

if __name__ == "__main__":
    main()