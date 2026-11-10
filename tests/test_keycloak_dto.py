"""KeycloakUserDTO reads Keycloak's camelCase JSON into snake_case fields, and accepts
any address Keycloak accepted — including special-use domains like a dev realm's
``.local``, which email-validator refuses."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx

from integrations.keycloak.entity import KeycloakUserDTO
from tests.fakes import make_user

DEV_EMAIL = "dev@user-profile.local"


def test_camel_case_json_lands_in_snake_case_fields() -> None:
    dto = KeycloakUserDTO.model_validate(
        {
            "id": "kc-1",
            "username": "an",
            "email": "an@example.com",
            "firstName": "An",
            "lastName": "Nguyen",
            "enabled": False,
            "createdTimestamp": 1_700_000_000_000,
            "emailVerified": True,  # one of Keycloak's many other fields: ignored
        }
    )
    assert (dto.first_name, dto.last_name, dto.created_timestamp, dto.enabled) == (
        "An",
        "Nguyen",
        1_700_000_000_000,
        False,
    )


def test_a_special_use_domain_parses() -> None:
    dto = KeycloakUserDTO.model_validate({"id": "kc-1", "username": "dev", "email": DEV_EMAIL})
    assert dto.email == DEV_EMAIL


async def test_a_user_with_such_an_address_can_read_their_profile(
    client: httpx.AsyncClient, save: Callable[..., Any], login_as: Callable[[str], None]
) -> None:
    """The response model must accept what the DTO let in, or the user gets a 500."""
    await save(make_user(oidc_provider_id="kc-dev", email=DEV_EMAIL))
    login_as("kc-dev")

    resp = await client.get("/v1/users/me")

    assert resp.status_code == 200
    assert resp.json()["data"]["email"] == DEV_EMAIL
