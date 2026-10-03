"""Keycloak's shapes, kept as Keycloak writes them.

``firstName`` looks wrong in a Python file, and that is the point: it marks where
foreign data stops. Translation into this service's vocabulary happens in exactly
one function (``src.users.policy.apply_idp_snapshot``), not at every use.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, EmailStr


class KeycloakUserDTO(BaseModel):
    """Subset of Keycloak's ``UserRepresentation`` (Admin REST API)."""

    # Keycloak returns many more fields; accept and ignore them.
    model_config = ConfigDict(extra="ignore")

    id: str
    username: str
    email: EmailStr | None = None
    firstName: str | None = None
    lastName: str | None = None
    enabled: bool = True
    createdTimestamp: int | None = None
