"""WebSocket boilerplate. Not in OpenAPI, so test_routes_protected cannot see it."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

# TestClient is NOT entered as a context manager: that would run the lifespan, which
# connects to Postgres — and the unit suite must not need Docker.


def test_rejects_a_connection_without_a_token(app: FastAPI) -> None:
    client = TestClient(app)
    with (
        pytest.raises(WebSocketDisconnect) as exc,
        client.websocket_connect("/v1/users/ws") as ws,
    ):
        ws.receive_text()
    assert exc.value.code == 1008


def test_accepts_a_valid_token(app: FastAPI, real_tokens: Callable[..., str]) -> None:
    token = real_tokens("kc-an")
    client = TestClient(app)
    with (
        client.websocket_connect(
            "/v1/users/ws", headers={"Authorization": f"Bearer {token}"}
        ) as ws,
    ):
        ws.send_text("hi")
        assert ws.receive_json() == {"echo": "hi", "sub": "kc-an"}
