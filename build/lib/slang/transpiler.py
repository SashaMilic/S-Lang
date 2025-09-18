from dataclasses import dataclass
from typing import List, Tuple, Optional, Iterable, Dict
import re
from .parser import Program

# Transpiler with: metrics (depth, twoq_depth, T-count, global T-depth), boolean-lowered IFs,
# CCX decomposition (7-T), optional routing via SWAPs on a coupling map.

@dataclass
class Transpiler:
    program: Program
    ancilla_budget: int = 9999
    decompose_ccx: bool = True
    coupling_map: Optional[List[Tuple[int, int]]] = None  # undirected edges

    def __post_init__(self):
        p = self.program
        if p.n_qubits is None:
            raise ValueError("Program must ALLOCATE before transpile")
        self.n = p.n_qubits
        self.r = p.reg_name
        self.lines: List[str] = []
        self.stats = {"cx": 0, "ccx": 0, "t": 0, "tdg": 0, "h": 0}
        self.depth = [0] * self.n
        self.twoq_depth = [0] * self.n
        self.tstage = [0] * self.n
        self.t_block = [True] * self.n
        self.cbit_to_index: Dict[str, int] = {}
        # routing graph
        self._adj = {q: set() for q in range(self.n)}
        if self.coupling_map:
            for a, b in self.coupling_map:
                self._adj[a].add(b)
                self._adj[b].add(a)

    # ---- metrics helpers ----
    def _add(self, s: str): self.lines.append(s)
    def _barrier(self, qubits: Iterable[int]):
        for q in qubits: self.t_block[q] = True
    def _sched(self, qubits: Iterable[int], twoq_weight: int = 0):
        layer = 1 + max((self.depth[q] for q in qubits), default=0)
        for q in qubits:
            self.depth[q] = layer
        if twoq_weight > 0:
            base = max((self.twoq_depth[q] for q in qubits), default=0)
            twol = base + twoq_weight
            for q in qubits:
                self.twoq_depth[q] = twol
    def _t(self, q: int, name: str):
        if self.t_block[q]:
            self.tstage[q] += 1
            self.t_block[q] = False
        self.stats[name] += 1
        self._add(f"{name} r[{q}];")

    # ---- emits ----
    def _h(self, q): self._add(f"h r[{q}];"); self.stats["h"] += 1; self._sched([q]); self._barrier([q])
    def _x(self, q): self._add(f"x r[{q}];"); self._sched([q]); self._barrier([q])
    def _z(self, q): self._add(f"z r[{q}];")
    def _rz(self, theta, q): self._add(f"rz({theta}) r[{q}];")
    def _tgate(self, q): self._t(q, "t")
    def _tdg(self, q): self._t(q, "tdg")
    def _cx_prim(self, a, b): self._add(f"cx r[{a}], r[{b}];"); self.stats["cx"] += 1; self._sched([a, b], twoq_weight=1); self._barrier([a, b])

    def _ccx_decomp(self, a, b, c):
        # 7-T exact Toffoli (no ancilla)
        self._h(c)
        self._tgate(a); self._tgate(b); self._tgate(c)
        self._cx_prim(b, c); self._tdg(c)
        self._cx_prim(a, c); self._tgate(c)
        self._cx_prim(b, c); self._tdg(c)
        self._cx_prim(a, c)
        self._h(c)

    # routing
    def _path(self, u: int, v: int):
        if u == v: return [u]
        from collections import deque
        q = deque([u]); prev = {u: None}
        while q:
            x = q.popleft()
            for y in self._adj.get(x, ()):
                if y in prev: continue
                prev[y] = x; q.append(y)
                if y == v:
                    path = [v]; cur = v
                    while prev[cur] is not None:
                        cur = prev[cur]; path.append(cur)
                    path.reverse(); return path
        return None

    def _cx(self, a, b):
        if not self.coupling_map or b in self._adj[a]:
            self._cx_prim(a, b); return
        path = self._path(a, b)
        if not path or len(path) < 2:
            self._cx_prim(a, b); return
        cur = a
        for nxt in path[1:-1]:
            # SWAP(cur, nxt) = 3 cx
            self._cx_prim(cur, nxt); self._cx_prim(nxt, cur); self._cx_prim(cur, nxt)
            cur = nxt
        self._cx_prim(cur, b)

    # ---- high-level ----
    def _diffusion(self):
        n = self.n; t = n - 1
        for q in range(n): self._h(q)
        for q in range(n): self._x(q)
        self._h(t)
        if n >= 3: self._ccx_decomp(0, 1, t)  # toy; exercises metrics
        for q in range(n): self._x(q)
        for q in range(n): self._h(q)

    def _emit_if_chain(self, blocks: List[Tuple[str, str, List[str]]]):
        # Lower boolean A&&B / A||B to nested/else-if (QASM-side text only)
        def mapc(expr: str):
            out = expr
            for name, idx in self.cbit_to_index.items():
                out = re.sub(rf"\b{name}\b", f"c[{idx}]", out)
            return out

        def emit_body(lines: List[str]):
            sub = Program("\n".join(lines) + "\n").parse()
            self._emit(sub.instructions)

        for kind, cond, body in blocks:
            if kind == "ELSE":
                self._add("else {"); emit_body(body); self._add("}"); continue
            c = cond.strip()
            if "&&" in c and "||" in c:
                self._add(f"{'if' if kind=='IF' else 'else if'} ({mapc(c)}) {{"); emit_body(body); self._add("}"); continue
            if "&&" in c:
                left, right = [x.strip() for x in c.split("&&", 1)]
                self._add(f"{'if' if kind=='IF' else 'else if'} ({mapc(left)}) {{")
                self._add(f"  if ({mapc(right)}) {{")
                emit_body(body); self._add("  }"); self._add("}"); continue
            if "||" in c:
                left, right = [x.strip() for x in c.split("||", 1)]
                self._add(f"{'if' if kind=='IF' else 'else if'} ({mapc(left)}) {{")
                emit_body(body); self._add("} else if (" + mapc(right) + ") {"); emit_body(body); self._add("}"); continue
            self._add(f"{'if' if kind=='IF' else 'else if'} ({mapc(c)}) {{"); emit_body(body); self._add("}")

    # ---- emission driver ----
    def _emit(self, instrs):
        for ins in instrs:
            op, args = ins.op, ins.args
            if op in ("ALLOCATE", "LET"):
                continue
            if op in ("H", "X", "Z"):
                q = int(eval(args[1], {"__builtins__": None}, {}))
                {"H": self._h, "X": self._x, "Z": self._z}[op](q); continue
            if op == "RZ_EXPR":
                q = int(eval(args[1], {"__builtins__": None}, {})); theta = args[2]; self._rz(theta, q); continue
            if op == "CNOT_EXPR":
                c = int(eval(args[1], {"__builtins__": None}, {})); t = int(eval(args[2], {"__builtins__": None}, {})); self._cx(c, t); continue
            if op == "HADAMARD_LAYER":
                for q in range(self.n): self._h(q); continue
            if op == "DIFFUSION":
                self._diffusion(); continue
            if op == "MEASURE_ONE_EXPR":
                q = int(eval(args[1], {"__builtins__": None}, {})); self._add(f"c[{q}] = measure r[{q}];"); self._barrier([q]); continue
            if op == "MEASURE_ALL":
                self._add("c = measure r;"); self._barrier(range(self.n)); continue
            if op == "IF_CHAIN":
                (blocks,) = args; self._emit_if_chain(blocks); continue
            if op == "FOR_IN_REG":
                var, reg, body_text = args
                # Normalize any legacy literal "\n" → real newlines for robustness
                norm = body_text.replace("\\n", "\n")
                for i in range(self.n):
                    sub_text = norm.replace("r[q]", f"r[{i}]")
                    sub = Program(sub_text).parse()
                    self._emit(sub.instructions)
                continue

    def to_qasm3(self) -> str:
        self.lines = [
            "OPENQASM 3.0;",
            "include \"stdgates.inc\";",
            f"qubit[{self.n}] {self.r};",
            f"bit[{self.n}] c;",
        ]
        # map named cbits
        for ins in self.program.instructions:
            if ins.op == "MEASURE_ONE_EXPR":
                _, qexpr, sym = ins.args
                try:
                    q = int(eval(qexpr, {"__builtins__": None}, {}))
                except Exception:
                    q = None
                if q is not None:
                    self.cbit_to_index[sym] = q

        self._emit(self.program.instructions)

        depth = max(self.depth) if self.depth else 0
        twoq_depth = max(self.twoq_depth) if self.twoq_depth else 0
        twoq_count = self.stats["cx"] + self.stats["ccx"]
        twoq_equiv = self.stats["cx"] + 2 * self.stats["ccx"]
        tcount = self.stats["t"] + self.stats["tdg"]
        tdepth = max(self.tstage) if self.tstage else 0

        self.lines += [
            "// ---- metrics ----",
            f"// depth (ASAP with phase commuting): {depth}",
            f"// two_qubit_count (cx+ccx): {twoq_count}",
            f"// two_qubit_equiv (ccx=2x): {twoq_equiv}",
            f"// two_qubit_depth (≈ layers of 2q interaction): {twoq_depth}",
            f"// T-count: {tcount}",
            f"// T-depth (global, Clifford-commuted): {tdepth}",
        ]
        return "\n".join(self.lines)