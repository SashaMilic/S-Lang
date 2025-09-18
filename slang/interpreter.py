from .parser import Program, eval_expr
from .runtime import StateVector, H, X, Z, Rz, CNOT_4
import numpy as np
import math, cmath, re
from typing import List

def _cr_phase(theta: float) -> np.ndarray:
    return np.diag([1,1,1, cmath.exp(1j*theta)]).astype(np.complex128)

# Pauli matrices for EXPECT/VAR
_P = {
    "I": np.eye(2, dtype=np.complex128),
    "X": np.array([[0,1],[1,0]], dtype=np.complex128),
    "Y": np.array([[0,-1j],[1j,0]], dtype=np.complex128),
    "Z": np.array([[1,0],[0,-1]], dtype=np.complex128),
}

class Interpreter:
    """Tiny statevector interpreter for a subset of S-Lang (+ Grover, EXPECT/VAR, FN/CALL)."""
    def __init__(self, program: Program):
        if program.n_qubits is None:
            raise ValueError("Program must ALLOCATE before run")
        self.p = program
        self.state = StateVector(program.n_qubits)
        self.env = {}
        self.cbits = {}
        self.counts = None
        self.fn_defs = dict(getattr(program, "fn_defs", {}))

    def _idx(self, expr: str) -> int:
        val = int(round(eval(expr, {"__builtins__": None}, {})))
        if not (0 <= val < self.p.n_qubits):
            raise IndexError(f"qubit index {val} out of range")
        return val

    def _run_text(self, text: str):
        sub = Program(text).parse()
        it = Interpreter(sub)
        it.state = self.state
        it.env = self.env
        it.cbits = self.cbits
        it.fn_defs = dict(self.fn_defs)
        it.run()
        self.state = it.state
        self.env = it.env
        self.cbits = it.cbits
        self.counts = it.counts
        self.fn_defs = it.fn_defs

    def _cond(self, expr: str) -> bool:
        s = expr
        for name, val in self.cbits.items():
            s = s.replace(name, "1" if val else "0")
        try:
            return bool(eval(s, {"__builtins__": None}, {}))
        except Exception:
            return False

    # ---- QFT/IQFT helpers ----
    def _swap(self, a:int, b:int):
        self.state.apply_two(a,b,CNOT_4)
        self.state.apply_two(b,a,CNOT_4)
        self.state.apply_two(a,b,CNOT_4)

    def _qft(self, noswap: bool):
        n = self.p.n_qubits
        for j in range(n):
            self.state.apply_single(j, H)
            for k in range(j+1, n):
                theta = math.pi / (2**(k-j))
                self.state.apply_two(k, j, _cr_phase(theta))
        if not noswap:
            for i in range(n//2):
                self._swap(i, n-1-i)

    def _iqft(self, reverse_swaps: bool):
        n = self.p.n_qubits
        if reverse_swaps:
            for i in range(n//2):
                self._swap(i, n-1-i)
        for j in reversed(range(n)):
            for k in reversed(range(j+1, n)):
                theta = -math.pi / (2**(k-j))
                self.state.apply_two(k, j, _cr_phase(theta))
            self.state.apply_single(j, H)

    # ---- Grover helpers ----
    def _markstate(self, bitstr: str):
        # phase flip on the single basis state matching bitstr
        if len(bitstr) != self.p.n_qubits:
            raise ValueError("MARKSTATE bitstring length must match register size")
        n = self.p.n_qubits
        # Multiply amplitude of matching basis state by -1
        idx = 0
        for i, b in enumerate(reversed(bitstr)):  # bit 0 = r[0] (LSB)
            if b == '1':
                idx |= (1 << i)
        self.state.state[idx] *= -1

    def _diffusion_exact(self):
        # Inversion about the mean: H^n X^n (phase flip on |0...0>) X^n H^n
        n = self.p.n_qubits
        for q in range(n): self.state.apply_single(q, H)
        for q in range(n): self.state.apply_single(q, X)
        # phase flip on |0...0>
        self.state.state[0] *= -1
        for q in range(n): self.state.apply_single(q, X)
        for q in range(n): self.state.apply_single(q, H)

    # ---- EXPECT / VAR ----
    def _parse_indices(self, parts: List[str]) -> List[int]:
        idxs=[]
        for s in parts:
            m = re.match(r"\w+\[\s*(.+)\s*\]$", s)
            if not m: raise ValueError(f"Bad qubit ref: {s}")
            idxs.append(self._idx(m.group(1)))
        return idxs

    def _expect_pauli(self, pauli: str, qubits: List[int]) -> float:
        if len(pauli) != len(qubits):
            raise ValueError("Pauli string length must match number of qubits")
        # Build full operator on n qubits (tensor I on others)
        ops = {q:_P[p] for p,q in zip(pauli, qubits)}
        N = self.p.n_qubits
        full = None
        for q in range(N-1, -1, -1):  # big-endian Kron order to match state basis
            op = ops.get(q, _P["I"])
            full = op if full is None else np.kron(op, full)
        psi = self.state.state
        val = np.vdot(psi, full @ psi)
        return float(val.real)  # imaginary should be ~0

    def run(self):
        for ins in self.p.instructions:
            op, args = ins.op, ins.args

            if op in ("ALLOCATE", "LET", "FN_DEF"):
                continue

            if op in ("H", "X", "Z"):
                q = self._idx(args[1])
                if op == "H": self.state.apply_single(q, H)
                elif op == "X": self.state.apply_single(q, X)
                elif op == "Z": self.state.apply_single(q, Z)
                continue

            if op == "RZ_EXPR":
                q = self._idx(args[1]); theta = float(eval(args[2], {"__builtins__": None, "pi": math.pi}))
                self.state.apply_single(q, Rz(theta)); continue

            if op == "CNOT_EXPR":
                c = self._idx(args[1]); t = self._idx(args[2]); self.state.apply_two(c, t, CNOT_4); continue

            if op == "HADAMARD_LAYER":
                for q in range(self.p.n_qubits): self.state.apply_single(q, H); continue

            if op == "DIFFUSION":
                self._diffusion_exact(); continue

            if op == "MARKSTATE":
                _, bitstr = args; self._markstate(bitstr); continue

            if op == "GROVER_ITERATE":
                _, bitstr = args; self._markstate(bitstr); self._diffusion_exact(); continue

            if op == "QFT":
                _, noswap = args; self._qft(noswap); continue

            if op == "IQFT":
                _, reverse_swaps = args; self._iqft(reverse_swaps); continue

            if op == "EXPECT":
                pauli, regs = args
                idxs = self._parse_indices(regs)
                val = self._expect_pauli(pauli, idxs)
                print(f"EXPECT {pauli} on {idxs} = {val:.6f}")
                continue

            if op == "VAR":
                pauli, regs = args
                idxs = self._parse_indices(regs)
                e = self._expect_pauli(pauli, idxs)
                # Var(P) = 1 - <P>^2 for Pauli (eigenvalues ±1)
                var = 1.0 - e*e
                print(f"VAR {pauli} on {idxs} = {var:.6f}")
                continue

            if op == "MEASURE_ONE_EXPR":
                q = self._idx(args[1])
                c = self.state.sample_all(1); bit = list(c.keys())[0][q]
                self.cbits[args[2]] = int(bit); continue

            if op == "MEASURE_ALL":
                shots = args[1]; self.counts = self.state.sample_all(shots); continue

            if op == "IF_CHAIN":
                (blocks,) = args
                taken = False
                for kind, cond, body in blocks:
                    if kind in ("IF", "ELIF") and (not taken) and self._cond(cond):
                        self._run_text("\n".join(body) + "\n"); taken = True
                    elif kind == "ELSE" and not taken:
                        self._run_text("\n".join(body) + "\n"); taken = True
                continue

            if op == "FOR_IN_REG":
                var, reg, body = args
                for i in range(self.p.n_qubits):
                    self.env[var] = float(i)
                    self._run_text(body.replace("r[q]", f"r[{i}]"))
                self.env.pop(var, None)
                continue

            if op == "CALL":
                name, vals = args
                if name not in self.fn_defs:
                    raise ValueError(f"Unknown function {name}")
                formal, body = self.fn_defs[name]
                if len(formal) != len(vals):
                    raise ValueError("CALL arity mismatch")
                # simple textual substitution for indices
                subst = body
                for f, v in zip(formal, vals):
                    subst = re.sub(rf"\br\[\s*{re.escape(f)}\s*\]", f"r[{int(eval(v, {'__builtins__':None}, {}))}]", subst)
                self._run_text(subst)
                continue

        return self.counts