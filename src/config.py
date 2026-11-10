"""Service settings: one root object, py-common groups nested under it.

Env keys follow the field names — ``postgres`` becomes ``POSTGRES__HOST`` and so on.
``BaseAppSettings`` sets ``extra="ignore"``, so a misspelt key is dropped *silently*
and the setting keeps its default. Check ``.env.example`` rather than guessing.

Settings are not split per domain on purpose: two independent ``BaseSettings``
objects would each resolve the env files on their own, and py-common requires
``get_environment()`` and ``settings.environment`` to agree.
"""

from __future__ import annotations

from functools import lru_cache
from importlib.metadata import version

from py_common.config import (
    BaseAppSettings,
    DatabaseSettings,
    KeycloakSettings,
    OtelSettings,
    ProfilerSettings,
    RedisSettings,
    WorkerSettings,
)
from pydantic import Field


class Settings(BaseAppSettings):
    app_name: str = "user-profile-service"
    # From pyproject.toml, so the version in OpenAPI and in logs cannot drift from it.
    app_version: str = Field(default_factory=lambda: version("user-profile-service"))

    # ECS JSON logs (py-common's format) in every environment, dev included, so what
    # you read locally is what the log pipeline receives. Set LOG_JSON=false for
    # coloured console output while developing.
    log_json: bool = True

    postgres: DatabaseSettings = Field(default_factory=DatabaseSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    keycloak: KeycloakSettings = Field(default_factory=KeycloakSettings)
    otel: OtelSettings = Field(default_factory=OtelSettings)
    profiler: ProfilerSettings = Field(default_factory=ProfilerSettings)
    # The Celery worker's broker, retries, lock TTL (src/worker/). Its Redis client is
    # `redis` above; the API reads neither unless REDIS_ENABLED.
    worker: WorkerSettings = Field(default_factory=WorkerSettings)

    grpc_enabled: bool = False
    grpc_host: str = "0.0.0.0"
    grpc_port: int = 50051

    # Serves a stand-in for Keycloak at the paths the real one uses. Only honoured
    # in dev. Whether the service talks to the fake or a real Keycloak is decided by
    # KEYCLOAK__SERVER_URL alone — there is no second switch to keep in step.
    dev_fake_keycloak: bool = False
    dev_keycloak_key_path: str = ".dev/keycloak_key.json"
    dev_keycloak_users_path: str = "scripts/data/keycloak_users.json"

    redis_enabled: bool = False


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


# Values that mean "dev" for a secret: the "dev-..." ones and the Postgres password of
# .env.example, and py-common's default Postgres password.
_DEV_VALUES = frozenset({"user_profile", "postgres"})


def check_runtime_settings(settings: Settings) -> None:
    """Fail at startup rather than run unguarded or on dev values.

    Errors name the variables, never their values."""
    if settings.is_dev:
        return
    # py-common's internal_router is fail-open by design: without a key it installs
    # no guard and relies on network isolation. This service does not rely on that,
    # so "forgot to configure it" becomes "does not start" instead of "the sync
    # endpoint is open".
    if not settings.http.internal_api_key:
        raise RuntimeError(
            "HTTP__INTERNAL_API_KEY must be set outside dev: "
            "internal_router installs no guard without it"
        )
    secrets = {
        "HTTP__INTERNAL_API_KEY": settings.http.internal_api_key,
        "POSTGRES__PASSWORD": settings.postgres.password,
        "KEYCLOAK__CLIENT_SECRET": settings.keycloak.client_secret,
    }
    dev = [
        name
        for name, value in secrets.items()
        if value and (value.startswith("dev-") or value in _DEV_VALUES)
    ]
    if dev:
        raise RuntimeError(f"Dev values outside dev: {', '.join(dev)}")
