"""WebSocket boilerplate. No business logic yet.

Two traps, both real:

1. ``RequestContextMiddleware`` and most HTTP middleware do not apply to the
   websocket scope, so there is no request ID unless the handler binds one.
2. Browsers cannot send an ``Authorization`` header on the websocket handshake.
   The mobile app can, which is what this accepts. A web client would need a
   subprotocol or a query parameter instead.

WebSocket routes do not appear in OpenAPI, so ``assert_routes_protected`` cannot
see them: authentication here is checked by its own test.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect, status
from py_common.logging import get_logger

from src.auth import auth
from src.users.constants import USERS_TAG

logger = get_logger(__name__)

ws_users = APIRouter(prefix="/users", tags=[USERS_TAG])


@ws_users.websocket("/ws")
async def user_events(websocket: WebSocket) -> None:
    header = websocket.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    try:
        claims = await auth.validator.decode_async(token)
    except HTTPException:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()
    try:
        while True:
            message = await websocket.receive_text()
            await websocket.send_json({"echo": message, "sub": claims.sub})
    except WebSocketDisconnect:
        logger.info("ws_disconnected", sub=claims.sub)
