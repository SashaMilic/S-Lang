# tools/self_check_grover.py
import math
from collections import Counter
import numpy as np

from slang.parser import Program
from slang.interpreter import Interpreter

def idx_msb(bitstr: str) -> int:
    # leftmost char = MSB, r[0] is LSB
    n = len(bitstr)
    idx = 0
    for i, b in enumerate(bitstr):
        if b == '1':
            idx |= 1 << (n - 1 - i)
    return idx

def idx_lsb(bitstr: str) -> int:
    # rightmost char = MSB (WRONG for our convention, but good to compare)
    idx = 0
    for i, b in enumerate(reversed(bitstr)):
        if b == '1':
            idx |= 1 << i
    return idx

def run_once(n=3, marked="101", shots=200):
    src = f"""
    SEED 1
    ALLOCATE r {n}
    HADAMARD_LAYER r
    GROVER_ITERATE r "{marked}"
    MEASURE r SHOTS {shots}
    """
    p = Program(src).parse()
    it = Interpreter(p)

    # Peek before running to compute indexes
    msb_idx = idx_msb(marked)
    lsb_idx = idx_lsb(marked)

    # Run (this performs H^n, oracle, diffusion, then samples)
    counts = it.run()
    psi = it.state.state  # statevector after measurement sampling (interpreter keeps vector)

    # Amplitude (just for introspection — sampling already done)
    amp_msb = psi[msb_idx]
    amp_lsb = psi[lsb_idx]

    total = sum(counts.values()) or 1
    probs = {k: v / total for k, v in counts.items()}

    print("=== Grover Self-Check ===")
    print(f"n={n}, marked='{marked}'")
    print(f"Index (MSB order)  : {msb_idx}")
    print(f"Index (LSB order)  : {lsb_idx}")
    print(f"|amp|^2 @ MSB index: {abs(amp_msb)**2:.6f}")
    print(f"|amp|^2 @ LSB index: {abs(amp_lsb)**2:.6f}")
    print(f"Counts (shots={total}): {dict(counts)}")
    # Normalize and show top few
    top = sorted(probs.items(), key=lambda kv: kv[1], reverse=True)[:8]
    print("Top outcomes (prob):")
    for k, p in top:
        print(f"  {k}: {p:.3f}")
    # Convenience asserts (won't raise, just prints guidance)
    if counts.get(marked, 0) == 0:
        print("NOTE: marked bitstring did not appear in samples.")
        print("      If |amp|^2@MSB is high but samples miss it, increase shots.")
    print("=========================\n")

if __name__ == "__main__":
    # 3-qubit canonical case; single Grover iterate should put ~78% on the marked item
    run_once(n=3, marked="101", shots=256)

    # Also try another mark to see consistency
    run_once(n=3, marked="011", shots=256)