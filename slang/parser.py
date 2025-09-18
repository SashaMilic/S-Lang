
import re, math
from dataclasses import dataclass
from typing import List, Tuple, Optional, Dict

PI_ENV = {"__builtins__": None, "pi": math.pi, "tau": math.tau}

def eval_expr(expr: str, env: Dict[str,float]) -> float:
    safe = dict(PI_ENV)
    for k,v in env.items(): safe[k]=float(v)
    return float(eval(expr, safe, {}))

@dataclass
class Instr:
    op: str
    args: Tuple

class Program:
    def __init__(self, text: str):
        self.text=text; self.n_qubits=None; self.reg_name=None
        self.instructions: List[Instr]=[]; self.seed=None
    def _clean_lines(self):
        raw_lines = self.text.splitlines()
        lines=[]
        for raw in raw_lines:
            s = raw.strip()
            if not s: continue
            if s.startswith('//') or s.startswith('#'): continue
            if '#' in s: s = s.split('#',1)[0].rstrip()
            if s: lines.append(s)
        return lines
    def parse(self):
        lines=self._clean_lines(); i=0
        while i<len(lines):
            ln = lines[i]
            if re.match(r"SEED\s+\d+", ln, re.I):
                self.seed=int(re.match(r"SEED\s+(\d+)", ln, re.I).group(1)); i+=1; continue
            if re.match(r"LET\s+\w+\s*=\s*.+$", ln, re.I):
                name, expr = re.match(r"LET\s+(\w+)\s*=\s*(.+)$", ln, re.I).groups()
                self.instructions.append(Instr("LET",(name,expr))); i+=1; continue
            if re.match(r"ALLOCATE\s+\w+\s+\d+", ln, re.I):
                m=re.match(r"ALLOCATE\s+(\w+)\s+(\d+)", ln, re.I); reg,n=m.group(1),int(m.group(2))
                self.reg_name, self.n_qubits = reg, n; self.instructions.append(Instr("ALLOCATE",(reg,n))); i+=1; continue
            if re.match(r"(H|X|Z)\s+\w+\[\s*.+\s*\]$", ln, re.I):
                g,reg,qexpr = re.match(r"(H|X|Z)\s+(\w+)\[\s*(.+)\s*\]$", ln, re.I).groups()
                self.instructions.append(Instr(g.upper(), (reg,qexpr))); i+=1; continue
            if re.match(r"RZ\s+.+\s+\w+\[\s*.+\s*\]$", ln, re.I):
                th,reg,qexpr = re.match(r"RZ\s+(.+)\s+(\w+)\[\s*(.+)\s*\]$", ln, re.I).groups()
                self.instructions.append(Instr("RZ_EXPR",(reg,qexpr,th))); i+=1; continue
            if re.match(r"CNOT\s+\w+\[\s*.+\s*\]\s*,\s*\w+\[\s*.+\s*\]$", ln, re.I):
                reg1,q1expr,reg2,q2expr = re.match(r"CNOT\s+(\w+)\[\s*(.+)\s*\]\s*,\s*(\w+)\[\s*(.+)\s*\]$", ln, re.I).groups()
                if reg1!=reg2: raise ValueError("same register only")
                self.instructions.append(Instr("CNOT_EXPR",(reg1,q1expr,q2expr))); i+=1; continue
            if re.match(r"HADAMARD_LAYER\s+\w+$", ln, re.I):
                reg = re.match(r"HADAMARD_LAYER\s+(\w+)$", ln, re.I).group(1)
                self.instructions.append(Instr("HADAMARD_LAYER",(reg,))); i+=1; continue
            if re.match(r"DIFFUSION\s+\w+$", ln, re.I):
                reg = re.match(r"DIFFUSION\s+(\w+)$", ln, re.I).group(1)
                self.instructions.append(Instr("DIFFUSION",(reg,))); i+=1; continue
            if re.match(r"MEASURE\s+\w+\[\s*.+\s*\]\s+AS\s+\w+$", ln, re.I):
                reg,qexpr,sym = re.match(r"MEASURE\s+(\w+)\[\s*(.+)\s*\]\s+AS\s+(\w+)$", ln, re.I).groups()
                self.instructions.append(Instr("MEASURE_ONE_EXPR",(reg,qexpr,sym))); i+=1; continue
            if re.match(r"MEASURE\s+\w+(?:\s+SHOTS\s+\d+)?$", ln, re.I):
                m=re.match(r"MEASURE\s+(\w+)\s*(?:SHOTS\s+(\d+))?$", ln, re.I); reg=m.group(1); shots=int(m.group(2)) if m.group(2) else 1024
                self.instructions.append(Instr("MEASURE_ALL",(reg,shots))); i+=1; continue
            if re.match(r"IF\s+(.+)\s*\{", ln, re.I):
                cond = re.match(r"IF\s+(.+)\s*\{", ln, re.I).group(1).strip()
                i+=1; blocks=[("IF",cond,[])]
                while i<len(lines):
                    if re.match(r"ELIF\s+(.+)\s*\{", lines[i], re.I):
                        c2 = re.match(r"ELIF\s+(.+)\s*\{", lines[i], re.I).group(1).strip(); i+=1; blocks.append(("ELIF", c2, [])); continue
                    if re.match(r"ELSE\s*\{", lines[i], re.I):
                        i+=1; blocks.append(("ELSE","",[])); continue
                    if re.match(r"ENDIF", lines[i], re.I): i+=1; break
                    if lines[i].strip()=="}": i+=1; continue
                    blocks[-1][2].append(lines[i]); i+=1
                self.instructions.append(Instr("IF_CHAIN",(blocks,))); continue
            if re.match(r"FOR\s+\w+\s+IN\s+\w+\s*\{", ln, re.I):
                var, reg = re.match(r"FOR\s+(\w+)\s+IN\s+(\w+)", ln, re.I).groups()
                body_lines=[]; i+=1
                while i<len(lines) and not re.match(r"ENDFOR", lines[i], re.I):
                    if lines[i].strip()=="}": i+=1; continue
                    body_lines.append(lines[i]); i+=1
                if i==len(lines): raise ValueError("ENDFOR missing")
                i+=1
                body_text="\\n".join(body_lines)+"\\n"
                self.instructions.append(Instr("FOR_IN_REG",(var, reg, body_text))); continue
            raise ValueError(f"Unrecognized: {ln}")
        return self
