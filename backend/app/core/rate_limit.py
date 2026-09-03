from __future__ import annotations

import hashlib
from collections import deque
from dataclasses import dataclass, field
from threading import Lock
from time import monotonic
from typing import Protocol

import redis

from app.core.config import get_settings


@dataclass
class _RateEntry:
    attempts: deque[float] = field(default_factory=deque)
    blocked_until: float = 0.0


class RateLimitExceeded(Exception):
    def __init__(self, retry_after: int) -> None:
        super().__init__("Límite de solicitudes excedido")
        self.retry_after = max(int(retry_after), 1)


class RateLimitUnavailable(RuntimeError):
    pass


class RateLimiter(Protocol):
    def check(self, key: str, *, limit: int, window_seconds: int) -> None: ...

    def record_failure(
        self,
        key: str,
        *,
        limit: int,
        window_seconds: int,
        lockout_seconds: int,
    ) -> None: ...

    def consume(self, key: str, *, limit: int, window_seconds: int) -> None: ...

    def reset(self, key: str) -> None: ...

    def healthcheck(self) -> None: ...


class InMemoryRateLimiter:
    """Limitador acotado para desarrollo y ejecución en un solo proceso."""

    def __init__(self, *, max_entries: int = 10_000) -> None:
        self._entries: dict[str, _RateEntry] = {}
        self._lock = Lock()
        self._max_entries = max(max_entries, 100)

    def _ensure_capacity(self) -> None:
        if len(self._entries) < self._max_entries:
            return
        oldest_key = next(iter(self._entries), None)
        if oldest_key is not None:
            self._entries.pop(oldest_key, None)

    @staticmethod
    def _prune(entry: _RateEntry, now: float, window_seconds: int) -> None:
        threshold = now - window_seconds
        while entry.attempts and entry.attempts[0] <= threshold:
            entry.attempts.popleft()

    def check(self, key: str, *, limit: int, window_seconds: int) -> None:
        del limit
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

    def healthcheck(self) -> None:
        return None


class RedisRateLimiter:
    """Limitador compartido y atómico para múltiples workers o servidores."""

    _CONSUME_SCRIPT = """
        local count = redis.call('INCR', KEYS[1])
        if count == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end
        local ttl = redis.call('TTL', KEYS[1])
        return {count, ttl}
    """
    _FAILURE_SCRIPT = """
        local blocked_ttl = redis.call('TTL', KEYS[2])
        if blocked_ttl > 0 then return blocked_ttl end
        local count = redis.call('INCR', KEYS[1])
        if count == 1 then redis.call('EXPIRE', KEYS[1], ARGV[2]) end
        if count >= tonumber(ARGV[1]) then
            redis.call('SET', KEYS[2], '1', 'EX', ARGV[3])
            redis.call('DEL', KEYS[1])
            return tonumber(ARGV[3])
        end
        return 0
    """

    def __init__(self, client: redis.Redis, *, prefix: str = "sisaca") -> None:
        self._client = client
        self._prefix = prefix.strip(": ") or "sisaca"

    def _key(self, category: str, key: str) -> str:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return f"{self._prefix}:rate:{category}:{digest}"

    @staticmethod
    def _raise_unavailable(exc: redis.RedisError) -> None:
        raise RateLimitUnavailable("El servicio compartido de límites no está disponible") from exc

    def check(self, key: str, *, limit: int, window_seconds: int) -> None:
        del limit, window_seconds
        try:
            retry_after = int(self._client.ttl(self._key("blocked", key)))
        except redis.RedisError as exc:
            self._raise_unavailable(exc)
        if retry_after > 0:
            raise RateLimitExceeded(retry_after)

    def record_failure(
        self,
        key: str,
        *,
        limit: int,
        window_seconds: int,
        lockout_seconds: int,
    ) -> None:
        try:
            self._client.eval(
                self._FAILURE_SCRIPT,
                2,
                self._key("failures", key),
                self._key("blocked", key),
                limit,
                window_seconds,
                lockout_seconds,
            )
        except redis.RedisError as exc:
            self._raise_unavailable(exc)

    def consume(self, key: str, *, limit: int, window_seconds: int) -> None:
        try:
            result = self._client.eval(
                self._CONSUME_SCRIPT,
                1,
                self._key("consumed", key),
                window_seconds,
            )
            count, ttl = int(result[0]), max(int(result[1]), 1)
        except redis.RedisError as exc:
            self._raise_unavailable(exc)
        except (TypeError, ValueError, IndexError) as exc:
            raise RateLimitUnavailable("Redis devolvió un estado de límite inválido") from exc
        if count > limit:
            raise RateLimitExceeded(ttl)

    def reset(self, key: str) -> None:
        try:
            self._client.delete(
                self._key("failures", key),
                self._key("blocked", key),
                self._key("consumed", key),
            )
        except redis.RedisError as exc:
            self._raise_unavailable(exc)

    def healthcheck(self) -> None:
        try:
            self._client.ping()
        except redis.RedisError as exc:
            self._raise_unavailable(exc)


def _build_rate_limiter() -> RateLimiter:
    settings = get_settings()
    if settings.rate_limit_backend != "redis":
        return InMemoryRateLimiter()
    if settings.rate_limit_redis_url is None:
        raise RuntimeError("RATE_LIMIT_REDIS_URL es obligatorio para usar Redis")
    client = redis.Redis.from_url(
        settings.rate_limit_redis_url.get_secret_value(),
        decode_responses=True,
        socket_connect_timeout=2,
        socket_timeout=2,
        health_check_interval=30,
    )
    try:
        client.ping()
    except redis.RedisError as exc:
        raise RuntimeError("No se pudo conectar con Redis para el rate limiting") from exc
    return RedisRateLimiter(client, prefix=settings.rate_limit_redis_prefix)


rate_limiter = _build_rate_limiter()
