import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi import HTTPException

from app.routers.modality_change_requests import (
    _GRADE_FIELDS,
    ModalityChangePreviewPayload,
    _build_subject_migration_plan,
    _enroll_all_subjects,
    _ensure_single_header,
    _migrate_subjects,
    _preview_with_cursor,
    _read_supporting_pdfs,
    _transformed_grade_values,
    _validate_pdf_content,
    _write_target_subject,
)


def preview_payload() -> ModalityChangePreviewPayload:
    return ModalityChangePreviewPayload(
        codigo_estud=491,
        carrera_destino=3,
        codigo_periodo_homologacion=1056,
    )


class MemoryUpload:
    def __init__(self, filename: str, content: bytes, content_type: str = "application/pdf") -> None:
        self.filename = filename
        self.content_type = content_type
        self._content = content
        self.closed = False

    async def read(self, size: int = -1) -> bytes:
        return self._content if size < 0 else self._content[:size]

    async def close(self) -> None:
        self.closed = True


class ModalityChangeDocumentUploadTests(unittest.IsolatedAsyncioTestCase):
    async def test_multiple_pdf_documents_are_validated_and_ordered(self) -> None:
        uploads = [
            MemoryUpload("solicitud.pdf", b"%PDF-1.7\nsolicitud"),
            MemoryUpload("resolucion.pdf", b"%PDF-1.7\nresolucion"),
        ]

        result = await _read_supporting_pdfs(uploads)  # type: ignore[arg-type]

        self.assertEqual([item["orden"] for item in result], [1, 2])
        self.assertEqual(
            [item["nombre_original"] for item in result],
            ["solicitud.pdf", "resolucion.pdf"],
        )
        self.assertTrue(all(upload.closed for upload in uploads))

    async def test_duplicate_pdf_content_is_rejected(self) -> None:
        content = b"%PDF-1.7\nmismo-contenido"
        uploads = [
            MemoryUpload("uno.pdf", content),
            MemoryUpload("dos.pdf", content),
        ]

        with self.assertRaises(HTTPException) as context:
            await _read_supporting_pdfs(uploads)  # type: ignore[arg-type]

        self.assertEqual(context.exception.status_code, 422)
        self.assertIn("repetido", str(context.exception.detail))
        self.assertTrue(all(upload.closed for upload in uploads))

    async def test_more_than_ten_documents_is_rejected(self) -> None:
        uploads = [
            MemoryUpload(f"respaldo-{index}.pdf", f"%PDF-1.7\n{index}".encode())
            for index in range(11)
        ]

        with self.assertRaises(HTTPException) as context:
            await _read_supporting_pdfs(uploads)  # type: ignore[arg-type]

        self.assertEqual(context.exception.status_code, 422)
        self.assertIn("hasta 10", str(context.exception.detail))
        self.assertTrue(all(upload.closed for upload in uploads))


