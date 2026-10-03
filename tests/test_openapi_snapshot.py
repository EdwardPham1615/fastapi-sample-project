"""docs/openapi.json must describe the code as it is."""

from __future__ import annotations

import json

from src.openapi import SPEC_PATH, build_spec


def test_committed_openapi_matches_code() -> None:
    """docs/openapi.json is the reviewed HTTP contract, and what Postman imports.

    Change an endpoint without running `make openapi` and the committed file lies
    to every client — this fails first, instead of the mobile team finding out.
    """
    committed = json.loads(SPEC_PATH.read_text())
    assert build_spec() == committed, (
        "docs/openapi.json is stale — run `make openapi` and commit it"
    )


def test_the_spec_is_the_production_api() -> None:
    paths = build_spec()["paths"]
    assert not [p for p in paths if p.startswith(("/dev", "/realms", "/admin"))]
