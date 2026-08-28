from collections import deque
from dataclasses import dataclass, field
from threading import Lock
from time import monotonic


@dataclass
class _RateEntry:
    attempts: deque[float] = field(default_factory=deque)
    blocked_until: float = 0.0


class RateLimitExceeded(Exception):
    def __init__(self, retry_after: int) -> None:
        super().__init__("Límite de solicitudes excedido")
        self.retry_after = max(int(retry_after), 1)


class InMemoryRateLimiter:
    """Límite defensivo local; en clúster debe sustituirse por un almacén compartido."""

    def __init__(self, *, max_entries: int = 10_000) -> None:
        self._entries: dict[str, _RateEntry] = {}
        self._lock = Lock()
        self._max_entries = max(max_entries, 100)

    def _ensure_capacity(self) -> None:
        if len(self._entries) < self._max_entries:
            return
        # El diccionario conserva el orden de inserción; se limita el uso de
        # memoria ante intentos distribuidos con identificadores aleatorios.
        oldest_key = next(iter(self._entries), None)
        if oldest_key is not None:
            self._entries.pop(oldest_key, None)

    @staticmethod
    def _prune(entry: _RateEntry, now: float, window_seconds: int) -> None:
        threshold = now - window_seconds
        while entry.attempts and entry.attempts[0] <= threshold:
            entry.attempts.popleft()

    def check(self, key: str, *, limit: int, window_seconds: int) -> None:
        now = monotonic()
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return
            self._prune(entry, now, window_seconds)
            if entry.blocked_until > now:
                raise RateLimitExceeded(int(entry.blocked_until - now) + 1)
            if not entry.attempts:
                self._entries.pop(key, None)

    def record_failure(
        self,
        key: str,
        *,
        limit: int,
        window_seconds: int,
        lockout_seconds: int,
    ) -> None:
        now = monotonic()
        with self._lock:
            if key not in self._entries:
                self._ensure_capacity()
            entry = self._entries.setdefault(key, _RateEntry())
            self._prune(entry, now, window_seconds)
            entry.attempts.append(now)
            if len(entry.attempts) >= limit:
                entry.blocked_until = max(entry.blocked_until, now + lockout_seconds)

    def consume(self, key: str, *, limit: int, window_seconds: int) -> None:
        now = monotonic()
        with self._lock:
            if key not in self._entries:
                self._ensure_capacity()
            entry = self._entries.setdefault(key, _RateEntry())
            self._prune(entry, now, window_seconds)
            if entry.blocked_until > now:
                raise RateLimitExceeded(int(entry.blocked_until - now) + 1)
            if len(entry.attempts) >= limit:
                retry_after = int(window_seconds - (now - entry.attempts[0])) + 1
                raise RateLimitExceeded(retry_after)
            entry.attempts.append(now)

    def reset(self, key: str) -> None:
        with self._lock:
            self._entries.pop(key, None)


rate_limiter = InMemoryRateLimiter()