class ModalityChangePreviewTests(unittest.TestCase):
    @patch(
        "app.routers.modality_change_requests._fetch_source_enrollments",
        return_value=[
            {
                "data": {"codigo_materia": 11, "PromedioFinal": 8.75, "num": 501},
                "codigo_materia": 11,
                "codigo_comun": "MAT-133",
                "codigo_normalizado": "MAT-133",
                "nombre": "Materia uno anterior",
                "nota_final": 8.75,
                "tiene_notas": True,
                "num": 501,
            }
        ],
    )
    @patch(
        "app.routers.modality_change_requests._existing_target_subjects",
        return_value={134: 1},
    )
    @patch(
        "app.routers.modality_change_requests._fetch_target_subjects",
        return_value=[
            {
                "codigo_materia": 133,
                "codigo_comun": "MAT-133",
                "nombre": "Materia uno",
                "nivel": 1,
                "creditos": 3.0,
            },
            {
                "codigo_materia": 134,
                "codigo_comun": "MAT-134",
                "nombre": "Materia dos",
                "nivel": 1,
                "creditos": 4.0,
            },
        ],
    )
    @patch(
        "app.routers.modality_change_requests._fetch_enrollment_period",
        side_effect=lambda _cursor, code: (
            {"codigo": 1056, "nombre": "HOMOLOGACION", "tipo": "H"}
            if code == 1056
            else {"codigo": 1060, "nombre": "REGULAR", "tipo": "R"}
        ),
    )
    @patch(
        "app.routers.modality_change_requests._fetch_modality",
        return_value={
            "codigo": 1,
            "nombre": "En linea",
            "jornada_codigo": 2,
            "jornada_nombre": "Nocturno",
        },
    )
    @patch(
        "app.routers.modality_change_requests._fetch_career",
        return_value={"codigo": 3, "nombre": "Administracion"},
    )
    @patch(
        "app.routers.modality_change_requests._fetch_student_context",
        return_value={
            "codigo_estud": 491,
            "carrera": 3,
            "carrera_nombre": "Administracion",
            "modalidad": 1,
            "modalidad_nombre": "En linea",
            "jornada_codigo": 2,
            "jornada_nombre": "Nocturno",
            "periodo": 1060,
        },
    )
    def test_preview_keeps_same_career_and_builds_one_header_for_all_subjects(
        self,
        _student_mock: MagicMock,
        _career_mock: MagicMock,
        _modality_mock: MagicMock,
        _period_mock: MagicMock,
        _subjects_mock: MagicMock,
        _existing_mock: MagicMock,
        _source_mock: MagicMock,
    ) -> None:
        cursor = MagicMock()
        cursor.fetchone.return_value = (0,)

        result = _preview_with_cursor(cursor, preview_payload())

        self.assertEqual(result["target_career"]["codigo"], result["student"]["carrera"])
        self.assertEqual(result["target_modality"]["codigo"], result["student"]["modalidad"])
        self.assertEqual(result["target_modality"]["jornada_nombre"], "Nocturno")
        self.assertEqual(result["summary"]["materias_pensum"], 2)
        self.assertEqual(result["summary"]["materias_a_migrar"], 1)
        self.assertEqual(result["summary"]["materias_por_matricular"], 0)
        self.assertEqual(result["summary"]["materias_existentes"], 1)
        self.assertEqual(result["summary"]["cabeceras_a_crear"], 1)
        self.assertEqual(
            [item["estado"] for item in result["subjects"]],
            ["MIGRAR", "EXISTENTE"],
        )

    @patch(
        "app.routers.modality_change_requests._fetch_enrollment_period",
        return_value={"codigo": 1056, "nombre": "HOMOLOGACION", "tipo": "H"},
    )
    @patch(
        "app.routers.modality_change_requests._fetch_modality",
        return_value={"codigo": 1, "nombre": "En linea"},
    )
    @patch(
        "app.routers.modality_change_requests._fetch_career",
        return_value={"codigo": 3, "nombre": "Administracion"},
    )
    @patch(
        "app.routers.modality_change_requests._fetch_student_context",
        return_value={"codigo_estud": 491, "carrera": 3, "modalidad": None},
    )
    def test_preview_requires_modality_in_previous_enrollment(
        self,
        _student_mock: MagicMock,
        _career_mock: MagicMock,
        _modality_mock: MagicMock,
        _period_mock: MagicMock,
    ) -> None:
        with self.assertRaises(HTTPException) as context:
            _preview_with_cursor(MagicMock(), preview_payload())

        self.assertEqual(context.exception.status_code, 409)
        self.assertIn("período anterior", str(context.exception.detail))

    def test_supporting_document_must_be_a_real_pdf(self) -> None:
        _validate_pdf_content("respaldo.pdf", "application/pdf", b"%PDF-1.7\ncontenido")

        with self.assertRaises(HTTPException):
            _validate_pdf_content("respaldo.pdf", "application/pdf", b"contenido")


