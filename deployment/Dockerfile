# Build from the repository root:
#   docker build -f deployment/Dockerfile -t user-profile-service .
#
# Python 3.14 is py-common's floor. Slim images cannot compile C extensions, which is
# why the service stays on versions that ship binary wheels (see pyproject.toml).

FROM python:3.14-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.12 /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
# git: the py-common dependency is pinned to a git tag.
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*
# README.md too: pyproject declares it, and hatchling refuses to build without it.
COPY pyproject.toml uv.lock README.md LICENSE ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
COPY integrations ./integrations
COPY alembic ./alembic
COPY alembic.ini ./
RUN uv sync --frozen --no-dev

FROM python:3.14-slim
WORKDIR /app
RUN useradd --create-home --uid 10001 app
COPY --from=build --chown=app:app /app /app
ENV PATH="/app/.venv/bin:$PATH" ENVIRONMENT=production
USER app
EXPOSE 8000 50051
# Migrations are NOT run on startup in production (POSTGRES__AUTO_MIGRATE=false):
# run `alembic upgrade head` from a deploy job, so replicas never race each other.
# src/__main__.py reads host and port from SERVER__HOST (default 0.0.0.0) and
# SERVER__PORT (default 8000); the bare `uvicorn` CLI would bind 127.0.0.1.
CMD ["python", "-m", "src"]
