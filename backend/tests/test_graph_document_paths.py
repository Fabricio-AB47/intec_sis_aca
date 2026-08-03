import unittest

from app.services.graph_documents import (
    GRAPH_DOCUMENT_ROOT,
    build_expedient_folder_path,
    safe_folder_part,
)


class GraphDocumentPathTests(unittest.TestCase):
    def test_uses_existing_student_expedient_root_and_identity(self) -> None:
        path = build_expedient_folder_path(
            module_code="INGLES",
            identification="1724-036-536",
            student_code=123,
            student_name="BORJA HERNÁNDEZ FABRICIO ALEXANDER",
            origin_id=77,
            expedient_code="ING-123-1060-333",
        )

        self.assertEqual(GRAPH_DOCUMENT_ROOT, "EXPEDIENTES ESTUDIANTILES")
        self.assertTrue(
            path.startswith(
                "EXPEDIENTES ESTUDIANTILES/"
                "BORJA HERNÁNDEZ FABRICIO ALEXANDER - 1724036536/IDIOMAS/"
            )
        )
        self.assertTrue(path.endswith("CASO 77 - ING-123-1060-333"))

    def test_separates_each_supported_module(self) -> None:
        expected_folders = {
            "INGLES": "IDIOMAS",
            "TITULACION": "TITULACION",
            "PRACTICAS": "PRACTICAS PREPROFESIONALES",
            "VINCULACION": "VINCULACION CON LA SOCIEDAD",
        }
        for module, folder in expected_folders.items():
            with self.subTest(module=module):
                path = build_expedient_folder_path(
                    module_code=module,
                    identification="0102030405",
                    student_code=10,
                    student_name="ESTUDIANTE PRUEBA",
                    origin_id=9,
                    expedient_code=f"{module}-9",
                )
                self.assertIn(f"/{folder}/", path)

    def test_folder_sanitization_preserves_names_and_removes_graph_separators(self) -> None:
        self.assertEqual(
            safe_folder_part('MUÑOZ / PEÑA: "CASO"'),
            "MUÑOZ _ PEÑA_ _CASO_",
        )

    def test_rejects_unknown_module_or_missing_identification(self) -> None:
        common = {
            "student_code": 1,
            "student_name": "ESTUDIANTE",
            "origin_id": 1,
        }
        with self.assertRaises(ValueError):
            build_expedient_folder_path(
                module_code="OTRO",
                identification="0102030405",
                **common,
            )
        with self.assertRaises(ValueError):
            build_expedient_folder_path(
                module_code="INGLES",
                identification="",
                **common,
            )


if __name__ == "__main__":
    unittest.main()
