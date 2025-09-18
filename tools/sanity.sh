#!/bin/bash
#init
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.."; pwd)"
cd "$ROOT"

echo "== Directory layout =="
for p in slang tools examples tests README.md pyproject.toml; do
  if [[ -e "$p" ]]; then echo "OK  $p"; else echo "MISS $p"; fi
done
[[ -e .github/workflows/ci.yml ]] && echo "OK  .github/workflows/ci.yml" || echo "MISS .github/workflows/ci.yml"

echo
echo "== Python import smoke =="
python - <<'PY'
import importlib
for m in ("slang", "slang.parser", "slang.interpreter", "slang.transpiler"):
    try:
        importlib.import_module(m)
        print("OK  import", m)
    except Exception as e:
        print("FAIL import", m, "->", e)
        raise
PY

echo
echo "== Transpile examples =="
mkdir -p out
python -m slang.cli transpile examples/bool_if_inline.slang -o out/bool_if_inline.qasm
python -m slang.cli transpile examples/loop_sugar.slang -o out/loop_sugar.qasm
python -m slang.cli transpile examples/diffusion_anc0.slang -o out/diffusion_anc0.qasm
python -m slang.cli transpile examples/routed_line_cx.slang \
  --coupling '[[0,1],[1,2],[2,3],[3,4],[4,5]]' \
  -o out/routed_line_cx.qasm
ls -1 out/*.qasm

echo
echo "== QASM footers contain metrics =="
grep -E "T-depth|two_qubit_depth|two_qubit_equiv" out/*.qasm || true

echo
echo "== Run tests =="

# Prefer module invocation to avoid PATH issues for the pytest CLI
if python3 -c 'import pytest' 2>/dev/null; then
  python3 -m pytest -q
else
  echo "pytest not installed. Install with one of:"
  echo "  python3 -m pip install \".[test]\"    # from repo root (uses pyproject extras)"
  echo "  python3 -m pip install pytest"
  exit 1
fi

echo
echo "All good ✅"
