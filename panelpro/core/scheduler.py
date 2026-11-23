"""A small in-process scheduler for panel-internal background jobs.

Jobs run on a daemon thread with a 1-second tick.  Any exception inside a
job is logged and swallowed — internal jobs must never crash the panel.
"""

from __future__ import annotations

import threading
import time
import traceback
from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass
class Job:
    name: str
    fn: Callable[[], None]
    interval: int
    next_run: float = field(default=0.0)


class Scheduler:
    """Restart-safe job runner (owns its own worker thread)."""

    def __init__(self) -> None:
        self.jobs: list[Job] = []
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def register(self, name: str, fn: Callable[[], None], interval: int) -> None:
        with self._lock:
            self.jobs.append(Job(name=name, fn=fn, interval=max(interval, 1)))

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="pp-scheduler")
        self._thread.start()

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            now = time.time()
            with self._lock:
                due = [j for j in self.jobs if now >= j.next_run]
                for job in due:
                    job.next_run = now + job.interval
            for job in due:
                try:
                    job.fn()
                except Exception:
                    traceback.print_exc()
            self._stop_event.wait(1.0)

    @property
    def is_alive(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def stop(self) -> None:
        self._stop_event.set()


SCHEDULER = Scheduler()
