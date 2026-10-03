"""Test doubles for this service's own interfaces.

Extend an interface, extend its fake in the same change — otherwise the fake stops
being a faithful substitute and tests lose coverage with nothing failing (the same
rule py-common applies to its own fakes).
"""

from __future__ import annotations

import uuid
from typing import Any

import httpx
import jwt
from cryptography.hazmat.primitives import serialization
from jwt import PyJWK
from jwt.algorithms import RSAAlgorithm
from jwt.exceptions import PyJWKClientError
from py_common.http.pagination import Page, PageMeta
from py_common.testing.fakes import InMemoryRepository
from py_common.testing.tokens import RsaKeyPair

from src.models import epoch_ms
from src.users.constants import DEFAULT_LANG, Gender, UserStatus
from src.users.models import User
from src.users.repository import IUserRepository


class InMemoryUserRepository(InMemoryRepository[User, uuid.UUID], IUserRepository):
    """py-common's in-memory repository plus this domain's two queries.

    Counts ``get`` calls so tests can prove a loader ran exactly once.
    """

    def __init__(self) -> None:
        super().__init__(default_order_by=["-created_at", "-id"])
        self.get_calls = 0

    async def get(self, entity_id: uuid.UUID) -> User | None:
        self.get_calls += 1
        return await super().get(entity_id)

    async def get_by_oidc_id(self, oidc_provider_id: str) -> User | None:
        return next(
            (u for u in self._items.values() if u.oidc_provider_id == oidc_provider_id), None
        )

    async def search(
        self, *, status: UserStatus | None, q: str | None, limit: int, offset: int
    ) -> Page[User]:
        items = list(await self.get_list(limit=10_000))
        if status is not None:
            items = [u for u in items if u.status == int(status)]
        if q:
            needle = q.lower()
            items = [
                u
                for u in items
                if any(needle in (v or "").lower() for v in (u.first_name, u.last_name, u.email))
            ]
        page = items[offset : offset + limit]
        return Page(
            items=page,
            meta=PageMeta(
                offset=offset,
                limit=limit,
                total_items=len(items),
                has_more=offset + limit < len(items),
            ),
        )


def make_user(**overrides: Any) -> User:
    """An ORM User ready for either repository.

    ``id`` is set here on purpose: the column default only runs at INSERT, so a bare
    ``User()`` has ``id=None`` and an in-memory repository would key it under None.
    """
    now = epoch_ms()
    values: dict[str, Any] = {
        "id": uuid.uuid4(),
        "oidc_provider_id": f"kc-{uuid.uuid4().hex[:12]}",
        "first_name": "An",
        "last_name": "Nguyen",
        "middle_name": None,
        "email": f"{uuid.uuid4().hex[:8]}@example.com",
        "phone": None,
        "dial_code": None,
        "gender": int(Gender.UNKNOWN),
        "birth_date": None,
        "status": int(UserStatus.ACTIVE),
        "lang": DEFAULT_LANG,
        "logged_in_methods": [],
        "created_at": now,
        "updated_at": now,
    }
    values.update(overrides)
    return User(**values)


def token_endpoint(request: httpx.Request) -> httpx.Response | None:
    """Answer Keycloak's client-credentials token endpoint, or None for any other path.

    For ``httpx.MockTransport`` handlers that stand in for Keycloak: since py-common
    0.3.0 the service-token fetch goes through the same transport as the Admin API.
    """
    if request.url.path.endswith("/protocol/openid-connect/token"):
        return httpx.Response(200, json={"access_token": "service-token", "expires_in": 300})
    return None


class StaticJWKSClient:
    """Serves one real RSA public key, so token signatures are verified for real.

    Installed through the same private seam py-common's own tests use
    (``validator._jwks_client``), because the validator fetches JWKS over the
    network, which an in-process test cannot answer.
    """

    def __init__(self, keypair: RsaKeyPair) -> None:
        public_key = serialization.load_pem_public_key(keypair.public_pem.encode())
        jwk = RSAAlgorithm.to_jwk(public_key, as_dict=True)  # type: ignore[arg-type]
        self._key = PyJWK({**jwk, "kid": keypair.kid, "alg": "RS256", "use": "sig"})

    def get_signing_key_from_jwt(self, token: str) -> PyJWK:
        if jwt.get_unverified_header(token).get("kid") != self._key.key_id:
            raise PyJWKClientError("unknown kid")
        return self._key
