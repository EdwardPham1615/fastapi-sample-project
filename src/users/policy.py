"""The business rules of the users domain. Plain functions: no I/O, no clock, no session.

Two callers from day one — the user editing their profile (``PATCH /users/me``) and
the reconciliation job (``sync.UserSyncService``) — which is why these live in their
own module rather than inside a route handler.

Must not import fastapi or sqlalchemy directly (tests/test_boundaries.py). It does
handle the ORM ``User`` — the model doubles as the entity — but only as a plain
object: it never builds a query or touches a session.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from src.users.constants import DEFAULT_LANG, Gender, UserStatus
from src.users.models import User

if TYPE_CHECKING:
    from integrations.keycloak.entity import KeycloakUserDTO

# ── Who owns which column ────────────────────────────────────────────────────
# The identity provider is the source of truth for these; every sync overwrites them.
IDP_OWNED = frozenset({"oidc_provider_id", "email", "status"})
# Seeded from the identity provider when the row is created, then owned by the app.
# This middle category is the one that is easy to forget — and the bug if you do: a
# later sync would overwrite a name the user corrected.
IDP_ON_INSERT_ONLY = frozenset({"first_name", "last_name"})
# Owned by the app. A sync never touches these.
APP_OWNED = frozenset(
    {"middle_name", "phone", "dial_code", "gender", "birth_date", "lang", "logged_in_methods"}
)
# What PATCH /users/me may change: app-owned fields plus the names.
# logged_in_methods is app-owned but written by login events, not by the user.
USER_EDITABLE = (APP_OWNED | IDP_ON_INSERT_ONLY) - {"logged_in_methods"}

_NOT_EDITABLE = frozenset({UserStatus.SUSPENDED, UserStatus.DELETED})


def status_from_idp(enabled: bool) -> UserStatus:
    return UserStatus.ACTIVE if enabled else UserStatus.INACTIVE


def apply_idp_snapshot(user: User | None, dto: KeycloakUserDTO, *, now: int) -> tuple[User, bool]:
    """Create or refresh a user from the identity provider's view of them.

    The one place Keycloak's vocabulary (``firstName``, ``enabled``) is translated
    into this service's. Returns the user (the same object when one was given) and
    whether anything changed; a new user always counts as changed.
    """
    idp_values: dict[str, Any] = {
        "oidc_provider_id": dto.id,
        "email": dto.email,
        "status": int(_idp_status(user, dto)),
    }

    if user is None:
        created_at = dto.createdTimestamp or now
        created = User(
            id=uuid.uuid4(),  # set explicitly: the column default only runs at INSERT
            **idp_values,
            first_name=dto.firstName,
            last_name=dto.lastName,
            gender=int(Gender.UNKNOWN),
            lang=DEFAULT_LANG,
            logged_in_methods=[],
            created_at=created_at,
            updated_at=now,
        )
        return created, True

    changed = False
    for field, value in idp_values.items():
        if getattr(user, field) != value:
            setattr(user, field, value)
            changed = True
    if changed:
        user.updated_at = now
    return user, changed


def _idp_status(user: User | None, dto: KeycloakUserDTO) -> UserStatus:
    # A user the app marked DELETED stays deleted even if the identity provider
    # still lists them as enabled — deletion here is a decision, not a projection.
    if user is not None and user.status == UserStatus.DELETED:
        return UserStatus.DELETED
    return status_from_idp(dto.enabled)


def can_update_profile(user: User) -> bool:
    return UserStatus(user.status) not in _NOT_EDITABLE


def apply_profile_update(user: User, changes: dict[str, Any], *, now: int) -> User:
    """Apply a user's own edits. Refuses any field the user does not own.

    The request schema already forbids unknown fields; this is the second wall, so
    the rule holds for any caller, not only the HTTP one.
    """
    forbidden = set(changes) - USER_EDITABLE
    if forbidden:
        raise ValueError(f"not user-editable: {sorted(forbidden)}")
    for field, value in changes.items():
        setattr(user, field, int(value) if isinstance(value, Gender) else value)
    user.updated_at = now
    return user


def next_status_on_deactivate(user: User) -> UserStatus:
    if user.status == UserStatus.DELETED:
        return UserStatus.DELETED
    return UserStatus.INACTIVE
