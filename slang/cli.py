
import argparse, sys, json
from pathlib import Path
from .parser import Program
from .transpiler import Transpiler
from .interpreter import Interpreter

def main(argv=None):
    ap=argparse.ArgumentParser(prog="slang")
    sub=ap.add_subparsers(dest="cmd", required=True)

    ap_tr=sub.add_parser("transpile", help="Transpile .slang to OpenQASM 3")
    ap_tr.add_argument("src")
    ap_tr.add_argument("-o","--out", default="-")
    ap_tr.add_argument("--ancilla-budget", type=int, default=9999)
    ap_tr.add_argument("--no-ccx-decompose", action="store_true")
    ap_tr.add_argument("--coupling", help="JSON list of undirected edges, e.g. [[0,1],[1,2]]")

    ap_run=sub.add_parser("run", help="Run a program on the toy interpreter")
    ap_run.add_argument("src")
    ap_run.add_argument("--shots", type=int, default=256)

    args = ap.parse_args(argv)

    if args.cmd=="transpile":
        src=Path(args.src).read_text()
        p=Program(src).parse()
        coupling = json.loads(args.coupling) if args.coupling else None
        t=Transpiler(p, ancilla_budget=args.ancilla_budget, decompose_ccx=(not args.no_ccx_decompose), coupling_map=coupling)
        qasm=t.to_qasm3()
        if args.out=="-": sys.stdout.write(qasm)
        else:
            Path(args.out).parent.mkdir(parents=True, exist_ok=True)
            Path(args.out).write_text(qasm+"\n")
            print(f"[ok] wrote {args.out}")
    elif args.cmd=="run":
        src=Path(args.src).read_text()
        p=Program(src).parse()
        it=Interpreter(p)
        counts = it.run()
        print(counts or {})

if __name__=="__main__":
    main()
