# slang/ir.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Any, Iterable

# ------------------------------ Core IR types -------------------------------

@dataclass
class QValue:
    name: str
    ty: str  # "i64", "f64", "bool", "qreg", "qbit", "void"

@dataclass
class QOp:
    op: str
    args: Tuple[Any, ...] = field(default_factory=tuple)
    results: List[QValue] = field(default_factory=list)
    attrs: Dict[str, Any] = field(default_factory=dict)
    loc: Optional[Tuple[int, int]] = None  # (line, col) in source when available
    def __str__(self) -> str:
        res = ""
        if self.results:
            res = ", ".join(v.name for v in self.results) + " = "
        a = ", ".join(repr(x) for x in self.args)
        s = f"{res}{self.op}({a})"
        if self.loc:
            s += f"  // @{self.loc[0]}:{self.loc[1]}"
        return s

@dataclass
class QBlock:
    name: str
    ops: List[QOp] = field(default_factory=list)
    def append(self, op: QOp) -> QOp:
        self.ops.append(op); return op
    # tiny helpers (sugar) used by passes/builders; optional
    def add(self, op: str, *args: Any, loc: Optional[Tuple[int,int]] = None, **attrs: Any) -> QOp:
        return self.append(QOp(op, tuple(args), [], dict(attrs), loc))
    def extend(self, ops: Iterable[QOp]) -> None:
        self.ops.extend(list(ops))

@dataclass
class QFunc:
    name: str
    params: List[QValue] = field(default_factory=list)
    blocks: List[QBlock] = field(default_factory=list)
    ret: Optional[str] = None
    def entry(self) -> QBlock:
        if not self.blocks:
            self.blocks.append(QBlock("entry"))
        return self.blocks[0]
    def new_block(self, name: str) -> QBlock:
        b = QBlock(name); self.blocks.append(b); return b

@dataclass
class QModule:
    funcs: Dict[str, QFunc] = field(default_factory=dict)
    meta: Dict[str, Any] = field(default_factory=dict)
    def add_func(self, fn: QFunc) -> QFunc:
        self.funcs[fn.name] = fn; return fn
    def get_func(self, name: str) -> Optional[QFunc]:
        return self.funcs.get(name)
    def ensure_func(self, name: str) -> QFunc:
        fn = self.get_func(name)
        if fn is None:
            fn = QFunc(name, [], [], None)
            self.add_func(fn)
        return fn
    def dump(self, include_meta: bool = False) -> str:
        out: List[str] = []
        if include_meta and self.meta:
            out.append("// meta: " + repr(self.meta))
        for fn in self.funcs.values():
            hdr = f"fn @{fn.name}(" + ", ".join(f"{p.name}:{p.ty}" for p in fn.params) + ")"
            if fn.ret: hdr += f" -> {fn.ret}"
            out.append(hdr + " {")
            for bb in fn.blocks:
                out.append(f"  ^{bb.name}:")
                for op in bb.ops:
                    out.append("    " + str(op))
            out.append("}")
        return "\n".join(out)

# ------------------------------ Builder utils -------------------------------

class IRBuilder:
    """Tiny helper to build IR in passes/tests without boilerplate."""
    def __init__(self, mod: QModule, func: Optional[QFunc] = None, block: Optional[QBlock] = None):
        self.mod = mod
        self.func = func or mod.ensure_func("main")
        self.block = block or self.func.entry()
    def at(self, block: QBlock) -> "IRBuilder":
        self.block = block; return self
    def op(self, name: str, *args: Any, loc: Optional[Tuple[int,int]] = None, **attrs: Any) -> QOp:
        return self.block.add(name, *args, loc=loc, **attrs)
    # Common gate sugars used by passes
    def h(self, reg: str, i: int): return self.op("q.h", reg, str(i))
    def x(self, reg: str, i: int): return self.op("q.x", reg, str(i))
    def z(self, reg: str, i: int): return self.op("q.z", reg, str(i))
    def rz_expr(self, reg: str, i: int, theta_expr: str): return self.op("q.rz_expr", reg, str(i), theta_expr)
    def cnot_expr(self, reg: str, c: int, t: int): return self.op("q.cnot_expr", reg, str(c), str(t))
    def swap_expr(self, reg: str, i: int, j: int): return self.op("q.swap_expr", reg, str(i), str(j))

# ------------------------------ Verification --------------------------------

def verify_ir(m: QModule) -> List[str]:
    """Lightweight verifier: checks basic module meta and op arities."""
    errs: List[str] = []
    reg = m.meta.get("reg")
    n = m.meta.get("n_qubits")
    if reg is None or n is None:
        errs.append("meta missing: 'reg' or 'n_qubits'")
    # Check op arities for commonly used ops
    arity = {
        "q.h": 2, "q.x": 2, "q.z": 2,
        "q.rz_expr": 3, "q.cnot_expr": 3, "q.swap_expr": 3,
        "q.qft": 2, "q.iqft": 2,
        "q.hadamard_layer": 1,
        "q.measure_all": (1, 2),  # (reg) or (reg, shots)
        "q.expect": 2, "q.var": 2,
    }
    for fn in m.funcs.values():
        for bb in fn.blocks:
            for op in bb.ops:
                need = arity.get(op.op)
                if need is None: continue
                got = len(op.args)
                if isinstance(need, tuple):
                    if got not in need:
                        errs.append(f"arity error: {op.op} expects {need}, got {got}")
                else:
                    if got != need:
                        errs.append(f"arity error: {op.op} expects {need}, got {got}")
    return errs

# ---- Lowering from Program --------------------------------------------------

from .parser import Program, Instr

def lower_program_to_ir(p: Program) -> QModule:
    """
    Lower the parsed Program into a single-function IR module.
    This keeps all ops in a linear entry block; passes are responsible
    for control-flow, routing, and decomposition.
    """
    m = QModule(meta={"seed": p.seed, "reg": p.reg_name, "n_qubits": p.n_qubits})
    main = QFunc("main", params=[QValue(p.reg_name or "r", "qreg")], ret="void")
    m.add_func(main)
    b = main.entry()
    m.meta["fn_defs"] = dict(p.fn_defs)

    # NOTE: parser.Instr currently doesn't carry source loc; loc=None for now.
    for ins in p.instructions:
        op, args = ins.op, ins.args
        if op in (
            "H", "X", "Z", "RZ_EXPR", "CNOT_EXPR", "HADAMARD_LAYER",
            "DIFFUSION", "MARKSTATE", "GROVER_ITERATE",
            "QFT", "IQFT", "EXPECT", "VAR",
            "LET", "CALL", "CALLR", "RETURN",
            "IMPORT", "TRACE", "DUMPSTATE", "PROBS",
            "MEASURE_ONE_EXPR", "MEASURE_ALL",
            "IF_CHAIN", "FOR_IN_REG", "FN_DEF"
        ):
            b.append(QOp(f"q.{op.lower()}", args=args, attrs={}, loc=None))
        else:
            b.append(QOp("q.unknown", args=(op, args), loc=None))

    # Optional: run a quick verify and stash warnings for debugging
    errs = verify_ir(m)
    if errs:
        m.meta.setdefault("verify", {})["errors"] = errs
    return m