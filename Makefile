# ---- Config knobs ---------------------------------------------------------
PY ?= python3
PIP := $(PY) -m pip
OUT ?= out
COUPLING ?= [[0,1],[1,2],[2,3],[3,4],[4,5]]

# Canonical list of shipped examples
EXAMPLES := \
  examples/bool_if_inline.slang \
  examples/diffusion_anc0.slang \
  examples/expect_demo.slang \
  examples/fn_call_cx.slang \
  examples/fn_prep.slang \
  examples/grover_mark3.slang \
  examples/grover_selfcheck.slang \
  examples/loop_sugar.slang \
  examples/mod_import_demo.slang \
  examples/qft_roundtrip.slang \
  examples/routed_line_cx.slang

# ---- Phony targets --------------------------------------------------------
# add "verify" to your PHONY list (wherever you keep it)
.PHONY: help install install-dev install-qiskit test transpile transpile-ir examples metrics metrics-ci sanity clean ir pipeline verify which-python doctor reinstall clean-pyc

help:
	@echo "Targets:"
	@echo "  make install         - install package only"
	@echo "  make install-dev     - install package + test extras"
	@echo "  make install-qiskit  - install parity tool extra (qiskit)"
	@echo "  make test            - run pytest (-q)"
	@echo "  make transpile       - transpile all examples into $(OUT)/"
	@echo "  make transpile-ir    - transpile all examples with IR pipeline into $(OUT)/"
	@echo "  make examples        - alias for 'transpile'"
	@echo "  make metrics         - analyze QASM files in $(OUT)/ with tools/qasm_to_qiskit_metrics.py"
	@echo "  make sanity          - run tools/sanity.sh"
	@echo "  make clean           - remove build artifacts and $(OUT)/"
	@echo "  make verify         - lower to IR and verify all examples (fails on error)"
	@echo "  make which-python    - print python/pip locations and versions"
	@echo "  make doctor          - env sanity: python/pip/qiskit import checks"
	@echo "  make reinstall       - uninstall + reinstall package (editable)"
	@echo "  make clean-pyc       - remove __pycache__/*.py[co]"

install:
	$(PIP) install --upgrade pip
	$(PIP) install .

install-dev:
	$(PIP) install --upgrade pip
	$(PIP) install ".[test]"

install-qiskit:
	$(PIP) install ".[qiskit]"

# Show which python/pip are being used and versions
which-python:
	@echo "PY         = $(PY)"
	@which $(PY) || true
	@$(PY) -V || true
	@echo "pip (module) = $$($(PY) -c 'import sys,shutil;print(shutil.which(\"pip\")) or print(\"(none)\")' 2>/dev/null || true)"
	@$(PY) -m pip -V || true

# Quick environment doctor
doctor: which-python
	@echo "---- python imports ----"
	@printf '%s\n' \
	'import sys' \
	'print("sys.version:", sys.version.replace("\\n"," "))' \
	'try:' \
	'    import qiskit' \
	'    print("qiskit:", getattr(qiskit, "__version__", "(ok)"))' \
	'    try:' \
	'        from qiskit.qasm3 import loads as _loads' \
	'        print("qasm3.loads: OK")' \
	'    except Exception as e:' \
	'        print("qasm3.loads: FAIL", e)' \
	'except Exception as e:' \
	'    print("qiskit: FAIL", e)' \
	'try:' \
	'    import slang' \
	'    print("slang import: OK")' \
	'except Exception as e:' \
	'    print("slang import: FAIL", e)' \
	| $(PY) -
	@echo "---- end doctor ----"

# Reinstall package cleanly (editable mode); useful after Python changes
reinstall: clean-pyc
	-$(PY) -m pip uninstall -y S-Lang slang || true
	$(PY) -m pip install --upgrade pip
	$(PY) -m pip install -e ".[test,qiskit]"

# Remove compiled artifacts
clean-pyc:
	find . -name "__pycache__" -type d -prune -exec rm -rf {} +
	find . -name "*.pyc" -o -name "*.pyo" -o -name "*.pyd" -delete

test:
	$(PY) -m pytest -q

# Transpile all shipped examples
transpile examples:
	mkdir -p $(OUT)
	@for f in $(EXAMPLES); do \
	  base=$$(basename $$f .slang); \
	  if grep -qE '^\s*ALLOCATE\s' "$$f"; then \
	    echo "[transpile] $$f -> $(OUT)/$$base.qasm"; \
	    $(PY) -m slang.cli transpile $$f \
	      --coupling '$(COUPLING)' \
	      -o $(OUT)/$$base.qasm || exit $$?; \
	  else \
	    echo "[skip] $$f (no ALLOCATE; module-only)"; \
	  fi; \
	done
	@ls -1 $(OUT)/*.qasm

# Transpile all examples through the IR pipeline
transpile-ir:
	mkdir -p $(OUT)
	@for f in $(EXAMPLES); do \
	  base=$$(basename $$f .slang); \
	  if grep -qE '^\s*ALLOCATE\s' "$$f"; then \
	    echo "[transpile-ir] $$f -> $(OUT)/$$base.ir.qasm"; \
	    $(PY) -m slang.cli transpile $$f \
	      --use-ir \
	      --coupling '$(COUPLING)' \
	      -o $(OUT)/$$base.ir.qasm || exit $$?; \
	  else \
	    echo "[skip] $$f (no ALLOCATE; module-only)"; \
	  fi; \
	done
	# Example with routing using a line coupling (override COUPLING as needed)
	$(PY) -m slang.cli transpile examples/routed_line_cx.slang \
	  --use-ir \
	  --coupling '$(COUPLING)' \
	  -o $(OUT)/routed_line_cx.ir.qasm
	@ls -1 $(OUT)/*.ir.qasm || true

# Run parity metrics via Qiskit loader on everything in $(OUT)
metrics:
	@set -e; \
	set -- $(wildcard $(OUT)/*.qasm); \
	if [ "$$#" -eq 0 ]; then echo "== no QASM files in $(OUT)/ =="; exit 0; fi; \
	for q in "$$@"; do \
	  echo "[metrics] $$q"; \
	  $(PY) tools/qasm_to_qiskit_metrics.py $$q || exit $$?; \
	done

# CI-friendly metrics run: transpile then analyze (ensures OUT exists)
.PHONY: metrics-ci
metrics-ci: transpile metrics

sanity:
	bash tools/sanity.sh

clean: clean-pyc
	rm -rf $(OUT) *.egg-info build dist .pytest_cache
	rm -rf $(OUT) __pycache__ .pytest_cache *.egg-info build dist
	find . -name "__pycache__" -type d -prune -exec rm -rf {} +

.PHONY: ir pipeline
ir:
	python3 -m slang.cli ir examples/loop_sugar.slang

pipeline:
	python3 -m slang.cli pipeline examples/loop_sugar.slang

# Verify IR for all examples (routing-aware via COUPLING)
verify:
	@set -e; \
	for f in $(EXAMPLES); do \
	  echo "[verify] $$f"; \
	  $(PY) -m slang.cli verify $$f --coupling '$(COUPLING)'; \
	done
	@echo "[verify] OK"
