import unittest
from inspect import getsource
from unittest.mock import MagicMock, patch
from uuid import uuid4

from app.services.graph_documents import (
    GRAPH_DOCUMENT_ROOT,
    _ensure_person,
    build_expedient_folder_path,
    complete_upload_session,
    prepare_expedient,
    register_upload_session,
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

    @patch("app.services.graph_documents.get_graph_database_connection")
    def test_english_can_register_a_two_gb_upload_session(self, database: MagicMock) -> None:
        connection = MagicMock()
        cursor = MagicMock()
        cursor.execute.return_value.fetchval.return_value = 1
        connection.cursor.return_value = cursor
        database.return_value.__enter__.return_value = connection

        register_upload_session(
            session_id=uuid4(),
            expedient_graph_id=10,
            document_type_code="EVIDENCIA_EXAMEN_INGLES",
            original_filename="parcial.mp4",
            cloud_filename="parcial.mp4",
            graph_path="EXPEDIENTES ESTUDIANTILES/ESTUDIANTE/IDIOMAS/parcial.mp4",
            content_type="video/mp4",
            expected_size=2 * 1024 * 1024 * 1024,
            upload_url="https://graph.example/upload",
            expires_at=None,
            audit_user="docente",
            max_expected_size=2 * 1024 * 1024 * 1024,
        )

        connection.commit.assert_called_once()

    def test_upload_session_rejects_files_above_its_module_limit(self) -> None:
        with self.assertRaisesRegex(ValueError, "2 GB"):
            register_upload_session(
                session_id=uuid4(),
                expedient_graph_id=10,
                document_type_code="EVIDENCIA_EXAMEN_INGLES",
                original_filename="parcial.mp4",
                cloud_filename="parcial.mp4",
                graph_path="EXPEDIENTES ESTUDIANTILES/ESTUDIANTE/IDIOMAS/parcial.mp4",
                content_type="video/mp4",
                expected_size=(2 * 1024 * 1024 * 1024) + 1,
                upload_url="https://graph.example/upload",
                expires_at=None,
                audit_user="docente",
                max_expected_size=2 * 1024 * 1024 * 1024,
            )

    def test_graph_identity_writes_are_safe_with_audit_triggers(self) -> None:
        person_source = getsource(_ensure_person)
        expedient_source = getsource(prepare_expedient)
        document_source = getsource(complete_upload_session)

        self.assertIn(
            "OUTPUT INSERTED.PersonaGraphRefId INTO @PersonaResultado",
            person_source,
        )
        self.assertIn(
            "OUTPUT INSERTED.ExpedienteGraphId INTO @ExpedienteResultado",
            expedient_source,
        )
        self.assertIn(
            "OUTPUT INSERTED.DocumentoGraphId INTO @DocumentoResultado",
            document_source,
        )


if __name__ == "__main__":
    unittest.main()
