"""The worker's one task, its schedule, and its startup check (src/worker/).

The task's job runs here on the test database with Keycloak faked at the transport.
A real prefork worker is tests/test_worker_spawn.py.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
import pytest
from celery import signals
from celery.utils.dispatch.signal import Signal
from py_common.config import Environment
from py_common.persistence import SqlAlchemyUnitOfWork
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import src.worker.app as worker_app
from integrations.keycloak.client import KeycloakAdminClient
from src.config import Settings
from src.worker.app import SYNC_USERS, celery_app
from src.worker.tasks import sync_users
from tests.fakes import token_endpoint

KEYCLOAK_USERS = [
    {"id": "kc-1", "username": "an", "email": "an@example.com", "firstName": "An"},
    {"id": "kc-2", "username": "binh", "email": "binh@example.com", "enabled": False},
]


class _Runtime:
    """The two things the job uses from src.worker.runtime.Runtime."""

    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession], keycloak: KeycloakAdminClient
    ) -> None:
        self._session_factory = session_factory
        self.keycloak = keycloak

    @asynccontextmanager
    async def uow(self) -> AsyncIterator[SqlAlchemyUnitOfWork]:
        async with SqlAlchemyUnitOfWork(self._session_factory) as uow:
            yield uow


async def test_the_sync_job_reports_like_the_route(
    settings: Settings, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return token_endpoint(request) or httpx.Response(200, json=KEYCLOAK_USERS)

    keycloak = KeycloakAdminClient(settings.keycloak, transport=httpx.MockTransport(handler))
    runtime = _Runtime(session_factory, keycloak)
    try:
        first = await sync_users.job(runtime)
        again = await sync_users.job(runtime)  # late ack can run it twice: must be harmless
    finally:
        await keycloak.aclose()

    assert first == {"created": 2, "updated": 0, "unchanged": 0}
    assert again == {"created": 0, "updated": 0, "unchanged": 2}


def test_the_task_and_its_nightly_schedule_are_registered() -> None:
    assert SYNC_USERS in celery_app.tasks
    entry = celery_app.conf.beat_schedule["users-sync-nightly"]
    assert entry["task"] == SYNC_USERS
    assert (entry["schedule"].hour, entry["schedule"].minute) == ({2}, {0})


@pytest.mark.parametrize("signal", [signals.worker_init, signals.beat_init], ids=["worker", "beat"])
def test_dev_values_outside_dev_stop_the_worker_and_beat(
    settings: Settings, monkeypatch: pytest.MonkeyPatch, signal: Signal
) -> None:
    """Sent through the real signal: Celery's Signal.send swallows an Exception from a
    receiver and the process starts anyway, so only an exception it lets through counts."""
    staging = settings.model_copy(
        update={
            "environment": Environment.STAGING,
            "http": settings.http.model_copy(update={"internal_api_key": "dev-key"}),
        }
    )
    monkeypatch.setattr(worker_app, "settings", staging)

    with pytest.raises(SystemExit, match="HTTP__INTERNAL_API_KEY"):
        signal.send(sender=None)


def test_importing_the_app_connects_to_nothing() -> None:
    """The API may import src.worker.app to send tasks: with no broker reachable, the
    import must still succeed, and quickly."""
    env = {**os.environ, "WORKER__BROKER_URL": "redis://127.0.0.1:1/0"}  # nothing listens
    # Fixed argv: this interpreter importing our module.
    done = subprocess.run(
        [sys.executable, "-c", "import src.worker.app"],
        env=env,
        capture_output=True,
        timeout=20,
        check=False,
    )
    assert done.returncode == 0, done.stderr.decode()[-2000:]