class ModalityChangeEnrollmentTests(unittest.TestCase):
    @patch(
        "app.routers.modality_change_requests._find_target_subject",
        return_value={"num": 900, "Num_Matricula": 2, "PromedioFinal": 9.5},
    )
    def test_existing_higher_destination_grade_is_not_overwritten(
        self,
        _target_mock: MagicMock,
    ) -> None:
        cursor = MagicMock()
        result = _write_target_subject(
            cursor,
            request_item={
                "codigo_estud": 491,
                "carrera_destino": 3,
                "codigo_periodo_homologacion": 1056,
            },
            subject={"codigo_materia": 133, "creditos": 3},
            source={"data": {"PromedioFinal": 8.5}},
            user_code="61",
            source_period_type="R",
            target_period_type="H",
        )

        update_sql = " ".join(cursor.execute.call_args.args[0].split())
        self.assertNotIn("[PromedioFinal]", update_sql)
        self.assertEqual(result["estado"], "MIGRADA")
        self.assertFalse(result["created"])
        self.assertIn("nota superior", result["observacion"])

    def test_regular_grade_keeps_its_final_with_homologation_40_60_weights(self) -> None:
        values = _transformed_grade_values(
            {"PromedioFinal": 8.5, "P1Tareas": 9},
            "R",
            "H",
        )

        self.assertEqual(values["teoriaHomo"], 8.5)
        self.assertEqual(values["practicahomo"], 8.5)
        theory_contribution = round(values["teoriaHomo"] * 0.40, 3)
        practice_contribution = round(values["practicahomo"] * 0.60, 3)
        self.assertEqual(theory_contribution, 3.4)
        self.assertEqual(practice_contribution, 5.1)
        self.assertEqual(theory_contribution + practice_contribution, 8.5)
        self.assertEqual(values["PromedioFinal"], 8.5)

    def test_homologation_grade_is_projected_to_all_regular_partials(self) -> None:
        values = _transformed_grade_values(
            {"teoriaHomo": 8, "practicahomo": 9},
            "H",
            "R",
        )

        self.assertEqual(values["PromedioFinal"], 8.6)
        self.assertTrue(all(values[field] == 8.6 for field in ("P1Tareas", "P2Examen", "promP3")))

    def test_regular_destination_only_includes_common_codes_and_existing_rows(self) -> None:
        source = {
            "data": {"codigo_materia": 11, "PromedioFinal": 9, "num": 10},
            "codigo_materia": 11,
            "codigo_comun": "UNI-01",
            "codigo_normalizado": "UNI-01",
            "nombre": "Origen",
            "nota_final": 9,
            "tiene_notas": True,
            "num": 10,
        }
        planned, unmatched = _build_subject_migration_plan(
            target_subjects=[
                {"codigo_materia": 21, "codigo_comun": "UNI-01", "nombre": "Uno"},
                {"codigo_materia": 22, "codigo_comun": "OTRA", "nombre": "Dos"},
                {"codigo_materia": 23, "codigo_comun": "EXISTE", "nombre": "Tres"},
            ],
            source_rows=[source],
            existing={23: 2},
            target_period_type="R",
        )

        self.assertEqual([item["codigo_materia"] for item in planned], [21, 23])
        self.assertEqual([item["estado"] for item in planned], ["MIGRAR", "EXISTENTE"])
        self.assertEqual(unmatched, [])

    def test_failed_common_subject_is_planned_as_repetition_without_grade_migration(self) -> None:
        source = {
            "data": {"codigo_materia": 11, "PromedioFinal": 6.99, "num": 10},
            "codigo_materia": 11,
            "codigo_comun": "UNI-01",
            "codigo_normalizado": "UNI-01",
            "nombre": "Origen reprobada",
            "nota_final": 6.99,
            "tiene_notas": True,
            "num": 10,
        }

        planned, unmatched = _build_subject_migration_plan(
            target_subjects=[
                {"codigo_materia": 21, "codigo_comun": "UNI-01", "nombre": "Destino"},
            ],
            source_rows=[source],
            existing={},
            target_period_type="R",
        )

        self.assertEqual(len(planned), 1)
        self.assertEqual(planned[0]["estado"], "REPETIR")
        self.assertIsNone(planned[0]["materia_origen"])
        self.assertEqual(planned[0]["nota_origen"], 6.99)
        self.assertTrue(planned[0]["requiere_repeticion"])
        self.assertEqual(unmatched, [])

    def test_grade_seven_is_planned_for_migration(self) -> None:
        source = {
            "data": {"codigo_materia": 11, "PromedioFinal": 7, "num": 10},
            "codigo_materia": 11,
            "codigo_comun": "UNI-01",
            "codigo_normalizado": "UNI-01",
            "nombre": "Origen aprobada",
            "nota_final": 7,
            "tiene_notas": True,
            "num": 10,
        }

        planned, _unmatched = _build_subject_migration_plan(
            target_subjects=[
                {"codigo_materia": 21, "codigo_comun": "UNI-01", "nombre": "Destino"},
            ],
            source_rows=[source],
            existing={},
            target_period_type="R",
        )

        self.assertEqual(planned[0]["estado"], "MIGRAR")
        self.assertEqual(planned[0]["materia_origen"], 11)
        self.assertFalse(planned[0]["requiere_repeticion"])

    @patch(
        "app.routers.modality_change_requests._next_subject_attempt",
        return_value=2,
    )
    @patch(
        "app.routers.modality_change_requests._find_target_subject",
        return_value=None,
    )
    def test_failed_source_is_written_as_clean_repetition(
        self,
        _target_mock: MagicMock,
        _attempt_mock: MagicMock,
    ) -> None:
        cursor = MagicMock()
        result = _write_target_subject(
            cursor,
            request_item={
                "codigo_estud": 491,
                "carrera_destino": 3,
                "codigo_periodo_homologacion": 1056,
            },
            subject={"codigo_materia": 133, "creditos": 3, "nota_origen": 6.99},
            source={
                "data": {
                    "PromedioFinal": 6.99,
                    "P1Tareas": 8,
                    "Num_Matricula": 3,
                },
                "codigo_materia": 11,
            },
            user_code="61",
            source_period_type="R",
            target_period_type="H",
        )

        insert_call = next(
            call
            for call in cursor.execute.call_args_list
            if "INSERT INTO dbo.CARRERAXESTUD" in call.args[0]
        )
        inserted_values = insert_call.args[1:]
        grade_values = inserted_values[7 : 7 + len(_GRADE_FIELDS)]
        self.assertTrue(all(value is None for value in grade_values))
        self.assertEqual(inserted_values[4], 4)
        self.assertEqual(result["estado"], "MATRICULADA")
        self.assertFalse(result["origen_mapeado"])
        self.assertTrue(result["requiere_repeticion"])
        self.assertIn("reprobada", result["observacion"].lower())

    @patch("app.routers.modality_change_requests._write_target_subject")
    def test_repetition_recovers_source_only_to_increment_the_attempt(
        self,
        write_mock: MagicMock,
    ) -> None:
        source = {
            "data": {"PromedioFinal": 6, "Num_Matricula": 2},
            "codigo_materia": 11,
            "codigo_comun": "UNI-01",
            "codigo_normalizado": "UNI-01",
            "nota_final": 6,
            "num": 10,
        }
        write_mock.return_value = {"codigo_materia": 21}

        _migrate_subjects(
            MagicMock(),
            request_item={"tipo_periodo_origen": "R", "tipo_periodo_destino": "H"},
            subjects=[
                {
                    "codigo_materia": 21,
                    "codigo_comun": "UNI-01",
                    "codigo_comun_origen": "UNI-01",
                    "materia_origen": None,
                    "nota_origen": 6,
                    "nombre": "Destino",
                }
            ],
            source_rows=[source],
            user_code="61",
        )

        self.assertIs(write_mock.call_args.kwargs["source"], source)

    def test_existing_header_is_reused_instead_of_inserted(self) -> None:
        cursor = MagicMock()
        cursor.fetchone.return_value = SimpleNamespace(Num_Matricula=1)
        request_item = {
            "codigo_estud": 491,
            "carrera_destino": 3,
            "codigo_periodo_homologacion": 1056,
        }

        created, number = _ensure_single_header(
            cursor,
            request_item,
            {
                "codigo": 3,
                "jornada_codigo": 1,
                "jornada_nombre": "Matutino",
            },
            "H",
        )

        statements = [" ".join(call.args[0].split()).upper() for call in cursor.execute.call_args_list]
        self.assertFalse(created)
        self.assertEqual(number, 1)
        self.assertEqual(sum("INSERT INTO DBO.CABECERA_MATRICULA" in sql for sql in statements), 0)
        self.assertEqual(sum("UPDATE DBO.CABECERA_MATRICULA" in sql for sql in statements), 1)

    @patch(
        "app.routers.modality_change_requests._next_subject_attempt",
        return_value=2,
    )
    @patch(
        "app.routers.modality_change_requests._existing_target_subjects",
        return_value={133: 1},
    )
    def test_enrollment_skips_existing_subject_and_inserts_each_missing_subject_once(
        self,
        _existing_mock: MagicMock,
        next_attempt_mock: MagicMock,
    ) -> None:
        cursor = MagicMock()
        request_item = {
            "codigo_estud": 491,
            "carrera_destino": 3,
            "codigo_periodo_homologacion": 1056,
        }
        subjects = [
            {"codigo_materia": 133, "creditos": 3},
            {"codigo_materia": 134, "creditos": 4},
        ]

        result = _enroll_all_subjects(cursor, request_item, subjects, "61", "H")

        statements = [" ".join(call.args[0].split()).upper() for call in cursor.execute.call_args_list]
        self.assertEqual(sum("INSERT INTO DBO.CARRERAXESTUD" in sql for sql in statements), 1)
        self.assertEqual(sum("UPDATE DBO.CARRERAXESTUD" in sql for sql in statements), 1)
        self.assertEqual([item["estado"] for item in result], ["EXISTENTE", "MATRICULADA"])
        next_attempt_mock.assert_called_once_with(cursor, 491, 3, 134)

    @patch(
        "app.routers.modality_change_requests._next_subject_attempt",
        return_value=1,
    )
    @patch(
        "app.routers.modality_change_requests._existing_target_subjects",
        return_value={},
    )
    def test_regular_period_uses_normal_enrollment_type_and_active_control(
        self,
        _existing_mock: MagicMock,
        _next_attempt_mock: MagicMock,
    ) -> None:
        cursor = MagicMock()
        request_item = {
            "codigo_estud": 491,
            "carrera_destino": 3,
            "codigo_periodo_homologacion": 1050,
        }

        result = _enroll_all_subjects(
            cursor,
            request_item,
            [{"codigo_materia": 133, "creditos": 3}],
            "61",
            "R",
        )

        insert_call = next(
            call
            for call in cursor.execute.call_args_list
            if "INSERT INTO dbo.CARRERAXESTUD" in call.args[0]
        )
        self.assertEqual(insert_call.args[-3:], ("N", 1, "61"))
        self.assertEqual(result[0]["estado"], "MATRICULADA")
        self.assertIn("período regular", result[0]["observacion"])


if __name__ == "__main__":
    unittest.main()
