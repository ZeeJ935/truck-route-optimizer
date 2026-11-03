"""A small thread-safe in-memory TTL cache for provider responses."""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from collections.abc import Callable, Hashable
from typing import Any

_MISSING = object()


class TTLCache:
    def __init__(self, ttl_seconds: float, max_entries: int = 1024, clock: Callable[[], float] = time.monotonic):
        if ttl_seconds <= 0 or max_entries <= 0:
            raise ValueError("ttl_seconds and max_entries must be positive.")
        self._ttl = ttl_seconds
        self._max_entries = max_entries
        self._clock = clock
        self._entries: OrderedDict[Hashable, tuple[float, Any]] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: Hashable, default: Any = None) -> Any:
        with self._lock:
            entry = self._entries.get(key, _MISSING)
            if entry is _MISSING:
                return default
            expires_at, value = entry
            if self._clock() >= expires_at:
                del self._entries[key]
                return default
            self._entries.move_to_end(key)
            return value

    def set(self, key: Hashable, value: Any) -> None:
        with self._lock:
            self._entries[key] = (self._clock() + self._ttl, value)
            self._entries.move_to_end(key)
            while len(self._entries) > self._max_entries:
                self._entries.popitem(last=False)

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)
