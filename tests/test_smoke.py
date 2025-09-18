from pathlib import Path
from slang.parser import Program
from slang.transpiler import Transpiler

def test_transpile_smoke():
    src = Path('examples/bool_if_inline.slang').read_text()
    p = Program(src).parse()
    t = Transpiler(p)
    qasm = t.to_qasm3()
    assert "OPENQASM 3.0;" in qasm
    assert "if (" in qasm
    assert "// T-depth" in qasm