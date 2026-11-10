"""Keycloak's shapes, in this codebase's snake_case.

The alias generator reads Keycloak's camelCase JSON (``firstName``); code and tests
use the field names. Translation into this service's own vocabulary (``enabled`` →
``UserStatus``) still happens in exactly one function,
``src.users.policy.apply_idp_snapshot``.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class KeycloakUserDTO(BaseModel):
    """Subset of Keycloak's ``UserRepresentation`` (Admin REST API)."""

    model_config = ConfigDict(
        # Keycloak returns many more fields; accept and ignore them.
        extra="ignore",
        # Read Keycloak's camelCase keys; still allow snake_case in code and tests.
        alias_generator=to_camel,
        populate_by_name=True,
    )

    id: str
    username: str
    # Plain str: Keycloak already validated it, and email-validator refuses special-use
    # domains such as a dev realm's `.local`.
    email: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    enabled: bool = True
    created_timestamp: int | None = None
