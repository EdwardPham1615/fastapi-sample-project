"""Tier *internal*: cron jobs, deploy jobs, other services — never the mobile app.

Guarded by ``X-API-Key`` through py-common's ``internal_router``. Two decisions sit
on top of the library, both in ``src/main.py``:

1. The library is deliberately fail-open: with no ``HTTP__INTERNAL_API_KEY`` it
   installs no guard at all. This service refuses to start outside dev instead.
2. These routes stay in the OpenAPI document. Hiding them with
   ``include_in_schema=False`` would take them out of what
   ``assert_routes_protected`` reads — the tier that most needs the check would
   escape it. OpenAPI is off in production anyway; SDK generation filters by tag.

Built by a factory, not at import time: whether the guard is installed depends on
the settings the *app* is built with. A module-level router would freeze that
decision to whatever the environment held when this file was first imported, so a
test or the OpenAPI export building the app with other settings would still get it.

Not versioned: both sides deploy together.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from py_common.security import internal_router

from src.entity import DataResponse
from src.users.constants import INTERNAL_TAG
from src.users.deps import KeycloakDep, SyncServiceDep
from src.users.entity import SyncReport

if TYPE_CHECKING:
    from fastapi import APIRouter

    from src.config import Settings


async def sync_users(keycloak: KeycloakDep, sync: SyncServiceDep) -> Any:
    # Inline, not BackgroundTasks: a lost sync is something you would want to know
    # about, and BackgroundTasks has no retry and dies with the worker. A real
    # schedule belongs to cron or a task queue.
    report = await sync.apply(await keycloak.list_all_users())
    return {"data": report}


def build_internal_users(settings: Settings) -> APIRouter:
    router = internal_router(settings, prefix="/users", tags=[INTERNAL_TAG])
    router.add_api_route(
        "/sync",
        sync_users,
        methods=["POST"],
        response_model=DataResponse[SyncReport],
        summary="Sync users from Keycloak",
    )
    return router
