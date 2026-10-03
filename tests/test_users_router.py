"""Tier *user* over HTTP, on SQLite."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx

from src.users.constants import UserStatus
from tests.fakes import make_user

PROBLEM = "application/problem+json"


async def test_get_my_profile(
    client: httpx.AsyncClient, save: Any, login_as: Callable[[str], None]
) -> None:
    user = make_user(oidc_provider_id="kc-an")
    await save(user)
    login_as("kc-an")

    resp = await client.get("/v1/users/me")

    assert resp.status_code == 200
    body = resp.json()
    assert body["data"]["id"] == str(user.id)
    assert body["code"] == 0 and body["request_id"]  # envelope filled by one validation pass


async def test_me_before_sync_is_a_problem_404(
    client: httpx.AsyncClient, login_as: Callable[[str], None]
) -> None:
    login_as("kc-nobody")
    resp = await client.get("/v1/users/me")
    assert resp.status_code == 404
    assert resp.headers["content-type"].startswith(PROBLEM)


async def test_me_is_not_swallowed_by_the_user_id_route(
    client: httpx.AsyncClient, save: Any, login_as: Callable[[str], None]
) -> None:
    # Regression for a measured trap: include /{user_id} before /me and this is a 422.
    await save(make_user(oidc_provider_id="kc-an"))
    login_as("kc-an")
    assert (await client.get("/v1/users/me")).status_code == 200


async def test_no_token_is_401_with_a_bearer_challenge(client: httpx.AsyncClient) -> None:
    resp = await client.get("/v1/users/me")
    assert resp.status_code == 401
    assert resp.headers["www-authenticate"] == "Bearer"
    assert resp.headers["content-type"].startswith(PROBLEM)


class TestUpdateMyProfile:
    async def test_changes_only_what_was_sent(
        self, client: httpx.AsyncClient, save: Any, login_as: Callable[[str], None]
    ) -> None:
        await save(make_user(oidc_provider_id="kc-an", lang="vi", updated_at=1))
        login_as("kc-an")

        resp = await client.patch("/v1/users/me", json={"phone": "912345678", "dial_code": "+84"})

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert (data["phone"], data["dial_code"], data["lang"]) == ("912345678", "+84", "vi")
        assert data["updated_at"] > 1

    async def test_identity_provider_fields_are_rejected_not_ignored(
        self, client: httpx.AsyncClient, save: Any, login_as: Callable[[str], None]
    ) -> None:
        await save(make_user(oidc_provider_id="kc-an"))
        login_as("kc-an")
        resp = await client.patch("/v1/users/me", json={"email": "x@example.com"})
        assert resp.status_code == 422
        assert resp.headers["content-type"].startswith(PROBLEM)

    async def test_empty_body_is_rejected(
        self, client: httpx.AsyncClient, save: Any, login_as: Callable[[str], None]
    ) -> None:
        await save(make_user(oidc_provider_id="kc-an"))
        login_as("kc-an")
        assert (await client.patch("/v1/users/me", json={})).status_code == 422

    async def test_birth_date_in_the_future_is_rejected(
        self, client: httpx.AsyncClient, save: Any, login_as: Callable[[str], None]
    ) -> None:
        await save(make_user(oidc_provider_id="kc-an"))
        login_as("kc-an")
        resp = await client.patch("/v1/users/me", json={"birth_date": 99_999_999_999_999})
        assert resp.status_code == 422

    async def test_suspended_users_cannot_edit(
        self, client: httpx.AsyncClient, save: Any, login_as: Callable[[str], None]
    ) -> None:
        await save(make_user(oidc_provider_id="kc-an", status=int(UserStatus.SUSPENDED)))
        login_as("kc-an")
        resp = await client.patch("/v1/users/me", json={"phone": "912345678"})
        assert resp.status_code == 403


async def test_deactivate(
    client: httpx.AsyncClient, save: Any, login_as: Callable[[str], None]
) -> None:
    await save(make_user(oidc_provider_id="kc-an"))
    login_as("kc-an")
    resp = await client.post("/v1/users/me/deactivate")
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == UserStatus.INACTIVE


async def test_list_is_paginated_newest_first(
    client: httpx.AsyncClient, save: Any, login_as: Callable[[str], None]
) -> None:
    users = [make_user(oidc_provider_id=f"kc-{i}", created_at=1_000 + i) for i in range(5)]
    await save(*users)
    login_as("kc-0")

    resp = await client.get("/v1/users", params={"limit": 2, "offset": 0})

    body = resp.json()
    assert [u["oidc_provider_id"] for u in body["data"]] == ["kc-4", "kc-3"]
    assert body["count"] == 2
    assert body["pagination"]["total_items"] == 5
    assert body["pagination"]["has_next"] is True


async def test_list_filters_by_status_and_text(
    client: httpx.AsyncClient, save: Any, login_as: Callable[[str], None]
) -> None:
    await save(
        make_user(oidc_provider_id="kc-a", first_name="Chi", status=int(UserStatus.ACTIVE)),
        make_user(oidc_provider_id="kc-b", first_name="Chi", status=int(UserStatus.INACTIVE)),
        make_user(oidc_provider_id="kc-c", first_name="Dung", status=int(UserStatus.ACTIVE)),
    )
    login_as("kc-a")

    resp = await client.get("/v1/users", params={"status": 1, "q": "chi"})

    assert [u["oidc_provider_id"] for u in resp.json()["data"]] == ["kc-a"]
