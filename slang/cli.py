import argparse, sys, json
from pathlib import Path
from .parser import Program
from .transpiler import Transpiler
from .interpreter import Interpreter
from .ir import lower_program_to_ir
from .passes import run_pipeline

def main(argv=None):
    ap = argparse.ArgumentParser(prog="slang")
    sub = ap.add_subparsers(dest="cmd", required=True)

    ap_tr = sub.add_parser("transpile", help="Transpile .slang to OpenQASM 3")
    ap_tr.add_argument("src")
    ap_tr.add_argument("-o", "--out", default="-")
    ap_tr.add_argument("--ancilla-budget", type=int, default=9999)
    ap_tr.add_argument("--no-ccx-decompose", action="store_true")
    ap_tr.add_argument("--coupling", help="JSON list of undirected edges, e.g. [[0,1],[1,2]]")
    ap_tr.add_argument("--use-ir", action="store_true", help="Lower to IR, run passes, then emit")

    ap_run = sub.add_parser("run", help="Run a program on the toy interpreter")
    ap_run.add_argument("src")
    ap_run.add_argument("--shots", type=int, default=256)

    ap_ir = sub.add_parser("ir", help="Lower .slang to IR and dump")
    ap_ir.add_argument("src")

    ap_pipe = sub.add_parser("pipeline", help="Run default pass pipeline and dump IR + log")
    ap_pipe.add_argument("src")

    args = ap.parse_args(argv)

    if args.cmd == "transpile":
        src = Path(args.src).read_text()
        p = Program(src).parse()
        coupling = json.loads(args.coupling) if args.coupling else None
        t = Transpiler(
            p,
            ancilla_budget=args.ancilla_budget,
            decompose_ccx=(not args.no_ccx_decompose),
            coupling_map=coupling,
            use_ir=args.use_ir,
        )
        qasm = t.to_qasm3()
        if args.out == "-":
            sys.stdout.write(qasm)
        else:
            Path(args.out).parent.mkdir(parents=True, exist_ok=True)
            Path(args.out).write_text(qasm + "\n")
            print(f"[ok] wrote {args.out}")

    elif args.cmd == "run":
        src = Path(args.src).read_text()
        p = Program(src).parse()
        it = Interpreter(p)
        counts = it.run()
        print(counts or {})

    elif args.cmd == "ir":
        src = Path(args.src).read_text()
        p = Program(src).parse()
        m = lower_program_to_ir(p)
        print(m.dump())

    elif args.cmd == "pipeline":
        src = Path(args.src).read_text()
        p = Program(src).parse()
        m = lower_program_to_ir(p)
        ctx = run_pipeline(m)
        print(m.dump())
        print("\n-- pipeline log --")
        for line in ctx.log:
            print(line)

if __name__ == "__main__":
    main()