"""The id loader attached to a router group (/users/{user_id}).

Behaviour measured on FastAPI 0.141.1 while planning, now pinned by tests.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx
from fastapi import FastAPI

from src.users.constants import UserStatus
from src.users.deps import user_repo, valid_user_id
from src.users.routers.v1 import user_item
from src.users.routers.v1_public import public_item
from tests.fakes import InMemoryUserRepository, make_user

MISSING = "00000000-0000-4000-8000-000000000000"


def use_repo(app: FastAPI, repo: InMemoryUserRepository) -> None:
    async def _repo() -> InMemoryUserRepository:
        return repo

    app.dependency_overrides[user_repo] = _repo


def test_the_loader_is_attached_to_the_groups_not_to_single_routes() -> None:
    """The point of the pattern: a route added to these groups later is checked even
    if its author never asks for ValidUser.

    Verified by mutation: removing `dependencies=[Depends(valid_user_id)]` from
    `user_item` makes this fail.
    """
    for group in (user_item, public_item):
        assert any(dep.dependency is valid_user_id for dep in group.dependencies), group.prefix


async def test_a_malformed_id_never_reaches_the_database(
    app: FastAPI, client: httpx.AsyncClient, login_as: Callable[[str], None]
) -> None:
    repo = InMemoryUserRepository()
    use_repo(app, repo)
    login_as("kc-an")

    resp = await client.get("/v1/users/not-a-uuid")

    assert resp.status_code == 422
    assert repo.get_calls == 0


async def test_an_unknown_id_is_a_problem_404(
    app: FastAPI, client: httpx.AsyncClient, login_as: Callable[[str], None]
) -> None:
    use_repo(app, InMemoryUserRepository())
    login_as("kc-an")

    resp = await client.get(f"/v1/users/{MISSING}")

    assert resp.status_code == 404
    assert resp.headers["content-type"].startswith("application/problem+json")


async def test_deleted_users_do_not_exist(
    app: FastAPI, client: httpx.AsyncClient, login_as: Callable[[str], None]
) -> None:
    """The loader is the one place "exists" is defined. Verified by mutation:
    dropping the DELETED branch from valid_user_id makes this a 200."""
    repo = InMemoryUserRepository()
    gone = make_user(status=int(UserStatus.DELETED))
    await repo.create(gone)
    use_repo(app, repo)
    login_as("kc-an")

    assert (await client.get(f"/v1/users/{gone.id}")).status_code == 404
    assert (await client.get(f"/v1/users/{gone.id}/card")).status_code == 404


async def test_a_deleted_user_is_indistinguishable_from_a_missing_one(
    app: FastAPI, client: httpx.AsyncClient, login_as: Callable[[str], None]
) -> None:
    """get_existing raises from two places — py-common's get_or_raise for a missing
    row, the domain's own check for a DELETED one. If their bodies differed, the 404
    would tell a caller the id was once valid."""
    repo = InMemoryUserRepository()
    gone = make_user(status=int(UserStatus.DELETED))
    await repo.create(gone)
    use_repo(app, repo)
    login_as("kc-an")

    def body(resp: httpx.Response) -> dict[str, Any]:
        per_request = {"instance", "request_id"}
        return {k: v for k, v in resp.json().items() if k not in per_request}

    deleted = await client.get(f"/v1/users/{gone.id}")
    missing = await client.get(f"/v1/users/{MISSING}")

    assert deleted.status_code == missing.status_code == 404
    assert body(deleted) == body(missing)
    assert body(missing)["detail"] == "User not found"


async def test_the_loader_runs_once_although_the_group_and_the_handler_both_ask(
    app: FastAPI, client: httpx.AsyncClient, login_as: Callable[[str], None]
) -> None:
    # The group-level dependency's return value is discarded by FastAPI; the handler
    # re-declares ValidUser and gets the cached result — no second lookup.
    repo = InMemoryUserRepository()
    user = make_user()
    await repo.create(user)
    use_repo(app, repo)
    login_as("kc-an")

    resp = await client.get(f"/v1/users/{user.id}")

    assert resp.status_code == 200
    assert resp.json()["data"]["id"] == str(user.id)
    assert repo.get_calls == 1


async def test_public_card_needs_no_token_and_leaks_nothing_private(
    app: FastAPI, client: httpx.AsyncClient, save: Any
) -> None:
    user = make_user(email="private@example.com", phone="912345678")
    await save(user)

    resp = await client.get(f"/v1/users/{user.id}/card")

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert set(data) == {"id", "first_name", "last_name"}
