"""Routers grouped by API version and trust tier. ``main.py`` includes only what this returns.

Tier is independent of domain and of version:

  /v1/...        public + user tiers, versioned (clients are outside our control)
  /internal/...  internal tier, not versioned (both sides deploy together)

Adding v2 is ``APIRouter(prefix="/v2")`` here. Give its routers their own tags:
the OpenAPI operationId is built from the first tag and the handler name, so v1 and
v2 sharing both would collide and break a generated client.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter

from src.users.routers.internal import build_internal_users
from src.users.routers.v1 import users as users_v1
from src.users.routers.v1_public import public_users as users_v1_public
from src.users.routers.ws import ws_users

if TYPE_CHECKING:
    from src.config import Settings


def build_routers(settings: Settings) -> list[APIRouter]:
    v1 = APIRouter(prefix="/v1")
    # The user tier is included first: its static /users/me routes must be matched
    # before any /users/{user_id} route from another router at the same depth.
    v1.include_router(users_v1)
    v1.include_router(users_v1_public)
    v1.include_router(ws_users)

    internal = APIRouter(prefix="/internal")
    internal.include_router(build_internal_users(settings))

    return [v1, internal]
