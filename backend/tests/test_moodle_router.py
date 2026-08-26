import unittest
from types import SimpleNamespace
from unittest.mock import patch

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.core.security import SessionUser
from app.integrations.moodle.client import MoodleFileStream
from app.integrations.moodle.exceptions import (
    MoodleApiError,
    MoodleConfigurationError,
    MoodleConnectionError,
    MoodleDisabledError,
    MoodleInstitutionalEmailNotFoundError,
    MoodleResultLimitExceededError,
    MoodleTimeoutError,
    MoodleWriteDisabledError,
)
from app.routers.moodle import (
    _MOODLE_ALERTS_ACCESS,
    _MOODLE_COURSES_ACCESS,
    _MOODLE_GRADES_ACCESS,
    _MOODLE_RESOURCES_ACCESS,
    _MOODLE_STATUS_ACCESS,
    _MOODLE_USERS_ACCESS,
    get_moodle_grade_alert_service,
    get_moodle_grade_sync_service,
    get_moodle_read_service,
    router,
)


def administrative_user() -> SessionUser:
    return SessionUser(
        login="admin@example.edu",
        nombres="Administrador de prueba",
        email="admin@example.edu",
        rol="ADMINISTRADOR",
    )


class FakeMoodleService:
    async def get_status(self):
        return {"enabled": True, "configured": True, "reachable": True, "site_name": "Moodle"}

    async def list_users(self, **kwargs):
        return {
            "items": [{"id": 1, "username": "usuario"}],
            "pagination": {"page": kwargs["page"], "page_size": kwargs["page_size"], "total_items": 1},
            "source": {"cached": False, "moodle_function": "core_user_get_users"},
            "received": kwargs,
        }

    async def list_courses(self, **kwargs):
        return {
            "items": [{"id": 8, "fullname": "Curso"}],
            "pagination": {"page": kwargs["page"], "page_size": kwargs["page_size"], "total_items": 1},
            "source": {"cached": False, "moodle_function": "core_course_get_courses_by_field"},
            "received": kwargs,
        }

    async def get_course_resources(self, course_id: int, **kwargs):
        return {
            "course": {"id": course_id, "fullname": "Curso"},
            "sections": [{"id": 1, "name": "Unidad 1", "modules": []}],
            "totals": {"sections": 1, "modules": 0, "files": 0, "visible_modules": 0},
            "source": {"cached": False, "moodle_function": "core_course_get_contents"},
            "received": kwargs,
        }

    async def set_user_active(self, user_id: int, *, active: bool):
        return {
            "ok": True,
            "changed": True,
            "message": "La cuenta se actualizó correctamente.",
            "user": {"id": user_id, "email": "ana@intec.edu.ec", "status": "ACTIVO" if active else "SUSPENDIDO"},
            "institutional_validation": {
                "validated": True,
                "codigo_estud": 10,
                "estudiante": "Ana López",
                "correo_intec": "ana@intec.edu.ec",
            },
            "audit_recorded": True,
        }

    async def set_section_visibility(self, course_id: int, section_id: int, *, visible: bool):
        return {
            "ok": True,
            "changed": True,
            "message": "La sección se actualizó correctamente.",
            "section": {"id": section_id, "course_id": course_id, "visible": visible},
            "audit_recorded": True,
        }

    async def set_section_name(self, course_id: int, section_id: int, *, name: str):
        return {
            "ok": True,
            "changed": True,
            "message": "El nombre de la sección se actualizó correctamente.",
            "section": {
                "id": section_id,
                "course_id": course_id,
                "name": name,
            },
            "audit_recorded": True,
        }

    async def open_course_resource_file(self, course_id: int, module_id: int, file_index: int):
        request = httpx.Request("GET", "https://moodle.example.edu/webservice/pluginfile.php/guia.pdf")
        response = httpx.Response(
            200,
            content=b"contenido-del-recurso",
            headers={"content-type": "application/pdf"},
            request=request,
        )
        return (
            {
                "course_id": course_id,
                "module_id": module_id,
                "content": {"filename": f"guía-{file_index}.pdf", "mimetype": "application/pdf"},
            },
            MoodleFileStream(response=response),
        )


class FailingMoodleService(FakeMoodleService):
    def __init__(self, error: Exception) -> None:
        self.error = error

    async def get_status(self):
        raise self.error

    async def set_user_active(self, user_id: int, *, active: bool):
        raise self.error


