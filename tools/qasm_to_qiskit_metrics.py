from qiskit import QuantumCircuit
from collections import defaultdict
import sys
from pathlib import Path

def analyze(qc: QuantumCircuit):
    stats = dict(cx=0, ccx=0, t=0, tdg=0, h=0)
    depth_by_qubit = defaultdict(int)
    twoq_depth_by_qubit = defaultdict(int)
    tstage_by_qubit = defaultdict(int)
    t_block = defaultdict(lambda: True)

    def barrier_touch(qubits):
        for q in qubits:
            t_block[q] = True

    for inst, qargs, cargs in qc.data:
        name = inst.name.lower()
        if name in ("t", "tdg", "z", "rz", "s", "sdg"):
            if name in ("t", "tdg"):
                q = qargs[0].index
                if t_block[q]:
                    tstage_by_qubit[q] += 1
                    t_block[q] = False
                stats[name] += 1
            continue
        if name in ("h", "x"):
            q = qargs[0].index
            if name in stats:
                stats[name] += 1
            depth_by_qubit[q] = depth_by_qubit[q] + 1
            barrier_touch([q])
            continue
        if name == "cx":
            a = qargs[0].index
            b = qargs[1].index
            stats["cx"] += 1
            layer = max(depth_by_qubit[a], depth_by_qubit[b]) + 1
            depth_by_qubit[a] = depth_by_qubit[b] = layer
            two_layer = max(twoq_depth_by_qubit[a], twoq_depth_by_qubit[b]) + 1
            twoq_depth_by_qubit[a] = twoq_depth_by_qubit[b] = two_layer
            barrier_touch([a, b])
            continue
        if name in ("ccx", "toffoli"):
            a = qargs[0].index
            b = qargs[1].index
            c = qargs[2].index
            stats["ccx"] += 1
            layer = max(depth_by_qubit[a], depth_by_qubit[b], depth_by_qubit[c]) + 1
            depth_by_qubit[a] = depth_by_qubit[b] = depth_by_qubit[c] = layer
            two_layer = max(twoq_depth_by_qubit[a], twoq_depth_by_qubit[b], twoq_depth_by_qubit[c]) + 2
            twoq_depth_by_qubit[a] = twoq_depth_by_qubit[b] = twoq_depth_by_qubit[c] = two_layer
            barrier_touch([a, b, c])
            continue
        if name == "measure":
            q = qargs[0].index
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
    qc = QuantumCircuit.from_qasm_str(qasm)
    print(analyze(qc))

if __name__ == "__main__":
    main()