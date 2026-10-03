"""Real Postgres. Skipped when POSTGRES_TEST_DSN is unset.

The skip lives in the fixture, not in a module-level ``pytestmark``: pytest silently
ignores ``pytestmark`` in a conftest, and the tests would then run against nothing
and fail rather than skip (py-common CLAUDE.md, "Integration tests").

The suite migrates the database up and down, so POSTGRES_TEST_DSN must point at a
throwaway database — `make test-integration-local` uses user_profile_test.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


@pytest.fixture(scope="session")
def postgres_dsn() -> str:
    dsn = os.environ.get("POSTGRES_TEST_DSN")
    if not dsn:
        pytest.skip("POSTGRES_TEST_DSN not set — run `make test-integration-local`")
    return dsn


def alembic_config(async_dsn: str) -> Config:
    cfg = Config("alembic.ini")
    # Migrations run on the sync driver; env.py honours an explicitly set URL.
    sync_dsn = async_dsn.replace("+asyncpg", "+psycopg")
    cfg.set_main_option("sqlalchemy.url", sync_dsn.replace("%", "%%"))
    return cfg


@pytest.fixture
def migrated(postgres_dsn: str) -> Iterator[Config]:
    """The schema exactly as the migrations build it — not metadata.create_all()."""
    cfg = alembic_config(postgres_dsn)
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    yield cfg
    command.downgrade(cfg, "base")


@pytest.fixture
async def pg_session_factory(
    postgres_dsn: str, migrated: Config
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(postgres_dsn)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()
