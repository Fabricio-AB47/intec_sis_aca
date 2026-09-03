import unittest
from unittest.mock import MagicMock, patch

import jwt
from fastapi import HTTPException
from starlette.requests import Request

from app.core.config import Settings
from app.core.rate_limit import (
    InMemoryRateLimiter,
    RateLimitExceeded,
    RateLimitUnavailable,
    RedisRateLimiter,
)
from app.core.security import (
    SessionUser,
    create_session_token,
    decode_session_token,
    hash_password,
    get_current_user,
    require_roles,
    verify_password,
)
from app.routers.auth import LoginRequest, _login_rate_keys
from app.services import graph


class SecurityHardeningTests(unittest.TestCase):
    @staticmethod
    def settings() -> Settings:
        return Settings(
            _env_file=None,
            B_NAME="INTECBDD_TEST",
            db_user="test_user",
            db_password="test_password",
            db_host="localhost",
            session_secret="test-session-secret-with-more-than-32-characters",
            auth_legacy_plaintext_enabled=False,
        )

    @staticmethod
    def user(role: str = "ADMINISTRADOR") -> SessionUser:
        return SessionUser(
            login="persona@example.edu.ec",
            nombres="Persona de prueba",
            rol=role,
            cedula="1724036536",
        )

    def test_password_hash_is_not_plaintext_and_verifies(self) -> None:
        password = "A-secure-test-password-42"
        encoded = hash_password(password)

        self.assertNotEqual(encoded, password)
        self.assertTrue(encoded.startswith("$argon2"))
        self.assertTrue(verify_password(password, encoded))
        self.assertFalse(verify_password("incorrect", encoded))

    def test_session_requires_issuer_audience_and_type(self) -> None:
        settings = self.settings()
        with patch("app.core.security.get_settings", return_value=settings):
            token = create_session_token(self.user())
            decoded = decode_session_token(token)

        self.assertEqual(decoded.login, "persona@example.edu.ec")

    def test_legacy_session_without_required_claims_is_rejected(self) -> None:
        settings = self.settings()
        token = jwt.encode(
            {"sub": "persona@example.edu.ec", "rol": "ADMINISTRADOR"},
            settings.signing_secret,
            algorithm="HS256",
        )

        with (
            patch("app.core.security.get_settings", return_value=settings),
            self.assertRaises(HTTPException) as context,
        ):
            decode_session_token(token)

        self.assertEqual(context.exception.status_code, 401)

    def test_admin_role_check_does_not_expand_to_finance(self) -> None:
        dependency = require_roles("ADMINISTRADOR", "ACADEMICO", "RECTOR")

        with self.assertRaises(HTTPException) as context:
            dependency(current_user=self.user("FINANCIERO"))

        self.assertEqual(context.exception.status_code, 403)

    def test_rate_limiter_blocks_after_limit(self) -> None:
        limiter = InMemoryRateLimiter()
        limiter.consume("client", limit=2, window_seconds=60)
        limiter.consume("client", limit=2, window_seconds=60)

        with self.assertRaises(RateLimitExceeded):
            limiter.consume("client", limit=2, window_seconds=60)

    def test_rate_limiter_bounds_memory(self) -> None:
        limiter = InMemoryRateLimiter(max_entries=100)
        for index in range(150):
            limiter.consume(f"client-{index}", limit=2, window_seconds=60)

        self.assertLessEqual(len(limiter._entries), 100)

    def test_redis_rate_limiter_uses_atomic_counter(self) -> None:
        client = MagicMock()
        client.eval.return_value = [3, 42]
        limiter = RedisRateLimiter(client, prefix="test")

        with self.assertRaises(RateLimitExceeded) as context:
            limiter.consume("client", limit=2, window_seconds=60)

        self.assertEqual(context.exception.retry_after, 42)
        self.assertEqual(client.eval.call_count, 1)

    def test_redis_rate_limiter_fails_closed_when_store_is_unavailable(self) -> None:
        import redis

        client = MagicMock()
        client.ttl.side_effect = redis.RedisError("unavailable")
        limiter = RedisRateLimiter(client, prefix="test")

        with self.assertRaises(RateLimitUnavailable):
            limiter.check("client", limit=2, window_seconds=60)

    def test_account_rate_limit_is_shared_across_source_ips(self) -> None:
        first_request = Request({"type": "http", "client": ("192.0.2.10", 5000)})
        second_request = Request({"type": "http", "client": ("198.51.100.20", 5000)})

        first_ip, first_account = _login_rate_keys(first_request, "Persona@Example.edu.ec")
        second_ip, second_account = _login_rate_keys(second_request, "persona@example.edu.ec")

        self.assertNotEqual(first_ip, second_ip)
        self.assertEqual(first_account, second_account)

    def test_login_payload_has_defensive_length_limits(self) -> None:
        with self.assertRaises(ValueError):
            LoginRequest(login="a" * 255, password="valid")
        with self.assertRaises(ValueError):
            LoginRequest(login="valid", password="a" * 1025)

    def test_current_user_reuses_session_validated_by_middleware(self) -> None:
        settings = self.settings()
        user = self.user()
        request = Request(
            {
                "type": "http",
                "headers": [
                    (
                        b"cookie",
                        f"{settings.session_cookie_name}=validated-token".encode("ascii"),
                    )
                ],
            }
        )
        request.state.session_user = user

        with (
            patch("app.core.security.get_settings", return_value=settings),
            patch("app.core.security.decode_session_token") as decode,
        ):
            current = get_current_user(request)

        self.assertIs(current, user)
        decode.assert_not_called()

    def test_revoked_session_token_is_rejected(self) -> None:
        settings = self.settings()
        with (
            patch("app.core.security.get_settings", return_value=settings),
            patch("app.core.security.session_revocations") as revocations,
        ):
            token = create_session_token(self.user())
            revocations.is_revoked.return_value = True

            with self.assertRaises(HTTPException) as context:
                decode_session_token(token)

        self.assertEqual(context.exception.status_code, 401)

    def test_graph_http_client_is_reused(self) -> None:
        previous_client = graph._GRAPH_HTTP_CLIENT
        graph._GRAPH_HTTP_CLIENT = None
        created_client = MagicMock()
        try:
            with patch.object(graph.httpx, "Client", return_value=created_client) as client_factory:
                first = graph._graph_http_client()
                second = graph._graph_http_client()

            self.assertIs(first, second)
            client_factory.assert_called_once()
        finally:
            graph._close_graph_http_client()
            graph._GRAPH_HTTP_CLIENT = previous_client


if __name__ == "__main__":
    unittest.main()
