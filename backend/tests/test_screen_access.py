import unittest
from unittest.mock import MagicMock, patch

from fastapi import HTTPException

from app.core.security import SessionUser, require_any_screen_access, require_screen_access
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
    _deactivate_non_admin_automatic_moodle_assignments,
    _deactivate_container_assignments,
    _ensure_screen_catalog_ready,
    _initialize_role_assignments,
    _materialize_role_screen_matrix,
    _migrate_flow_screen_assignments,
    _migrate_new_screen_default_assignments,
    _migrate_split_screen_assignments,
    _role_screen_matrix_is_complete,
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
        self.assertEqual(screen["label"], "Matriculación académica")
        self.assertIn("cabecera de matrícula", screen["description"].lower())
        self.assertIn("matricula-acad", CONTAINER_PAGES)
        self.assertNotIn("matricula-acad", ALL_PAGES)
        self.assertIn("matricula-acad/individual", ALL_PAGES)
        self.assertNotIn("matricula-acad", ADMIN_ONLY_PAGES)
        for role, denied_pages in ROLE_DENIED_PAGES.items():
            with self.subTest(role=role):
                self.assertNotIn("matricula-acad", denied_pages)

    def test_moodle_teams_enrollment_is_an_assignable_integration(self) -> None:
        screen = next(item for item in SCREEN_CATALOG if item["page"] == "moodle-teams")

        self.assertEqual(screen["label"], "Matrícula Moodle-Teams")
        self.assertEqual(screen["group"], "Integraciones")
        self.assertIn("docentes", screen["description"].lower())
        self.assertIn("estudiantes", screen["description"].lower())
        self.assertIn("moodle-teams", ALL_PAGES)
        self.assertNotIn("moodle-teams", ADMIN_ONLY_PAGES)

    def test_moodle_evaluation_dates_is_independently_assignable(self) -> None:
        screen = next(
            item for item in SCREEN_CATALOG
            if item["page"] == "moodle/evaluation-dates"
        )

        self.assertEqual(screen["label"], "Fechas de evaluaciones")
        self.assertEqual(screen["group"], "Moodle")
        self.assertEqual(screen["parent_page"], "moodle")
        self.assertIn("moodle/evaluation-dates", ALL_PAGES)

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

    def test_teacher_enrollment_is_grouped_with_enrollment(self) -> None:
        screen = next(item for item in SCREEN_CATALOG if item["page"] == "matricula-docente")

        self.assertEqual(screen["label"], "Matrícula docente")
        self.assertEqual(screen["group"], "Matrícula")
        self.assertIn("matricula-docente", ALL_PAGES)
        self.assertIn("matricula-docente", DEFAULT_ACCESS["ACADEMICO"])

    def test_update_screens_share_one_catalog_group(self) -> None:
        update_pages = {
            "actualizar-datos-estudiante",
            "actualizar-correo-intec",
            "fecha-grado",
            "gestion-sisacademico/actualizacion_est",
            "gestion-sisacademico/actualizacion_estudiantes",
        }

        for page in update_pages:
            with self.subTest(page=page):
                screen = next(item for item in SCREEN_CATALOG if item["page"] == page)
                self.assertEqual(screen["group"], "Actualización")

    def test_enrollment_flows_share_one_catalog_group(self) -> None:
        enrollment_pages = {
            "matricula",
            "matricula-docente",
            "matricula-acad/individual",
            "matricula-acad/masiva",
            "matricula-acad/prerrequisitos",
            "gestion-sisacademico/preinscripciones",
            "gestion-sisacademico/datos_factura",
            "gestion-sisacademico/cabecera_matricula",
            "gestion-sisacademico/matricula_materias",
            "gestion-sisacademico/pagos_matricula",
        }

        for page in enrollment_pages:
            with self.subTest(page=page):
                screen = next(item for item in SCREEN_CATALOG if item["page"] == page)
                self.assertEqual(screen["group"], "Matrícula")

    def test_admission_flows_share_one_catalog_group(self) -> None:
        admission_pages = {
            "preinscripcion/registro",
            "preinscripcion/inscritos",
            "preinscripcion/documentos",
            "preinscripcion/seguimiento",
            "preinscripcion/cabecera",
            "preinscripcion/materias",
        }

        for page in admission_pages:
            with self.subTest(page=page):
                screen = next(item for item in SCREEN_CATALOG if item["page"] == page)
                self.assertEqual(screen["group"], "Admisiones")

    def test_registration_is_an_explicit_assignable_screen(self) -> None:
        screen = next(item for item in SCREEN_CATALOG if item["page"] == "preinscripcion")
        self.assertEqual(screen["label"], "Inscripción de estudiantes")
        self.assertEqual(screen["group"], "Inscripción")
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

        catalog_merges = [
            statement
            for statement in cursor.statements
            if "MERGE CFG.PANTALLAPORTAL" in statement
        ]
        self.assertEqual(len(catalog_merges), 1)
        self.assertIn("USING (VALUES", catalog_merges[0])

        implicit_grants = [
            statement
            for statement in cursor.statements
            if "INSERT INTO CFG.ACCESOPANTALLAROL" in statement
        ]
        self.assertEqual(implicit_grants, [])

    @patch("app.services.screen_access._synchronize_screen_catalog")
    @patch("app.services.screen_access.get_integration_control_connection")
    def test_catalog_bootstrap_runs_once_per_process(
        self,
        get_connection: MagicMock,
        synchronize_catalog: MagicMock,
    ) -> None:
        connection = get_connection.return_value.__enter__.return_value
        cursor = connection.cursor.return_value

        with patch("app.services.screen_access._catalog_bootstrapped", False):
            _ensure_screen_catalog_ready()
            _ensure_screen_catalog_ready()

        get_connection.assert_called_once_with()
        synchronize_catalog.assert_called_once_with(cursor)
        connection.commit.assert_called_once_with()

    @patch("app.services.screen_access._role_payloads", return_value=[{"pages": ["dashboard"]}])
    @patch("app.services.screen_access.get_integration_control_connection")
    @patch("app.services.screen_access._ensure_screen_catalog_ready")
    def test_save_updates_the_complete_role_in_one_statement(
        self,
        ensure_catalog: MagicMock,
        get_connection: MagicMock,
        role_payloads: MagicMock,
    ) -> None:
        connection = get_connection.return_value.__enter__.return_value
        cursor = connection.cursor.return_value

        result = save_screen_access("ACADEMICO", ["dashboard"], updated_by="prueba")

        self.assertEqual(result, {"pages": ["dashboard"]})
        ensure_catalog.assert_called_once_with()
        self.assertEqual(cursor.execute.call_count, 1)
        statement = " ".join(cursor.execute.call_args.args[0].split()).upper()
        self.assertIn("UPDATE CFG.ACCESOPANTALLAROL", statement)
        self.assertIn("CASE WHEN PANTALLACODIGO IN", statement)
        role_payloads.assert_called_once_with(cursor, ["ACADEMICO"])
        connection.commit.assert_called_once_with()

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
            if params[0] == "ESTUDIANTE" and params[3] == "portal-estudiante"
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

    def test_moodle_is_exposed_as_assignable_subscreens(self) -> None:
        expected = {
            "moodle/alerts",
            "moodle/courses",
            "moodle/evaluation-dates",
            "moodle/grades",
            "moodle/resources",
            "moodle/status",
            "moodle/users",
        }

        self.assertIn("moodle", CONTAINER_PAGES)
        self.assertNotIn("moodle", ALL_PAGES)
        self.assertEqual(
            {
                page
                for page, parent in FLOW_PARENT_BY_PAGE.items()
                if parent == "moodle"
            },
            expected,
        )
        self.assertTrue(expected.issubset(set(DEFAULT_ACCESS["ADMINISTRADOR"])))
        self.assertTrue(expected.issubset(set(ALL_PAGES)))
        self.assertTrue(expected.isdisjoint(ADMIN_ONLY_PAGES))
        self.assertIn("moodle/alerts", DEFAULT_ACCESS["ACADEMICO"])
        self.assertIn("moodle/alerts", DEFAULT_ACCESS["DOCENTE"])
        optional_pages = expected - {"moodle/alerts"}
        for role, pages in DEFAULT_ACCESS.items():
            if role == "ADMINISTRADOR":
                continue
            with self.subTest(role=role):
                self.assertTrue(optional_pages.isdisjoint(pages))

    def test_automatic_moodle_grants_are_removed_only_outside_administration(self) -> None:
        optional_pages = {
            "moodle/courses",
            "moodle/evaluation-dates",
            "moodle/grades",
            "moodle/resources",
            "moodle/status",
            "moodle/users",
        }

        class RecordingCursor:
            def __init__(self) -> None:
                self.executions: list[tuple[str, tuple[object, ...]]] = []

            def execute(self, statement: str, *params: object) -> None:
                self.executions.append((" ".join(statement.split()).upper(), params))

        cursor = RecordingCursor()
        _deactivate_non_admin_automatic_moodle_assignments(cursor)

        self.assertEqual(len(cursor.executions), 1)
        statement, params = cursor.executions[0]
        self.assertIn("ROLCODIGO <> N'ADMINISTRADOR'", statement)
        self.assertIn("SISTEMA_PREDETERMINADO_ADMIN", statement)
        self.assertIn("USUARIOACTUALIZACION", statement)
        self.assertEqual(set(map(str, params[: len(optional_pages)])), optional_pages)
        self.assertNotIn("moodle/alerts", set(map(str, params)))
        self.assertNotIn("PRUEBA", set(map(str, params[4:])))

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

    def test_role_screen_matrix_materializes_every_catalog_option_once(self) -> None:
        class RecordingCursor:
            def __init__(self) -> None:
                self.executions: list[tuple[str, tuple[object, ...]]] = []

            def execute(self, statement: str, *params: object) -> None:
                self.executions.append((" ".join(statement.split()).upper(), params))

        cursor = RecordingCursor()
        _materialize_role_screen_matrix(cursor)

        self.assertEqual(len(cursor.executions), 1)
        statement, params = cursor.executions[0]
        role_codes = tuple(role["value"] for role in ROLE_CATALOG)
        self.assertEqual(params[:len(role_codes)], role_codes)
        self.assertEqual(params[len(role_codes):], ALL_PAGES)
        self.assertIn("CROSS JOIN", statement)
        self.assertIn("WHEN NOT MATCHED THEN INSERT", statement)
        self.assertNotIn("WHEN MATCHED THEN", statement)
        self.assertIn("SISTEMA_CATALOGO", statement)

    def test_new_career_change_screen_is_seeded_without_overwriting_manual_choices(self) -> None:
        class RecordingCursor:
            def __init__(self) -> None:
                self.executions: list[tuple[str, tuple[object, ...]]] = []

            def execute(self, statement: str, *params: object) -> None:
                self.executions.append((" ".join(statement.split()).upper(), params))

        cursor = RecordingCursor()
        _migrate_new_screen_default_assignments(cursor)

        self.assertEqual(
            {params for _, params in cursor.executions},
            {
                ("ACADEMICO", "solicitudes-cambio-carrera"),
                ("SECRETARIA", "solicitudes-cambio-carrera"),
            },
        )
        for statement, _ in cursor.executions:
            self.assertIn("TARGET.USUARIOACTUALIZACION = N'SISTEMA_CATALOGO'", statement)
            self.assertIn("SISTEMA_SOLICITUDES_V1", statement)
            self.assertNotIn("WHEN MATCHED AND TARGET.ACTIVO = 1", statement)

    def test_complete_role_screen_matrix_avoids_repeating_migrations(self) -> None:
        class CountRow:
            def __init__(self, total: int) -> None:
                self.Total = total

        class CountCursor:
            def __init__(self, total: int) -> None:
                self.total = total
                self.params: tuple[object, ...] = ()

            def execute(self, statement: str, *params: object) -> None:
                self.asserted_statement = " ".join(statement.split()).upper()
                self.params = params

            def fetchone(self) -> CountRow:
                return CountRow(self.total)

        expected_total = len(ROLE_CATALOG) * len(ALL_PAGES)
        complete_cursor = CountCursor(expected_total)
        incomplete_cursor = CountCursor(expected_total - 1)

        self.assertTrue(_role_screen_matrix_is_complete(complete_cursor))
        self.assertFalse(_role_screen_matrix_is_complete(incomplete_cursor))
        self.assertIn("COUNT_BIG(*)", complete_cursor.asserted_statement)
        self.assertEqual(
            complete_cursor.params,
            tuple(role["value"] for role in ROLE_CATALOG) + ALL_PAGES,
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

    @patch("app.services.screen_access.role_has_screen_access")
    def test_any_screen_dependency_accepts_the_shared_operation(
        self,
        check_access: MagicMock,
    ) -> None:
        check_access.side_effect = lambda _role, page: page == "moodle-teams"
        dependency = require_any_screen_access("moodle/courses", "moodle-teams")
        current_user = profile("ACADEMICO")

        self.assertIs(dependency(current_user), current_user)
        self.assertEqual(
            check_access.call_args_list,
            [
                unittest.mock.call("ACADEMICO", "moodle/courses"),
                unittest.mock.call("ACADEMICO", "moodle-teams"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
