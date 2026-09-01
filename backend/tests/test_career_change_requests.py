import unittest
from datetime import date, datetime, time
from decimal import Decimal
from unittest.mock import patch

from fastapi import HTTPException

from app.routers.career_change_requests import (
    _archive_supporting_document,
    _build_equivalence_preview,
    _decode_snapshot_data,
    _normalize_subject_name,
    _restore_snapshot_rows,
    _snapshot_row,
    _subject_similarity,
    _validate_pdf_content,
)


def source_subject(
    code: int,
    common_code: str,
    name: str,
    grade: float,
) -> dict[str, object]:
    return {
        "codigo_materia": code,
        "codigo_comun": common_code,
        "nombre": name,
        "nivel": 1,
        "creditos": 3,
        "carrera": 4,
        "periodo": 1050,
        "periodo_nombre": "C1-2026-PC",
        "nota_final": grade,
    }


def target_subject(code: int, common_code: str, name: str) -> dict[str, object]:
    return {
        "codigo_materia": code,
        "codigo_comun": common_code,
        "nombre": name,
        "nivel": 1,
        "creditos": 3,
    }


class CareerChangeEquivalenceTests(unittest.TestCase):
    def test_normalizes_accents_and_non_significant_words(self) -> None:
        self.assertEqual(
            _normalize_subject_name("Gestión de la Información"),
            "GESTION INFORMACION",
        )

    def test_common_subject_code_has_priority(self) -> None:
        preview = _build_equivalence_preview(
            [source_subject(10, "VGA-ES-2023-10", "Materia anterior", 8.5)],
            [target_subject(80, "vga-es-2023-10", "Materia destino")],
        )

        self.assertEqual(len(preview["matches"]), 1)
        match = preview["matches"][0]
        self.assertEqual(match["tipo_coincidencia"], "CODIGO_EXACTO")
        self.assertTrue(match["seleccion_recomendada"])

    def test_exact_normalized_name_is_recommended(self) -> None:
        preview = _build_equivalence_preview(
            [source_subject(11, "", "Administración de la Base de Datos", 9)],
            [target_subject(81, "", "Administracion Base Datos")],
        )

        match = preview["matches"][0]
        self.assertEqual(match["tipo_coincidencia"], "NOMBRE_EXACTO")
        self.assertTrue(match["seleccion_recomendada"])

    def test_similar_name_requires_manual_confirmation(self) -> None:
        self.assertGreaterEqual(
            _subject_similarity("Programación orientada a objetos", "Programación orientada objetos I"),
            0.84,
        )
        preview = _build_equivalence_preview(
            [source_subject(12, "", "Programación orientada a objetos", 8)],
            [target_subject(82, "", "Programación orientada objetos I")],
        )

        match = preview["matches"][0]
        self.assertEqual(match["tipo_coincidencia"], "NOMBRE_SIMILAR")
        self.assertFalse(match["seleccion_recomendada"])

    def test_failed_subject_is_not_proposed_for_equivalence(self) -> None:
        preview = _build_equivalence_preview(
            [source_subject(13, "MAT-01", "Matemática", 6.99)],
            [target_subject(83, "MAT-01", "Matemática")],
        )

        self.assertEqual(preview["matches"], [])
        self.assertEqual(preview["summary"]["aprobadas_origen"], 0)
        self.assertEqual(len(preview["unmatched_targets"]), 1)

    def test_validates_pdf_extension_signature_and_size(self) -> None:
        _validate_pdf_content("respaldo.pdf", "application/pdf", b"%PDF-1.7\ncontenido")

        invalid_cases = (
            ("respaldo.txt", "text/plain", b"%PDF-1.7"),
            ("respaldo.pdf", "application/pdf", b"contenido"),
            ("respaldo.pdf", "application/pdf", b""),
        )
        for filename, content_type, content in invalid_cases:
            with self.subTest(filename=filename, content=content):
                with self.assertRaises(HTTPException):
                    _validate_pdf_content(filename, content_type, content)

    @patch("app.routers.career_change_requests.set_document_origin")
    @patch("app.routers.career_change_requests.complete_upload_session")
    @patch("app.routers.career_change_requests.upload_bytes")
    @patch("app.routers.career_change_requests.register_upload_session")
    @patch("app.routers.career_change_requests.ensure_folder")
    @patch("app.routers.career_change_requests.prepare_expedient")
    def test_archives_support_in_existing_student_expedient(
        self,
        prepare_expedient_mock,
        ensure_folder_mock,
        register_upload_session_mock,
        upload_bytes_mock,
        complete_upload_session_mock,
        set_document_origin_mock,
    ) -> None:
        prepare_expedient_mock.return_value = {
            "expedient_graph_id": 91,
            "folder_path": (
                "EXPEDIENTES ESTUDIANTILES/ESTUDIANTE PRUEBA - 1724036536/"
                "SOLICITUDES/CASO 45 - CAMBIO-CARRERA-45"
            ),
        }
        upload_bytes_mock.return_value = {
            "id": "graph-item-1",
            "webUrl": "https://example.test/respaldo.pdf",
        }
        complete_upload_session_mock.return_value = {
            "document_graph_id": 321,
            "graph_web_url": "https://example.test/respaldo.pdf",
        }

        result = _archive_supporting_document(
            request_id=45,
            student={
                "cedula": "1724036536",
                "codigo_estud": 77,
                "estudiante": "ESTUDIANTE PRUEBA",
                "correo": "estudiante@intec.edu.ec",
            },
            original_filename="solicitud firmada.pdf",
            content=b"%PDF-1.7\ncontenido",
            audit_user="academico@intec.edu.ec",
        )

        prepare_expedient_mock.assert_called_once_with(
            module_code="SOLICITUDES",
            identification="1724036536",
            student_code=77,
            student_name="ESTUDIANTE PRUEBA",
            student_email="estudiante@intec.edu.ec",
            base_origin="INTEC_INTEGRACION_CONTROL",
            schema_origin="sol",
            table_origin="SolicitudCambioCarrera",
            origin_id=45,
            expedient_code="CAMBIO-CARRERA-45",
            audit_user="academico@intec.edu.ec",
        )
        expected_folder = (
            "EXPEDIENTES ESTUDIANTILES/ESTUDIANTE PRUEBA - 1724036536/"
            "SOLICITUDES/CASO 45 - CAMBIO-CARRERA-45/CAMBIO DE CARRERA"
        )
        ensure_folder_mock.assert_called_once_with(expected_folder)
        self.assertEqual(result["document_id"], 321)
        self.assertTrue(result["graph_path"].startswith(f"{expected_folder}/"))
        register_upload_session_mock.assert_called_once()
        upload_bytes_mock.assert_called_once()
        complete_upload_session_mock.assert_called_once()
        set_document_origin_mock.assert_called_once_with(321, 45)


