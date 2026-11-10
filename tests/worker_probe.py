"""A real Celery worker and one probe task, run in subprocesses by
tests/test_worker_spawn.py.

    PROBE_DIR=<dir> python -m tests.worker_probe worker   # prefork worker, spawn children
    PROBE_DIR=<dir> python -m tests.worker_probe send     # queue probe.touch

Uses kombu's filesystem transport in PROBE_DIR, so no Redis is needed.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from py_common.worker import WorkerRuntime

from src.worker.app import celery_app, worker

BOX = Path(os.environ["PROBE_DIR"])
FLAG = "flag"

celery_app.conf.broker_url = "filesystem://"
celery_app.conf.broker_transport_options = {
    "data_folder_in": str(BOX / "queue"),
    "data_folder_out": str(BOX / "queue"),
    "processed_folder": str(BOX / "processed"),
    "store_processed": False,
    # Default is ./control, which would leave exchange files in the repo.
    "control_folder": str(BOX / "control"),
}


@worker.task("probe.touch", max_retries=0)
async def touch(runtime: WorkerRuntime, name: str) -> str:
    (BOX / name).write_text("ok")
    return name


def main(command: str) -> None:
    (BOX / "queue").mkdir(exist_ok=True)
    (BOX / "processed").mkdir(exist_ok=True)
    if command == "send":
        touch.delay(FLAG)
        return
    import billiard

    # macOS's default, forced so Linux CI exercises the same path.
    billiard.set_start_method("spawn", force=True)
    celery_app.worker_main(
        [
            "worker",
            "--include",
            "tests.worker_probe",
            "--queues",
            # Celery's default queue: src.worker.app sets no other.
            "celery",
            "--concurrency",
            "1",
            "--loglevel",
            "INFO",
            "--without-mingle",
            "--without-gossip",
            "--without-heartbeat",
        ]
    )


if __name__ == "__main__":
    main(sys.argv[1])
