from .parser import Program, eval_expr
from .runtime import StateVector, H, X, Z, Rz, CNOT_4

class Interpreter:
    """Tiny statevector interpreter for a subset of S-Lang."""
    def __init__(self, program: Program):
        if program.n_qubits is None:
            raise ValueError("Program must ALLOCATE before run")
        self.p = program
        self.state = StateVector(program.n_qubits)
        self.env = {}
        self.cbits = {}
        self.counts = None

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
        it.run()
        self.state = it.state
        self.env = it.env
        self.cbits = it.cbits
        self.counts = it.counts

    def _cond(self, expr: str) -> bool:
        s = expr
        for name, val in self.cbits.items():
            s = s.replace(name, "1" if val else "0")
        try:
            return bool(eval(s, {"__builtins__": None}, {}))
        except Exception:
            return False

    def run(self):
        for ins in self.p.instructions:
            op, args = ins.op, ins.args

            if op in ("ALLOCATE", "LET"):
                continue

            if op in ("H", "X", "Z"):
                q = self._idx(args[1])
                if op == "H":
                    self.state.apply_single(q, H)
                elif op == "X":
                    self.state.apply_single(q, X)
                elif op == "Z":
                    self.state.apply_single(q, Z)
                continue

            if op == "RZ_EXPR":
                q = self._idx(args[1])
                theta = float(eval(args[2], {"__builtins__": None, "pi": 3.1415926535}))
                self.state.apply_single(q, Rz(theta))
                continue

            if op == "CNOT_EXPR":
                c = self._idx(args[1])
                t = self._idx(args[2])
                self.state.apply_two(c, t, CNOT_4)
                continue

            if op == "HADAMARD_LAYER":
                for q in range(self.p.n_qubits):
                    self.state.apply_single(q, H)
                continue

            if op == "DIFFUSION":
                # very toy: H->X->CX(last-1,last)->X->H
                n = self.p.n_qubits
                for q in range(n):
                    self.state.apply_single(q, H)
                for q in range(n):
                    self.state.apply_single(q, X)
                if n >= 2:
                    self.state.apply_two(n - 2, n - 1, CNOT_4)
                for q in range(n):
                    self.state.apply_single(q, X)
                for q in range(n):
                    self.state.apply_single(q, H)
                continue

            if op == "MEASURE_ONE_EXPR":
                q = self._idx(args[1])
                # sample one shot on full register and read bit q
                c = self.state.sample_all(1)
                bit = list(c.keys())[0][q]
                self.cbits[args[2]] = int(bit)
                continue

            if op == "MEASURE_ALL":
                shots = args[1]
                self.counts = self.state.sample_all(shots)
                continue

            if op == "IF_CHAIN":
                (blocks,) = args
                taken = False
                for kind, cond, body in blocks:
                    if kind in ("IF", "ELIF") and (not taken) and self._cond(cond):
                        self._run_text("\n".join(body) + "\n")
                        taken = True
                    elif kind == "ELSE" and not taken:
                        self._run_text("\n".join(body) + "\n")
                        taken = True
                continue

            if op == "FOR_IN_REG":
                var, reg, body = args
                # body uses real newlines; run once per qubit with substitution
                for i in range(self.p.n_qubits):
                    self.env[var] = float(i)
                    self._run_text(body.replace("r[q]", f"r[{i}]"))
                self.env.pop(var, None)
                continue

        return self.counts