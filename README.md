# user-profile-service

[![CI](https://github.com/EdwardPham1615/fastapi-sample-project/actions/workflows/ci.yml/badge.svg)](https://github.com/EdwardPham1615/fastapi-sample-project/actions/workflows/ci.yml)

Reference FastAPI service built on [py-common](https://github.com/EdwardPham1615/py-common)
`v0.3.0`, and its first consumer. One sample module, **user-profile**, for a mobile app:
users are created in Keycloak and synced into a local `users` table; this service owns
their profile fields.

The layout and its rules are in [docs/architecture.md](docs/architecture.md).

## Requirements

- Python **3.14** (py-common's floor) and [uv](https://docs.astral.sh/uv/)
- Docker, for Postgres

## Quick start

```bash
make install            # uv sync
cp .env.example .env    # dev values; see the comments in the file
make infra-up           # Postgres on localhost:5433
make migrate            # alembic upgrade head
make seed               # load mock Keycloak users
make run                # python -m src --reload → http://localhost:8000/docs
```

There is no Keycloak to install. With `DEV_FAKE_KEYCLOAK=true` the app serves a
stand-in at the paths the real Keycloak uses, and `KEYCLOAK__SERVER_URL` points at the
app itself. The real token validator, service-token provider and Admin API client all
run against it unchanged. To use a real Keycloak, change `KEYCLOAK__SERVER_URL` and set
`DEV_FAKE_KEYCLOAK=false` — no code changes.

```bash
TOKEN=$(make -s token sub=5f0c7a4e-1b2d-4c3e-9f10-000000000001)
curl -s localhost:8000/v1/users/me -H "Authorization: Bearer $TOKEN"
curl -s -X PATCH localhost:8000/v1/users/me -H "Authorization: Bearer $TOKEN" \
  -H 'content-type: application/json' -d '{"phone":"912345678","dial_code":"+84"}'
curl -s -X POST localhost:8000/internal/users/sync -H 'X-API-Key: dev-key'
```

## API

| Method | Path | Tier |
|---|---|---|
| `GET` | `/v1/users` | user — `limit`, `offset`, `status`, `q` |
| `GET` | `/v1/users/me` | user |
| `PATCH` | `/v1/users/me` | user — only fields the user owns |
| `POST` | `/v1/users/me/deactivate` | user |
| `GET` | `/v1/users/{user_id}` | user |
| `GET` | `/v1/users/{user_id}/card` | public |
| `WS` | `/v1/users/ws` | user (boilerplate) |
| `POST` | `/internal/users/sync` | internal — `X-API-Key` |
| gRPC | `users.v1.UserService/GetProfile` | boilerplate, `GRPC_ENABLED=true` |

Users are never created or deleted through this API: Keycloak owns that.

### Postman

`docs/openapi.json` is the API as production serves it, generated from code:

```bash
make openapi
```

Import it into Postman (OpenAPI 3.1 is supported), or point Spec Hub at the file in
Git so the collection stays in sync. Tags become folders; user routes come with
Bearer auth and internal routes with an `X-API-Key` header. The file is committed and
`tests/test_openapi_snapshot.py` fails if it falls behind the code — so every change
to the HTTP contract shows up in review as a diff.

For local exploration including `/dev/token`, import the running server's
`http://localhost:8000/openapi.json` instead.

## Logs

ECS JSON (py-common's format), one object per line, in **every** environment — what
you read locally is what the log pipeline receives. Set `LOG_JSON=false` for coloured
console output while developing.

The logger's name is under `log.logger` (ECS), not a bare `logger` — changed in
py-common 0.3.0; saved searches and alerts on the old field need the new name.
`tests/test_logging.py` pins the format.

Start the server with `make run` / `python -m src`: it reads host and port from
`SERVER__*`. The `uvicorn` CLI also logs ECS since py-common 0.3.0, but ignores those
settings.

## Tests

```bash
make check                    # ruff + mypy --strict + unit tests; no Docker
make test-integration-local   # the same against real Postgres
```

The unit suite runs on SQLite. It cannot prove the `smallint[]` column type, SQLSTATE
handling or the migrations — the integration suite does.

## Migrations

```bash
make revision m="add avatar url"   # → alembic/versions/000002_add_avatar_url.py
make migrate
```

Revisions are numbered automatically. Two branches that both create the next number
collide when merged; whoever merges second renumbers.

## Not done

- **Accent-insensitive search.** `q` uses `ILIKE`, so "chi" does not find "Chính".
  Needs the `unaccent` extension; `tests/integration` pins the current behaviour.
- **gRPC error mapping.** The servicer aborts with gRPC codes by hand; `AppError` is
  not yet mapped to gRPC status codes.
- **WebSocket** is an authenticated echo, nothing more. Browsers cannot send an
  `Authorization` header on the handshake; a web client would need another scheme.
- **Service-to-service auth.** `/internal` uses an API key; a `client_credentials`
  service token would be stronger.
- **RBAC.** `auth.requires(HasRole(...) | HasScope(...))` is available and unused.
- **Real Keycloak sync.** Pull-on-demand only; a schedule belongs to cron or a queue.
