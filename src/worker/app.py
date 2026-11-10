"""The worker: py-common's Celery app with this service's task and schedule.

Cheap to import (connects to nothing), so the API may import this module to send a
task; it must never import ``src.worker.tasks`` (tests/test_boundaries.py). Run it with
``make worker`` and ``make beat``.

Everything a worker gets wrong quietly is py-common's ``Worker``: spawned pool children
on macOS, child logs swallowed by Celery's stdout redirect, tracing per process, late
acknowledgement. Late ack means a task in a killed worker runs again, so **every task
must be safe to run twice**.
"""

from __future__ import annotations

from celery import signals
from celery.schedules import crontab
from py_common.worker import Worker, WorkerRuntime

from src.config import Settings, check_runtime_settings, get_settings

SYNC_USERS = "users.sync"

settings = get_settings()


@signals.worker_init.connect
@signals.beat_init.connect
def check_settings_on_start(**_: object) -> None:
    """The API's startup check, for the worker and beat too.

    Raises SystemExit, not the check's RuntimeError: Celery's Signal.send catches any
    Exception a receiver raises and the process starts anyway. Measured on Celery 5.6.3,
    a staging worker on dev values reached "ready" and its output showed no error at all.
    SystemExit is a BaseException, which Signal.send lets through.
    """
    try:
        check_runtime_settings(settings)
    except RuntimeError as exc:
        raise SystemExit(f"refusing to start: {exc}") from exc


def make_runtime(settings: Settings) -> WorkerRuntime:
    # Imported here: a process that only sends tasks must not build the worker's clients.
    from src.worker.runtime import Runtime

    return Runtime(settings)


worker = Worker(
    "user_profile",
    # Logs and traces are named <app_name>-worker and <app_name>-beat.
    settings,
    runtime_factory=make_runtime,
    include=["src.worker.tasks"],
    beat_schedule={
        "users-sync-nightly": {"task": SYNC_USERS, "schedule": crontab(hour=2, minute=0)},
    },
    json_logs=settings.log_json,
)

# What `celery -A src.worker.app` runs.
celery_app = worker.celery
