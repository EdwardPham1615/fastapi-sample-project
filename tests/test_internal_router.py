"""Tier *internal*: X-API-Key, and the startup guard this service adds on top."""

from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI

from integrations.keycloak.client import KeycloakAdminClient
from src.config import Settings
from src.main import create_app
from src.users.deps import keycloak_admin_client
from tests.conftest import INTERNAL_KEY
from tests.fakes import token_endpoint


@pytest.fixture
def fake_keycloak(app: FastAPI, settings: Settings) -> None:
    """The real KeycloakAdminClient, with only its transport swapped."""

    def handler(request: httpx.Request) -> httpx.Response:
        users = [{"id": "kc-1", "username": "an", "enabled": True}]
        return token_endpoint(request) or httpx.Response(200, json=users)

    async def _client() -> KeycloakAdminClient:
        return KeycloakAdminClient(settings.keycloak, transport=httpx.MockTransport(handler))

    app.dependency_overrides[keycloak_admin_client] = _client


@pytest.mark.parametrize("headers", [{}, {"X-API-Key": "wrong"}])
async def test_without_the_right_key_it_is_401(
    client: httpx.AsyncClient, headers: dict[str, str]
) -> None:
    resp = await client.post("/internal/users/sync", headers=headers)
    assert resp.status_code == 401
    # An API key in a custom header is not an HTTP auth scheme; py-common does not
    # send a Bearer challenge here, deliberately.
    assert "www-authenticate" not in resp.headers


@pytest.mark.usefixtures("fake_keycloak")
async def test_with_the_key_it_syncs(client: httpx.AsyncClient) -> None:
    resp = await client.post("/internal/users/sync", headers={"X-API-Key": INTERNAL_KEY})
    assert resp.status_code == 200
    assert resp.json()["data"] == {"created": 1, "updated": 0, "unchanged": 0}


def test_the_app_refuses_to_start_outside_dev_without_a_key(settings: Settings) -> None:
    # py-common's internal_router installs no guard at all without a key. This
    # service turns that into a startup failure rather than an open endpoint.
    staging = settings.model_copy(update={"environment": "staging"})
    staging.http = staging.http.model_copy(update={"internal_api_key": None})

    with pytest.raises(RuntimeError, match="HTTP__INTERNAL_API_KEY"):
        create_app(staging)
