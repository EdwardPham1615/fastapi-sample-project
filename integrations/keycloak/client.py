"""Keycloak Admin REST API.

A concrete class with no interface in front of it: there is one Keycloak. An
interface earns its place when there are two real implementations in production
(two SMS vendors, S3 and GCS) — a dev fake and a test double do not count:

- tests swap the transport: ``KeycloakAdminClient(settings, transport=MockTransport(...))``.
  The same transport reaches the service-token fetch, so a test answers the token
  endpoint and the Admin API in one handler, exactly as the network would.
- dev swaps the network: ``src/dev/keycloak.py`` serves the Admin API at the real
  path, so this class runs unchanged against it.

Nothing in this package imports from ``src`` — enforced by tests/test_boundaries.py.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from py_common.http.client import create_http_client
from py_common.security import ClientCredentialsTokenProvider
from py_common.utils import AsyncCircuitBreaker

from integrations.keycloak.entity import KeycloakUserDTO

if TYPE_CHECKING:
    import httpx
    from py_common.config import KeycloakSettings


class KeycloakAdminClient:
    def __init__(
        self,
        settings: KeycloakSettings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._settings = settings
        self._tokens = ClientCredentialsTokenProvider(settings, transport=transport)
        self._http = create_http_client(
            base_url=settings.server_url.rstrip("/"),
            timeout=10.0,
            connect_retries=3,
            circuit_breaker=AsyncCircuitBreaker(name="keycloak"),
            transport=transport,
        )

    async def list_users(self, *, first: int = 0, max_results: int = 100) -> list[KeycloakUserDTO]:
        token = await self._tokens.get_token()
        resp = await self._http.get(
            f"/admin/realms/{self._settings.realm}/users",
            params={"first": first, "max": max_results},
            headers={"Authorization": f"Bearer {token}"},
        )
        resp.raise_for_status()
        return [KeycloakUserDTO.model_validate(item) for item in resp.json()]

    async def list_all_users(self, *, page_size: int = 100) -> list[KeycloakUserDTO]:
        users: list[KeycloakUserDTO] = []
        first = 0
        while True:
            page = await self.list_users(first=first, max_results=page_size)
            users.extend(page)
            if len(page) < page_size:
                return users
            first += page_size

    async def aclose(self) -> None:
        await self._http.aclose()
