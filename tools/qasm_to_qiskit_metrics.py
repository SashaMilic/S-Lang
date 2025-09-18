from collections import defaultdict
from pathlib import Path
import sys

# NOTE: Lazy-import Qiskit inside main() so mixed installs don’t explode at import time.

def analyze(qc):
    """Compute simple metrics from a qiskit.QuantumCircuit."""
    stats = dict(cx=0, ccx=0, t=0, tdg=0, h=0)
    depth_by_qubit = defaultdict(int)
    twoq_depth_by_qubit = defaultdict(int)
    tstage_by_qubit = defaultdict(int)
    t_block = defaultdict(lambda: True)

    # Qiskit 1.x: map a Qubit object to its integer index via circuit.find_bit().index
    def qindex(qbit):
        loc = qc.find_bit(qbit)
        return loc.index

    def barrier_touch(qubits):
        for q in qubits:
            t_block[q] = True

    for instr in qc.data:
        op = instr.operation
        qubits = instr.qubits
        clbits = instr.clbits
        name = op.name.lower()

        if name in ("t", "tdg", "z", "rz", "s", "sdg"):
            if name in ("t", "tdg"):
                q = qindex(qubits[0])
                if t_block[q]:
                    tstage_by_qubit[q] += 1
                    t_block[q] = False
                stats[name] += 1
            continue

        if name in ("h", "x"):
            q = qindex(qubits[0])
            if name in stats:
                stats[name] += 1
            depth_by_qubit[q] = depth_by_qubit[q] + 1
            barrier_touch([q])
            continue

        if name == "cx":
            a = qindex(qubits[0])
            b = qindex(qubits[1])
            stats["cx"] += 1
            layer = max(depth_by_qubit[a], depth_by_qubit[b]) + 1
            depth_by_qubit[a] = depth_by_qubit[b] = layer
            two_layer = max(twoq_depth_by_qubit[a], twoq_depth_by_qubit[b]) + 1
            twoq_depth_by_qubit[a] = twoq_depth_by_qubit[b] = two_layer
            barrier_touch([a, b])
            continue

        if name in ("ccx", "toffoli"):
            a = qindex(qubits[0])
            b = qindex(qubits[1])
            c = qindex(qubits[2])
            stats["ccx"] += 1
            layer = max(depth_by_qubit[a], depth_by_qubit[b], depth_by_qubit[c]) + 1
            depth_by_qubit[a] = depth_by_qubit[b] = depth_by_qubit[c] = layer
            two_layer = max(twoq_depth_by_qubit[a], twoq_depth_by_qubit[b], twoq_depth_by_qubit[c]) + 2
            twoq_depth_by_qubit[a] = twoq_depth_by_qubit[b] = twoq_depth_by_qubit[c] = two_layer
            barrier_touch([a, b, c])
            continue

        if name == "measure":
            # account a single layer on the measured qubit
            q = qindex(qubits[0])
            depth_by_qubit[q] = depth_by_qubit[q] + 1
            barrier_touch([q])

    depth = max(depth_by_qubit.values()) if depth_by_qubit else 0
    twoq_depth = max(twoq_depth_by_qubit.values()) if twoq_depth_by_qubit else 0
    tdepth = max(tstage_by_qubit.values()) if tstage_by_qubit else 0
    twoq_count = stats["cx"] + stats["ccx"]
    twoq_equiv = stats["cx"] + 2 * stats["ccx"]
    tcount = stats["t"] + stats["tdg"]
    return dict(
        depth=depth,
        twoq_depth=twoq_depth,
        twoq_count=twoq_count,
        twoq_equiv=twoq_equiv,
        tcount=tcount,
        tdepth=tdepth,
        **stats,
    )

def main():
    if len(sys.argv) < 2:
        print("usage: python tools/qasm_to_qiskit_metrics.py <file.qasm>")
        return
    qasm = Path(sys.argv[1]).read_text()
    header = qasm.lstrip().splitlines()[0] if qasm.strip() else ""

    # Strip include lines (helps some Terra builds that already define std gates)
    def strip_includes(text: str) -> str:
        return "\n".join(line for line in text.splitlines() if not line.strip().lower().startswith("include "))
    qasm_no_includes = strip_includes(qasm)

    try:
        if header.startswith("OPENQASM 3"):
            try:
                from qiskit.qasm3 import loads as qasm3_loads  # type: ignore
            except Exception as e:
                raise RuntimeError(
                    "QASM3 detected but qiskit.qasm3 is unavailable. "
                    "Install a recent Qiskit:\n  python3 -m pip install 'qiskit>=1.0'\n"
                    "See https://qisk.it/packaging-1-0 for environment guidance."
                ) from e
            try:
                qc = qasm3_loads(qasm)
            except Exception:
                qc = qasm3_loads(qasm_no_includes)
        else:
            try:
                from qiskit import QuantumCircuit  # type: ignore
            except Exception as e:
                raise RuntimeError(
                    "QASM2 input but 'from qiskit import QuantumCircuit' failed. "
                    "Install Qiskit:\n  python3 -m pip install 'qiskit>=1.0'"
                ) from e
            qc = QuantumCircuit.from_qasm_str(qasm)
    except Exception as e:
        msg = str(e)
        if "invalid environment" in msg.lower() or "both qiskit >=" in msg.lower():
            print(
                "Error: Qiskit reports a mixed 0.x / >=1.0 install.\n"
                "Fix by using a fresh virtual environment and reinstalling Qiskit:\n"
                "  python3 -m venv .venv && source .venv/bin/activate\n"
                "  python3 -m pip install -U pip\n"
                "  python3 -m pip install 'qiskit>=1.0'\n"
                "More details: https://qisk.it/packaging-1-0"
            )
        else:
            print(f"Failed to parse QASM: {e}")
        sys.exit(2)

    # qasm3.loads may return a list of circuits
    try:
        from qiskit import QuantumCircuit as _QC  # noqa: F401
        if isinstance(qc, (list, tuple)):
            if not qc:
                print("Error: QASM3 parser returned no circuits."); sys.exit(2)
            qc = qc[0]
    except Exception:
        pass

    print(analyze(qc))

if __name__ == "__main__":
    main()