"""Reconcile the local ``users`` table with the identity provider.

The only service class in the project, and it exists because of a measurable fact
rather than a rule: it has several callers (the internal route, ``scripts/seed.py``,
the tests) and its loop branches on insert vs update.

It takes **data, not a client**. Where the users come from — the Admin API, a JSON
file, a test list — is the caller's business, which is why no Keycloak interface or
mock client exists anywhere.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from py_common.utils import SYSTEM_CLOCK, Clock

from src.models import epoch_ms
from src.users import policy
from src.users.entity import SyncReport

if TYPE_CHECKING:
    from integrations.keycloak.entity import KeycloakUserDTO
    from src.users.repository import IUserRepository


class UserSyncService:
    def __init__(self, repo: IUserRepository, *, clock: Clock = SYSTEM_CLOCK) -> None:
        self._repo = repo
        self._clock = clock

    async def apply(self, users: Sequence[KeycloakUserDTO]) -> SyncReport:
        """Upsert by ``oidc_provider_id``. Idempotent: a second run changes nothing."""
        report = SyncReport()
        now = epoch_ms(self._clock)
        for dto in users:
            existing = await self._repo.get_by_oidc_id(dto.id)
            user, changed = policy.apply_idp_snapshot(existing, dto, now=now)
            if existing is None:
                await self._repo.create(user)
                report.created += 1
            elif changed:
                await self._repo.update(user)
                report.updated += 1
            else:
                report.unchanged += 1
        return report
