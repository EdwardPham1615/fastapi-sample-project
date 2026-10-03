"""What the SQLite unit suite cannot prove.

SQLite stores logged_in_methods as JSON and has no SQLSTATE codes, so the column
type, the constraint behaviour and the 409 mapping are only real here.
"""

from __future__ import annotations

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from integrations.keycloak.entity import KeycloakUserDTO
from src.exceptions import is_unique_violation
from src.users.constants import LoginMethod, UserStatus
from src.users.sqlalchemy_repository import UserRepository
from src.users.sync import UserSyncService
from tests.fakes import make_user

pytestmark = pytest.mark.integration

Factory = async_sessionmaker[AsyncSession]


async def test_logged_in_methods_is_a_real_smallint_array(pg_session_factory: Factory) -> None:
    user = make_user(logged_in_methods=[int(LoginMethod.GOOGLE), int(LoginMethod.OTP)])
    async with pg_session_factory() as session:
        await UserRepository(session).create(user)
        await session.commit()

        column_type = await session.scalar(
            text(
                "SELECT udt_name FROM information_schema.columns "
                "WHERE table_name = 'users' AND column_name = 'logged_in_methods'"
            )
        )
        stored = await session.scalar(
            text("SELECT logged_in_methods FROM users WHERE id = :id"), {"id": user.id}
        )

    assert column_type == "_int2"  # Postgres' name for smallint[]
    assert stored == [LoginMethod.GOOGLE, LoginMethod.OTP]


async def test_a_duplicate_is_recognised_as_a_unique_violation(pg_session_factory: Factory) -> None:
    """Pins the assumption src.exceptions.is_unique_violation rests on: that the
    asyncpg driver exposes SQLSTATE 23505 on the wrapped error."""
    async with pg_session_factory() as session:
        repo = UserRepository(session)
        await repo.create(make_user(oidc_provider_id="kc-dup"))
        with pytest.raises(IntegrityError) as exc:
            await repo.create(make_user(oidc_provider_id="kc-dup"))

    assert is_unique_violation(exc.value)
    assert "uq_users_oidc_provider_id" in str(exc.value)  # py-common's naming convention


async def test_a_not_null_violation_is_not_mistaken_for_a_conflict(
    pg_session_factory: Factory,
) -> None:
    async with pg_session_factory() as session:
        with pytest.raises(IntegrityError) as exc:
            await session.execute(
                text(
                    "INSERT INTO users (id, oidc_provider_id, created_at, updated_at, "
                    "gender, status, lang, logged_in_methods) "
                    "VALUES (gen_random_uuid(), NULL, 0, 0, 0, 1, 'vi', '{}')"
                )
            )

    assert not is_unique_violation(exc.value)


async def test_search_on_postgres(pg_session_factory: Factory) -> None:
    async with pg_session_factory() as session:
        repo = UserRepository(session)
        for i, name in enumerate(["Chi", "chinh", "Dung"]):
            await repo.create(make_user(first_name=name, created_at=1_000 + i))
        await session.commit()

        page = await repo.search(status=UserStatus.ACTIVE, q="CHI", limit=10, offset=0)

    assert [u.first_name for u in page.items] == ["chinh", "Chi"]  # ILIKE, newest first
    assert page.meta.total_items == 2


async def test_search_is_not_accent_insensitive_yet(pg_session_factory: Factory) -> None:
    """Pins a known limitation rather than hiding it: ILIKE ignores case, not
    diacritics, so "chi" does not find "Chính". For Vietnamese names that is a real
    gap; fixing it needs the `unaccent` extension (README, "Not done"). When that
    lands, this test should flip — and be rewritten, not deleted."""
    async with pg_session_factory() as session:
        repo = UserRepository(session)
        await repo.create(make_user(first_name="Chính"))
        await session.commit()

        page = await repo.search(status=None, q="chi", limit=10, offset=0)

    assert page.items == []


async def test_sync_is_idempotent_on_postgres(pg_session_factory: Factory) -> None:
    users = [
        KeycloakUserDTO(id="kc-1", username="an", email="an@example.com", enabled=True),
        KeycloakUserDTO(id="kc-2", username="binh", email="binh@example.com", enabled=False),
    ]
    first_run = {"created": 2, "updated": 0, "unchanged": 0}
    second_run = {"created": 0, "updated": 0, "unchanged": 2}
    for expected in (first_run, second_run):
        async with pg_session_factory() as session:
            report = await UserSyncService(UserRepository(session)).apply(users)
            await session.commit()
        assert report.model_dump() == expected


def test_migrations_round_trip(migrated: Config) -> None:
    """Static and reversible: down to nothing and back up, cleanly."""
    command.downgrade(migrated, "base")
    command.upgrade(migrated, "head")
    command.check(migrated)  # the migrated schema still matches the models exactly
