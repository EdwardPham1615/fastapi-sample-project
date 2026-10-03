"""Composition root: the one place that knows every implementation.

Run with ``python -m src`` (see src/__main__.py for why not the uvicorn CLI). Order
inside ``create_app`` follows py-common's README "Quick usage", and parts of it are
load-bearing — see the comments.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi.routing import APIRoute
from py_common.cache import create_redis
from py_common.http import (
    HealthCheck,
    build_health_router,
    build_problem_types_router,
    register_exception_handlers,
)
from py_common.logging import setup_logging
from py_common.persistence import (
    create_engine_and_sessionmaker,
    database_lifespan_resource,
    migration_lifespan_resource,
)
from py_common.runtime import GrpcServer, LifespanResource, build_lifespan, create_base_app
from py_common.telemetry import setup_telemetry
from py_common.telemetry.profiler import enable_profiler
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from src.api import build_routers
from src.config import Settings, get_settings
from src.exceptions import integrity_error_handler
from src.middleware import apply_middleware
from src.users.grpc import servicer as users_grpc

if TYPE_CHECKING:
    from fastapi import FastAPI
    from grpc import aio
    from redis.asyncio import Redis


def custom_generate_unique_id(route: APIRoute) -> str:
    """operationId = "<first tag>-<handler name>", e.g. "users-get_my_profile".

    A generated client SDK names its methods from this, so it is worth keeping
    readable. Routes without a tag fall back to "default" rather than raising.
    """
    tag = route.tags[0] if route.tags else "default"
    return f"{tag}-{route.name}"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    # py-common's internal_router is fail-open by design: without a key it installs
    # no guard and relies on network isolation. This service does not rely on that,
    # so "forgot to configure it" becomes "does not start" instead of "the sync
    # endpoint is open".
    if not settings.is_dev and not settings.http.internal_api_key:
        raise RuntimeError(
            "HTTP__INTERNAL_API_KEY must be set outside dev: "
            "internal_router installs no guard without it"
        )

    setup_logging(
        level=settings.log_level,
        service_name=settings.app_name,
        environment=settings.environment.value,
        json_logs=settings.log_json,
    )

    engine, session_factory = create_engine_and_sessionmaker(settings.postgres)
    redis: Redis | None = create_redis(settings.redis) if settings.redis_enabled else None

    async def ping_db() -> None:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))

    def register_users(server: aio.Server) -> None:
        users_grpc.register(server, session_factory)

    grpc_server = GrpcServer(
        host=settings.grpc_host,
        port=settings.grpc_port,
        enabled=settings.grpc_enabled,  # start() is a no-op when False
        registrars=[register_users],
    )

    resources: list[LifespanResource] = [
        migration_lifespan_resource(settings.postgres),  # no-op unless POSTGRES__AUTO_MIGRATE
        database_lifespan_resource(engine),
    ]
    if redis is not None:
        redis_client = redis

        async def _noop() -> None:
            return None

        async def _close_redis() -> None:
            await redis_client.aclose()

        resources.append(LifespanResource(name="redis", startup=_noop, shutdown=_close_redis))

    show_docs = settings.is_dev or settings.debug
    app = create_base_app(
        title=settings.app_name,
        version=settings.app_version,
        is_dev=settings.is_dev,
        debug=settings.debug,
        # create_base_app hides /docs and /redoc outside dev, but NOT the schema itself.
        openapi_url="/openapi.json" if show_docs else None,
        generate_unique_id_function=custom_generate_unique_id,
        lifespan=build_lifespan(resources, grpc_server=grpc_server),
    )
    app.state.settings = settings
    app.state.session_factory = session_factory

    # Exception handlers BEFORE middleware: the other way round, a 500 raised deep in
    # the stack loses its X-Request-ID and CORS headers (py-common CLAUDE.md).
    register_exception_handlers(app, problem_type_base_url=settings.http.problem_type_base_url)
    app.add_exception_handler(IntegrityError, integrity_error_handler)
    apply_middleware(app, settings, redis=redis)

    setup_telemetry(
        app,
        service_name=settings.app_name,
        otlp_endpoint=settings.otel.exporter_otlp_endpoint,
        insecure=settings.otel.exporter_otlp_insecure,
        sampler_arg=settings.otel.traces_sampler_arg,
        enabled=settings.otel.enabled,
        environment=settings.environment.value,
        metrics_enabled=settings.otel.metrics_enabled,
        metrics_export_interval_ms=settings.otel.metrics_export_interval_ms,
        prometheus_metrics=settings.otel.prometheus_enabled,
    )
    enable_profiler(app, settings.profiler, environment=settings.environment.value)

    app.include_router(build_health_router([HealthCheck(name="postgres", check=ping_db)]))
    app.include_router(
        build_problem_types_router(problem_type_base_url=settings.http.problem_type_base_url)
    )
    for router in build_routers(settings):
        app.include_router(router)

    if settings.is_dev and settings.dev_fake_keycloak:
        from src.dev.keycloak import build_fake_keycloak_router  # dev-only code path

        app.include_router(build_fake_keycloak_router(settings))

    # MCP, when needed: app.mount("/mcp", mcp_asgi_app) — it is a sub-application.
    return app


app = create_app()
