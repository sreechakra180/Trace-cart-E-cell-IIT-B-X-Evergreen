# TraceCart Makefile
# Two install tiers: core (engine, tests, demo-from-cache) and vision (re-run real detector)
# Usage: make demo, make test, make eval-dev, make eval-test, make report

.PHONY: all clean demo test eval-dev eval-test report

all: clean demo

# Install tiers
pip-install-core:
	pip install -r requirements-core.txt

pip-install-vision:
	pip install -r requirements-vision.txt

# Core tier: install then demo from committed cache
demo: pip-install-core
	@python -m tracecart.run --scenario S03 --mode cache --out runs/demo-$(shell git rev-parse --short HEAD 2>/dev/null || echo "local")

# Run end-to-end pipeline from committed cache
run: pip-install-core
	@python -m tracecart.run --scenario S03 --mode cache --out runs/demo-$(shell git rev-parse --short HEAD 2>/dev/null || echo "local")

# Test suite (core tier, no torch needed)
test: pip-install-core
	@python -m pytest tests/ -v

# Evaluation on dev split
eval-dev: pip-install-core
	@python -m tracecart.run --scenario S03 --mode cache --out runs/test-dev --eval

# Evaluation on test split (requires prereg-v1 tag + config hash)
eval-test: pip-install-core
	@python -m tracecart.run --scenario S03 --mode cache --out runs/test-test --eval

# Generate report
report: pip-install-core
	@python -m tracecart.run --scenario S03 --mode cache --out runs/report --eval --baseline

# Vision tier: re-run real detector on clips (pulls torch/weights)
vision: pip-install-vision
	@python -m tracecart.feeds.generate
	@python -m tracecart.run --scenario S01 --mode live --out runs/demo-live

# Interactive workbench & API server
serve: pip-install-core
	@python -m uvicorn app.server:app --host 127.0.0.1 --port 8000

clean:
	rm -rf runs/ .pytest_cache/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true