# Architecture

This service is the reference layout for FastAPI services built on
[py-common](https://github.com/EdwardPham1615/py-common). The rules below are the
reusable part; where a rule is enforced by a test, the test is named.

## Layout

```
src/                  the service: one package per domain + the composition root
  main.py             composition root — the one place that knows every implementation
  api.py              routers grouped by API version and trust tier
  auth.py             the single Auth instance
  <domain>/           one per domain (users/ today)
  usecases/           orchestration ACROSS domains (empty until needed)
integrations/         wrappers around third-party systems (keycloak/ today)
alembic/              migrations, numbered 000001, 000002, ...
proto/                gRPC contracts
docs/openapi.json     the HTTP contract, generated — `make openapi`
```

`constants/` and `utils/` at the top level exist but are empty: py-common already
provides the clock, retry, ids and pagination limits. Add a file there only when a
second domain needs the same thing.

## A domain

| File | Holds |
|---|---|
| `constants.py` | constants **and** enums of the domain |
| `models.py` | what becomes a database table |
| `entity.py` | every other struct — HTTP request/response models, and a pure entity if one is ever split out |
| `repository.py` | the interface (`IUserRepository`) — the only repository symbol other domains import |
| `sqlalchemy_repository.py` | the implementation — imported only by composition points |
| `policy.py` | business rules as plain functions, when there are any |
| `deps.py` | injectors (return a value) and loaders (turn a URL id into a checked object) |
| `routers/` | HTTP and WebSocket, one file per trust tier |
| `grpc/` | gRPC servicer, when the domain speaks gRPC |

Create only the files that have content.

**Entity.** The ORM model doubles as the entity. py-common's `Repository[EntityT, IdT]`
is generic over any entity — only `SqlAlchemyRepository` is bound to the ORM — so a
domain that later needs a pure entity subclasses `Repository` directly and adds a
`mapper.py`. Callers do not change: they depend on the interface.

**Interfaces are ABCs**, because py-common's `Repository` is one and a `Protocol`
cannot inherit from an ABC. Implementations inherit the interface explicitly; a
missing method fails at instantiation.

## Where business logic goes

In the route handler, by default. Pull it out when one of these becomes true:

1. a **second caller** appears — another route, transport, script or job;
2. it has a **branch worth testing** without HTTP;
3. the handler passes **~30 lines** or needs more than two collaborators.

Applied to `users/`, this produced exactly one service class (`UserSyncService`, with
several callers) and one module of rules (`policy.py`, used by both the profile edit
and the sync). Everything else is a few lines in a handler.

**Adding a transport is a second caller.** A gRPC servicer or WebSocket handler must
call the same repository and rules as the HTTP route, never a copy — which is the
moment logic leaves the handler.

## Trust tiers

The router axis is the trust tier, independent of domain and of version.

| Tier | Caller | Router | Versioned | In OpenAPI |
|---|---|---|---|---|
| public | anyone | plain `APIRouter` | yes | yes |
| user | the mobile app | py-common `protected_router(auth, ...)` | yes | yes |
| internal | jobs, other services | py-common `internal_router(settings, ...)`, `X-API-Key` | no | **yes** |

One file per tier. A new route inherits its file's tier, so it cannot be left
unprotected by accident — `tests/test_routes_protected.py` checks the app as
production builds it.

- **The guard is half of a tier; the response model is the other half.** Public
  routes return `UserCard`, never `UserPublic`.
- **Internal is not a weaker user.** Do not mint a user to run a job.
- **py-common's `internal_router` is fail-open** without `HTTP__INTERNAL_API_KEY`.
  This service refuses to start outside dev instead (`src/main.py`).
- **Internal routes stay in OpenAPI.** Hiding them would hide them from
  `assert_routes_protected` too.
- **Middleware is app-wide and cannot be scoped to a domain.** Anything that should
  cover one group of routes is `APIRouter(dependencies=[...])`.

## Loading ids from the URL

Routes with an id in the path receive a **loaded, checked object**, not the id. The
loader is attached to a **router group**, not to each route:

```python
users     = protected_router(auth, prefix="/users", ...)                     # (a)
user_item = APIRouter(prefix="/{user_id}", dependencies=[Depends(valid_user_id)])  # (b)
...
users.include_router(user_item)   # LAST — see below
```

- A route added to (b) is checked even if its author forgets `ValidUser`.
- Handlers that need the object still declare `ValidUser`; FastAPI caches the
  loader's result per request, so it runs once.
- A malformed id is a 422 before the database is touched.
- The loader is the one place that defines "exists" (a DELETED user does not).
- For resources owned by a user, answer **404, not 403**: a 403 confirms the id exists.
- **Include (b) after every static route of (a).** Include it first and `/users/me`
  is matched as `/users/{user_id}` — a 422. Measured on FastAPI 0.141.1; pinned by
  `tests/test_users_router.py::test_me_is_not_swallowed_by_the_user_id_route`.

The "context" handed to the handler is the dependency's return value — typed, and
visible in the handler signature — not `request.state`.

## Across domains

| | |
|---|---|
| ✅ | depend on another domain's repository **interface** |
| ✅ | hold another domain's entity as a read-only value |
| ❌ | build a query against another domain's model, or **join across domain tables** |
| ❌ | import another domain's concrete repository |
| ❌ | write to another domain's tables outside its repository |
| → | too involved, or circular → `src/usecases/` |

Foreign keys across domains are database constraints, **not** `relationship()`s.
py-common's `SqlAlchemyRepository.delete` is a bulk DELETE that runs no ORM
cascades, so cascades must be `ON DELETE CASCADE` anyway.

## Transactions

py-common's `UnitOfWork` spans one engine. So:

> **Nothing opens its own session.** Routes, services, usecases and repositories all
> receive the request's unit of work.

It works because FastAPI caches a dependency per request: `Depends(get_uow)` reached
from two domains is the same object. gRPC has no dependency injection, so a servicer
opens one unit of work per RPC — the rule is the same, only who satisfies it moves.

## Integrations

A client is a concrete class. Add an interface only for **two real production
implementations** (two SMS vendors, S3 and GCS). A dev fake and a test double do not
count:

- tests swap the transport (`httpx.MockTransport`);
- dev swaps the network — `src/dev/keycloak.py` serves the real Keycloak paths.

`integrations/` never imports `src` (`tests/test_boundaries.py`).

## Migrations

Numbered `000001_<slug>.py`, assigned by a hook in `alembic/env.py`.
`revision_environment = true` in `alembic.ini` is **required**: without it a
non-autogenerate revision skips `env.py` and gets a random id.
`tests/test_migrations.py` checks one head and that numbers follow the chain.

## Logging

py-common's ECS JSON, in every environment; `LOG_JSON=false` is a local opt-out, not
an environment default. Since py-common 0.3.0 `setup_logging` adopts uvicorn's loggers,
so the format no longer depends on how the process is started; `python -m src` is
still the entry point because it is where `SERVER__*` settings are read.

## Enforced by tests

| Rule | Test |
|---|---|
| no route is public by accident | `test_routes_protected.py` |
| integrations do not import the service | `test_boundaries.py` |
| only composition points import concrete repositories | `test_boundaries.py` |
| policy stays framework-free | `test_boundaries.py` |
| no domain imports usecases | `test_boundaries.py` |
| loaders are attached to groups | `test_loaders.py` |
| migrations: one head, sequential | `test_migrations.py` |
| `docs/openapi.json` matches the code | `test_openapi_snapshot.py` |
| logs are ECS JSON, logger under `log.logger` | `test_logging.py` |
