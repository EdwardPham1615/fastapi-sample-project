"""No route is public by accident — checked on the app as production would build it."""

from __future__ import annotations

from py_common.testing.routes import PYCOMMON_PUBLIC_PREFIXES, assert_routes_protected

from src.main import create_app
from src.openapi import export_settings

# Every endpoint meant to be reachable without authentication, written down here.
PUBLIC_PATHS = ["/v1/users/{user_id}/card"]


def test_no_route_is_accidentally_public() -> None:
    """Built with production-shaped settings, as assert_routes_protected's own
    docstring asks: an internal_router built without a key installs no guard.

    Two limits, stated by py-common and worth repeating:
    - it does not check authorization (a route that forgets requires(...) passes);
    - WebSocket routes are not in OpenAPI, so /users/ws is covered by test_ws.py.

    A third, found while writing this service: a route using optional auth declares
    the HTTPBearer scheme, so the check reads it as protected even though anyone
    can call it. The public card route is such a route — it would pass even if it
    were missing from PUBLIC_PATHS. Its openness is pinned by
    test_loaders.test_public_card_needs_no_token_and_leaks_nothing_private.
    """
    app = create_app(export_settings())
    assert_routes_protected(
        app,
        public_prefixes=PYCOMMON_PUBLIC_PREFIXES,
        public_paths=PUBLIC_PATHS,
    )


def test_internal_routes_stay_in_the_openapi_document() -> None:
    """Hiding them (include_in_schema=False) would take them out of what the check
    above reads — the tier that most needs checking would silently escape it."""
    paths = create_app(export_settings()).openapi()["paths"]
    assert paths["/internal/users/sync"]["post"]["security"] == [{"APIKeyHeader": []}]
