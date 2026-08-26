import secrets
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi import HTTPException

from app.core.security import SessionUser
from app.routers.portal_academico import _GRADES_ADMIN_ACCESS
from app.routers.students import _DASHBOARD_ACCESS
from app.services.auth import (
    _authenticate_administrative_user,
    _normalize_role,
    _student_access_allowed,
    authenticate_user,
)


TEST_CREDENTIAL = secrets.token_urlsafe(18)


def profile(role: str, *, cedula: str = "1724036536") -> SessionUser:
    return SessionUser(
        login="persona@institucion.edu.ec",
        nombres="Persona de prueba",
        email="persona@institucion.edu.ec",
        rol=role,
        cedula=cedula,
    )


class AuthenticateProfilesTests(unittest.TestCase):
    def authenticate_with(self, administrative=None, student=None, teacher=None):
        with (
            patch("app.services.auth._authenticate_administrative_user", return_value=administrative),
            patch("app.services.auth._authenticate_student", return_value=student),
            patch("app.services.auth._authenticate_teacher", return_value=teacher),
        ):
            return authenticate_user("persona@institucion.edu.ec", TEST_CREDENTIAL)

    def test_returns_student_and_teacher_profiles(self):
        session = self.authenticate_with(
            student=profile("ESTUDIANTE"),
            teacher=profile("DOCENTE"),
        )

        self.assertEqual(
            [item["rol"] for item in session["perfiles"]],
            ["ESTUDIANTE", "DOCENTE"],
        )

    def test_returns_teacher_and_administrative_profiles(self):
        session = self.authenticate_with(
            administrative=profile("ADMINISTRADOR"),
            teacher=profile("DOCENTE"),
        )

        self.assertEqual(
            [item["rol"] for item in session["perfiles"]],
            ["ADMINISTRADOR", "DOCENTE"],
        )

    def test_returns_all_three_profiles_without_duplicates(self):
        session = self.authenticate_with(
            administrative=profile("ADMINISTRADOR"),
            student=profile("ESTUDIANTE"),
            teacher=profile("DOCENTE"),
        )

        roles = [item["rol"] for item in session["perfiles"]]
        self.assertEqual(roles, ["ADMINISTRADOR", "ESTUDIANTE", "DOCENTE"])
        self.assertEqual(len(roles), len(set(roles)))


class AdministrativeTypeTests(unittest.TestCase):
    @staticmethod
    def administrative_row(tp_us, *, tipousuario="1", detalle="ADMINISTRADOR"):
        return SimpleNamespace(
            login="administrativo@institucion.edu.ec",
            password=TEST_CREDENTIAL,
            nombres="Persona administrativa",
            id_usuarios=25,
            estado="A",
            email="administrativo@institucion.edu.ec",
            tp_us=tp_us,
            tipousuario=tipousuario,
            detalle_tipo_us=detalle,
            cedula="1724036536",
        )

    def authenticate_row(self, row):
        connection = MagicMock()
        connection.__enter__.return_value = connection
        connection.cursor.return_value.fetchall.return_value = [row]

        with (
            patch("app.services.auth.get_connection", return_value=connection),
            patch("app.services.auth.verify_password", return_value=True),
        ):
            return _authenticate_administrative_user(
                "administrativo@institucion.edu.ec",
                TEST_CREDENTIAL,
            )

    def test_rejects_null_tp_us_even_when_legacy_role_fields_have_values(self):
        with self.assertRaisesRegex(
            PermissionError,
            "sin tipo de usuario asignado",
        ):
            self.authenticate_row(self.administrative_row(None))

    def test_rejects_blank_tp_us_even_when_legacy_role_fields_have_values(self):
        with self.assertRaisesRegex(
            PermissionError,
            "sin tipo de usuario asignado",
        ):
            self.authenticate_row(self.administrative_row("   "))

    def test_resolves_administrative_role_only_from_tp_us(self):
        user = self.authenticate_row(
            self.administrative_row(
                "4",
                tipousuario="1",
                detalle="ADMINISTRADOR",
            )
        )

        self.assertIsNotNone(user)
        self.assertEqual(user.rol, "ACADEMICO")
        self.assertEqual(user.origen, "USUARIO_SIS")


class StudentStatusTests(unittest.TestCase):
    def test_allows_supported_student_statuses(self):
        supported = (
            ("Activo", "A"),
            ("Retirado", "R"),
            ("Inactivo", "P"),
            ("Graduado", "G"),
            ("Inactivo", None),
        )

        for correo_status, academic_status in supported:
            with self.subTest(correo_status=correo_status, academic_status=academic_status):
                self.assertTrue(_student_access_allowed(correo_status, academic_status))

    def test_rejects_continuing_education_and_status_d(self):
        rejected = (
            ("E Continua", "D"),
            ("D", "D"),
            ("Activo", "D"),
            (None, "A"),
        )

        for correo_status, academic_status in rejected:
            with self.subTest(correo_status=correo_status, academic_status=academic_status):
                self.assertFalse(_student_access_allowed(correo_status, academic_status))


class AcademicAndWellbeingProfileTests(unittest.TestCase):
    def test_catalog_codes_resolve_to_expected_profiles(self):
        self.assertEqual(_normalize_role("4"), "ACADEMICO")
        self.assertEqual(_normalize_role("ACADEMICA"), "ACADEMICO")
        self.assertEqual(_normalize_role("3"), "BIENESTAR")

    def test_academic_and_wellbeing_can_open_grades(self):
        for role in ("ACADEMICO", "BIENESTAR"):
            with self.subTest(role=role):
                self.assertEqual(_GRADES_ADMIN_ACCESS(profile(role)).rol, role)

    def test_academic_and_wellbeing_can_open_dashboard(self):
        for role in ("ACADEMICO", "BIENESTAR"):
            with self.subTest(role=role):
                self.assertEqual(_DASHBOARD_ACCESS(profile(role)).rol, role)

    def test_unrelated_role_cannot_open_administrative_grades(self):
        with self.assertRaises(HTTPException) as context:
            _GRADES_ADMIN_ACCESS(profile("DOCENTE"))
        self.assertEqual(context.exception.status_code, 403)


if __name__ == "__main__":
    unittest.main()
