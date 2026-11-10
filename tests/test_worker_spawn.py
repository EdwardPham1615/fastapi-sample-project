"""A real prefork worker with spawned children, as on macOS (~7 s). Checks that
the task runs (needs ``FORKED_BY_MULTIPROCESSING``) and that the child's log reaches
stdout (needs Celery's stdout redirect off)."""

from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import IO

ROOT = Path(__file__).resolve().parents[1]
SUCCEEDED = re.compile(r"probe\.touch\[[0-9a-f-]+\] succeeded")


def probe(
    command: str, env: dict[str, str], log: IO[bytes] | None = None
) -> subprocess.Popen[bytes]:
    # Fixed argv: this interpreter, our module, "worker" or "send".
    return subprocess.Popen(  # noqa: S603
        [sys.executable, "-m", "tests.worker_probe", command],
        cwd=ROOT,
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT if log else None,
    )


def test_spawned_worker_runs_task_and_logs_it(tmp_path: Path) -> None:
    env = {**os.environ, "PROBE_DIR": str(tmp_path), "PYTHONPATH": str(ROOT)}
    # The child must prove the module sets it, not inherit it from pytest.
    env.pop("FORKED_BY_MULTIPROCESSING", None)
    log_path = tmp_path / "worker.log"

    with log_path.open("wb") as log:
        worker = probe("worker", env, log)
        try:
            assert probe("send", env).wait(timeout=30) == 0
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                if (tmp_path / "flag").exists() and SUCCEEDED.search(log_path.read_text()):
                    break
                time.sleep(0.2)
        finally:
            worker.terminate()
            try:
                worker.wait(timeout=30)
            except subprocess.TimeoutExpired:
                worker.kill()

    output = log_path.read_text()
    assert (tmp_path / "flag").exists(), f"task did not run:\n{output[-2000:]}"
    assert SUCCEEDED.search(output), f"task ran but its log line is missing:\n{output[-2000:]}"
