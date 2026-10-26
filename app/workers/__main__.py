"""Process queued jobs until interrupted.

python -m app.workers
"""

from __future__ import annotations

import logging
import signal
import threading
import time
import uuid

from app.db.session import get_session_factory
from app.workers.health import HEARTBEAT_INTERVAL, record_poll
from app.workers.runner import run_available

logger = logging.getLogger("reconai.jobs")
_stop = False


def _request_stop(signum: int, _frame: object) -> None:
    del signum
    global _stop
    _stop = True


def _beat(worker_id: str) -> None:
    session = get_session_factory()()
    try:
        record_poll(session, worker_id)
    except Exception:
        logger.warning("worker_heartbeat_failed worker_id=%s", worker_id)
    finally:
        session.close()


def _heartbeat(worker_id: str) -> None:
    while not _stop:
        _beat(worker_id)
        deadline = time.monotonic() + HEARTBEAT_INTERVAL.total_seconds()
        while not _stop and time.monotonic() < deadline:
            time.sleep(0.2)


def main() -> None:
    signal.signal(signal.SIGINT, _request_stop)
    signal.signal(signal.SIGTERM, _request_stop)
    worker_id = f"worker-{uuid.uuid4().hex[:8]}"
    threading.Thread(
        target=_heartbeat,
        args=(worker_id,),
        name="worker-heartbeat",
        daemon=True,
    ).start()
    while not _stop:
        session = get_session_factory()()
        try:
            claimed = run_available(session, worker_id=worker_id, limit=1)
        finally:
            session.close()
        if _stop:
            break
        time.sleep(0.5 if claimed else 2)


if __name__ == "__main__":
    main()
