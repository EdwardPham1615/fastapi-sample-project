"""Composition point of the users domain: where implementations meet interfaces.

Two kinds of dependency live here:

- **Injectors** return a value to the handler (``RepoDep``, ``CurrentUser``, ``ValidUser``).
- **Loaders** turn an id in the URL into a checked object before the handler runs.
  Attach them to a router group, not to individual routes (see routers/v1.py).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends
from pydantic import UUID4

from integrations.keycloak.client import KeycloakAdminClient
from src.auth import CurrentClaims
from src.config import get_settings
from src.database import UowDep
from src.exceptions import ProfileNotSynced
from src.users.models import User
from src.users.repository import IUserRepository
from src.users.sqlalchemy_repository import UserRepository
from src.users.sync import UserSyncService

# ── Injectors ────────────────────────────────────────────────────────────────


async def user_repo(uow: UowDep) -> IUserRepository:
    assert uow.session is not None
    return UserRepository(uow.session)


RepoDep = Annotated[IUserRepository, Depends(user_repo)]


async def user_sync_service(repo: RepoDep) -> UserSyncService:
    return UserSyncService(repo)


SyncServiceDep = Annotated[UserSyncService, Depends(user_sync_service)]


async def keycloak_admin_client() -> AsyncIterator[KeycloakAdminClient]:
    client = KeycloakAdminClient(get_settings().keycloak)
    try:
        yield client
    finally:
        await client.aclose()


KeycloakDep = Annotated[KeycloakAdminClient, Depends(keycloak_admin_client)]


# ── Loaders ──────────────────────────────────────────────────────────────────


async def current_user(claims: CurrentClaims, repo: RepoDep) -> User:
    """The same loader pattern as ``valid_user_id``, keyed by the token's subject."""
    user = await repo.get_by_oidc_id(claims.sub)
    if user is None:
        raise ProfileNotSynced()
    return user


CurrentUser = Annotated[User, Depends(current_user)]


async def valid_user_id(user_id: UUID4, repo: RepoDep) -> User:
    """Load the user named in the URL, or 404 before the handler runs.

    What "exists" means (a DELETED user does not) is ``IUserRepository.get_existing``'s
    to decide; every route in the group follows it without having to remember.
    """
    return await repo.get_existing(user_id)


ValidUser = Annotated[User, Depends(valid_user_id)]
