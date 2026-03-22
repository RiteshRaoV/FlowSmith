.PHONY: install test test-unit test-integration lint fmt typecheck migrate clean

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
install:
	pip install -e ".[dev]"

# ---------------------------------------------------------------------------
# Testing
# ---------------------------------------------------------------------------

# Unit tests only — no Postgres required, runs in milliseconds
test-unit:
	pytest tests/unit/ -v

# Integration tests — requires Postgres via docker-compose
test-integration:
	pytest tests/integration/ -v -m integration

# Run everything
test:
	pytest tests/ -v --cov=flowforge --cov-report=term-missing

# ---------------------------------------------------------------------------
# Code quality
# ---------------------------------------------------------------------------
lint:
	ruff check flowforge/ tests/

fmt:
	ruff format flowforge/ tests/

typecheck:
	mypy flowforge/

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

# Run SQL migrations against DATABASE_URL
migrate:
	@echo "Running FlowForge migrations..."
	@for f in flowforge/migrations/*.sql; do \
		echo "  -> $$f"; \
		psql "$$DATABASE_URL" -f "$$f"; \
	done
	@echo "Done."

# ---------------------------------------------------------------------------
# Docker (local dev + integration tests)
# ---------------------------------------------------------------------------
db-up:
	docker-compose up -d postgres
	@echo "Waiting for Postgres to be ready..."
	@sleep 2

db-down:
	docker-compose down

# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------
clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache"   -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	@echo "Clean."
