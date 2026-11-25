# Test targets. Uses the project venv if it exists.
#   make test        offline tests only (free, no API calls) - the default
#   make test-live   real conversations against the OpenAI API (COSTS MONEY)
#   make test-smoke  just the one-question smoke test (costs a little)
#   make test-all    offline + live

PYTHON := $(if $(wildcard venv/bin/python),venv/bin/python,python3)
PYTEST := $(PYTHON) -m pytest

.PHONY: test test-live test-smoke test-all

test:
	$(PYTEST) -m "not live"

test-live:
	@echo "Running LIVE tests: these call the OpenAI API and cost money."
	$(PYTEST) -m live -v

test-smoke:
	$(PYTEST) -m live tests/test_smoke.py -v

test-all:
	$(PYTEST) -m "live or not live"
