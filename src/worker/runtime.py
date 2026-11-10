"""What one worker process holds beyond py-common's runtime (an event loop, Redis, the
database engine): the Keycloak client the sync needs.

Built lazily by py-common's ``Worker`` on a process's first task, after the fork:
async connections cannot cross one.
"""

from __future__ import annotations

from py_common.worker import WorkerRuntime

from integrations.keycloak.client import KeycloakAdminClient
from src.config import Settings


class Runtime(WorkerRuntime):
    settings: Settings

    def __init__(self, settings: Settings) -> None:
        super().__init__(settings)
        self.keycloak = KeycloakAdminClient(settings.keycloak)

    async def aclose(self) -> None:
        await self.keycloak.aclose()
        await super().aclose()
