"""Shared fixtures. The unit suite needs no Docker: it runs on in-memory SQLite.

Know what that does NOT prove: SQLite stores logged_in_methods as JSON, not
smallint[], and enforces nothing Postgres-specific. tests/integration covers those.
"""

from __future__ import annotations

import os

# Set before anything imports `src`: src.auth builds its token validator from the
# settings at import time. Process environment beats the local .env file.
os.environ.update(
    {
        "ENVIRONMENT": "dev",
        "APP_NAME": "user-profile-service",
        "KEYCLOAK__SERVER_URL": "http://keycloak.test",
        "KEYCLOAK__REALM": "test",
        "KEYCLOAK__CLIENT_ID": "user-profile-service",
        "KEYCLOAK__CLIENT_SECRET": "test-secret",
        "KEYCLOAK__ALLOWED_AZP": '["mobile-app"]',
        "HTTP__INTERNAL_API_KEY": "test-key",
        "OTEL__ENABLED": "false",
        "DEV_FAKE_KEYCLOAK": "false",
        "GRPC_ENABLED": "false",
        "REDIS_ENABLED": "false",
    }
)

from collections.abc import AsyncIterator, Callable, Iterator
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from py_common.persistence import Base
from py_common.security import TokenClaims
from py_common.testing.tokens import (
    RsaKeyPair,
    generate_rsa_keypair,
    issue_test_token,
)
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from src.auth import auth
from src.config import Settings, get_settings
from src.main import create_app
from src.users.models import User
from tests.fakes import StaticJWKSClient

INTERNAL_KEY = "test-key"


@pytest.fixture
def settings() -> Settings:
    return get_settings()


@pytest.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest.fixture
def app(settings: Settings, session_factory: async_sessionmaker[AsyncSession]) -> Iterator[FastAPI]:
    application = create_app(settings)
    # The app built its own Postgres engine lazily and never connects it: the
    # request-scoped unit of work reads this factory instead.
    application.state.session_factory = session_factory
    yield application
    application.dependency_overrides.clear()


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
def save(session_factory: async_sessionmaker[AsyncSession]) -> Callable[..., Any]:
    async def _save(*users: User) -> None:
        async with session_factory() as session:
            session.add_all(users)
            await session.commit()

    return _save


@pytest.fixture
def login_as(app: FastAPI) -> Callable[[str], None]:
    """Replace authentication with fixed claims.

    Overrides ``auth.current_user`` — the exact callable protected_router depends
    on — so both the router guard and every CurrentClaims parameter see it.
    """

    def _login(sub: str) -> None:
        async def _claims() -> TokenClaims:
            return TokenClaims(sub=sub)

        app.dependency_overrides[auth.current_user] = _claims

    return _login


@pytest.fixture
def keypair() -> RsaKeyPair:
    return generate_rsa_keypair(kid="test-kid")


@pytest.fixture
def real_tokens(keypair: RsaKeyPair, settings: Settings) -> Iterator[Callable[..., str]]:
    """Real RS256 tokens, verified by the real validator against a real public key."""
    validator = auth.validator
    saved = (validator._jwks_client, validator._jwks_fetched_at)
    validator._jwks_client = StaticJWKSClient(keypair)  # type: ignore[assignment]
    validator._jwks_fetched_at = float("inf")  # never expires during the test

    kc = settings.keycloak

    def _issue(sub: str, *, azp: str | None = "mobile-app", **kwargs: Any) -> str:
        extra = {"azp": azp} if azp is not None else None
        return issue_test_token(
            keypair,
            issuer=kc.issuer,
            audience=kc.audience or kc.client_id,
            sub=sub,
            extra_claims=extra,
            **kwargs,
        )

    yield _issue
    validator._jwks_client, validator._jwks_fetched_at = saved
