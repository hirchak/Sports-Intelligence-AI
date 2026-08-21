.PHONY: help dev up down logs logs-worker logs-beat telegram-up telegram-down telegram-logs bootstrap migrate test test-integration lint format typecheck lock check

help:
	@echo "Targets:"
	@echo "  dev             - start the full stack and follow api logs"
	@echo "  up              - build and start the full stack (detached)"
	@echo "  down            - stop the stack"
	@echo "  logs            - follow api logs"
	@echo "  logs-worker     - follow worker logs"
	@echo "  logs-beat       - follow beat logs"
	@echo "  telegram-up     - start the stack with the telegram bot profile"
	@echo "  telegram-down   - stop the telegram bot service"
	@echo "  telegram-logs   - follow telegram bot logs"
	@echo "  bootstrap       - create .env if missing, start postgres + redis"
	@echo "  migrate         - run alembic migrations inside the api container"
	@echo "  test            - run pytest (unit, no external services)"
	@echo "  test-integration- run pytest integration tests (needs local services)"
	@echo "  lint            - ruff check + format check"
	@echo "  format          - apply ruff formatting"
	@echo "  typecheck       - mypy on src/"
	@echo "  lock            - regenerate uv.lock"
	@echo "  check           - lint + typecheck + test"

dev: up logs

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f sports-api

logs-worker:
	docker compose logs -f sports-worker

logs-beat:
	docker compose logs -f sports-beat

telegram-up:
	docker compose --profile telegram up -d --build sports-telegram

telegram-down:
	docker compose --profile telegram stop sports-telegram

telegram-logs:
	docker compose logs -f sports-telegram

bootstrap:
	@test -f .env || cp .env.example .env
	docker compose up -d sports-postgres sports-redis

migrate:
	docker compose run --rm sports-api alembic upgrade head

seed:
	docker compose run --rm sports-api python scripts/seed_leagues.py

test:
	uv run pytest -q -m "not integration"

test-integration:
	@docker compose exec -T sports-postgres createdb -U sports -O sports sports_intel_test 2>/dev/null || true
	TEST_DATABASE_URL="postgresql+asyncpg://sports:sports_dev_password@localhost:5433/sports_intel_test" \
	TEST_REDIS_URL="redis://localhost:6380/15" \
	uv run pytest -q -m integration

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
