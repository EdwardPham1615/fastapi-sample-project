"""The worker's tasks. Each must be safe to run twice (late acknowledgement)."""

from __future__ import annotations

from src.users.sqlalchemy_repository import UserRepository
from src.users.sync import UserSyncService
from src.worker.app import SYNC_USERS, worker
from src.worker.runtime import Runtime


@worker.task(SYNC_USERS, lock=True)
async def sync_users(runtime: Runtime) -> dict[str, int]:
    """Upsert every Keycloak user, as ``POST /internal/users/sync`` does, on a schedule.

    Safe twice: an upsert, so a second run reports them unchanged. The lock keeps a
    scheduled run and a manual one from overlapping (the loser returns None).
    """
    # Fetched before the transaction opens, so no transaction waits on the network.
    users = await runtime.keycloak.list_all_users()
    async with runtime.uow() as uow:
        assert uow.session is not None
        report = await UserSyncService(UserRepository(uow.session)).apply(users)
    return report.model_dump()
