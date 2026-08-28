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
    upload_bytes,
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
            "BECAS": "BECAS",
            "INGLES": "IDIOMAS",
            "TITULACION": "TITULACION",
            "PRACTICAS": "PRACTICAS PREPROFESIONALES",
            "VINCULACION": "VINCULACION CON LA SOCIEDAD",
            "FACTURACION": "FACTURAS",
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

    @patch("app.services.graph_documents._auth_headers", return_value={"Authorization": "Bearer test"})
    @patch("app.services.graph_documents._item_path_url", return_value="https://graph.example/file")
    @patch("app.services.graph_documents.httpx.Client")
    def test_upload_bytes_uses_simple_upload_for_signed_pdf(
        self,
        client_factory: MagicMock,
        _item_path: MagicMock,
        _headers: MagicMock,
    ) -> None:
        client = client_factory.return_value.__enter__.return_value
        response = client.put.return_value
        response.json.return_value = {"id": "pdf-1"}

        result = upload_bytes("DOCENTES/docente/informe.pdf", b"%PDF-test", "application/pdf")

        self.assertEqual(result["id"], "pdf-1")
        client.put.assert_called_once_with(
            "https://graph.example/file:/content",
            headers={"Authorization": "Bearer test", "Content-Type": "application/pdf"},
            content=b"%PDF-test",
        )
        response.raise_for_status.assert_called_once()

    @patch("app.services.graph_documents.GRAPH_UPLOAD_CHUNK_BYTES", 4)
    @patch("app.services.graph_documents.GRAPH_SIMPLE_UPLOAD_MAX_BYTES", 5)
    @patch(
        "app.services.graph_documents.create_upload_session",
        return_value={"uploadUrl": "https://graph.example/session"},
    )
    @patch("app.services.graph_documents.httpx.Client")
    def test_upload_bytes_uses_a_session_for_large_archive(
        self,
        client_factory: MagicMock,
        _session: MagicMock,
    ) -> None:
        client = client_factory.return_value.__enter__.return_value
        first_response = MagicMock(status_code=202)
        second_response = MagicMock(status_code=202)
        final_response = MagicMock(status_code=201)
        final_response.json.return_value = {"id": "zip-1"}
        client.put.side_effect = [first_response, second_response, final_response]

        result = upload_bytes("DOCENTES/docente/documentos.zip", b"abcdefghij", "application/zip")

        self.assertEqual(result["id"], "zip-1")
        self.assertEqual(client.put.call_count, 3)
        self.assertEqual(
            client.put.call_args_list[-1].kwargs["headers"]["Content-Range"],
            "bytes 8-9/10",
        )


if __name__ == "__main__":
    unittest.main()
