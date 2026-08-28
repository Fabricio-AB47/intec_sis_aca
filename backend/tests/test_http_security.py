import unittest
from uuid import UUID

from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app.core.security import SessionUser, create_session_token, get_current_user
from app.main import app, settings


PUBLIC_API_PATHS = {
    "/api/auth/login",
    "/api/auth/logout",
    "/api/auth/microsoft/callback",
    "/api/evaluacion-docente/questions",
    "/api/evaluacion-docente/identity/{cedula}",
    "/api/evaluacion-docente/student/{cedula}",
    "/api/evaluacion-docente/teacher/{cedula}",
    "/api/evaluacion-docente/evaluate",
    "/api/evaluacion-docente/teacher/evaluate",
}


def _dependency_calls(route: APIRoute) -> set[object]:
    calls: set[object] = set()

    def collect(dependency) -> None:
        if dependency.call is not None:
            calls.add(dependency.call)
        for child in dependency.dependencies:
            collect(child)

    collect(route.dependant)
    return calls


class HttpSecurityTests(unittest.TestCase):
    def test_sensitive_api_routes_require_an_authenticated_session(self) -> None:
        unprotected: list[str] = []
        for route in app.routes:
            if not isinstance(route, APIRoute) or not route.path.startswith("/api/"):
                continue
            if route.path in PUBLIC_API_PATHS:
                continue
            if get_current_user not in _dependency_calls(route):
                unprotected.append(f"{','.join(sorted(route.methods or []))} {route.path}")

        self.assertEqual(unprotected, [], "Rutas API sin autenticación: " + "; ".join(unprotected))

    def test_unauthenticated_session_endpoint_is_rejected(self) -> None:
        with TestClient(app) as client:
            response = client.get("/api/auth/me")

        self.assertEqual(response.status_code, 401)

    def test_security_headers_and_safe_request_id_are_returned(self) -> None:
        with TestClient(app) as client:
            response = client.get("/", headers={"X-Request-ID": "identificador no permitido"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(response.headers["X-Frame-Options"], "DENY")
        self.assertEqual(response.headers["X-Permitted-Cross-Domain-Policies"], "none")
        self.assertEqual(response.headers["Referrer-Policy"], "no-referrer")
        self.assertNotEqual(response.headers["X-Request-ID"], "identificador no permitido")
        UUID(response.headers["X-Request-ID"])

    def test_cross_site_request_with_session_cookie_is_rejected(self) -> None:
        token = create_session_token(
            SessionUser(
                login="security-test@example.edu.ec",
                nombres="Prueba de seguridad",
                rol="ADMINISTRADOR",
            )
        )
        with TestClient(app) as client:
            client.cookies.set(settings.session_cookie_name, token)
            response = client.post(
                "/api/auth/select-profile",
                json={"rol": "ADMINISTRADOR"},
                headers={"Origin": "https://attacker.invalid", "Sec-Fetch-Site": "cross-site"},
            )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "Solicitud rechazada por la política de origen.")


if __name__ == "__main__":
    unittest.main()
