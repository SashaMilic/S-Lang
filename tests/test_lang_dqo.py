from slang.parser import Program
from slang.interpreter import Interpreter
from slang.transpiler import Transpiler

def test_callr_return_and_let():
    src = """
    SEED 1
    ALLOCATE r 1
    FN F(a,b) { RETURN a + b } ENDFN
    CALLR k = F(2,3)
    LET m = k * 2
    H r[0]
    MEASURE r SHOTS 8
    """
    p = Program(src).parse()
    _ = Transpiler(p).to_qasm3()
    it = Interpreter(p)
    it.run()
    assert it.env["k"] == 5
    assert it.env["m"] == 10

def test_import_and_trace(capsys, tmp_path):
    mod = tmp_path/"mod.slang"
    mod.write_text("FN HELLO() { RETURN 7 } ENDFN\n")
    src = f'''
    SEED 1
    ALLOCATE r 1
    IMPORT "{mod}"
    CALLR x = HELLO()
    TRACE "ok"
    '''
    p = Program(src).parse()
    it = Interpreter(p); it.run()
    assert it.env["x"] == 7
    out = capsys.readouterr().out
    assert "[TRACE] ok" in out