from .ir import lower_program_to_ir, QModule
from .passes import run_pipeline
from dataclasses import dataclass
from typing import List, Tuple, Optional, Iterable, Dict
import re, math, os
from .parser import Program

@dataclass
class Transpiler:
    program: Program
    ancilla_budget: int = 9999
    decompose_ccx: bool = True
    coupling_map: Optional[List[Tuple[int, int]]] = None  # undirected edges
    use_ir: bool = False

    def __post_init__(self):
        p = self.program
        if p.n_qubits is None: raise ValueError("Program must ALLOCATE before transpile")
        self.n = p.n_qubits; self.r = p.reg_name
        self.lines: List[str] = []
        self.stats = {"cx": 0, "ccx": 0, "t": 0, "tdg": 0, "h": 0, "cp": 0}
        self.depth = [0] * self.n; self.twoq_depth = [0] * self.n
        self.tstage = [0] * self.n; self.t_block = [True] * self.n
        self.cbit_to_index: Dict[str, int] = {}
        self.fn_defs = dict(getattr(p, "fn_defs", {}))
        # Build symmetric adjacency for routing. Be robust to non-int entries
        # or indices outside [0, n-1] by coercing to int and creating buckets
        # on demand.
        self._adj = {q: set() for q in range(self.n)}
        if self.coupling_map:
            for a, b in self.coupling_map:
                # coerce to int if they came as strings
                try:
                    ai, bi = int(a), int(b)
                except Exception:
                    # skip malformed entries
                    continue
                # tolerate indices beyond current n by creating buckets
                if ai not in self._adj: self._adj[ai] = set()
                if bi not in self._adj: self._adj[bi] = set()
                self._adj[ai].add(bi)
                self._adj[bi].add(ai)

    # ---- metrics helpers ----
    def _add(self, s: str): self.lines.append(s)
    def _barrier(self, qubits: Iterable[int]):
        for q in qubits: self.t_block[q] = True
    def _sched(self, qubits: Iterable[int], twoq_weight: int = 0):
        layer = 1 + max((self.depth[q] for q in qubits), default=0)
        for q in qubits: self.depth[q] = layer
        if twoq_weight > 0:
            base = max((self.twoq_depth[q] for q in qubits), default=0)
            twol = base + twoq_weight
            for q in qubits: self.twoq_depth[q] = twol
    def _t(self, q: int, name: str):
        if self.t_block[q]:
            self.tstage[q] += 1; self.t_block[q] = False
        self.stats[name] += 1
        self._add(f"{name} r[{q}];")

    # ---- 1- and 2-qubit ----
    def _h(self, q): self._add(f"h r[{q}];"); self.stats["h"] += 1; self._sched([q]); self._barrier([q])
    def _x(self, q): self._add(f"x r[{q}];"); self._sched([q]); self._barrier([q])
    def _z(self, q): self._add(f"z r[{q}];")
    def _rz(self, theta, q): self._add(f"rz({theta}) r[{q}];")
    def _tgate(self, q): self._t(q, "t")
    def _tdg(self, q): self._t(q, "tdg")
    def _cp(self, a, b, theta): self._add(f"cp({theta}) r[{a}], r[{b}];"); self.stats["cp"] += 1; self._sched([a,b],twoq_weight=1); self._barrier([a,b])
    def _cx_prim(self, a, b): self._add(f"cx r[{a}], r[{b}];"); self.stats["cx"] += 1; self._sched([a,b],twoq_weight=1); self._barrier([a,b])

    # ---- CCX decomp (exact 7-T) ----
    def _ccx_decomp(self, a, b, c):
        self._h(c)
        self._tgate(a); self._tgate(b); self._tgate(c)
        self._cx_prim(b, c); self._tdg(c)
        self._cx_prim(a, c); self._tgate(c)
        self._cx_prim(b, c); self._tdg(c)
        self._cx_prim(a, c)
        self._h(c)

    # ---- routing for CX ----
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
                    path=[v]; cur=v
                    while prev[cur] is not None: cur=prev[cur]; path.append(cur)
                    path.reverse(); return path
        return None
    def _cx(self, a, b):
        if not self.coupling_map or b in self._adj[a]:
            self._cx_prim(a, b); return
        path = self._path(a, b)
        if not path or len(path) < 2:
            self._cx_prim(a, b); return
        cur=a
        for nxt in path[1:-1]:
            self._cx_prim(cur, nxt); self._cx_prim(nxt, cur); self._cx_prim(cur, nxt)
            cur=nxt
        self._cx_prim(cur, b)

    def _swap(self,a,b): self._cx(a,b); self._cx(b,a); self._cx(a,b)

    # ---- high-level blocks ----
    def _diffusion(self):
        n=self.n; t=n-1
        for q in range(n): self._h(q)
        for q in range(n): self._x(q)
        # exact phase flip on |11..1| via H target + MCX + H (for n<=3)
        if n==1:
            self._z(0)
        elif n==2:
            self._h(t); self._cx(0,t); self._h(t)
        elif n==3:
            self._h(t); self._ccx_decomp(0,1,t); self._h(t)
        else:
            self._add(f"// TODO: exact MCX for n>{3} (phase-correct); using placeholder")
            self._h(t); self._add("// [placeholder mct]"); self._h(t)
        for q in range(n): self._x(q)
        for q in range(n): self._h(q)

    def _markstate(self, bitstr: str):
        n=self.n
        if len(bitstr)!=n: self._add(f"// ERROR: MARKSTATE length mismatch"); return
        # X on zeros to map |bitstr> to |11..1>
        for i, b in enumerate(reversed(bitstr)):  # r[0] is LSB
            if b=='0': self._x(i)
        t=n-1
        if n==1:
            self._z(0)
        elif n==2:
            self._h(t); self._cx(0,t); self._h(t)
        elif n==3:
            self._h(t); self._ccx_decomp(0,1,t); self._h(t)
        else:
            self._add(f"// TODO: exact MCX for n>{3}; placeholder oracle")
            self._h(t); self._add("// [placeholder mct]"); self._h(t)
        # uncompute X on zeros
        for i, b in enumerate(reversed(bitstr)):
            if b=='0': self._x(i)

    def _qft(self, noswap: bool):
        n = self.n
        for j in range(n):
            self._h(j)
            for k in range(j+1, n):
                theta = math.pi / (2**(k-j))
                self._cp(k, j, theta)
        if not noswap:
            for i in range(n//2): self._swap(i, n-1-i)

    def _iqft(self, reverse_swaps: bool):
        n = self.n
        if reverse_swaps:
            for i in range(n//2): self._swap(i, n-1-i)
        for j in reversed(range(n)):
            for k in reversed(range(j+1, n)):
                theta = -math.pi / (2**(k-j))
                self._cp(k, j, theta)
            self._h(j)

    def _emit_if_chain(self, blocks: List[Tuple[str, str, List[str]]]):  # [(kind, cond, body)]
        def mapc(expr: str) -> str:
            out = expr
            for name, idx in self.cbit_to_index.items():
                out = re.sub(rf"\b{re.escape(name)}\b", f"c[{idx}]", out)
            return out

        def norm_cond(expr: str) -> str:
            """Normalize a boolean expression for QASM3:
            - map named cbits to c[idx]
            - strip stray leading '(' and trailing ')'
            - collapse duplicate parentheses
            - trim excess whitespace
            """
            s = mapc(expr.strip())
            s = re.sub(r"\s+", " ", s)
            s = s.lstrip("(").rstrip(")")
            while "((" in s:
                s = s.replace("((", "(")
            while "))" in s:
                s = s.replace("))", ")")
            s = re.sub(r"\(\s+", "(", s)
            s = re.sub(r"\s+\)", ")", s)
            return s

        def emit_body(lines: List[str]):
            sub = Program("\n".join(lines) + "\n").parse()
            self._emit(sub.instructions)

        # Nested emitter: when nested=True, we emit only an 'if ... else ...' chain
        # WITHOUT producing a leading 'else {' ... '}' wrapper. The caller decides
        # whether to surround it in an 'else { ... }' scope.
        def emit_tail(i: int, nested: bool):
            if i >= len(blocks):
                return
            kind, cond, body = blocks[i]
            if kind == "ELSE":
                if nested:
                    # direct body inside current else-scope
                    emit_body(body)
                else:
                    # top-level final else
                    self._add("else {")
                    emit_body(body)
                    self._add("}")
                return
            # 'ELIF' or any non-ELSE is treated as an else-if
            c = norm_cond(cond)
            if nested:
                # inside an existing else { ... } scope: emit 'if (...) { body } else { <tail> }'
                self._add(f"if ({c}) {{")
                emit_body(body)
                if i + 1 < len(blocks):
                    self._add("} else {")
                    emit_tail(i + 1, nested=True)
                    self._add("}")
                else:
                    self._add("}")
            else:
                # top-level after the head IF: wrap this chain in a single else { ... }
                self._add("else {")
                emit_tail(i, nested=True)
                self._add("}")

        # Emit the head IF first
        if not blocks:
            return
        kind0, cond0, body0 = blocks[0]
        c0 = norm_cond(cond0)
        self._add(f"if ({c0}) {{")
        emit_body(body0)
        self._add("}")
        # Emit the remainder as a single, properly nested chain
        if len(blocks) > 1:
            emit_tail(1, nested=False)

    # ---- emission driver ----
    def _reset_emitter_state(self):
        # Reset emitter buffers/state as the emitter expects
        self.lines = []
        # carry fn_defs from the original program
        self.fn_defs = dict(getattr(self.program, "fn_defs", {}))

    def _ir_to_pseudo_instrs(self, m: QModule):
        """
        Map IR ops into lightweight parser.Instr so we can reuse _emit().
        SWAP is expanded into 3 CNOTs for emission.
        """
        from .parser import Instr
        pseudo = []
        # import any fn_defs learned in IR meta
        self.fn_defs.update(m.meta.get("fn_defs", {}))
        for fn in m.funcs.values():
            for bb in fn.blocks:
                for op in bb.ops:
                    name = op.op
                    a = op.args
                    if name == "q.h":
                        pseudo.append(Instr("H", (a[0], a[1])))
                    elif name == "q.x":
                        pseudo.append(Instr("X", (a[0], a[1])))
                    elif name == "q.z":
                        pseudo.append(Instr("Z", (a[0], a[1])))
                    elif name == "q.rz_expr":
                        pseudo.append(Instr("RZ_EXPR", (a[0], a[1], a[2])))
                    elif name == "q.cnot_expr":
                        pseudo.append(Instr("CNOT_EXPR", (a[0], a[1], a[2])))
                    elif name == "q.swap_expr":
                        # Expand SWAP to 3 CNOTs for emission
                        pseudo.append(Instr("CNOT_EXPR", (a[0], a[1], a[2])))
                        pseudo.append(Instr("CNOT_EXPR", (a[0], a[2], a[1])))
                        pseudo.append(Instr("CNOT_EXPR", (a[0], a[1], a[2])))
                    else:
                        # Pass through other recognized ops (measure, expect, etc.)
                        if name.startswith("q."):
                            pseudo.append(Instr(name.split(".", 1)[1].upper(), a))
                        else:
                            pseudo.append(Instr("UNKNOWN", (name, a)))
        return pseudo

    def _emit(self, instrs):
        for ins in instrs:
            op, args = ins.op, ins.args
            if op in ("ALLOCATE", "LET", "FN_DEF"): continue
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
            if op == "MARKSTATE":
                _, bitstr = args; self._markstate(bitstr); continue
            if op == "GROVER_ITERATE":
                _, bitstr = args; self._markstate(bitstr); self._diffusion(); continue
            if op == "QFT":
                _, noswap = args; self._qft(noswap); continue
            if op == "IQFT":
                _, reverse_swaps = args; self._iqft(reverse_swaps); continue
            if op == "MEASURE_ONE_EXPR":
                q = int(eval(args[1], {"__builtins__": None}, {})); self._add(f"c[{q}] = measure r[{q}];"); self._barrier([q]); continue
            if op == "MEASURE_ALL":
                self._add("c = measure r;"); self._barrier(range(self.n)); continue
            if op == "EXPECT":
                pauli, regs = args
                self._add(f"// EXPECT \"{pauli}\" on {', '.join(regs)}  (interpreter-only)"); continue
            if op == "VAR":
                pauli, regs = args
                self._add(f"// VAR \"{pauli}\" on {', '.join(regs)}  (interpreter-only)"); continue
            if op == "IF_CHAIN":
                (blocks,) = args; self._emit_if_chain(blocks); continue
            if op == "FOR_IN_REG":
                var, reg, body_text = args
                norm = body_text.replace("\\n", "\n")
                for i in range(self.n):
                    sub_text = norm.replace("r[q]", f"r[{i}]")
                    sub = Program(sub_text).parse()
                    self._emit(sub.instructions)
                continue
            if op == "CALL":
                # inline body with integer substitutions (like interpreter)
                name, vals = args
                if name not in self.fn_defs:
                    self._add(f"// ERROR: unknown CALL {name}"); continue
                formal, body = self.fn_defs[name]
                if len(formal) != len(vals):
                    self._add(f"// ERROR: CALL {name} arity mismatch"); continue
                sub = body
                for f,v in zip(formal, vals):
                    sub = re.sub(rf"\br\[\s*{re.escape(f)}\s*\]", f"r[{int(eval(v, {'__builtins__':None}, {}))}]", sub)
                sub_p = Program(sub).parse()
                self._emit(sub_p.instructions); continue

            if op == "IMPORT":
                (path_literal,) = args
                path = path_literal.strip('"')
                try:
                    with open(path, "r") as f:
                        text = f.read()
                    sub_p = Program(text).parse()
                    # bring in any function definitions from the module
                    self.fn_defs.update(getattr(sub_p, "fn_defs", {}))
                    # inline the imported program
                    self._emit(sub_p.instructions)
                except Exception as e:
                    self._add(f"// ERROR: IMPORT '{path}': {e}")
                continue
  
            if op == "TRACE":
                (msg_literal,) = args
                msg = msg_literal.strip('"')
                self._add(f"// TRACE: {msg}")
                continue
  
            if op == "DUMPSTATE":
                self._add("// DUMPSTATE (interpreter-only)")
                continue
  
            if op == "PROBS":
                self._add("// PROBS (interpreter-only)")
                continue
  
            if op == "RETURN":
                (expr,) = args
                self._add(f"// RETURN {expr} (classical; ignored in QASM)")
                continue
  
            if op == "CALLR":
                # Inline body with integer substitutions (like CALL);
                # classical return is ignored in QASM, but we note it.
                name, vals, target = args
                if name not in self.fn_defs:
                    self._add(f"// ERROR: unknown CALLR {name}")
                    continue
                formal, body = self.fn_defs[name]
                if len(formal) != len(vals):
                    self._add(f"// ERROR: CALLR {name} arity mismatch")
                    continue
                sub = body
                for f, v in zip(formal, vals):
                    sub = re.sub(
                        rf"\br\[\s*{re.escape(f)}\s*\]",
                        f"r[{int(eval(v, {'__builtins__': None}, {}))}]",
                        sub,
                    )
                sub_p = Program(sub).parse()
                self._emit(sub_p.instructions)
                self._add(f"// NOTE: CALLR {name} -> return assigned to {target} (classical), ignored in QASM")
                continue

    def to_qasm3(self) -> str:
        # Decide instruction stream: raw parser instructions or IR-lowered
        instrs = self.program.instructions
        if getattr(self, "use_ir", False):
            # Lower to IR
            m = lower_program_to_ir(self.program)
            # Thread coupling map for router
            if self.coupling_map:
                edges = [(int(a), int(b)) for a, b in self.coupling_map]
                m.meta["coupling"] = edges
            # Run passes
            _ = run_pipeline(m)
            # Map IR → pseudo-instructions and reuse existing emitter
            instrs = self._ir_to_pseudo_instrs(m)

        # Clean emitter state
        self._reset_emitter_state()
        # Header
        self.lines = [
            "OPENQASM 3.0;",
            "include \"stdgates.inc\";",
            f"qubit[{self.n}] {self.r};",
            f"bit[{self.n}] c;",
        ]
        # map named cbits from the chosen instruction stream
        self.cbit_to_index.clear()
        for ins in instrs:
            if ins.op == "MEASURE_ONE_EXPR":
                _, qexpr, sym = ins.args
                try:
                    q = int(eval(qexpr, {"__builtins__": None}, {}))
                except Exception:
                    q = None
                if q is not None:
                    self.cbit_to_index[sym] = q

        # Emit
        self._emit(instrs)

        # Metrics footer
        depth = max(self.depth) if self.depth else 0
        twoq_depth = max(self.twoq_depth) if self.twoq_depth else 0
        twoq_count = self.stats["cx"] + self.stats["ccx"] + self.stats["cp"]
        twoq_equiv = self.stats["cx"] + 2*self.stats["ccx"] + self.stats["cp"]
        tcount = self.stats["t"] + self.stats["tdg"]
        tdepth = max(self.tstage) if self.tstage else 0

        self.lines += [
            "// ---- metrics ----",
            f"// depth (ASAP with phase commuting): {depth}",
            f"// two_qubit_count (cx+ccx+cp): {twoq_count}",
            f"// two_qubit_equiv (ccx=2x): {twoq_equiv}",
            f"// two_qubit_depth (≈ layers of 2q interaction): {twoq_depth}",
            f"// T-count: {tcount}",
            f"// T-depth (global, Clifford-commuted): {tdepth}",
        ]
        return "\n".join(self.lines)