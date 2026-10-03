"""Tier *public*: no authentication.

A plain ``APIRouter`` on purpose. py-common evaluated and rejected a
``public_router`` helper: a public router is just ``APIRouter(...)``, and a wrapper
would add a name and no behaviour. Every path here must be listed in
``public_paths`` in tests/test_routes_protected.py — every open endpoint appears at
a call site.

The guard is only half of a tier. The other half is the response model: routes here
return ``UserCard``, never ``UserPublic``.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from src.auth import OptionalClaims
from src.entity import DataResponse
from src.users.constants import USERS_PUBLIC_TAG
from src.users.deps import ValidUser, valid_user_id
from src.users.entity import UserCard

public_users = APIRouter(prefix="/users", tags=[USERS_PUBLIC_TAG], dependencies=[])

# Same loader, same group pattern as the user tier.
public_item = APIRouter(prefix="/{user_id}", dependencies=[Depends(valid_user_id)])


@public_item.get("/card", response_model=DataResponse[UserCard], summary="Get a public user card")
async def get_user_card(user: ValidUser, viewer: OptionalClaims) -> Any:
    # `viewer` is None for an anonymous caller. An invalid token is still a 401.
    return {"data": user}


public_users.include_router(public_item)
