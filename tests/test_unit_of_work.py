"""The request's transaction commits before the response leaves, so a failed commit
is never reported as success (needs ``scope="function"`` on the dependency)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, get_args

import httpx
import pytest
from fastapi.params import Depends
from py_common.persistence import SqlAlchemyUnitOfWork
from sqlalchemy.exc import OperationalError

from src.database import UowDep
from tests.fakes import make_user


def test_uow_dependency_exits_before_the_response() -> None:
    marker = get_args(UowDep)[1]
    assert isinstance(marker, Depends)
    assert marker.scope == "function"


async def test_failed_commit_is_not_reported_as_success(
    client: httpx.AsyncClient,
    save: Callable[..., Any],
    login_as: Callable[[str], None],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await save(make_user(oidc_provider_id="kc-commit", first_name="Before"))
    login_as("kc-commit")

    async def failing_commit(self: SqlAlchemyUnitOfWork) -> None:
        raise OperationalError("COMMIT", {}, Exception("connection lost"))

    monkeypatch.setattr(SqlAlchemyUnitOfWork, "commit", failing_commit)
    response = await client.patch("/v1/users/me", json={"first_name": "After"})

    assert response.status_code == 500
    monkeypatch.undo()
    me = (await client.get("/v1/users/me")).json()["data"]
    assert me["first_name"] == "Before"
