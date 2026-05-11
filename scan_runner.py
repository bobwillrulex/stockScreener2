"""Shared manual and scheduled scan execution."""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from market_schedule import MARKET_TIMEZONE, next_four_hour_scan_time
from scan_storage import latest_scan_summary, persist_scan_results
from screener import run_scan

LOGGER = logging.getLogger(__name__)


@dataclass
class ScanRuntimeState:
    """In-memory status for the most recent scan execution."""

    last_started_at: str | None = None
    last_finished_at: str | None = None
    last_error: str | None = None
    last_scan_database: dict[str, object] | None = None
    next_scheduled_scan_at: str | None = None
    is_running: bool = False
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def snapshot(self) -> dict[str, object]:
        with self.lock:
            latest_database = latest_scan_summary()
            return {
                "last_started_at": self.last_started_at,
                "last_finished_at": self.last_finished_at,
                "last_error": self.last_error,
                "last_scan_database": self.last_scan_database or latest_database,
                "next_scheduled_scan_at": self.next_scheduled_scan_at,
                "is_running": self.is_running,
            }


STATE = ScanRuntimeState()
_SCAN_LOCK = threading.Lock()


def execute_scan(threshold: float = 0.1, max_workers: int | None = None) -> dict[str, Any]:
    """Run the screener once, persist results, and update runtime status."""
    if max_workers is None:
        max_workers = int(os.getenv("SCAN_WORKERS", "4"))

    if not _SCAN_LOCK.acquire(blocking=False):
        raise RuntimeError("A scan is already running.")

    started_at = datetime.now(MARKET_TIMEZONE).isoformat(timespec="seconds")
    with STATE.lock:
        STATE.is_running = True
        STATE.last_started_at = started_at
        STATE.last_error = None

    try:
        results = run_scan(threshold=threshold, max_workers=max_workers)
        persisted_scan = persist_scan_results(results)
        finished_at = datetime.now(MARKET_TIMEZONE).isoformat(timespec="seconds")
        persisted_dict = persisted_scan.as_dict()
        with STATE.lock:
            STATE.last_finished_at = finished_at
            STATE.last_scan_database = persisted_dict
        return {"results": results, "scan_database": persisted_dict}
    except Exception as exc:
        with STATE.lock:
            STATE.last_error = str(exc)
        raise
    finally:
        with STATE.lock:
            STATE.is_running = False
        _SCAN_LOCK.release()


def _scheduled_scan_loop(threshold: float) -> None:
    while True:
        next_scan_at = next_four_hour_scan_time()
        with STATE.lock:
            STATE.next_scheduled_scan_at = next_scan_at.isoformat(timespec="seconds")
        time.sleep(max(0.0, (next_scan_at - datetime.now(MARKET_TIMEZONE)).total_seconds()))
        try:
            execute_scan(threshold=threshold)
        except Exception as exc:  # noqa: BLE001 - keep scheduler alive after scan failures
            LOGGER.exception("Scheduled scan failed: %s", exc)


def start_scheduled_scans(threshold: float | None = None) -> threading.Thread:
    """Start the daemon scheduler that scans at NYSE 4-hour candle closes."""
    scan_threshold = threshold if threshold is not None else float(os.getenv("SCAN_THRESHOLD", "0.1"))
    thread = threading.Thread(
        target=_scheduled_scan_loop,
        args=(scan_threshold,),
        name="nyse-4h-scan-scheduler",
        daemon=True,
    )
    thread.start()
    return thread
