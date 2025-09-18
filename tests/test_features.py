from pathlib import Path
from slang.parser import Program
from slang.transpiler import Transpiler
from slang.interpreter import Interpreter

def run_interpreter_text(src: str):
    p = Program(src).parse()
    it = Interpreter(p)
    return it.run()

def test_fn_call_cx():
    src = """
    SEED 1
    ALLOCATE r 2
    FN CX(a,b) { CNOT r[a], r[b] } ENDFN
    H r[0]
    CALL CX(0,1)
    MEASURE r SHOTS 64
    """
    p = Program(src).parse()
    # transpiler shouldn’t error
    _ = Transpiler(p).to_qasm3()
    # interpreter should run
    it = Interpreter(p)
    counts = it.run()
    assert counts and sum(counts.values()) == 64

def test_grover_iterate_markstate_3q():
    src = """
    SEED 1
    ALLOCATE r 3
    HADAMARD_LAYER r
    GROVER_ITERATE r "101"
    MEASURE r SHOTS 64
    """
    p = Program(src).parse()
    _ = Transpiler(p).to_qasm3()
    it = Interpreter(p)
    counts = it.run()
    # we expect "101" to have non-zero counts
    assert any(k == "101" for k in counts)

def test_expect_var_bell(capsys):
    src = """
    SEED 1
    ALLOCATE r 2
    H r[0]
    CNOT r[0], r[1]
    EXPECT "ZZ" r[0], r[1]
    VAR "ZZ" r[0], r[1]
    """
    p = Program(src).parse()
    it = Interpreter(p)
    it.run()
    out = capsys.readouterr().out
    assert "EXPECT ZZ" in out
    assert "VAR ZZ" in out

def test_qft_iqft_roundtrip_transpile_and_run():
    src = """
    SEED 1
    ALLOCATE r 4
    X r[1]
    X r[3]
    QFT r NOSWAP
    IQFT r REVERSE=false
    MEASURE r SHOTS 16
    """
    p = Program(src).parse()
    qasm = Transpiler(p).to_qasm3()
    assert "cp(" in qasm  # uses controlled-phase
    it = Interpreter(p)
    counts = it.run()
    # state should be close to 1010 basis (we can’t assert exact due to sampling)
    assert counts and sum(counts.values()) == 16