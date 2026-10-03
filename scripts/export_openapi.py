"""Write docs/openapi.json — the reviewed HTTP contract of this service.

    make openapi

Needs no running server and no database. Postman imports the file directly
(OpenAPI 3.1 is supported), or Spec Hub can track it in the Git repository.
"""

from __future__ import annotations

from src.openapi import SPEC_PATH, write_spec

if __name__ == "__main__":
    write_spec()
    print(f"wrote {SPEC_PATH}")
