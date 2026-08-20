.PHONY: help dev up down logs bootstrap migrate test lint format typecheck lock check

help:
	@echo "Targets:"
	@echo "  dev        - start the full stack and follow api logs"
	@echo "  up         - build and start the full stack (detached)"
	@echo "  down       - stop the stack"
	@echo "  logs       - follow api logs"
	@echo "  bootstrap  - create .env if missing, start postgres + redis"
	@echo "  migrate    - run alembic migrations inside the api container"
	@echo "  test       - run pytest"
	@echo "  lint       - ruff check + format check"
	@echo "  format     - apply ruff formatting"
	@echo "  typecheck  - mypy on src/"
	@echo "  lock       - regenerate uv.lock"
	@echo "  check      - lint + typecheck + test"

dev: up logs

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f sports-api

bootstrap:
	@test -f .env || cp .env.example .env
	docker compose up -d sports-postgres sports-redis

migrate:
	docker compose run --rm sports-api alembic upgrade head

test:
	uv run pytest -q

lint:
	uv run ruff check .
	uv run ruff format --check .

format:
	uv run ruff format .

typecheck:
	uv run mypy src

lock:
	uv lock

check: lint typecheck test
