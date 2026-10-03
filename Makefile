.PHONY: help install lint format format-check typecheck test test-cov check proto \
	infra-up infra-down test-integration-local migrate revision seed run token openapi

UV ?= uv
COMPOSE := docker compose -f deployment/docker-compose.yaml
CODE := src integrations scripts tests alembic
# The integration suite drops and recreates tables: point it at the *_test database
# only. Same credentials and port as deployment/docker-compose.yaml.
POSTGRES_TEST_DSN ?= postgresql+asyncpg://user_profile:user_profile@localhost:5433/user_profile_test

help: ## Show available targets
	@awk 'BEGIN {FS = ":.*##"; printf "Usage: make <target>\n\n"} \
		/^[a-zA-Z0-9_-]+:.*?##/ { printf "  %-24s %s\n", $$1, $$2 }' $(MAKEFILE_LIST)

install: ## Install dependencies (uv sync) — needs Python 3.14
	$(UV) sync --extra dev

lint: ## Ruff lint
	$(UV) run ruff check $(CODE)

format: ## Ruff format (writes)
	$(UV) run ruff format $(CODE)

format-check: ## Ruff format check
	$(UV) run ruff format --check $(CODE)

typecheck: ## mypy --strict on src and integrations
	$(UV) run mypy

test: ## Unit tests — SQLite, no Docker needed
	$(UV) run pytest

test-cov: ## Unit tests with coverage
	$(UV) run pytest --cov --cov-report=term-missing

check: lint format-check typecheck test-cov ## Everything CI runs, locally

proto: ## Regenerate gRPC stubs from proto/
	$(UV) run python -m grpc_tools.protoc -I proto/users/v1 \
		--python_out=src/users/grpc --grpc_python_out=src/users/grpc --pyi_out=src/users/grpc \
		proto/users/v1/user.proto
	@# protoc writes an absolute `import user_pb2`, which does not resolve inside a package.
	sed -i.bak 's/^import user_pb2 as user__pb2$$/from . import user_pb2 as user__pb2/' \
		src/users/grpc/user_pb2_grpc.py && rm -f src/users/grpc/user_pb2_grpc.py.bak

infra-up: ## Start Postgres (and wait until healthy)
	$(COMPOSE) up -d --wait

infra-down: ## Stop Postgres and DELETE its data
	$(COMPOSE) down -v

test-integration-local: infra-up ## Integration suite against the real Postgres
	POSTGRES_TEST_DSN=$(POSTGRES_TEST_DSN) $(UV) run pytest tests/integration -v --no-cov

migrate: ## alembic upgrade head
	$(UV) run alembic upgrade head

revision: ## New migration, numbered automatically: make revision m="add x"
	@test -n "$(m)" || { echo 'usage: make revision m="describe the change"'; exit 1; }
	$(UV) run alembic revision --autogenerate -m "$(m)"

seed: ## Load scripts/data/keycloak_users.json through UserSyncService
	$(UV) run python -m scripts.seed

run: ## Run the app with reload (host/port from SERVER__* — see src/__main__.py)
	$(UV) run python -m src --reload

token: ## Mint a dev user token: make token sub=<oidc_provider_id>
	@test -n "$(sub)" || { echo 'usage: make token sub=<oidc_provider_id>  (see `make seed`)'; exit 1; }
	@curl -sf -X POST localhost:8000/dev/token -H 'content-type: application/json' \
		-d '{"sub":"$(sub)"}' | $(UV) run python -c "import json,sys; print(json.load(sys.stdin)['access_token'])"

openapi: ## Write docs/openapi.json (the reviewed HTTP contract; Postman imports it)
	$(UV) run python -m scripts.export_openapi
