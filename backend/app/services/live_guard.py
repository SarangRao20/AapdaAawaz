"""Cost limits for the public Awaaz Live WebSocket.

A live call spends Gnani credits while it runs and the caller app has no login, so a public
connection is capped instead of open-ended: one call at a time per address, a global ceiling, and
a rolling hourly quota per address. Signed-in dashboard calls skip these limits — the admin chose
to open them. The counters live in memory on purpose: a restart is a clean slate, and a second
worker would need a shared store before it could enforce anything anyway.
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable

WINDOW_S = 60 * 60


class LiveGuard:
    def __init__(self, max_concurrent: int, max_per_ip: int, max_per_hour: int,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.max_concurrent = max(1, max_concurrent)
        self.max_per_ip = max(1, max_per_ip)
        self.max_per_hour = max(1, max_per_hour)
        self._clock = clock
        self._lock = threading.Lock()
        self._active: dict[str, int] = defaultdict(int)
        self._starts: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, address: str) -> str | None:
        """Take a slot for `address`. None means go ahead; otherwise the reason to refuse."""
        with self._lock:
            now = self._clock()
            if sum(self._active.values()) >= self.max_concurrent:
                return "busy"
            if self._active[address] >= self.max_per_ip:
                return "already_calling"
            starts = self._starts[address]
            while starts and now - starts[0] >= WINDOW_S:
                starts.popleft()
            if len(starts) >= self.max_per_hour:
                return "hourly_limit"
            self._active[address] += 1
            starts.append(now)
            return None

    def release(self, address: str) -> None:
        with self._lock:
            active = self._active.get(address, 0) - 1
            if active > 0:
                self._active[address] = active
            else:
                self._active.pop(address, None)

    def clear(self) -> None:
        with self._lock:
            self._active.clear()
            self._starts.clear()

    def snapshot(self) -> dict:
        with self._lock:
            return {"active": sum(self._active.values()), "max_concurrent": self.max_concurrent}


__all__ = ["LiveGuard", "WINDOW_S"]
