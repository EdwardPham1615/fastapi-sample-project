"""KeycloakAdminClient against a mocked transport — no interface, no mock client class.

One ``MockTransport`` answers both hops, the service-token fetch and the Admin API,
because py-common's token provider takes the same transport (0.3.0).
"""

from __future__ import annotations

import httpx

from integrations.keycloak.client import KeycloakAdminClient
from src.config import Settings
from tests.fakes import token_endpoint


def _user(n: int) -> dict[str, object]:
    return {"id": f"kc-{n}", "username": f"u{n}", "enabled": True, "extraField": "ignored"}


async def test_lists_users_with_the_service_token(settings: Settings) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return token_endpoint(request) or httpx.Response(200, json=[_user(1), _user(2)])

    client = KeycloakAdminClient(settings.keycloak, transport=httpx.MockTransport(handler))
    try:
        users = await client.list_users()
    finally:
        await client.aclose()

    assert [u.id for u in users] == ["kc-1", "kc-2"]
    token_call, admin_call = seen
    # The token fetch went through the injected transport, not the real network.
    assert token_call.url == httpx.URL(settings.keycloak.token_url)
    assert b"grant_type=client_credentials" in token_call.content
    assert admin_call.url.path == f"/admin/realms/{settings.keycloak.realm}/users"
    assert admin_call.headers["authorization"] == "Bearer service-token"


async def test_list_all_users_follows_pages_until_a_short_one(settings: Settings) -> None:
    pages = {0: [_user(1), _user(2)], 2: [_user(3)]}

    def handler(request: httpx.Request) -> httpx.Response:
        return token_endpoint(request) or httpx.Response(
            200, json=pages[int(request.url.params["first"])]
        )

    client = KeycloakAdminClient(settings.keycloak, transport=httpx.MockTransport(handler))
    try:
        users = await client.list_all_users(page_size=2)
    finally:
        await client.aclose()

    assert [u.id for u in users] == ["kc-1", "kc-2", "kc-3"]
