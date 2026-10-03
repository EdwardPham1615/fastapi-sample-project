"""Authentication with real RS256 tokens, checked by the real validator.

Other tests override ``auth.current_user``; this one does not, so the wiring itself
— protected_router, the validator, the azp allow-list, the access-log binding — is
under test rather than bypassed.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from tests.fakes import make_user


async def test_a_valid_token_reaches_the_handler(
    client: httpx.AsyncClient, save: Any, real_tokens: Callable[..., str]
) -> None:
    await save(make_user(oidc_provider_id="kc-an"))
    token = real_tokens("kc-an")

    resp = await client.get("/v1/users/me", headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 200


@pytest.mark.parametrize(
    ("azp", "why"),
    [(None, "no azp claim at all"), ("some-other-client", "azp not in KEYCLOAK__ALLOWED_AZP")],
)
async def test_tokens_from_other_clients_are_rejected(
    client: httpx.AsyncClient, save: Any, real_tokens: Callable[..., str], azp: str | None, why: str
) -> None:
    # aud alone would accept these: Keycloak fills aud from the clients the subject
    # holds roles on, not from the client that asked (vault: "Keycloak aud vs azp").
    await save(make_user(oidc_provider_id="kc-an"))
    token = real_tokens("kc-an", azp=azp)

    resp = await client.get("/v1/users/me", headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 401, why


async def test_a_tampered_token_is_rejected(
    client: httpx.AsyncClient, save: Any, real_tokens: Callable[..., str]
) -> None:
    await save(make_user(oidc_provider_id="kc-an"))
    token = real_tokens("kc-an")
    head, payload, sig = token.split(".")
    tampered = f"{head}.{payload}.{sig[:-4]}AAAA"

    resp = await client.get("/v1/users/me", headers={"Authorization": f"Bearer {tampered}"})

    assert resp.status_code == 401


async def test_optional_auth_treats_an_invalid_token_as_an_error_not_as_anonymous(
    client: httpx.AsyncClient, save: Any, real_tokens: Callable[..., str]
) -> None:
    """py-common's choice, kept: swallowing a broken token would hide a broken client."""
    user = make_user()
    await save(user)

    anonymous = await client.get(f"/v1/users/{user.id}/card")
    broken = await client.get(
        f"/v1/users/{user.id}/card", headers={"Authorization": "Bearer not.a.token"}
    )

    assert anonymous.status_code == 200
    assert broken.status_code == 401


async def test_the_access_log_carries_the_user(
    client: httpx.AsyncClient,
    save: Any,
    real_tokens: Callable[..., str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """py-common's access log reads request.state.user.sub. Up to 0.2.1 nothing in
    the library wrote it and this service bound it itself; since 0.3.0 Auth does.
    Kept because the log naming the user is this service's requirement, whoever
    satisfies it.
    """
    await save(make_user(oidc_provider_id="kc-an"))
    token = real_tokens("kc-an")

    with caplog.at_level(logging.INFO):
        await client.get("/v1/users/me", headers={"Authorization": f"Bearer {token}"})

    access_lines = [r for r in caplog.records if "kc-an" in r.getMessage()]
    assert access_lines, "no log line carried the user id"
