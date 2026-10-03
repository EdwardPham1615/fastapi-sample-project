"""gRPC transport for the users domain. Boilerplate: one RPC.

A transport is a thin adapter over the same repository and rules the HTTP routes
use — never a copy of their logic. Adding a second transport is exactly the kind of
"second caller" that justifies pulling logic out of a route handler.

Two things differ from HTTP, both because gRPC has no FastAPI dependency injection:

- the servicer opens its own unit of work per RPC (repositories still *receive* a
  session; nothing below this line opens one);
- the id loader cannot be a dependency, so the servicer calls the repository method
  the loader delegates to (``get_existing``) and turns its not-found into a status.

Only NOT_FOUND is mapped; a general ``AppError`` → gRPC status mapping is not done
yet (see README "Not done").
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

import grpc
from py_common.errors import AppError, ErrorCode
from py_common.persistence import SqlAlchemyUnitOfWork

from src.users.grpc import user_pb2, user_pb2_grpc
from src.users.sqlalchemy_repository import UserRepository

if TYPE_CHECKING:
    from grpc import aio
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


class UserServicer(user_pb2_grpc.UserServiceServicer):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def GetProfile(self, request: Any, context: aio.ServicerContext[Any, Any]) -> Any:
        try:
            user_id = UUID(request.user_id)
        except ValueError:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "user_id is not a UUID")

        async with SqlAlchemyUnitOfWork(self._session_factory) as uow:
            assert uow.session is not None
            try:
                user = await UserRepository(uow.session).get_existing(user_id)
            except AppError as exc:
                if exc.error_code is not ErrorCode.NOT_FOUND:
                    raise
                await context.abort(grpc.StatusCode.NOT_FOUND, exc.detail or exc.title)
            return user_pb2.UserProfile(
                id=str(user.id),
                oidc_provider_id=user.oidc_provider_id,
                first_name=user.first_name or "",
                last_name=user.last_name or "",
                email=user.email or "",
                status=user.status,
                updated_at=user.updated_at,
            )


def register(server: aio.Server, session_factory: async_sessionmaker[AsyncSession]) -> None:
    """The domain registers its own servicer; ``main.py`` only composes registrars."""
    # protoc generates this without annotations.
    user_pb2_grpc.add_UserServiceServicer_to_server(  # type: ignore[no-untyped-call]
        UserServicer(session_factory), server
    )
