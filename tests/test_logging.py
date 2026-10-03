"""Logs are ECS JSON unless LOG_JSON=false.

create_app once passed json_logs=not settings.is_dev, so dev logs were never ECS.
(The other cause found then — the `uvicorn` CLI's own logging config — is fixed in
py-common 0.3.0 and is py-common's to test.)
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from py_common.logging import get_logger

import src.__main__ as entry
from src.config import Settings, get_settings
from src.main import create_app

ECS_CORE = {"@timestamp", "log.level", "message", "ecs.version"}


def test_logs_are_ecs_json_by_default(
    settings: Settings, capsys: pytest.CaptureFixture[str]
) -> None:
    assert settings.log_json is True
    create_app(settings)  # configures logging, against the captured stdout
    capsys.readouterr()

    get_logger("tests.probe").info("probe_event", user_id="kc-1")
    line = capsys.readouterr().out.strip().splitlines()[-1]

    record = json.loads(line)
    assert record.keys() >= ECS_CORE
    assert record["message"] == "probe_event"
    # ECS names the field log.logger (py-common >= 0.3.0; it was a bare `logger`).
    assert record["log"]["logger"] == "tests.probe"
    assert "logger" not in record
    assert record["service"]["name"] == "user-profile-service"


def test_entry_point_serves_the_app_from_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, Any] = {}

    def fake_run(app: str, server: object, **kwargs: Any) -> None:
        calls.update(app=app, server=server, kwargs=kwargs)

    monkeypatch.setattr(entry, "run_from_settings", fake_run)
    entry.main(["--reload"])

    assert calls["app"] == "src.main:app"
    assert calls["server"] == get_settings().server  # SERVER__HOST / SERVER__PORT
    assert calls["kwargs"]["reload"] is True
