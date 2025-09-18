# slang/passes.py
from __future__ import annotations
from typing import List, Callable, Optional, Any, Dict, Tuple
from dataclasses import dataclass
from .ir import QModule, QFunc, QBlock, QOp

@dataclass
class PassContext:
    changed: bool = False
    log: List[str] = None
    def __post_init__(self):
        if self.log is None:
            self.log = []

PassFn = Callable[[QModule, PassContext], None]

# ---- Small helpers ----------------------------------------------------------

def _replace_ops(bb: QBlock, start_idx: int, repl: List[QOp]) -> None:
    """Replace op at start_idx with the list repl (in-place)."""
    bb.ops[start_idx:start_idx+1] = repl

def _int(s: Any) -> int:
    return int(s) if not isinstance(s, str) else int(eval(s, {"__builtins__": None}, {}))

def _touch_qubits(op: QOp) -> List[int]:
    """Return involved qubit indices for primitive ops with expr args."""
    name = op.op
    if name in ("q.h", "q.x", "q.z", "q.rz_expr"):
        # args: (reg, qexpr) or (reg, qexpr, theta) for rz_expr
        return [_int(op.args[1])]
    if name == "q.cnot_expr":
        # (reg, ctrl_expr, tgt_expr)
        return [_int(op.args[1]), _int(op.args[2])]
    if name == "q.swap_expr":
        return [_int(op.args[1]), _int(op.args[2])]
    return []

# ---- Decomposition ----------------------------------------------------------

