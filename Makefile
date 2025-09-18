# ---- Config knobs ---------------------------------------------------------
PY ?= python3
PIP := $(PY) -m pip
OUT ?= out
COUPLING ?= [[0,1],[1,2],[2,3],[3,4],[4,5]]

# ---- Phony targets --------------------------------------------------------
.PHONY: help install install-dev install-qiskit test transpile examples metrics sanity clean

help:
	@echo "Targets:"
	@echo "  make install         - install package only"
	@echo "  make install-dev     - install package + test extras"
	@echo "  make install-qiskit  - install parity tool extra (qiskit)"
	@echo "  make test            - run pytest (-q)"
	@echo "  make transpile       - transpile all examples into $(OUT)/"
	@echo "  make examples        - alias for 'transpile'"
	@echo "  make metrics         - analyze QASM files in $(OUT)/ with tools/qasm_to_qiskit_metrics.py"
	@echo "  make sanity          - run tools/sanity.sh"
	@echo "  make clean           - remove build artifacts and $(OUT)/"

install:
	$(PIP) install --upgrade pip
	$(PIP) install .

install-dev:
	$(PIP) install --upgrade pip
	$(PIP) install ".[test]"

install-qiskit:
	$(PIP) install ".[qiskit]"

test:
	$(PY) -m pytest -q

# Transpile all shipped examples
transpile examples:
	mkdir -p $(OUT)
	$(PY) -m slang.cli transpile examples/bool_if_inline.slang -o $(OUT)/bool_if_inline.qasm
	$(PY) -m slang.cli transpile examples/loop_sugar.slang -o $(OUT)/loop_sugar.qasm
	$(PY) -m slang.cli transpile examples/diffusion_anc0.slang -o $(OUT)/diffusion_anc0.qasm
	$(PY) -m slang.cli transpile examples/routed_line_cx.slang \
		--coupling '$(COUPLING)' \
		-o $(OUT)/routed_line_cx.qasm
	@ls -1 $(OUT)/*.qasm

# Run parity metrics via Qiskit loader on everything in $(OUT)
metrics:
	@set -e; \
	for f in $(OUT)/*.qasm; do \
		echo "== $$f =="; \
		$(PY) tools/qasm_to_qiskit_metrics.py $$f; \
	done

# CI-friendly metrics run: transpile then analyze (ensures OUT exists)
.PHONY: metrics-ci
metrics-ci: transpile metrics

sanity:
	bash tools/sanity.sh

clean:
	rm -rf $(OUT) __pycache__ .pytest_cache *.egg-info build dist
	find . -name "__pycache__" -type d -prune -exec rm -rf {} +

.PHONY: ir pipeline
ir:
	python3 -m slang.cli ir examples/loop_sugar.slang

pipeline:
	python3 -m slang.cli pipeline examples/loop_sugar.slang
