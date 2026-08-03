import unittest
from unittest.mock import patch

from fastapi import HTTPException

from app.core.security import SessionUser
from app.routers.screen_access import list_screen_access
from app.services.screen_access import (
    ADMIN_ONLY_PAGES,
    ALL_PAGES,
    DEFAULT_ACCESS,
    ROLE_CATALOG,
    ROLE_DENIED_PAGES,
    SCREEN_CATALOG,
    _initialize_role_assignments,
    _role_payloads,
    _sync_catalog,
    normalize_role,
    save_screen_access,
)


def profile(role: str) -> SessionUser:
    return SessionUser(
        login="usuario@intec.edu.ec",
        nombres="Usuario de prueba",
        email="usuario@intec.edu.ec",
        rol=role,
    )


class ScreenAccessCatalogTests(unittest.TestCase):
    def test_catalog_pages_are_unique(self) -> None:
        self.assertEqual(len(ALL_PAGES), len(set(ALL_PAGES)))
        self.assertEqual(len(SCREEN_CATALOG), len(ALL_PAGES))

    def test_legacy_map_is_not_an_assignable_screen(self) -> None:
        self.assertNotIn("sisacademico-v1", ALL_PAGES)
        for role, pages in DEFAULT_ACCESS.items():
            with self.subTest(role=role):
                self.assertNotIn("sisacademico-v1", pages)

    def test_every_role_has_valid_default_pages(self) -> None:
        role_codes = {item["value"] for item in ROLE_CATALOG}
        self.assertEqual(role_codes, set(DEFAULT_ACCESS))
        for role, pages in DEFAULT_ACCESS.items():
            with self.subTest(role=role):
                self.assertTrue(set(pages).issubset(ALL_PAGES))

    def test_administrator_default_is_the_complete_catalog(self) -> None:
        self.assertEqual(tuple(DEFAULT_ACCESS["ADMINISTRADOR"]), ALL_PAGES)

    def test_administration_pages_are_exclusive_to_administrator(self) -> None:
        self.assertEqual(ADMIN_ONLY_PAGES, {"sistema-academico", "asignacion-pantallas"})
        for role, pages in DEFAULT_ACCESS.items():
            with self.subTest(role=role):
                if role == "ADMINISTRADOR":
                    self.assertTrue(ADMIN_ONLY_PAGES.issubset(pages))
                else:
                    self.assertTrue(ADMIN_ONLY_PAGES.isdisjoint(pages))

    def test_student_cannot_receive_document_expedients(self) -> None:
        self.assertEqual(
            ROLE_DENIED_PAGES["ESTUDIANTE"],
            frozenset({"expedientes-documentales"}),
        )
        self.assertNotIn("expedientes-documentales", DEFAULT_ACCESS["ESTUDIANTE"])

    def test_rejects_student_document_expedient_assignment(self) -> None:
        with self.assertRaises(ValueError):
            save_screen_access(
                "ESTUDIANTE",
                ["portal-estudiante", "expedientes-documentales"],
                updated_by="prueba",
            )

    def test_normalizes_every_administrative_tp_us(self) -> None:
        expected = {
            "1": "ADMINISTRADOR",
            "2": "FINANCIERO",
            "3": "BIENESTAR",
            "4": "ACADEMICO",
            "5": "ADMISIONES",
            "6": "RECTOR",
            "7": "VICERRECTOR",
            "8": "SOPORTE",
            "9": "INVITADO_SOP",
            "10": "SECRETARIA",
        }
        for tp_us, role in expected.items():
            with self.subTest(tp_us=tp_us):
                self.assertEqual(normalize_role(tp_us), role)

    def test_normalizes_supported_role_aliases(self) -> None:
        self.assertEqual(normalize_role("admin"), "ADMINISTRADOR")
        self.assertEqual(normalize_role("administracion"), "ADMINISTRADOR")
        self.assertEqual(normalize_role("Secretaría académica"), "SECRETARIA")
        self.assertEqual(normalize_role("invitado_sop"), "INVITADO_SOP")

    def test_rejects_unknown_role_before_opening_database(self) -> None:
        with self.assertRaises(ValueError):
            save_screen_access("ROL_DESCONOCIDO", ["dashboard"], updated_by="prueba")

    def test_rejects_unknown_screen_before_opening_database(self) -> None:
        with self.assertRaises(ValueError):
            save_screen_access("ACADEMICO", ["pantalla-inexistente"], updated_by="prueba")

    def test_rejects_empty_assignment_before_opening_database(self) -> None:
        with self.assertRaises(ValueError):
            save_screen_access("BIENESTAR", [], updated_by="prueba")

    def test_rejects_assignment_with_only_administrator_screen(self) -> None:
        with self.assertRaises(ValueError):
            save_screen_access("ACADEMICO", ["sistema-academico"], updated_by="prueba")

        with self.assertRaises(ValueError):
            save_screen_access("BIENESTAR", ["asignacion-pantallas"], updated_by="prueba")

    def test_catalog_sync_does_not_grant_new_screens_to_configured_profiles(self) -> None:
        class RecordingCursor:
            def __init__(self) -> None:
                self.statements: list[str] = []

            def execute(self, statement: str, *params: object) -> None:
                del params
                self.statements.append(" ".join(statement.split()).upper())

        cursor = RecordingCursor()
        _sync_catalog(cursor)

        implicit_grants = [
            statement
            for statement in cursor.statements
            if "INSERT INTO CFG.ACCESOPANTALLAROL" in statement
        ]
        self.assertEqual(implicit_grants, [])

    def test_initial_assignments_are_materialized_only_for_missing_roles(self) -> None:
        class ExistingRole:
            RolCodigo = "ACADEMICO"

            def __getitem__(self, index: int) -> str:
                del index
                return self.RolCodigo

        class RecordingCursor:
            def __init__(self) -> None:
                self.executions: list[tuple[str, tuple[object, ...]]] = []

            def execute(self, statement: str, *params: object) -> None:
                self.executions.append((" ".join(statement.split()).upper(), params))

            def fetchall(self) -> list[ExistingRole]:
                return [ExistingRole()]

        cursor = RecordingCursor()
        _initialize_role_assignments(cursor)

        seeded_roles = {
            str(params[0])
            for statement, params in cursor.executions
            if "MERGE CFG.ACCESOPANTALLAROL" in statement
        }
        self.assertNotIn("ADMINISTRADOR", seeded_roles)
        self.assertNotIn("ACADEMICO", seeded_roles)
        self.assertEqual(
            seeded_roles,
            {item["value"] for item in ROLE_CATALOG} - {"ADMINISTRADOR", "ACADEMICO"},
        )

    def test_unconfigured_role_fails_closed_without_runtime_defaults(self) -> None:
        class EmptyCursor:
            def execute(self, statement: str, *params: object) -> None:
                del statement, params

            def fetchall(self) -> list[object]:
                return []

        role = _role_payloads(EmptyCursor(), ["ACADEMICO"])[0]

        self.assertFalse(role["configured"])
        self.assertEqual(role["pages"], [])


class ScreenAccessRouterTests(unittest.TestCase):
    def test_only_administrator_can_request_complete_matrix(self) -> None:
        with self.assertRaises(HTTPException) as context:
            list_screen_access(profile("ACADEMICO"), include_all=True)
        self.assertEqual(context.exception.status_code, 403)

    @patch("app.routers.screen_access.get_screen_access")
    def test_current_role_reads_only_its_assignment(self, get_access: object) -> None:
        get_access.return_value = {
            "source": "INTEC_INTEGRACION_CONTROL.cfg",
            "synchronized_at": "2026-07-28T12:00:00+00:00",
            "current_role": "BIENESTAR",
            "screens": [],
            "roles": [],
        }

        result = list_screen_access(profile("BIENESTAR"), include_all=False)

        self.assertEqual(result["current_role"], "BIENESTAR")
        get_access.assert_called_once_with("BIENESTAR", include_all=False)


if __name__ == "__main__":
    unittest.main()
