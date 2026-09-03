from __future__ import annotations

import hashlib
from threading import Lock
from time import time

import redis

from app.core.config import get_settings


class SessionRevocationUnavailable(RuntimeError):
    pass


class SessionRevocationStore:
    def __init__(self) -> None:
        settings = get_settings()
        self._enabled = settings.session_revocation_enabled
        self._prefix = settings.rate_limit_redis_prefix.strip(": ") or "sisaca"
        self._memory: dict[str, int] = {}
        self._lock = Lock()
        self._redis: redis.Redis | None = None
        if self._enabled and settings.rate_limit_backend == "redis":
            if settings.rate_limit_redis_url is None:
                raise RuntimeError("RATE_LIMIT_REDIS_URL es obligatorio para revocar sesiones")
            self._redis = redis.Redis.from_url(
                settings.rate_limit_redis_url.get_secret_value(),
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2,
                health_check_interval=30,
            )

    def _key(self, session_id: str) -> str:
        digest = hashlib.sha256(session_id.encode("utf-8")).hexdigest()
        return f"{self._prefix}:session:revoked:{digest}"

    def is_revoked(self, session_id: str) -> bool:
        if not self._enabled or not session_id:
            return False
        if self._redis is not None:
            try:
                return bool(self._redis.exists(self._key(session_id)))
            except redis.RedisError as exc:
                raise SessionRevocationUnavailable(
                    "No se pudo verificar la vigencia de la sesión"
                ) from exc
        now = int(time())
        with self._lock:
            expired = [key for key, expires_at in self._memory.items() if expires_at <= now]
            for key in expired:
                self._memory.pop(key, None)
            return session_id in self._memory

    def revoke(self, session_id: str, expires_at: int) -> None:
        if not self._enabled or not session_id:
            return
        ttl = max(int(expires_at) - int(time()), 1)
        if self._redis is not None:
            try:
                self._redis.set(self._key(session_id), "1", ex=ttl)
                return
            except redis.RedisError as exc:
                raise SessionRevocationUnavailable(
                    "No se pudo revocar la sesión"
                ) from exc
        with self._lock:
            self._memory[session_id] = int(time()) + ttl

    def healthcheck(self) -> None:
        if self._redis is None:
            return
        try:
            self._redis.ping()
        except redis.RedisError as exc:
            raise SessionRevocationUnavailable(
                "No se pudo comprobar el almacén de sesiones"
            ) from exc


session_revocations = SessionRevocationStore()
