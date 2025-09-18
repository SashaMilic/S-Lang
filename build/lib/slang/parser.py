import re, math
from dataclasses import dataclass
from typing import List, Tuple, Optional, Dict

PI_ENV = {"__builtins__": None, "pi": math.pi, "tau": math.tau}

def eval_expr(expr: str, env: Dict[str, float]) -> float:
    safe = dict(PI_ENV)
    for k, v in env.items():
        safe[k] = float(v)
    return float(eval(expr, safe, {}))

@dataclass
class Instr:
    op: str
    args: Tuple

class Program:
    def __init__(self, text: str):
        self.text = text
        self.n_qubits: Optional[int] = None
        self.reg_name: Optional[str] = None
        self.instructions: List[Instr] = []
        self.seed: Optional[int] = None
        # function defs collected during parse
        self.fn_defs: Dict[str, Tuple[List[str], str]] = {}

    def _clean_lines(self) -> List[str]:
        raw_lines = self.text.splitlines()
        lines: List[str] = []
        for raw in raw_lines:
            s = raw.strip()
            if not s:
                continue
            if s.startswith("//") or s.startswith("#"):
                continue
            if "#" in s:
                s = s.split("#", 1)[0].rstrip()
            if s:
                lines.append(s)
        # Normalize literal "\n" into real newlines and resplit
        norm_lines: List[str] = []
        for s in lines:
            if "\\n" in s:
                norm_lines.extend(s.replace("\\n", "\n").splitlines())
            else:
                norm_lines.append(s)
        return norm_lines

    def parse(self) -> "Program":
        lines = self._clean_lines()
        i = 0
        while i < len(lines):
            ln = lines[i]

            # ---------------- Core ---------------
            if re.match(r"SEED\s+\d+", ln, re.I):
                self.seed = int(re.match(r"SEED\s+(\d+)", ln, re.I).group(1)); i += 1; continue

            if re.match(r"LET\s+\w+\s*=\s*.+$", ln, re.I):
                name, expr = re.match(r"LET\s+(\w+)\s*=\s*(.+)$", ln, re.I).groups()
                self.instructions.append(Instr("LET", (name, expr))); i += 1; continue

            if re.match(r"ALLOCATE\s+\w+\s+\d+", ln, re.I):
                m = re.match(r"ALLOCATE\s+(\w+)\s+(\d+)", ln, re.I)
                reg, n = m.group(1), int(m.group(2))
                self.reg_name, self.n_qubits = reg, n
                self.instructions.append(Instr("ALLOCATE", (reg, n))); i += 1; continue

            if re.match(r"(H|X|Z)\s+\w+\[\s*.+\s*\]$", ln, re.I):
                g, reg, qexpr = re.match(r"(H|X|Z)\s+(\w+)\[\s*(.+)\s*\]$", ln, re.I).groups()
                self.instructions.append(Instr(g.upper(), (reg, qexpr))); i += 1; continue

            if re.match(r"RZ\s+.+\s+\w+\[\s*.+\s*\]$", ln, re.I):
                th, reg, qexpr = re.match(r"RZ\s+(.+)\s+(\w+)\[\s*(.+)\s*\]$", ln, re.I).groups()
                self.instructions.append(Instr("RZ_EXPR", (reg, qexpr, th))); i += 1; continue

            if re.match(r"CNOT\s+\w+\[\s*.+\s*\]\s*,\s*\w+\[\s*.+\s*\]$", ln, re.I):
                reg1, q1expr, reg2, q2expr = re.match(
                    r"CNOT\s+(\w+)\[\s*(.+)\s*\]\s*,\s*(\w+)\[\s*(.+)\s*\]$", ln, re.I
                ).groups()
                if reg1 != reg2:
                    raise ValueError("CNOT must use the same register on both operands")
                self.instructions.append(Instr("CNOT_EXPR", (reg1, q1expr, q2expr))); i += 1; continue

            if re.match(r"HADAMARD_LAYER\s+\w+$", ln, re.I):
                reg = re.match(r"HADAMARD_LAYER\s+(\w+)$", ln, re.I).group(1)
                self.instructions.append(Instr("HADAMARD_LAYER", (reg,))); i += 1; continue

            if re.match(r"DIFFUSION\s+\w+$", ln, re.I):
                reg = re.match(r"DIFFUSION\s+(\w+)$", ln, re.I).group(1)
                self.instructions.append(Instr("DIFFUSION", (reg,))); i += 1; continue

            # --------------- Grover ops -----------------
            if re.match(r"MARKSTATE\s+\w+\s+\"[01]+\"$", ln, re.I):
                reg, bitstr = re.match(r"MARKSTATE\s+(\w+)\s+\"([01]+)\"$", ln, re.I).groups()
                self.instructions.append(Instr("MARKSTATE", (reg, bitstr))); i += 1; continue

            if re.match(r"GROVER_ITERATE\s+\w+\s+\"[01]+\"$", ln, re.I):
                reg, bitstr = re.match(r"GROVER_ITERATE\s+(\w+)\s+\"([01]+)\"$", ln, re.I).groups()
                self.instructions.append(Instr("GROVER_ITERATE", (reg, bitstr))); i += 1; continue

            # --------------- QFT/IQFT -------------
            if re.match(r"QFT\s+\w+(?:\s+NOSWAP)?$", ln, re.I):
                m = re.match(r"QFT\s+(\w+)(?:\s+(NOSWAP))?$", ln, re.I)
                reg = m.group(1); noswap = bool(m.group(2))
                self.instructions.append(Instr("QFT", (reg, noswap))); i += 1; continue

            if re.match(r"IQFT\s+\w+(?:\s+REVERSE\s*=\s*(?:true|false))?$", ln, re.I):
                m = re.match(r"IQFT\s+(\w+)(?:\s+REVERSE\s*=\s*(true|false))?$", ln, re.I)
                reg = m.group(1); rev = m.group(2)
                reverse = True if (rev is None or rev.lower()=="true") else False
                self.instructions.append(Instr("IQFT", (reg, reverse))); i += 1; continue

            # --------------- EXPECT / VAR ---------------------------
            if re.match(r"EXPECT\s+\"[IXYZ]+\"\s+\w+\[.+\](?:\s*,\s*\w+\[.+\])*$", ln, re.I):
                m = re.match(r"EXPECT\s+\"([IXYZ]+)\"\s+(.+)$", ln, re.I)
                pauli = m.group(1)
                regs = [s.strip() for s in m.group(2).split(",")]
                self.instructions.append(Instr("EXPECT", (pauli, regs))); i += 1; continue

            if re.match(r"VAR\s+\"[IXYZ]+\"\s+\w+\[.+\](?:\s*,\s*\w+\[.+\])*$", ln, re.I):
                m = re.match(r"VAR\s+\"([IXYZ]+)\"\s+(.+)$", ln, re.I)
                pauli = m.group(1)
                regs = [s.strip() for s in m.group(2).split(",")]
                self.instructions.append(Instr("VAR", (pauli, regs))); i += 1; continue

            # --------------- Modules / Debug / IO -------------------
            if re.match(r'IMPORT\s+"[^"]+"\s*$', ln, re.I):
                path = re.match(r'IMPORT\s+"([^"]+)"\s*$', ln, re.I).group(1)
                self.instructions.append(Instr("IMPORT", (f'"{path}"',))); i += 1; continue

            if re.match(r'TRACE\s+"[^"]+"\s*$', ln, re.I):
                msg = re.match(r'TRACE\s+"([^"]+)"\s*$', ln, re.I).group(1)
                self.instructions.append(Instr("TRACE", (f'"{msg}"',))); i += 1; continue

            if re.match(r'DUMPSTATE\s*$', ln, re.I):
                self.instructions.append(Instr("DUMPSTATE", tuple())); i += 1; continue

            if re.match(r'PROBS\s*$', ln, re.I):
                self.instructions.append(Instr("PROBS", tuple())); i += 1; continue

            # --------------- Functions ------------------------------
            # FN definitions: support both single-line "{ ... } ENDFN" and multi-line bodies
            if re.match(r"FN\s+\w+\s*\((.*?)\)\s*\{", ln, re.I):
                # Single- or multi-line FN
                m_hdr = re.match(r"FN\s+(\w+)\s*\((.*?)\)\s*\{", ln, re.I)
                name, arglist = m_hdr.group(1), m_hdr.group(2)
                args = [a.strip() for a in arglist.split(",")] if arglist.strip() else []
                tail = ln[m_hdr.end():].strip()
                if tail:
                    m_inline = re.match(r"^(.*)\}\s*ENDFN\s*$", tail, re.I)
                    if m_inline:
                        body_inside = m_inline.group(1).strip()
                        parts = [p.strip() for p in re.split(r";\s*", body_inside) if p.strip()]
                        body = "\n".join(parts) + ("\n" if parts else "")
                        self.fn_defs[name] = (args, body)
                        self.instructions.append(Instr("FN_DEF", (name, args, body)))
                        i += 1
                        continue
                # multi-line body until ENDFN
                i += 1
                body_lines: List[str] = []
                while i < len(lines) and not re.match(r"ENDFN", lines[i], re.I):
                    if lines[i].strip() == "}":
                        i += 1
                        while i < len(lines) and (not lines[i].strip() or lines[i].strip().startswith(("#","//"))):
                            i += 1
                        continue
                    body_lines.append(lines[i]); i += 1
                if i == len(lines): raise ValueError("ENDFN missing")
                i += 1  # consume ENDFN
                body = "\n".join(body_lines) + ("\n" if body_lines else "")
                self.fn_defs[name] = (args, body)
                self.instructions.append(Instr("FN_DEF", (name, args, body)))
                continue

            if re.match(r"CALL\s+\w+\s*\((.*?)\)$", ln, re.I):
                name, argexprs = re.match(r"CALL\s+(\w+)\s*\((.*?)\)$", ln, re.I).groups()
                vals = [x.strip() for x in argexprs.split(",")] if argexprs.strip() else []
                self.instructions.append(Instr("CALL", (name, vals))); i += 1; continue

            # CALLR target = F(args)
            if re.match(r'CALLR\s+\w+\s*=\s*\w+\s*\((.*?)\)\s*$', ln, re.I):
                tgt, fname, arglist = re.match(
                    r'CALLR\s+(\w+)\s*=\s*(\w+)\s*\((.*?)\)\s*$', ln, re.I
                ).groups()
                vals = [x.strip() for x in arglist.split(",")] if arglist.strip() else []
                self.instructions.append(Instr("CALLR", (fname, vals, tgt))); i += 1; continue

            # RETURN <expr> (appears in FN bodies; we still allow at top level and interpreter will error if misused)
            if re.match(r'RETURN\s+.+$', ln, re.I):
                expr = re.match(r'RETURN\s+(.+)$', ln, re.I).group(1)
                self.instructions.append(Instr("RETURN", (expr,))); i += 1; continue

            # --------------- Measure ------------------------------------
            if re.match(r"MEASURE\s+\w+\[\s*.+\s*\]\s+AS\s+\w+$", ln, re.I):
                reg, qexpr, sym = re.match(
                    r"MEASURE\s+(\w+)\[\s*(.+)\s*\]\s+AS\s+(\w+)$", ln, re.I
                ).groups()
                self.instructions.append(Instr("MEASURE_ONE_EXPR", (reg, qexpr, sym))); i += 1; continue

            if re.match(r"MEASURE\s+\w+(?:\s+SHOTS\s+\d+)?$", ln, re.I):
                m = re.match(r"MEASURE\s+(\w+)\s*(?:SHOTS\s+(\d+))?$", ln, re.I)
                reg = m.group(1); shots = int(m.group(2)) if m.group(2) else 1024
                self.instructions.append(Instr("MEASURE_ALL", (reg, shots))); i += 1; continue

            # --------------- Control Flow -------------------------------
            if re.match(r"IF\s+(.+)\s*\{", ln, re.I):
                cond = re.match(r"IF\s+(.+)\s*\{", ln, re.I).group(1).strip()
                i += 1; blocks: List[Tuple[str, str, List[str]]] = [("IF", cond, [])]
                while i < len(lines):
                    if re.match(r"ELIF\s+(.+)\s*\{", lines[i], re.I):
                        c2 = re.match(r"ELIF\s+(.+)\s*\{", lines[i], re.I).group(1).strip()
                        i += 1; blocks.append(("ELIF", c2, [])); continue
                    if re.match(r"ELSE\s*\{", lines[i], re.I):
                        i += 1; blocks.append(("ELSE", "", [])); continue
                    if re.match(r"ENDIF", lines[i], re.I):
                        i += 1; break
                    if lines[i].strip() == "}":
                        i += 1; continue
                    blocks[-1][2].append(lines[i]); i += 1
                self.instructions.append(Instr("IF_CHAIN", (blocks,))); continue

            if re.match(r"FOR\s+\w+\s+IN\s+\w+\s*\{", ln, re.I):
                var, reg = re.match(r"FOR\s+(\w+)\s+IN\s+(\w+)", ln, re.I).groups()
                body_lines: List[str] = []; i += 1
                while i < len(lines) and not re.match(r"ENDFOR", lines[i], re.I):
                    if lines[i].strip() == "}":
                        i += 1; continue
                    body_lines.append(lines[i]); i += 1
                if i == len(lines): raise ValueError("ENDFOR missing")
                i += 1
                body_text = "\n".join(body_lines) + "\n"
                self.instructions.append(Instr("FOR_IN_REG", (var, reg, body_text))); continue

            # -------------------------------------------------------------
            raise ValueError(f"Unrecognized: {ln}")

        return self