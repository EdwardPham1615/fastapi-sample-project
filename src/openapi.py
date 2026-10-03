"""Build the OpenAPI document of the *real* API, from code.

Shared by ``scripts/export_openapi.py`` (writes ``docs/openapi.json``) and
``tests/test_openapi_snapshot.py`` (fails when that file no longer matches), so the
two cannot describe different APIs.

Why from code: outside dev ``openapi_url`` is None, so the production API's schema
cannot be fetched over HTTP at all — but ``app.openapi()`` still builds it
(verified on FastAPI 0.141.1).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.config import Settings

SPEC_PATH = Path("docs/openapi.json")


def export_settings() -> Settings:
    """Production-shaped settings, pinned so the output is the same on every machine.

    - environment=production: no /dev/* routes, exactly what clients will meet.
    - an internal API key, so internal routes carry the X-API-Key scheme (and the
      app's startup guard is satisfied). The value never appears in the spec.
    - app_name pinned explicitly: keyword arguments beat environment variables, so
      an APP_NAME exported in someone's shell cannot change the committed file.
    - _env_file=None: the local .env plays no part.
    """
    return Settings(
        _env_file=None,
        environment="production",
        app_name="user-profile-service",
        http={"internal_api_key": "export-only"},
        otel={"enabled": False},
        dev_fake_keycloak=False,
    )


def build_spec() -> dict[str, Any]:
    from src.main import create_app  # deferred: importing main builds the default app

    spec = create_app(export_settings()).openapi()
    # Postman takes the base URL from the first server; change it per environment there.
    spec["servers"] = [{"url": "http://localhost:8000", "description": "local"}]
    return spec


def render(spec: dict[str, Any]) -> str:
    return json.dumps(spec, indent=2, ensure_ascii=False) + "\n"


def write_spec(path: Path = SPEC_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render(build_spec()))
