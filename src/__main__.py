"""Run the service: ``python -m src`` (``--reload`` to restart on changes).

The one place the server is configured: host, port and workers come from
``SERVER__*`` settings, the same way everywhere. The bare ``uvicorn`` CLI ignores them
and binds 127.0.0.1 by default — unreachable from outside a container.

Logging no longer depends on how the process starts: up to py-common 0.2.1 the CLI's
own logging config sent uvicorn's lines past the ECS formatter (8 of 19 lines plain
text); since 0.3.0 ``setup_logging`` adopts uvicorn's loggers. Measured 2026-09-28:
18 of 18 lines ECS through either the CLI or this entry point.
"""

from __future__ import annotations

import sys

from py_common.runtime import run_from_settings

from src.config import get_settings


def main(argv: list[str] | None = None) -> None:
    args = sys.argv[1:] if argv is None else argv
    # Host and port come from SERVER__HOST / SERVER__PORT (py-common ServerSettings).
    run_from_settings("src.main:app", get_settings().server, reload="--reload" in args)


if __name__ == "__main__":
    main()
