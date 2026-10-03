"""UserSyncService takes data, not a client — so no Keycloak double exists here."""

from __future__ import annotations

from datetime import UTC, datetime

from py_common.utils import FixedClock

from integrations.keycloak.entity import KeycloakUserDTO
from src.models import epoch_ms
from src.users.constants import UserStatus
from src.users.sync import UserSyncService
from tests.fakes import InMemoryUserRepository

CLOCK = FixedClock(datetime(2026, 9, 25, 12, 0, tzinfo=UTC))
USERS = [
    KeycloakUserDTO(id="kc-1", username="an", email="an@example.com", firstName="An", enabled=True),
    KeycloakUserDTO(
        id="kc-2", username="binh", email="binh@example.com", firstName="Binh", enabled=False
    ),
]


async def test_first_run_creates_everyone() -> None:
    repo = InMemoryUserRepository()
    report = await UserSyncService(repo, clock=CLOCK).apply(USERS)

    assert report.model_dump() == {"created": 2, "updated": 0, "unchanged": 0}
    binh = await repo.get_by_oidc_id("kc-2")
    assert binh is not None
    assert binh.status == UserStatus.INACTIVE
    assert binh.updated_at == epoch_ms(CLOCK)  # deterministic: injected clock


async def test_second_run_changes_nothing() -> None:
    repo = InMemoryUserRepository()
    service = UserSyncService(repo, clock=CLOCK)
    await service.apply(USERS)

    report = await service.apply(USERS)

    assert report.model_dump() == {"created": 0, "updated": 0, "unchanged": 2}


async def test_a_users_own_edits_survive_the_next_sync() -> None:
    repo = InMemoryUserRepository()
    service = UserSyncService(repo, clock=CLOCK)
    await service.apply(USERS)
    an = await repo.get_by_oidc_id("kc-1")
    assert an is not None
    an.first_name, an.phone = "Ân", "912345678"  # edited in the app

    changed_upstream = [USERS[0].model_copy(update={"email": "an@new.example.com"}), USERS[1]]
    report = await service.apply(changed_upstream)

    assert report.updated == 1
    assert an.email == "an@new.example.com"  # the identity provider owns email
    assert (an.first_name, an.phone) == ("Ân", "912345678")  # the app owns these now
