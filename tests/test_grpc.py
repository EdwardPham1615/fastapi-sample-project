"""The gRPC boilerplate actually serves — over a real in-process gRPC server."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from typing import Any

import grpc
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.users.constants import UserStatus
from src.users.grpc import servicer, user_pb2, user_pb2_grpc
from tests.fakes import make_user


@pytest.fixture
async def stub(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[Any]:
    server = grpc.aio.server()
    servicer.register(server, session_factory)  # the same registrar main.py composes
    port = server.add_insecure_port("127.0.0.1:0")
    await server.start()
    async with grpc.aio.insecure_channel(f"127.0.0.1:{port}") as channel:
        yield user_pb2_grpc.UserServiceStub(channel)
    await server.stop(grace=None)


async def test_get_profile(stub: Any, save: Callable[..., Any]) -> None:
    user = make_user(first_name="An")
    await save(user)

    reply = await stub.GetProfile(user_pb2.GetProfileRequest(user_id=str(user.id)))

    assert (reply.id, reply.first_name) == (str(user.id), "An")


@pytest.mark.parametrize(
    ("make_id", "code"),
    [
        (lambda _: "not-a-uuid", grpc.StatusCode.INVALID_ARGUMENT),
        (lambda _: "00000000-0000-4000-8000-000000000000", grpc.StatusCode.NOT_FOUND),
        (lambda deleted: str(deleted.id), grpc.StatusCode.NOT_FOUND),  # same rule as HTTP
    ],
)
async def test_errors(
    stub: Any, save: Callable[..., Any], make_id: Callable[[Any], str], code: grpc.StatusCode
) -> None:
    deleted = make_user(status=int(UserStatus.DELETED))
    await save(deleted)

    with pytest.raises(grpc.aio.AioRpcError) as exc:
        await stub.GetProfile(user_pb2.GetProfileRequest(user_id=make_id(deleted)))

    assert exc.value.code() == code
