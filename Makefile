.PHONY: install dev test test-unit test-integration lint typecheck migrate migration api worker stack-up stack-down admin simulator e2e benchmark

install:
	uv sync --all-extras

dev:
	uv run uvicorn apps.api.main:create_app --factory --reload --host 0.0.0.0 --port 8000

test:
	uv run pytest tests/ --cov=src/pages_to_audio --cov-report=term-missing

test-unit:
	uv run pytest tests/unit/ -m unit

test-integration:
	uv run pytest tests/integration/ -m integration

lint:
	uv run ruff check src/ apps/ tests/ scripts/
	uv run ruff format --check src/ apps/ tests/ scripts/

typecheck:
	uv run mypy src/pages_to_audio

migrate:
	uv run alembic upgrade head

migration:
	@if [ -z "$(name)" ]; then echo "Usage: make migration name='description'"; exit 1; fi
	uv run alembic revision --autogenerate -m "$(name)"

api:
	uv run uvicorn apps.api.main:create_app --factory --host 0.0.0.0 --port 8000

worker:
	uv run python -m src.pages_to_audio.workflows.worker

stack-up:
	docker compose -f infra/docker-compose.dev.yml up -d --build

stack-down:
	docker compose -f infra/docker-compose.dev.yml down

admin:
	@echo "Admin panel disponível a partir da FASE 10"; exit 1

simulator:
	uv run python scripts/simulate_android.py

e2e:
	uv run pytest tests/e2e/ -m e2e

benchmark:
	@echo "Benchmark disponível a partir da FASE 7"; exit 1
