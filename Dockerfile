# syntax=docker/dockerfile:1

FROM python:3.12-slim AS base

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

WORKDIR /app

COPY pyproject.toml uv.lock README.md alembic.ini ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src ./src

FROM base AS production

RUN uv sync --frozen --no-dev
RUN useradd --create-home --uid 10001 appuser
USER appuser

EXPOSE 8000

CMD ["uvicorn", "sports_intelligence.api.app:app", "--host", "0.0.0.0", "--port", "8000"]

FROM base AS development

RUN uv sync --frozen --dev --editable

EXPOSE 8000

CMD ["uvicorn", "sports_intelligence.api.app:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
