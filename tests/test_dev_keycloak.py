"""The dev stand-in for Keycloak — the whole local loop depends on it."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import jwt
import pytest

from src.config import Settings
from src.main import create_app


@pytest.fixture
async def dev_client(settings: Settings, tmp_path: Path) -> AsyncIterator[httpx.AsyncClient]:
    users_file = tmp_path / "users.json"
    users_file.write_text(json.dumps([{"id": "kc-1", "username": "an", "enabled": True}]))
    dev = settings.model_copy(
        update={
            "dev_fake_keycloak": True,
            "dev_keycloak_key_path": str(tmp_path / "key.json"),
            "dev_keycloak_users_path": str(users_file),
        }
    )
    transport = httpx.ASGITransport(app=create_app(dev))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


def _realm(settings: Settings) -> str:
    return f"/realms/{settings.keycloak.realm}/protocol/openid-connect"


async def test_serves_a_jwks_the_minted_tokens_verify_against(
    dev_client: httpx.AsyncClient, settings: Settings
) -> None:
    jwks = (await dev_client.get(f"{_realm(settings)}/certs")).json()
    token = (await dev_client.post("/dev/token", json={"sub": "kc-1"})).json()["access_token"]

    key = jwt.PyJWK(jwks["keys"][0])
    claims = jwt.decode(token, key.key, algorithms=["RS256"], audience=settings.keycloak.client_id)
    assert claims["sub"] == "kc-1"
    assert claims["iss"] == settings.keycloak.issuer
    assert claims["azp"] == "mobile-app"  # stamped so KEYCLOAK__ALLOWED_AZP passes for real


async def test_client_credentials_then_admin_api(
    dev_client: httpx.AsyncClient, settings: Settings
) -> None:
    kc = settings.keycloak
    form = {"grant_type": "client_credentials", "client_id": kc.client_id}

    wrong = await dev_client.post(f"{_realm(settings)}/token", data={**form, "client_secret": "x"})
    assert wrong.status_code == 401

    ok = await dev_client.post(
        f"{_realm(settings)}/token", data={**form, "client_secret": kc.client_secret}
    )
    service_token = ok.json()["access_token"]
    assert ok.json()["expires_in"] > 0  # ClientCredentialsTokenProvider reads this

    users_path = f"/admin/realms/{kc.realm}/users"
    denied = await dev_client.get(users_path, headers={"Authorization": "Bearer nope"})
    listed = await dev_client.get(users_path, headers={"Authorization": f"Bearer {service_token}"})
    assert denied.status_code == 401
    assert [u["id"] for u in listed.json()] == ["kc-1"]


async def test_is_absent_outside_dev(client: httpx.AsyncClient) -> None:
    # The default test app has DEV_FAKE_KEYCLOAK=false.
    assert (await client.post("/dev/token", json={"sub": "x"})).status_code == 404
