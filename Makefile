PYTHON ?= python3.13
VENV   ?= .venv
BIN     = $(VENV)/bin
COMPOSE = docker compose

.PHONY: setup lint test up down replay pipeline demo demo-bad demo-down preflight review-bundle dagster-ui site

setup:
	@command -v $(PYTHON) >/dev/null 2>&1 || { echo "Python 3.13 not found. Install it, or run make setup PYTHON=python3 (3.12 is untested)."; exit 1; }
	$(PYTHON) -m venv $(VENV)
	$(BIN)/pip install -r requirements/direct.txt -c requirements/constraints.txt

lint:
	$(BIN)/ruff check .
	$(BIN)/ruff format --check .

test:
	$(BIN)/pytest

up:
	mkdir -p data/warehouse
	$(COMPOSE) up -d --build
	bash scripts/wait_for_health.sh

down:
	$(COMPOSE) down

# Replay synthetic data into a running stack. Override DAYS, SITES or SPEED if needed.
DAYS  ?= 1
SITES ?= 2
SPEED ?= 0
replay:
	$(BIN)/python -m ingest.replay --synthetic --days $(DAYS) --sites $(SITES) --speed $(SPEED)

pipeline:
	$(BIN)/python -m orchestration.run

demo:
	bash scripts/demo.sh

demo-bad:
	bash scripts/demo_bad.sh

demo-down:
	$(COMPOSE) --profile obs down -v

preflight:
	bash scripts/preflight.sh --tree

review-bundle:
	bash scripts/make_review_bundle.sh

# Opens the Dagster UI on port 3001 (Grafana uses 3000). Uses a local Dagster home folder.
dagster-ui:
	mkdir -p dagster_home
	DAGSTER_HOME=$(CURDIR)/dagster_home $(BIN)/dagster dev -m orchestration.definitions -p 3001

# Build the static demo page data from the warehouse: site/data/summary.json.
site:
	$(BIN)/python site/export.py --db $${DUCKDB_PATH:-data/warehouse/mcb.duckdb}
