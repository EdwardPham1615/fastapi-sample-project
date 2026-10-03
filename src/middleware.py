"""Middleware for the whole app — and only for the whole app.

Starlette middleware cannot be scoped to a domain: ``add_middleware`` applies to
every request. Anything that should cover one group of routes belongs on that
``APIRouter`` as ``dependencies=[...]`` instead.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from py_common.http.middleware import apply_standard_middleware

if TYPE_CHECKING:
    from fastapi import FastAPI
    from redis.asyncio import Redis

    from src.config import Settings


def apply_middleware(app: FastAPI, settings: Settings, *, redis: Redis | None = None) -> None:
    # CORS, security headers, metrics, request context, gzip, timeout, body limit,
    # idempotency — in the one order that works.
    apply_standard_middleware(app, settings, redis=redis)
    # Service-specific middleware goes BELOW this line, which places it INSIDE the
    # CORS and security layers. The other way round, a 500 loses its X-Request-ID
    # and CORS headers (py-common CLAUDE.md, "Errors are Problem Details").
