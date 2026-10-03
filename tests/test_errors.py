"""IntegrityError → 409 only for unique violations.

That asyncpg really exposes SQLSTATE 23505 is proven on Postgres in
tests/integration; this checks the handler is wired into the app and branches right.
"""

from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.exc import IntegrityError


def _integrity_error(sqlstate: str) -> IntegrityError:
    return IntegrityError("INSERT ...", {}, SimpleNamespace(sqlstate=sqlstate))  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("sqlstate", "status", "meaning"),
    [("23505", 409, "unique violation"), ("23502", 500, "not-null violation is a bug")],
)
async def test_integrity_errors_are_split_by_sqlstate(
    app: FastAPI, sqlstate: str, status: int, meaning: str
) -> None:
    async def boom() -> None:
        raise _integrity_error(sqlstate)

    app.add_api_route("/boom", boom)
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/boom")

    assert resp.status_code == status, meaning
    assert resp.headers["content-type"].startswith("application/problem+json")
    assert "uq_" not in resp.text  # constraint names stay in the log, not the response
