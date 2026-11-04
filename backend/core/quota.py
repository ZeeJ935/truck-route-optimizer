"""An app-wide daily budget, kept in server memory.

Used to cap uncached Open-Meteo locations per UTC day. The counter lives in the
process, so it resets when the server restarts or the free instance sleeps.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime

from .errors import DailyLimitReached


class DailyQuota:
    def __init__(self, limit: int, clock: Callable[[], float] = time.time):
        if limit <= 0:
            raise ValueError("limit must be positive.")
        self.limit = limit
        self._clock = clock
        self._lock = threading.Lock()
        self._day = self._today()
        self._used = 0

    def _today(self) -> str:
        return datetime.fromtimestamp(self._clock(), UTC).strftime("%Y-%m-%d")

    def _roll(self) -> None:
        today = self._today()
        if today != self._day:
            self._day = today
            self._used = 0

    @property
    def used(self) -> int:
        with self._lock:
            self._roll()
            return self._used

    def ensure_available(self, amount: int) -> None:
        """Raise DailyLimitReached if `amount` more would pass the daily limit."""
        with self._lock:
            self._roll()
            if self._used + amount > self.limit:
                raise DailyLimitReached()

    def consume(self, amount: int) -> None:
        """Record `amount` uses, or raise DailyLimitReached without recording them."""
        if amount <= 0:
            return
        with self._lock:
            self._roll()
            if self._used + amount > self.limit:
                raise DailyLimitReached()
            self._used += amount