class CareerChangeBackupTests(unittest.TestCase):
    def test_snapshot_preserves_sql_compatible_values(self) -> None:
        original = {
            "codigo_estud": 77,
            "cod_anio_Basica": 4,
            "codigo_materia": 81,
            "Num_Matricula": 1,
            "paralelo": "A",
            "NumGrupo": 1,
            "PromedioFinal": Decimal("8.75"),
            "Fecha_Matricula": datetime(2026, 8, 31, 12, 30, 45),
            "FechaCertificado": date(2026, 8, 31),
            "HoraPrueba": time(9, 15, 30),
            "Contenido": b"\x00\x01respaldo",
        }

        snapshot = _snapshot_row("MATERIA", original)
        restored = _decode_snapshot_data(snapshot["datos_json"], snapshot["sha256"])

        self.assertEqual(restored, original)

    def test_snapshot_rejects_tampered_content(self) -> None:
        snapshot = _snapshot_row(
            "CABECERA",
            {"codigo_estud": 77, "cod_anio_Basica": 4, "codigo_periodo": 1050},
        )

        with self.assertRaises(HTTPException) as context:
            _decode_snapshot_data(
                snapshot["datos_json"].replace("1050", "1051"),
                snapshot["sha256"],
            )

        self.assertEqual(context.exception.status_code, 409)

    def test_restore_rejects_another_student_or_career(self) -> None:
        snapshot = _snapshot_row(
            "CABECERA",
            {"codigo_estud": 77, "cod_anio_Basica": 4, "codigo_periodo": 1050},
        )

        with self.assertRaises(HTTPException) as context:
            _restore_snapshot_rows(
                object(),
                [snapshot],
                expected_student=78,
                expected_career=4,
            )

        self.assertEqual(context.exception.status_code, 409)

    def test_restore_rejects_a_tampered_natural_key(self) -> None:
        snapshot = _snapshot_row(
            "CABECERA",
            {"codigo_estud": 77, "cod_anio_Basica": 4, "codigo_periodo": 1050},
        )
        snapshot["clave_natural"] = "[77,4,9999]"

        with self.assertRaises(HTTPException) as context:
            _restore_snapshot_rows(
                object(),
                [snapshot],
                expected_student=77,
                expected_career=4,
            )

        self.assertEqual(context.exception.status_code, 409)

    def test_restore_skips_rows_that_already_exist(self) -> None:
        class ExistingRowCursor:
            def execute(self, *_args: object) -> None:
                return None

            def fetchone(self) -> tuple[int]:
                return (1,)

        rows = [
            _snapshot_row(
                "CABECERA",
                {"codigo_estud": 77, "cod_anio_Basica": 4, "codigo_periodo": 1050},
            ),
            _snapshot_row(
                "MATERIA",
                {
                    "codigo_estud": 77,
                    "cod_anio_Basica": 4,
                    "codigo_materia": 81,
                    "Num_Matricula": 1,
                    "paralelo": "A",
                    "NumGrupo": 1,
                },
            ),
        ]

        result = _restore_snapshot_rows(
            ExistingRowCursor(),
            rows,
            expected_student=77,
            expected_career=4,
        )

        self.assertEqual(result["cabeceras_restauradas"], 0)
        self.assertEqual(result["materias_restauradas"], 0)
        self.assertEqual(result["existentes_omitidos"], 2)


if __name__ == "__main__":
    unittest.main()
