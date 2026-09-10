import unittest
from inspect import getsource
from unittest.mock import patch

from app.routers import document_expedients, english_exams, titulacion
from app.services import english_approval, graph_documents


def _graph_row(code: str, status: str, document_id: int) -> dict[str, object]:
    return {
        "TipoExpedienteGraphCodigo": "INGLES",
        "TipoDocumentoCodigo": code,
        "DocumentoGraphId": document_id,
        "EstadoDocumentoGraphCodigo": status,
        "NombreArchivo": f"{code.lower()}.pdf",
        "VersionActual": 1,
        "UsuarioCarga": "secretaria@intec.edu.ec",
    }


class EnglishApprovalDocumentTests(unittest.TestCase):
    def test_catalog_requires_exactly_three_pdf_documents(self) -> None:
        codes = [item["code"] for item in english_approval.ENGLISH_APPROVAL_DOCUMENT_TYPES]

        self.assertEqual(
            codes,
            [
                "CERTIFICADO_APROBACION_INGLES",
                "ACTA_CALIFICACIONES_INGLES",
                "EVIDENCIA_EXAMEN_INGLES",
            ],
        )
        self.assertEqual(document_expedients._ENGLISH_DOCUMENT_TYPES, [dict(item) for item in english_approval.ENGLISH_APPROVAL_DOCUMENT_TYPES])
        for code in codes:
            self.assertEqual(document_expedients._PDF_FILE_EXTENSIONS[code], ".pdf")

    @patch("app.services.english_approval._english_grade")
    @patch("app.services.english_approval.list_documents")
    def test_approval_requires_grade_and_all_three_validated_documents(
        self,
        list_documents_mock,
        grade_mock,
    ) -> None:
        list_documents_mock.return_value = [
            _graph_row(code, "VALIDADO", index)
            for index, code in enumerate(english_approval.ENGLISH_APPROVAL_DOCUMENT_CODES, start=1)
        ]
        grade_mock.return_value = {
            "found": True,
            "exam_id": 10,
            "final_grade": 8.5,
            "status": "APROBADO",
            "approved": True,
        }

        result = english_approval.english_approval_status("085-057-5739")

        self.assertTrue(result["approved"])
        self.assertEqual(result["status"], "APROBADO")
        self.assertEqual(result["validated_count"], 3)
        list_documents_mock.assert_called_once_with("0850575739")

    @patch("app.services.english_approval._english_grade")
    @patch("app.services.english_approval.list_documents")
    def test_loaded_documents_remain_pending_until_each_is_reviewed(
        self,
        list_documents_mock,
        grade_mock,
    ) -> None:
        codes = list(english_approval.ENGLISH_APPROVAL_DOCUMENT_CODES)
        list_documents_mock.return_value = [
            _graph_row(codes[0], "VALIDADO", 1),
            _graph_row(codes[1], "CARGADO", 2),
            _graph_row(codes[2], "CARGADO", 3),
        ]
        grade_mock.return_value = {
            "found": True,
            "exam_id": 10,
            "final_grade": 9.0,
            "status": "APROBADO",
            "approved": True,
        }

        result = english_approval.english_approval_status("0850575739")

        self.assertFalse(result["approved"])
        self.assertEqual(result["status"], "EN_REVISION")
        self.assertEqual(result["uploaded_count"], 3)
        self.assertEqual(result["validated_count"], 1)

    @patch("app.services.english_approval._english_grade")
    @patch("app.services.english_approval.list_documents")
    def test_validated_documents_do_not_bypass_a_pending_grade(
        self,
        list_documents_mock,
        grade_mock,
    ) -> None:
        list_documents_mock.return_value = [
            _graph_row(code, "VALIDADO", index)
            for index, code in enumerate(english_approval.ENGLISH_APPROVAL_DOCUMENT_CODES, start=1)
        ]
        grade_mock.return_value = {
            "found": True,
            "exam_id": 10,
            "final_grade": 6.5,
            "status": "REPROBADO",
            "approved": False,
        }

        result = english_approval.english_approval_status("0850575739")

        self.assertFalse(result["approved"])
        self.assertEqual(result["status"], "PENDIENTE_NOTA")

    def test_graph_review_is_scoped_and_observation_is_required(self) -> None:
        source = getsource(graph_documents.review_document)

        self.assertIn('review_status == "OBSERVADO" and not detail', source)
        self.assertIn("allowed_types", source)
        self.assertIn("NumeroIdentificacion", source)
        self.assertIn("TipoExpedienteGraphCodigo", source)
        self.assertIn("DOCUMENTO_VALIDADO", source)
        self.assertIn("DOCUMENTO_OBSERVADO", source)

    def test_grade_publication_and_titulation_use_documental_rule(self) -> None:
        english_sync_source = getsource(english_exams._sync_titulation_english)
        titulation_save_source = getsource(titulacion.save_titulacion_notas)

        self.assertIn("sync_titulation_english_approval", english_sync_source)
        self.assertIn("english_approval_status", titulation_save_source)
        self.assertIn("No se puede aprobar Inglés A2+", titulation_save_source)


if __name__ == "__main__":
    unittest.main()
