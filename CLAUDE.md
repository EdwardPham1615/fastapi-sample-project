# CLAUDE.md

Guidance for Claude Code in this repository.

## What this is

A reference FastAPI service and the **first consumer** of py-common (`../py-common`,
pinned to tag `v0.3.0`). It is copied to start new services, so a shortcut here gets
copied too. Rules live in `docs/architecture.md`; read it before adding a domain, a
router or a migration.

## Commands

```bash
make check                   # ruff + format check + mypy --strict + pytest — before pushing
make test                    # unit suite, SQLite, no Docker
make infra-up                # Postgres on :5433
make test-integration-local  # integration suite against it
make migrate | seed | run
make revision m="..."        # numbered migration
make openapi                 # regenerate docs/openapi.json — commit the diff
make proto                   # regenerate gRPC stubs
```

## Before trusting py-common from memory

The library moves under this repo (v0.1.0 → v0.2.1 → v0.3.0 while it was being
built). Before relying on a py-common API, read it:
`.venv/lib/python3.14/site-packages/py_common/`, or `../py-common` at the pinned tag,
and its `CHANGELOG.md` when bumping. Still true at v0.3.0:

- `Repository` is an ABC, not a Protocol — interfaces here are ABCs.
- `internal_router` is fail-open without `HTTP__INTERNAL_API_KEY`.
- `Auth.optional_user` raises on an invalid token rather than returning None.
- `get_or_raise` knows only "row missing"; domain rules on top (DELETED) live in
  `IUserRepository.get_existing`, and must raise the *same* 404.
- A route using `OptionalClaims` counts as public for `assert_routes_protected`:
  list it in `PUBLIC_PATHS`.

Gaps this repo used to fill itself, now in py-common 0.3.0 — do not re-add them:
`request.state.user` binding, a token-provider test subclass (pass `transport=`),
the `sqlalchemy<2.1` pin, and avoiding the uvicorn CLI for log format.

## Traps with a test on them

- Start the server with `python -m src` (`make run`): it reads `SERVER__*`; the
  bare uvicorn CLI binds 127.0.0.1.
- Logs are ECS JSON in every environment (`LOG_JSON`, default true). Do not tie the
  format to `is_dev` again — that is how dev logs stopped being ECS.
- Include a `/{id}` sub-router **after** the static routes of its parent, or
  `/users/me` becomes a 422.
- SQLAlchemy column defaults run at INSERT: `User().id` is None until flush. Set it
  when handing ORM objects to an in-memory repository.
- A column default callable with one positional parameter receives the execution
  context — which is why `models._now_ms()` takes none.
- `ARRAY(...).with_variant(JSON, "sqlite")` exists only for the unit suite; the real
  type is tested in `tests/integration`.
- `alembic.ini` must keep `revision_environment = true`, or migration numbering breaks.
- Do not enter `TestClient(app)` as a context manager in unit tests: it runs the
  lifespan, which connects to Postgres.
- Settings are read at import by `src/auth.py`; tests set the environment at the top
  of `tests/conftest.py`, before any `src` import.

## When you add something

- A route: put it in the router file of its tier. Public paths go in
  `tests/test_routes_protected.py::PUBLIC_PATHS`.
- An endpoint change: `make openapi` and commit `docs/openapi.json`.
- A repository method: add it to the interface **and** to `tests/fakes.py`.
- A migration: `make revision`, then review the generated file — autogenerate leaked
  the SQLite JSON variant into the first one.
- Anything py-common should own: record it in the Obsidian note
  `Projects/py-common` → "Candidate additions" instead of building it here for good.
