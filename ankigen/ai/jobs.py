"""Background jobs the UI polls, so long AI calls never block the window."""

from __future__ import annotations

import threading
import time
import uuid
from collections.abc import Callable
from typing import Any

from .generate import Progress
from .http import AiError, Cancelled

KEEP_FINISHED = 20


class Job:
    def __init__(self, work: Callable[[Job], None]) -> None:
        self.id = uuid.uuid4().hex[:12]
        self.progress = Progress()
        self.cancel = threading.Event()
        self.state = "running"  # running | done | error | cancelled
        self.error = ""
        self.started = time.monotonic()
        self.finished: float | None = None
        self.lock = threading.Lock()
        self._thread = threading.Thread(target=self._run, args=(work,), daemon=True)

    def start(self) -> Job:
        self._thread.start()
        return self

    def _run(self, work: Callable[[Job], None]) -> None:
        try:
            work(self)
            state = "cancelled" if self.cancel.is_set() else "done"
        except Cancelled:
            state = "cancelled"
        except AiError as e:
            state, self.error = "error", str(e)
        except Exception as e:  # noqa: BLE001 - shown in the UI
            state, self.error = "error", f"{type(e).__name__}: {e}"
        with self.lock:
            self.state = state
            self.finished = time.monotonic()

    def snapshot(self, since: int = 0) -> dict[str, Any]:
        """Status plus the cards from index ``since`` on (the UI asks for new ones only)."""
        with self.lock:
            p = self.progress
            end = (self.finished or time.monotonic()) - self.started
            return {
                "id": self.id,
                "state": self.state,
                "error": self.error,
                "done": p.done,
                "total": p.total,
                "message": p.message,
                "elapsed": round(end, 1),
                "cards": p.cards[since:],
                "card_count": len(p.cards),
                "warnings": list(p.warnings),
                "pages": {str(n): t for n, t in sorted(p.pages.items())},
            }


class Jobs:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}

    def start(self, work: Callable[[Job], None]) -> Job:
        self._prune()
        job = Job(work)
        self._jobs[job.id] = job
        return job.start()

    def get(self, job_id: str) -> Job:
        job = self._jobs.get(job_id)
        if job is None:
            raise KeyError("That generation job no longer exists")
        return job

    def _prune(self) -> None:
        finished = [j for j in self._jobs.values() if j.finished is not None]
        for j in sorted(finished, key=lambda j: j.finished or 0)[:-KEEP_FINISHED]:
            self._jobs.pop(j.id, None)