def _decompose_qft_ops(reg: str, n: int, noswap: bool) -> List[QOp]:
    """
    QFT decomposition to {h, cnot, rz} using CRZ via CNOT - RZ - CNOT.
    Qubit index convention: leftmost bit is MSB; we use indices 0..n-1.
    """
    ops: List[QOp] = []
    # i: target from 0..n-1
    for i in range(n):
        # controlled-phase from j=i+1..n-1, control=j target=i with angle pi / 2^(j-i)
        for j in range(i+1, n):
            angle = f"({3.141592653589793}/(2**{j - i}))"
            # CRZ(angle) via CNOT(j,i); RZ(angle) on i; CNOT(j,i)
            ops.append(QOp("q.cnot_expr", args=(reg, str(j), str(i))))
            ops.append(QOp("q.rz_expr",    args=(reg, str(i), angle)))
            ops.append(QOp("q.cnot_expr", args=(reg, str(j), str(i))))
        # H on target
        ops.append(QOp("q.h", args=(reg, str(i))))
    if not noswap:
        # final bit-reversal: swap i <-> (n-1-i)
        for i in range(n//2):
            ops.append(QOp("q.swap_expr", args=(reg, str(i), str(n-1-i))))
    return ops

def _decompose_iqft_ops(reg: str, n: int, reverse: bool) -> List[QOp]:
    """
    IQFT is the dagger of QFT. reverse==False means skip the initial undo-swaps.
    """
    ops: List[QOp] = []
    # optional reverse swaps first (undo bit reversal)
    if reverse:
        for i in range(n//2):
            ops.append(QOp("q.swap_expr", args=(reg, str(i), str(n-1-i))))
    # then reverse order of QFT with negative angles
    for i in reversed(range(n)):
        # H dagger == H
        ops.append(QOp("q.h", args=(reg, str(i))))
        for j in reversed(range(i+1, n)):
            angle = f"-({3.141592653589793}/(2**{j - i}))"
            ops.append(QOp("q.cnot_expr", args=(reg, str(j), str(i))))
            ops.append(QOp("q.rz_expr",   args=(reg, str(i), angle)))
            ops.append(QOp("q.cnot_expr", args=(reg, str(j), str(i))))
    return ops

def pass_decompose(m: QModule, ctx: PassContext) -> None:
    """
    Decompose high-level ops:
      - q.qft(reg, noswap) → {h, cnot, rz, swap}
      - q.iqft(reg, reverse) → ...
      - (Leave q.diffusion for now; it’s already lowered in your backend. We can add it next.)
    """
    n_qubits = m.meta.get("n_qubits")
    reg = m.meta.get("reg")
    if n_qubits is None or reg is None:
        return
    for fn in m.funcs.values():
        for bb in fn.blocks:
            i = 0
            while i < len(bb.ops):
                op = bb.ops[i]
                if op.op == "q.qft":
                    r, noswap = op.args[0], bool(op.args[1])
                    repl = _decompose_qft_ops(r, n_qubits, noswap)
                    _replace_ops(bb, i, repl); ctx.changed = True
                    ctx.log.append(f"decompose: QFT → {len(repl)} prims")
                    i += len(repl); continue
                if op.op == "q.iqft":
                    r, reverse = op.args[0], bool(op.args[1])
                    repl = _decompose_iqft_ops(r, n_qubits, reverse)
                    _replace_ops(bb, i, repl); ctx.changed = True
                    ctx.log.append(f"decompose: IQFT → {len(repl)} prims")
                    i += len(repl); continue
                i += 1

# ---- Routing (simple SWAP inserter) ----------------------------------------

def _neighbors(coupling: List[Tuple[int,int]], u: int) -> List[int]:
    out = []
    for a,b in coupling:
        if a == u: out.append(b)
        elif b == u: out.append(a)
    return out

def _shortest_path(coupling: List[Tuple[int,int]], s: int, t: int) -> Optional[List[int]]:
    # BFS
    from collections import deque
    q = deque([s]); prev = {s: None}
    while q:
        u = q.popleft()
        if u == t:
            path = []
            while u is not None:
                path.append(u); u = prev[u]
            return list(reversed(path))
        for v in _neighbors(coupling, u):
            if v not in prev:
                prev[v] = u; q.append(v)
    return None

def pass_route(m: QModule, ctx: PassContext) -> None:
    """
    For each q.cnot_expr(control, target), if not adjacent under coupling map,
    insert SWAPs along a shortest path to bring qubits together, apply CNOT, then swap back.
    """
    coupling = m.meta.get("coupling")
    if not coupling:
        return
    for fn in m.funcs.values():
        for bb in fn.blocks:
            i = 0
            while i < len(bb.ops):
                op = bb.ops[i]
                if op.op == "q.cnot_expr":
                    reg, c, t = op.args
                    c_i = _int(c); t_i = _int(t)
                    # adjacent?
                    if (c_i, t_i) in coupling or (t_i, c_i) in coupling:
                        i += 1; continue
                    path = _shortest_path(coupling, c_i, t_i)
                    if not path or len(path) < 2:
                        i += 1; continue
                    # Bring target towards control (swap along path except the last edge)
                    swaps_fwd = []
                    cur = path[0]
                    for nxt in path[1:-1]:
                        swaps_fwd.append(QOp("q.swap_expr", args=(reg, str(cur), str(nxt))))
                        cur = nxt
                    # Now cur is adjacent to t_i; perform CNOT(cur, t_i).
                    cnot = QOp("q.cnot_expr", args=(reg, str(cur), str(path[-1])))
                    swaps_back = list(reversed(swaps_fwd))
                    repl = swaps_fwd + [cnot] + swaps_back
                    _replace_ops(bb, i, repl); ctx.changed = True
                    ctx.log.append(f"route: inserted {len(swaps_fwd)*2} SWAPs for CNOT {c_i}->{t_i}")
                    i += len(repl); continue
                i += 1

# ---- Scheduler (parallel layers per qubit sets) -----------------------------

def pass_schedule(m: QModule, ctx: PassContext) -> None:
    """
    Simple parallel layer scheduler: we compute two depths:
     - overall op depth (counting any op)
     - two-qubit parallel depth (counting only {cnot, swap})
    """
    depth_by_q: Dict[int, int] = {}
    two_depth_by_q: Dict[int, int] = {}
    two_ops = {"q.cnot_expr", "q.swap_expr"}
    for fn in m.funcs.values():
        for bb in fn.blocks:
            for op in bb.ops:
                qs = _touch_qubits(op)
                if not qs:
                    # non-qubit op: barrier for Ts is out of scope here
                    continue
                # overall depth
                layer = max((depth_by_q.get(q, 0) for q in qs), default=0) + 1
                for q in qs: depth_by_q[q] = layer
                # two-qubit depth
                if op.op in two_ops:
                    tlayer = max((two_depth_by_q.get(q, 0) for q in qs), default=0) + 1
                    for q in qs: two_depth_by_q[q] = tlayer
    m.meta["sched.depth"] = max(depth_by_q.values(), default=0)
    m.meta["sched.twoq_depth"] = max(two_depth_by_q.values(), default=0)
    ctx.log.append(f"schedule: depth={m.meta['sched.depth']}, twoq_depth={m.meta['sched.twoq_depth']}")

# ---- Cost (counts) ----------------------------------------------------------

def pass_cost(m: QModule, ctx: PassContext) -> None:
    counts: Dict[str, int] = {}
    for fn in m.funcs.values():
        for bb in fn.blocks:
            for op in bb.ops:
                counts[op.op] = counts.get(op.op, 0) + 1
    m.meta["cost.counts"] = counts
    ctx.log.append(f"cost: {counts}")

# ---- Canonicalize / Const-fold ---------------------------------------------

def pass_const_fold(m: QModule, ctx: PassContext) -> None:
    # trivial scaffold (we still evaluate precisely in interpreter)
    for fn in m.funcs.values():
        for bb in fn.blocks:
            for op in bb.ops:
                if op.op == "q.let":
                    try:
                        name, expr = op.args
                        if str(expr).strip().isdigit():
                            op.attrs["const"] = int(expr)
                            ctx.log.append(f"const-fold LET {name}={op.attrs['const']}")
                            ctx.changed = True
                    except Exception:
                        pass

def pass_canonicalize(m: QModule, ctx: PassContext) -> None:
    # reserved for small normalizations
    return

# ---- Pipeline ---------------------------------------------------------------

DEFAULT_PIPELINE: List[PassFn] = [
    pass_const_fold,
    pass_canonicalize,
    pass_decompose,
    pass_route,
    pass_schedule,
    pass_cost,
]

def run_pipeline(m: QModule, passes: Optional[List[PassFn]] = None) -> PassContext:
    ctx = PassContext()
    for p in (passes or DEFAULT_PIPELINE):
        p(m, ctx)
        ctx.log.append(f"{p.__name__}: changed={ctx.changed}")
        ctx.changed = False
    return ctx