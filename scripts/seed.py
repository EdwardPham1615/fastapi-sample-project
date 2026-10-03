"""Load the mock Keycloak users into the local database.

    make seed

Goes through the same ``UserSyncService.apply`` the internal sync endpoint uses —
just with users read from a file instead of the Admin API. No running app needed.
Idempotent: run it twice and the second run reports everything unchanged.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from py_common.persistence import SqlAlchemyUnitOfWork, create_engine_and_sessionmaker

from integrations.keycloak.entity import KeycloakUserDTO
from src.config import get_settings
from src.users.sqlalchemy_repository import UserRepository
from src.users.sync import UserSyncService


def load_users(path: str) -> list[KeycloakUserDTO]:
    return [KeycloakUserDTO.model_validate(item) for item in json.loads(Path(path).read_text())]


async def seed(users: list[KeycloakUserDTO]) -> None:
    settings = get_settings()
    engine, session_factory = create_engine_and_sessionmaker(settings.postgres, instrument=False)
    try:
        async with SqlAlchemyUnitOfWork(session_factory) as uow:
            assert uow.session is not None
            report = await UserSyncService(UserRepository(uow.session)).apply(users)
    finally:
        await engine.dispose()

    print(f"seeded from {settings.dev_keycloak_users_path}: {report.model_dump()}")
    print("oidc_provider_id values, for `make token sub=...`:")
    for user in users:
        print(f"  {user.id}  {user.username}{'' if user.enabled else '  (disabled)'}")


if __name__ == "__main__":
    asyncio.run(seed(load_users(get_settings().dev_keycloak_users_path)))
