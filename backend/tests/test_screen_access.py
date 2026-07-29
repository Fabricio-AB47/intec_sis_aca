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
    SCREEN_CATALOG,
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

    def test_every_role_has_valid_default_pages(self) -> None:
        role_codes = {item["value"] for item in ROLE_CATALOG}
        self.assertEqual(role_codes, set(DEFAULT_ACCESS))
        for role, pages in DEFAULT_ACCESS.items():
            with self.subTest(role=role):
                self.assertTrue(set(pages).issubset(ALL_PAGES))

    def test_administrator_default_is_the_complete_catalog(self) -> None:
        self.assertEqual(tuple(DEFAULT_ACCESS["ADMINISTRADOR"]), ALL_PAGES)

    def test_academic_flow_is_exclusive_to_administrator(self) -> None:
        self.assertEqual(ADMIN_ONLY_PAGES, {"sistema-academico"})
        for role, pages in DEFAULT_ACCESS.items():
            with self.subTest(role=role):
                if role == "ADMINISTRADOR":
                    self.assertTrue(ADMIN_ONLY_PAGES.issubset(pages))
                else:
                    self.assertTrue(ADMIN_ONLY_PAGES.isdisjoint(pages))

    def test_normalizes_supported_administrator_aliases(self) -> None:
        self.assertEqual(normalize_role("1"), "ADMINISTRADOR")
        self.assertEqual(normalize_role("admin"), "ADMINISTRADOR")
        self.assertEqual(normalize_role("administracion"), "ADMINISTRADOR")

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
