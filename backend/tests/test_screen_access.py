import unittest
from unittest.mock import MagicMock, patch

from fastapi import HTTPException

from app.core.security import SessionUser, require_screen_access
from app.routers.screen_access import list_screen_access
from app.services.screen_access import (
    ADMIN_ONLY_PAGES,
    ALL_PAGES,
    ASSIGNABLE_SCREEN_CATALOG,
    CONTAINER_PAGES,
    DEFAULT_ACCESS,
    FLOW_PARENT_BY_PAGE,
    KNOWN_PAGES,
    ROLE_CATALOG,
    ROLE_DENIED_PAGES,
    SCREEN_CATALOG,
    _deactivate_container_assignments,
    _initialize_role_assignments,
    _migrate_flow_screen_assignments,
    _migrate_split_screen_assignments,
    _role_payloads,
    _sync_catalog,
    normalize_role,
    role_has_screen_access,
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
        self.assertEqual(len(KNOWN_PAGES), len(set(KNOWN_PAGES)))
        self.assertEqual(len(SCREEN_CATALOG), len(KNOWN_PAGES))
        self.assertEqual(len(ASSIGNABLE_SCREEN_CATALOG), len(ALL_PAGES))
        self.assertTrue(CONTAINER_PAGES.isdisjoint(ALL_PAGES))

    def test_every_registered_flow_has_parent_metadata(self) -> None:
        self.assertGreater(len(FLOW_PARENT_BY_PAGE), 0)
        for page, parent in FLOW_PARENT_BY_PAGE.items():
            with self.subTest(page=page):
                screen = next(item for item in SCREEN_CATALOG if item["page"] == page)
                self.assertEqual(screen["kind"], "flow")
                self.assertEqual(screen["parent_page"], parent)
                self.assertTrue(page.startswith(f"{parent}/"))

    def test_catalog_codes_fit_the_database_column(self) -> None:
        self.assertLessEqual(max(map(len, ALL_PAGES)), 80)

    def test_student_enrollment_is_an_assignable_screen(self) -> None:
        screen = next(item for item in SCREEN_CATALOG if item["page"] == "matricula-acad")
        self.assertEqual(screen["label"], "Matriculacion academica")
        self.assertIn("cabecera de matricula", screen["description"].lower())
        self.assertIn("matricula-acad", CONTAINER_PAGES)
        self.assertNotIn("matricula-acad", ALL_PAGES)
        self.assertIn("matricula-acad/individual", ALL_PAGES)
        self.assertNotIn("matricula-acad", ADMIN_ONLY_PAGES)
        for role, denied_pages in ROLE_DENIED_PAGES.items():
            with self.subTest(role=role):
                self.assertNotIn("matricula-acad", denied_pages)

    def test_enrollment_flows_are_independently_assignable(self) -> None:
        enrollment_flows = {
            page
            for page, parent in FLOW_PARENT_BY_PAGE.items()
            if parent == "matricula-acad"
        }
        self.assertEqual(
            enrollment_flows,
            {
                "matricula-acad/individual",
                "matricula-acad/masiva",
                "matricula-acad/prerrequisitos",
            },
        )
        self.assertTrue(enrollment_flows.issubset(DEFAULT_ACCESS["ACADEMICO"]))
        self.assertTrue(enrollment_flows.issubset(DEFAULT_ACCESS["ADMINISTRADOR"]))
        self.assertTrue(enrollment_flows.isdisjoint(DEFAULT_ACCESS["DOCENTE"]))

    def test_registration_is_an_explicit_assignable_screen(self) -> None:
        screen = next(item for item in SCREEN_CATALOG if item["page"] == "preinscripcion")
        self.assertEqual(screen["label"], "Inscripcion de estudiantes")
        self.assertEqual(screen["group"], "Inscripcion")
        self.assertIn("registro previo", screen["description"].lower())
        self.assertIn("preinscripcion", CONTAINER_PAGES)
        self.assertNotIn("preinscripcion", ALL_PAGES)
        self.assertIn("preinscripcion/registro", ALL_PAGES)

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

    def test_student_portal_split_inherits_legacy_access_only_when_missing(self) -> None:
        class RecordingCursor:
            def __init__(self) -> None:
                self.executions: list[tuple[str, tuple[object, ...]]] = []

            def execute(self, statement: str, *params: object) -> None:
                self.executions.append((" ".join(statement.split()).upper(), params))

        cursor = RecordingCursor()
        _migrate_split_screen_assignments(cursor)

        student_migrations = [
            (statement, params)
            for statement, params in cursor.executions
            if params[0] == "ESTUDIANTE"
        ]
        self.assertEqual(
            {str(params[1]) for _, params in student_migrations},
            {
                "portal-estudiante-malla-curricular",
                "portal-estudiante-malla-academica",
                "portal-estudiante-calificaciones",
            },
        )
        for statement, params in student_migrations:
            self.assertIn("WHEN NOT MATCHED THEN INSERT", statement)
            self.assertNotIn("WHEN MATCHED THEN", statement)
            self.assertEqual(params[2:], ("ESTUDIANTE", "portal-estudiante"))

    def test_flow_permissions_are_created_without_overwriting_existing_choices(self) -> None:
        class RecordingCursor:
            def __init__(self) -> None:
                self.executions: list[tuple[str, tuple[object, ...]]] = []

            def execute(self, statement: str, *params: object) -> None:
                self.executions.append((" ".join(statement.split()).upper(), params))

        cursor = RecordingCursor()
        _migrate_flow_screen_assignments(cursor)

        academic = {
            str(params[1]): (statement, params)
            for statement, params in cursor.executions
            if params[0] == "ACADEMICO"
        }
        self.assertEqual(set(academic), set(FLOW_PARENT_BY_PAGE))
        assigned_statement, assigned_params = academic["gestion-sisacademico/matricula_materias"]
        unassigned_statement, unassigned_params = academic["gestion-sisacademico/moodle_notas"]
        self.assertEqual(assigned_params[2], 1)
        self.assertEqual(unassigned_params[2], 0)
        for statement in (assigned_statement, unassigned_statement):
            self.assertIn("WHEN NOT MATCHED THEN INSERT", statement)
            self.assertNotIn("WHEN MATCHED THEN", statement)

    def test_legacy_container_assignments_are_deactivated_after_migration(self) -> None:
        class RecordingCursor:
            def __init__(self) -> None:
                self.executions: list[tuple[str, tuple[object, ...]]] = []

            def execute(self, statement: str, *params: object) -> None:
                self.executions.append((" ".join(statement.split()).upper(), params))

        cursor = RecordingCursor()
        _deactivate_container_assignments(cursor)

        self.assertEqual(len(cursor.executions), 1)
        statement, params = cursor.executions[0]
        self.assertIn("UPDATE CFG.ACCESOPANTALLAROL", statement)
        self.assertIn("SISTEMA_CONTENEDORES", statement)
        self.assertEqual(set(map(str, params)), set(CONTAINER_PAGES))

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


class ScreenAccessAuthorizationTests(unittest.TestCase):
    @patch("app.services.screen_access.get_integration_control_connection")
    def test_effective_assignment_allows_the_screen(self, get_connection: MagicMock) -> None:
        connection = MagicMock()
        connection.cursor.return_value.fetchone.return_value = (1,)
        get_connection.return_value.__enter__.return_value = connection

        self.assertTrue(role_has_screen_access("SECRETARIA", "matricula-acad"))
        connection.cursor.return_value.execute.assert_called_once()
        self.assertEqual(
            connection.cursor.return_value.execute.call_args.args[-3:],
            ("SECRETARIA", "matricula-acad", "matricula-acad/%"),
        )

    @patch("app.services.screen_access.get_integration_control_connection")
    def test_missing_assignment_denies_the_screen(self, get_connection: MagicMock) -> None:
        connection = MagicMock()
        connection.cursor.return_value.fetchone.return_value = None
        get_connection.return_value.__enter__.return_value = connection

        self.assertFalse(role_has_screen_access("DOCENTE", "matricula-acad"))

    @patch("app.services.screen_access.role_has_screen_access", return_value=True)
    def test_screen_dependency_accepts_an_assigned_profile(self, check_access: MagicMock) -> None:
        dependency = require_screen_access("matricula-acad")
        current_user = profile("BIENESTAR")

        self.assertIs(dependency(current_user), current_user)
        check_access.assert_called_once_with("BIENESTAR", "matricula-acad")

    @patch("app.services.screen_access.role_has_screen_access", return_value=False)
    def test_screen_dependency_rejects_an_unassigned_profile(self, check_access: MagicMock) -> None:
        dependency = require_screen_access("matricula-acad")

        with self.assertRaises(HTTPException) as context:
            dependency(profile("DOCENTE"))

        self.assertEqual(context.exception.status_code, 403)
        check_access.assert_called_once_with("DOCENTE", "matricula-acad")


if __name__ == "__main__":
    unittest.main()