class FakeMoodleGradeSyncService:
    async def preview(self, **kwargs):
        return {"received": kwargs}

    async def apply(self, **kwargs):
        return {"received": kwargs}


class FakeMoodleGradeAlertService:
    def __init__(self) -> None:
        self.invalidations = 0

    def invalidate_cache(self) -> None:
        self.invalidations += 1

    async def list_alerts(self, user, *, refresh: bool = False):
        return {"role": user.rol, "refresh": refresh, "summary": {"total": 0}}


class MoodleRouterTests(unittest.TestCase):
    def _client(
        self,
        service=None,
        access_dependency=None,
        grade_service=None,
        alert_service=None,
    ) -> TestClient:
        app = FastAPI()
        app.include_router(router)
        access = access_dependency or administrative_user
        app.dependency_overrides[_MOODLE_STATUS_ACCESS] = access
        app.dependency_overrides[_MOODLE_USERS_ACCESS] = access
        app.dependency_overrides[_MOODLE_COURSES_ACCESS] = access
        app.dependency_overrides[_MOODLE_RESOURCES_ACCESS] = access
        app.dependency_overrides[_MOODLE_GRADES_ACCESS] = access
        app.dependency_overrides[_MOODLE_ALERTS_ACCESS] = access
        app.dependency_overrides[get_moodle_read_service] = lambda: service or FakeMoodleService()
        app.dependency_overrides[get_moodle_grade_sync_service] = (
            lambda: grade_service or FakeMoodleGradeSyncService()
        )
        app.dependency_overrides[get_moodle_grade_alert_service] = (
            lambda: alert_service or FakeMoodleGradeAlertService()
        )
        return TestClient(app)

    def test_status_endpoint(self) -> None:
        with self._client() as client:
            response = client.get("/api/moodle/status")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["reachable"])
        self.assertNotIn("token", response.text.lower())

    def test_users_endpoint_forwards_only_supported_filters(self) -> None:
        with self._client() as client:
            response = client.get(
                "/api/moodle/users",
                params={
                    "page": 2,
                    "page_size": 25,
                    "email": "ana@intec.edu.ec",
                    "state": "active",
                    "auth": "oauth2",
                    "refresh": "true",
                },
            )

        self.assertEqual(response.status_code, 200)
        received = response.json()["received"]
        self.assertEqual(received["page"], 2)
        self.assertEqual(received["email"], "ana@intec.edu.ec")
        self.assertEqual(received["state"], "active")
        self.assertTrue(received["refresh"])

    def test_courses_endpoint_forwards_only_supported_filters(self) -> None:
        with self._client() as client:
            response = client.get(
                "/api/moodle/courses",
                params={
                    "page": 1,
                    "page_size": 10,
                    "search": "idiomas",
                    "visibility": "visible",
                    "category_id": 4,
                },
            )

        self.assertEqual(response.status_code, 200)
        received = response.json()["received"]
        self.assertEqual(received["visibility"], "visible")
        self.assertEqual(received["category_id"], 4)

    def test_course_resources_endpoint_loads_selected_course(self) -> None:
        with self._client() as client:
            response = client.get("/api/moodle/courses/8/resources?refresh=true")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["course"]["id"], 8)
        self.assertTrue(response.json()["received"]["refresh"])

    def test_section_visibility_endpoint_updates_requested_section(self) -> None:
        with self._client() as client:
            response = client.patch(
                "/api/moodle/courses/8/sections/30/visibility",
                json={"visible": False},
            )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["section"]["visible"])
        self.assertTrue(response.json()["audit_recorded"])

    def test_section_visibility_rejects_unknown_body_fields(self) -> None:
        with self._client() as client:
            response = client.patch(
                "/api/moodle/courses/8/sections/30/visibility",
                json={"visible": True, "campo_no_admitido": True},
            )

        self.assertEqual(response.status_code, 422)

    def test_section_name_endpoint_updates_requested_section(self) -> None:
        with self._client() as client:
            response = client.patch(
                "/api/moodle/courses/8/sections/30/name",
                json={"name": "  Unidad actualizada  "},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["section"]["name"], "Unidad actualizada")
        self.assertTrue(response.json()["audit_recorded"])

    def test_section_name_rejects_blank_or_unknown_body_fields(self) -> None:
        with self._client() as client:
            blank_response = client.patch(
                "/api/moodle/courses/8/sections/30/name",
                json={"name": "   "},
            )
            extra_response = client.patch(
                "/api/moodle/courses/8/sections/30/name",
                json={"name": "Unidad", "campo_no_admitido": True},
            )

        self.assertEqual(blank_response.status_code, 422)
        self.assertEqual(extra_response.status_code, 422)

    def test_resource_file_endpoint_proxies_download_without_token(self) -> None:
        with self._client() as client:
            response = client.get(
                "/api/moodle/courses/8/modules/44/files/0",
                params={"disposition": "attachment"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"contenido-del-recurso")
        self.assertEqual(response.headers["content-type"], "application/pdf")
        self.assertIn("attachment", response.headers["content-disposition"])
        self.assertNotIn("token", response.text.casefold())

    def test_user_status_endpoint_updates_requested_account(self) -> None:
        with self._client() as client:
            response = client.patch("/api/moodle/users/24/status", json={"active": False})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["user"]["id"], 24)
        self.assertEqual(response.json()["user"]["status"], "SUSPENDIDO")
        self.assertTrue(response.json()["institutional_validation"]["validated"])

    def test_user_status_endpoint_rejects_unknown_body_fields(self) -> None:
        with self._client() as client:
            response = client.patch(
                "/api/moodle/users/24/status",
                json={"active": True, "campo_no_admitido": True},
            )

        self.assertEqual(response.status_code, 422)

    def test_user_status_endpoint_requires_valid_user_id(self) -> None:
        with self._client() as client:
            response = client.patch("/api/moodle/users/0/status", json={"active": True})

        self.assertEqual(response.status_code, 422)

    def test_user_status_requires_email_in_intec_database(self) -> None:
        error = MoodleInstitutionalEmailNotFoundError("Correo no encontrado")
        with self._client(FailingMoodleService(error)) as client:
            response = client.patch("/api/moodle/users/24/status", json={"active": True})

        self.assertEqual(response.status_code, 409)

    def test_user_status_write_flag_is_enforced(self) -> None:
        error = MoodleWriteDisabledError("Operación deshabilitada")
        with self._client(FailingMoodleService(error)) as client:
            response = client.patch("/api/moodle/users/24/status", json={"active": False})

        self.assertEqual(response.status_code, 503)

    def test_invalid_local_parameters_return_422(self) -> None:
        with self._client() as client:
            response = client.get("/api/moodle/users?page=0&page_size=500&state=otro")

        self.assertEqual(response.status_code, 422)

    def test_invalid_course_visibility_returns_422(self) -> None:
        with self._client() as client:
            response = client.get("/api/moodle/courses?visibility=privado")

        self.assertEqual(response.status_code, 422)

    def test_grade_preview_forwards_up_to_three_periods_and_replacement_flag(self) -> None:
        with self._client() as client:
            response = client.post(
                "/api/moodle/grades/preview?refresh=true",
                json={
                    "course_id": 47,
                    "period_codes": [1015, 1016, 1017],
                    "replace_existing": True,
                },
            )

        self.assertEqual(response.status_code, 200)
        received = response.json()["received"]
        self.assertEqual(received["course_id"], 47)
        self.assertEqual(received["period_codes"], [1015, 1016, 1017])
        self.assertTrue(received["refresh"])
        self.assertTrue(received["replace_existing"])

    def test_grade_apply_keeps_legacy_single_period_compatibility(self) -> None:
        alert_service = FakeMoodleGradeAlertService()
        with self._client(alert_service=alert_service) as client:
            response = client.post(
                "/api/moodle/grades/apply",
                json={"course_id": 47, "period_code": 1015, "replace_existing": True},
            )

        self.assertEqual(response.status_code, 200)
        received = response.json()["received"]
        self.assertEqual(received["actor"], "admin@example.edu")
        self.assertEqual(received["period_codes"], [1015])
        self.assertTrue(received["replace_existing"])
        self.assertEqual(alert_service.invalidations, 1)

    def test_grade_alerts_forwards_session_and_refresh(self) -> None:
        with self._client() as client:
            response = client.get("/api/moodle/grades/alerts?refresh=true")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["role"], "ADMINISTRADOR")
        self.assertTrue(response.json()["refresh"])

    def test_grade_selection_deduplicates_period_codes(self) -> None:
        with self._client() as client:
            response = client.post(
                "/api/moodle/grades/preview",
                json={"course_id": 47, "period_codes": [1015, 1015, 1016]},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["received"]["period_codes"], [1015, 1016])

    def test_grade_selection_requires_one_to_three_periods(self) -> None:
        with self._client() as client:
            empty_response = client.post(
                "/api/moodle/grades/preview",
                json={"course_id": 47},
            )
            excessive_response = client.post(
                "/api/moodle/grades/preview",
                json={"course_id": 47, "period_codes": [1011, 1012, 1013, 1014]},
            )

        self.assertEqual(empty_response.status_code, 422)
        self.assertEqual(excessive_response.status_code, 422)

    def test_access_without_authentication_preserves_401(self) -> None:
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_moodle_read_service] = FakeMoodleService

        with TestClient(app) as client:
            response = client.get("/api/moodle/status")

        self.assertEqual(response.status_code, 401)

    def test_disabled_moodle_returns_503(self) -> None:
        with self._client(FailingMoodleService(MoodleDisabledError("Integración deshabilitada"))) as client:
            response = client.get("/api/moodle/status")

        self.assertEqual(response.status_code, 503)

    def test_missing_configuration_returns_503(self) -> None:
        error = MoodleConfigurationError("El token de Moodle no está configurado")
        with self._client(FailingMoodleService(error)) as client:
            response = client.get("/api/moodle/status")

        self.assertEqual(response.status_code, 503)

    def test_result_limit_returns_503(self) -> None:
        error = MoodleResultLimitExceededError("La consulta superó el límite")
        with self._client(FailingMoodleService(error)) as client:
            response = client.get("/api/moodle/status")

        self.assertEqual(response.status_code, 503)

    def test_timeout_returns_504(self) -> None:
        with self._client(FailingMoodleService(MoodleTimeoutError("Tiempo agotado"))) as client:
            response = client.get("/api/moodle/status")

        self.assertEqual(response.status_code, 504)

    def test_connection_error_returns_502(self) -> None:
        with self._client(FailingMoodleService(MoodleConnectionError("Sin conexión"))) as client:
            response = client.get("/api/moodle/status")

        self.assertEqual(response.status_code, 502)

    def test_existing_authorization_behavior_is_preserved(self) -> None:
        def forbidden():
            raise HTTPException(status_code=403, detail="No tiene asignada la pantalla")

        with self._client(access_dependency=forbidden) as client:
            response = client.get("/api/moodle/status")

        self.assertEqual(response.status_code, 403)

    def test_each_submenu_uses_its_own_permission(self) -> None:
        def forbidden():
            raise HTTPException(status_code=403, detail="No tiene asignada la pantalla")

        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[_MOODLE_STATUS_ACCESS] = administrative_user
        app.dependency_overrides[_MOODLE_USERS_ACCESS] = forbidden
        app.dependency_overrides[_MOODLE_COURSES_ACCESS] = administrative_user
        app.dependency_overrides[_MOODLE_RESOURCES_ACCESS] = administrative_user
        app.dependency_overrides[get_moodle_read_service] = FakeMoodleService

        with TestClient(app) as client:
            status_response = client.get("/api/moodle/status")
            users_response = client.get("/api/moodle/users")
            courses_response = client.get("/api/moodle/courses")
            resources_response = client.get("/api/moodle/courses/8/resources")

        self.assertEqual(status_response.status_code, 200)
        self.assertEqual(users_response.status_code, 403)
        self.assertEqual(courses_response.status_code, 200)
        self.assertEqual(resources_response.status_code, 200)

    def test_token_is_removed_from_upstream_error_response(self) -> None:
        secret = "token-router-no-real"
        settings = SimpleNamespace(moodle_token=SecretStr(secret))
        error = MoodleApiError(f"Moodle rechazó la credencial {secret}")

        with patch("app.routers.moodle.get_settings", return_value=settings):
            with self._client(FailingMoodleService(error)) as client:
                response = client.get("/api/moodle/status")

        self.assertEqual(response.status_code, 502)
        self.assertNotIn(secret, response.text)
        self.assertIn("credencial protegida", response.text)


if __name__ == "__main__":
    unittest.main()
