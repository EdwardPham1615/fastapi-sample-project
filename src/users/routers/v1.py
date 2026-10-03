"""Tier *user*: the mobile app, authenticated with a Keycloak user token.

Two router groups:

  (a) ``users``      /users            — authentication inherited from protected_router
  (b) ``user_item``  /users/{user_id}  — child of (a); ``valid_user_id`` runs for every
                                         route in it before the handler

Business logic sits in the handlers: each is a few lines over the repository and
``policy``. A service appears only when something has a second caller (see sync.py).
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, status
from py_common.http import Pagination, ProblemDetail
from py_common.persistence.pagination import DEFAULT_LIMIT, MAX_LIMIT
from py_common.security import protected_router

from src.auth import auth
from src.entity import DataResponse
from src.exceptions import ProfileNotEditable
from src.models import epoch_ms
from src.users import policy
from src.users.constants import USERS_TAG, UserStatus
from src.users.deps import CurrentUser, RepoDep, ValidUser, valid_user_id
from src.users.entity import UserPublic, UserUpdateMe

_ERRORS: dict[int | str, dict[str, Any]] = {
    status.HTTP_401_UNAUTHORIZED: {
        "model": ProblemDetail,
        "description": "Missing or invalid token",
    },
    status.HTTP_404_NOT_FOUND: {"model": ProblemDetail, "description": "Not found"},
}

# ── (a) /users ───────────────────────────────────────────────────────────────
users = protected_router(
    auth,
    prefix="/users",
    tags=[USERS_TAG],
    responses=_ERRORS,
)


@users.get("", response_model=DataResponse[list[UserPublic]], summary="List users")
async def list_users(
    repo: RepoDep,
    status_: Annotated[UserStatus | None, Query(alias="status")] = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Any:
    page = await repo.search(status=status_, q=q, limit=limit, offset=offset)
    return {
        "data": page.items,
        "count": len(page.items),
        "pagination": Pagination(
            offset=page.meta.offset,
            limit=page.meta.limit,
            total_items=page.meta.total_items,
            has_next=page.meta.has_more,
            has_prev=offset > 0,
        ),
    }


# Every /me route is declared BEFORE (b) is included at the bottom of this file.
# Include (b) first and `/users/me` is matched as `/users/{user_id}` — a 422.
# Measured on FastAPI 0.141.1; guarded by tests/test_loaders.py.


@users.get("/me", response_model=DataResponse[UserPublic], summary="Get my profile")
async def get_my_profile(user: CurrentUser) -> Any:
    # A dict, not DataResponse(...): response_model builds the envelope once.
    return {"data": user}


@users.patch(
    "/me",
    response_model=DataResponse[UserPublic],
    summary="Update my profile",
    responses={status.HTTP_403_FORBIDDEN: {"model": ProblemDetail}},
)
async def update_my_profile(payload: UserUpdateMe, user: CurrentUser, repo: RepoDep) -> Any:
    if not policy.can_update_profile(user):
        raise ProfileNotEditable()
    changes = payload.model_dump(exclude_unset=True)
    policy.apply_profile_update(user, changes, now=epoch_ms())
    return {"data": await repo.update(user)}


@users.post(
    "/me/deactivate", response_model=DataResponse[UserPublic], summary="Deactivate my account"
)
async def deactivate_my_account(user: CurrentUser, repo: RepoDep) -> Any:
    user.status = int(policy.next_status_on_deactivate(user))
    user.updated_at = epoch_ms()
    return {"data": await repo.update(user)}


# ── (b) /users/{user_id} ─────────────────────────────────────────────────────
# Attaching the loader to the group, not to each route, is the point: a route added
# here later is checked even if its author forgets to ask for ValidUser. Handlers
# that need the object still declare ValidUser — FastAPI caches the loader's result
# per request, so it runs once, not twice.
user_item = APIRouter(prefix="/{user_id}", dependencies=[Depends(valid_user_id)])


@user_item.get("", response_model=DataResponse[UserPublic], summary="Get a user")
async def get_user(user: ValidUser) -> Any:
    return {"data": user}


# ── Include (b) into (a) LAST, after every static route of (a). ─────────────
users.include_router(user_item)
