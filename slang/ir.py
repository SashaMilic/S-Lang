# slang/ir.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Any

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
    def __str__(self) -> str:
        res = ""
        if self.results:
            res = ", ".join(v.name for v in self.results) + " = "
        a = ", ".join(repr(x) for x in self.args)
        return f"{res}{self.op}({a})"

@dataclass
class QBlock:
    name: str
    ops: List[QOp] = field(default_factory=list)
    def append(self, op: QOp) -> QOp:
        self.ops.append(op); return op

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

@dataclass
class QModule:
    funcs: Dict[str, QFunc] = field(default_factory=dict)
    meta: Dict[str, Any] = field(default_factory=dict)
    def add_func(self, fn: QFunc) -> QFunc:
        self.funcs[fn.name] = fn; return fn
    def dump(self) -> str:
        out = []
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

# ---- Lowering from Program --------------------------------------------------

from .parser import Program, Instr

def lower_program_to_ir(p: Program) -> QModule:
    m = QModule(meta={"seed": p.seed, "reg": p.reg_name, "n_qubits": p.n_qubits})
    main = QFunc("main", params=[QValue(p.reg_name or "r", "qreg")], ret="void")
    m.add_func(main)
    b = main.entry()
    m.meta["fn_defs"] = dict(p.fn_defs)

    for ins in p.instructions:
        op, args = ins.op, ins.args
        # Wrap into IR with stable names
        if op in (
            "H", "X", "Z", "RZ_EXPR", "CNOT_EXPR", "HADAMARD_LAYER",
            "DIFFUSION", "MARKSTATE", "GROVER_ITERATE",
            "QFT", "IQFT", "EXPECT", "VAR",
            "LET", "CALL", "CALLR", "RETURN",
            "IMPORT", "TRACE", "DUMPSTATE", "PROBS",
            "MEASURE_ONE_EXPR", "MEASURE_ALL",
            "IF_CHAIN", "FOR_IN_REG", "FN_DEF"
        ):
            b.append(QOp(f"q.{op.lower()}", args=args, attrs={}))
        else:
            b.append(QOp("q.unknown", args=(op, args)))
    return m