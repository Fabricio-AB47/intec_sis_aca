from datetime import datetime, timedelta, timezone
from io import BytesIO
import unittest
from unittest.mock import MagicMock, patch

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
import jwt
from pydantic import ValidationError
from pypdf import PdfReader

from app.core.config import get_settings
from app.core.security import SessionUser, get_current_user, require_screen_access
from app.routers import teacher_evaluation as evaluation
from app.routers import teacher_evaluation_history as history
from app.services.screen_access import ALL_PAGES, DEFAULT_ACCESS
from app.services.teacher_evaluation_generation import (
    GENERATION_POLICY_VERSION,
    GENERATION_PREFIX,
    acquire_self_evaluation_lock,
    decode_generation_metadata,
    encode_generation_metadata,
    generate_self_evaluation_answers,
    generation_report_notices,
)


def questions(count=20):
    return [{"id_pregunta": index + 1, "puntaje_min": 1, "puntaje_max": 5} for index in range(count)]


def actor(role="ADMINISTRADOR"):
    return SessionUser(login="administrador@intec.edu.ec", nombres="Administrador", id_usuario=95, rol=role)


def course(subject=31, teacher=12, key="materia"):
    return {"key": key, "codigo_materia": subject, "codigo_docente_eval": teacher,
            "codigo_periodo": 101, "detalle_periodo": "2023", "cod_jornada": "1", "paralelo": "PB1",
            "docente": "Docente vinculado", "cedula_docente": "0805755739"}


def plan(statuses=("PENDIENTE", "EXISTENTE")):
    return {"fingerprint": "valid", "instrument": {"Id_Instrumento": 7, "Id_Tipo_Evaluacion": 2},
            "items": [{"course": course(index + 31, key=str(index)), "status": status,
                       "answers": [{"id_pregunta": 1, "puntaje": 4}, {"id_pregunta": 2, "puntaje": 5}], "score_10": 9.0}
                      for index, status in enumerate(statuses)]}


def connection():
    conn = MagicMock()
    conn.__enter__.return_value = conn
    return conn


class GeneratedAnswersTests(unittest.TestCase):
    def test_score_range_and_valid_choices_for_many_seeds_and_sizes(self):
        for count in (2, 3, 17, 20, 45, 100, 199, 200, 201, 399, 400, 999, 1000):
            for seed in range(100):
                result = generate_self_evaluation_answers(questions(count), str(seed), "course")
                scores = [answer["puntaje"] for answer in result["answers"]]
                self.assertEqual(len(scores), count)
                self.assertTrue(set(scores) <= {4, 5})
                self.assertGreaterEqual(result["score_10"], 9)
                self.assertLess(result["score_10"], 10)
                self.assertIn(4, scores)
                self.assertGreaterEqual(sum(scores) / count * 2, 9)
                self.assertLess(evaluation._score_to_100(round(sum(scores) / count, 2)), 100)
                self.assertEqual(result["score_10"], round(evaluation._score_to_100(sum(scores) / count) / 10, 2))

    def test_single_question_cannot_meet_range_without_changing_scale(self):
        with self.assertRaisesRegex(ValueError, "al menos dos preguntas"):
            generate_self_evaluation_answers(questions(1), "seed", "course")

    def test_large_instrument_cannot_round_up_to_ten_even_at_highest_random_choice(self):
        count = 10001
        rng = MagicMock()
        rng.randint.side_effect = lambda _minimum, maximum: maximum
        with patch("app.services.teacher_evaluation_generation.random.Random", return_value=rng):
            result = generate_self_evaluation_answers(questions(count), "seed", "course")
        average = sum(answer["puntaje"] for answer in result["answers"]) / count
        self.assertGreaterEqual(result["score_10"], 9)
        self.assertLess(result["score_10"], 10)
        self.assertLess(evaluation._score_to_100(round(average, 2)), 100)

    def test_two_question_instrument_has_exact_nine(self):
        result = generate_self_evaluation_answers(questions(2), "seed", "course")
        self.assertEqual(result["score_10"], 9)
        self.assertEqual(sorted(answer["puntaje"] for answer in result["answers"]), [4, 5])

    def test_preview_and_confirmation_generate_same_answers(self):
        self.assertEqual(generate_self_evaluation_answers(questions(), "seed", "course"),
                         generate_self_evaluation_answers(questions(), "seed", "course"))

    def test_different_courses_do_not_all_receive_same_answers(self):
        values = {str(generate_self_evaluation_answers(questions(), "seed", str(key))) for key in range(20)}
        self.assertGreater(len(values), 1)

    def test_invalid_or_duplicate_questions_rejected(self):
        for data in ([], questions(1) * 2, [{"id_pregunta": 1, "puntaje_min": 0, "puntaje_max": 10}]):
            with self.subTest(data=data), self.assertRaises(ValueError):
                generate_self_evaluation_answers(data, "seed", "course")


class GenerationValidationTests(unittest.TestCase):
    def test_teacher_identity_preserves_leading_zeroes_and_normalizes_formatting(self):
        identity = history._teacher_identity({**course(), "cedula_docente": " 080-575 5739 ", "docente": " Docente vinculado "})
        self.assertEqual(identity, {"teacher_code": 12, "teacher_name": "Docente vinculado", "teacher_cedula": "0805755739"})

    def test_missing_teacher_identity_is_rejected(self):
        for cedula in (None, "", "  -  "):
            with self.subTest(cedula=cedula), self.assertRaises(HTTPException) as error:
                history._teacher_identity({**course(), "cedula_docente": cedula})
            self.assertEqual(error.exception.status_code, 400)
            self.assertIn("cédula", error.exception.detail)

    def test_missing_cedula_blocks_preview_before_loading_instrument(self):
        with (patch.object(history, "_validate_periods", return_value=[{"codigo_periodo": 101}]),
              patch.object(history, "_validate_teachers"),
              patch.object(history, "_historical_courses", return_value=[{**course(), "cedula_docente": None}]),
              patch.object(evaluation, "_fetch_question_rows") as instrument,
              self.assertRaises(HTTPException)):
            history._generation_plan(MagicMock(), MagicMock(), history.HistoricalSelfEvaluationSelection(periods=[101], teachers=[12]), "seed")
        instrument.assert_not_called()

    def test_selection_has_no_teacher_or_period_count_cap(self):
        teachers = list(range(1, 2502))
        periods = list(range(1, 1102))
        selection = history.HistoricalSelfEvaluationSelection(periods=periods, teachers=teachers)
        self.assertEqual(selection.teachers, teachers)
        self.assertEqual(selection.periods, periods)

    def test_large_teacher_selection_token_can_be_confirmed(self):
        selection = history.HistoricalSelfEvaluationSelection(periods=[101], teachers=list(range(100000000000000000, 100000000000002501)))
        token = history._preview_token(actor(), selection, "seed", "valid")
        self.assertGreater(len(token), 20000)
        payload = history.HistoricalSelfEvaluationConfirm(preview_token=token, confirmed=True, reason="Motivo administrativo")
        self.assertEqual(history._decode_preview_token(payload.preview_token, actor())["selection"]["teachers"], selection.teachers)

    def test_selection_is_sorted_and_duplicates_are_rejected(self):
        selection = history.HistoricalSelfEvaluationSelection(periods=[103, 101], teachers=[12, 11])
        self.assertEqual(selection.periods, [101, 103])
        for values in ([1, 1], [0], [-1], []):
            with self.subTest(values=values), self.assertRaises(ValidationError):
                history.HistoricalSelfEvaluationSelection(periods=values, teachers=[1])

    def test_reason_and_explicit_confirmation_are_required(self):
        for params in ({"confirmed": False, "reason": "Motivo administrativo"},
                       {"confirmed": True, "reason": " " * 12}):
            with self.subTest(params=params), self.assertRaises(ValidationError):
                history.HistoricalSelfEvaluationConfirm(preview_token="token", **params)

    def test_preview_token_is_bound_to_actor(self):
        token = history._preview_token(actor(), history.HistoricalSelfEvaluationSelection(periods=[101], teachers=[12]), "seed", "valid")
        self.assertEqual(history._decode_preview_token(token, actor())["fingerprint"], "valid")
        other = actor().model_copy(update={"login": "otro@intec.edu.ec"})
        with self.assertRaises(HTTPException):
            history._decode_preview_token(token, other)
        with self.assertRaises(HTTPException):
            history._decode_preview_token(token, actor("ACADEMICO"))

    def test_expired_or_tampered_preview_rejected(self):
        settings = get_settings()
        data = {"sub": actor().login, "actor_id": 95, "typ": "historical_self_evaluation_preview",
                "iss": settings.jwt_issuer, "aud": settings.jwt_audience, "jti": "expired",
                "iat": datetime.now(timezone.utc) - timedelta(hours=2),
                "nbf": datetime.now(timezone.utc) - timedelta(hours=2),
                "exp": datetime.now(timezone.utc) - timedelta(hours=1)}
        expired = jwt.encode(data, settings.signing_secret, algorithm="HS256")
        for token in (expired, "invalid.jwt.token"):
            with self.subTest(token=token), self.assertRaises(HTTPException):
                history._decode_preview_token(token, actor())

    def test_period_filter_uses_start_year_not_end_year(self):
        rows = [{"codigo_periodo": 1, "detalle_periodo": "2022 - 2023", "fecha_inicio": "2022-11-01"},
                {"codigo_periodo": 2, "detalle_periodo": "2025 - 2026", "fecha_inicio": "2025-11-01"},
                {"codigo_periodo": 3, "detalle_periodo": "C1-2024", "fecha_inicio": None},
                {"codigo_periodo": 4, "detalle_periodo": "2026", "fecha_inicio": "2026-01-01"}]
        cursor = MagicMock()
        cursor.fetchall.return_value = rows
        with patch.object(evaluation, "_row_dict", side_effect=lambda _cursor, row: row):
            self.assertEqual([row["codigo_periodo"] for row in history._historical_periods(cursor)], [2, 3])

    def test_nonhistorical_period_rejected(self):
        with patch.object(history, "_historical_periods", return_value=[{"codigo_periodo": 101}]), self.assertRaises(HTTPException):
            history._validate_periods(MagicMock(), [102])


class ActiveTeacherSelectionTests(unittest.TestCase):
    def test_teacher_query_uses_active_user_and_normalized_identity_without_duplicate_joins(self):
        cursor = MagicMock()
        cursor.fetchall.return_value = [{"codigo_doc": 12, "docente": "Docente activo", "cedula_doc": "1712345678", "codigo_periodo": 101}]
        with patch.object(evaluation, "_row_dict", side_effect=lambda _cursor, row: row):
            self.assertEqual(history._historical_teachers(cursor, [12, 13])[0]["codigo_doc"], 12)
        sql, *params = cursor.execute.call_args.args
        self.assertIn("SELECT 1 FROM dbo.USUARIOS teacher_user", sql)
        self.assertIn(evaluation._active_state_condition("teacher_user.Estado"), sql)
        self.assertIn("LTRIM(RTRIM(teacher_user.cedula))", sql)
        self.assertIn("LTRIM(RTRIM(dd.cedula_doc))", sql)
        self.assertIn("NULLIF", sql)
        self.assertNotIn("INNER JOIN dbo.USUARIOS", sql)
        self.assertEqual(params, [12, 13])

    def test_catalog_returns_only_active_teacher_query_without_quantity_caps(self):
        conn = connection()
        teachers = [{"codigo_doc": 12, "docente": "Activo", "cedula_doc": "1712345678"}]
        with (patch.object(history, "get_connection", return_value=conn),
              patch.object(history, "_historical_periods", return_value=[{"codigo_periodo": 101}]),
              patch.object(history, "_historical_teachers", return_value=teachers) as lookup):
            result = history.get_historical_self_evaluation_catalog(actor())
        self.assertEqual(result["teachers"], teachers)
        self.assertIsNone(result["max_teachers"])
        self.assertIsNone(result["max_applications"])
        lookup.assert_called_once_with(conn.cursor.return_value, periods=[101])

    def test_inactive_or_missing_teacher_blocks_whole_selection_before_loading_courses(self):
        selection = history.HistoricalSelfEvaluationSelection(periods=[101], teachers=[12, 13])
        with (patch.object(history, "_validate_periods", return_value=[{"codigo_periodo": 101}]),
              patch.object(history, "_historical_teachers", return_value=[{"codigo_doc": 12}]),
              patch.object(history, "_historical_courses") as courses,
              patch.object(evaluation, "_fetch_question_rows") as instrument,
              self.assertRaises(HTTPException) as error):
            history._generation_plan(MagicMock(), MagicMock(), selection, "seed")
        self.assertEqual(error.exception.status_code, 400)
        self.assertIn("inactivos", error.exception.detail)
        courses.assert_not_called()
        instrument.assert_not_called()

    def test_all_active_teachers_are_validated_in_a_single_query(self):
        cursor = MagicMock()
        teachers = list(range(1, 56))
        with patch.object(history, "_historical_teachers", return_value=[{"codigo_doc": code} for code in teachers]) as lookup:
            history._validate_teachers(cursor, teachers, [101, 102])
        lookup.assert_called_once_with(cursor, teachers, periods=[101, 102])

    def test_teacher_query_filters_periods_and_consolidates_assignments_without_duplicates(self):
        cursor = MagicMock()
        cursor.fetchall.return_value = [
            {"codigo_doc": 12, "docente": "Activo", "cedula_doc": "1712345678", "codigo_periodo": period}
            for period in (102, 101, 102)
        ]
        with patch.object(evaluation, "_row_dict", side_effect=lambda _cursor, row: row):
            teachers = history._historical_teachers(cursor, [12, 13], periods=[101, 102])
        sql, *params = cursor.execute.call_args.args
        self.assertIn("INNER JOIN dbo.CARRERAXDOCENTE cxd ON cxd.codigo_doc = dd.codigo_doc", sql)
        self.assertIn("cxd.codigo_periodo IN (?, ?)", sql)
        self.assertEqual(params, [12, 13, 101, 102])
        self.assertEqual(teachers, [{"codigo_doc": 12, "docente": "Activo", "cedula_doc": "1712345678", "periods": [101, 102]}])

    def test_catalog_without_historical_periods_has_no_teachers_or_assignment_queries(self):
        conn = connection()
        with patch.object(history, "get_connection", return_value=conn), patch.object(history, "_historical_periods", return_value=[]):
            result = history.get_historical_self_evaluation_catalog(actor())
        self.assertEqual(result["teachers"], [])
        conn.cursor.return_value.execute.assert_not_called()

    def test_teacher_with_no_classes_in_selected_period_is_rejected(self):
        cursor = MagicMock()
        with patch.object(history, "_historical_teachers", return_value=[]) as lookup, self.assertRaises(HTTPException) as error:
            history._validate_teachers(cursor, [12], [101])
        lookup.assert_called_once_with(cursor, [12], periods=[101])
        self.assertEqual(error.exception.status_code, 400)
        self.assertIn("sin clases asignadas", error.exception.detail)

    def test_course_query_also_excludes_inactive_teachers(self):
        cursor = MagicMock()
        cursor.fetchall.return_value = []
        self.assertEqual(history._historical_courses(cursor, [101], [12]), [])
        self.assertIn(history._active_teacher_condition("dd"), cursor.execute.call_args.args[0])


class DuplicateAndTransactionTests(unittest.TestCase):
    def test_new_campaign_returns_id_without_bypassing_audit_triggers(self):
        cursor = MagicMock()
        cursor.fetchone.side_effect = [None, [4]]
        result = evaluation._get_or_create_campaign(cursor, codigo_periodo=101, detalle_periodo="2023", flow="auto_docente")
        self.assertEqual(result, 4)
        sql, *params = cursor.execute.call_args.args
        self.assertIn("SET NOCOUNT ON;", sql)
        self.assertIn("DECLARE @CampaniaCreada TABLE (Id_Campania int NOT NULL)", sql)
        self.assertIn("OUTPUT INSERTED.Id_Campania INTO @CampaniaCreada (Id_Campania)", sql)
        self.assertIn("SELECT Id_Campania FROM @CampaniaCreada", sql)
        self.assertEqual(sql.count("?"), len(params))
        self.assertNotIn("DISABLE TRIGGER", sql)

    def test_existing_active_campaign_is_reused_without_insert(self):
        cursor = MagicMock()
        cursor.fetchone.return_value = [4]
        result = evaluation._get_or_create_campaign(cursor, codigo_periodo=101, detalle_periodo="2023", flow="auto_docente")
        self.assertEqual(result, 4)
        cursor.execute.assert_called_once()
        self.assertNotIn("INSERT", cursor.execute.call_args.args[0])

    def test_campaign_without_returned_id_stops_generation(self):
        cursor = MagicMock()
        cursor.fetchone.side_effect = [None, None]
        with self.assertRaises(HTTPException) as error:
            evaluation._get_or_create_campaign(cursor, codigo_periodo=101, detalle_periodo="2023", flow="auto_docente")
        self.assertEqual(error.exception.status_code, 500)

    def test_normal_and_bulk_saves_return_bigint_id_with_audit_compatible_output(self):
        for bulk in (False, True):
            with self.subTest(bulk=bulk):
                cursor = MagicMock()
                cursor.fetchone.return_value = [2147483649]
                answers = [evaluation.TeacherEvaluationAnswer(id_pregunta=1, puntaje=4)]
                result = evaluation._save_application(
                    cursor, flow="auto_docente", instrument={"Id_Instrumento": 7, "Id_Tipo_Evaluacion": 2},
                    campaign_id=4, evaluator_code=12, evaluated_student_code=None, course=course(), answers=answers,
                    origin_table="source", origin_evaluator_table="generated", origin_evaluated_table="teacher", bulk_answers=bulk,
                )
                self.assertEqual(result["application_id"], 2147483649)
                sql, *params = cursor.execute.call_args_list[0].args
                self.assertIn("SET NOCOUNT ON;", sql)
                self.assertIn("DECLARE @AplicacionCreada TABLE (Id_Aplicacion bigint NOT NULL)", sql)
                self.assertIn("OUTPUT INSERTED.Id_Aplicacion INTO @AplicacionCreada (Id_Aplicacion)", sql)
                self.assertIn("SELECT Id_Aplicacion FROM @AplicacionCreada", sql)
                self.assertNotIn("DISABLE TRIGGER", sql)
                self.assertEqual(sql.count("?"), len(params))
                if bulk:
                    self.assertEqual(cursor.executemany.call_args.args[1][0][:3], (2147483649, 1, 4))
                else:
                    self.assertEqual(cursor.execute.call_args_list[1].args[1:4], (2147483649, 1, 4))

    def test_application_without_returned_id_does_not_save_answers(self):
        cursor = MagicMock()
        cursor.fetchone.return_value = None
        with self.assertRaises(HTTPException) as error:
            evaluation._save_application(
                cursor, flow="auto_docente", instrument={"Id_Instrumento": 7, "Id_Tipo_Evaluacion": 2},
                campaign_id=4, evaluator_code=12, evaluated_student_code=None, course=course(),
                answers=[evaluation.TeacherEvaluationAnswer(id_pregunta=1, puntaje=4)],
                origin_table="source", origin_evaluator_table="generated", origin_evaluated_table="teacher", bulk_answers=True,
            )
        self.assertEqual(error.exception.status_code, 500)
        cursor.execute.assert_called_once()
        cursor.executemany.assert_not_called()

    def test_existing_index_supports_legacy_actor_origin(self):
        cursor = MagicMock()
        cursor.fetchall.return_value = [{"Cod_Periodo": "101", "Cod_Materia": "31", "Cod_Evaluador": None,
                                        "Origen_Evaluador_Clave": None, "Origen_Clave": "auto_docente|12|101|31|1|PB1",
                                        "Jornada": "1", "Paralelo": "pb1 "}]
        with patch.object(evaluation, "_row_dict", side_effect=lambda _cursor, row: row):
            index = history._existing_self_evaluation_index(cursor, [101], {"Id_Tipo_Evaluacion": 2})
        self.assertTrue(history._has_existing_self_evaluation(index, course()))
        self.assertFalse(history._has_existing_self_evaluation(index, course(teacher=13)))
        self.assertFalse(history._has_existing_self_evaluation(index, {**course(), "paralelo": "PB2"}))
        self.assertFalse(history._has_existing_self_evaluation(index, {**course(), "cod_jornada": "2"}))
        self.assertTrue(history._has_existing_self_evaluation(index, {**course(subject=32), "codigos_materia_relacionados": [31, 32]}))

    def test_application_lock_rejects_timeout(self):
        cursor = MagicMock()
        cursor.fetchone.return_value = [-1]
        with self.assertRaises(HTTPException):
            acquire_self_evaluation_lock(cursor)

    def test_application_lock_accepts_granted_result(self):
        cursor = MagicMock()
        cursor.fetchone.return_value = [0]
        acquire_self_evaluation_lock(cursor)

    def run_generation(self, generation_plan, save_side_effect=None, plan_side_effect=None, offset=None):
        academic_conn, evaluation_conn = connection(), connection()
        preview = {"selection": {"periods": [101], "teachers": [12]}, "seed": "seed", "fingerprint": "valid", "jti": "batch"}
        payload = history.HistoricalSelfEvaluationConfirm(preview_token="token", confirmed=True, reason="Regularización administrativa", offset=offset)
        with (patch.object(history, "get_connection", return_value=academic_conn),
              patch.object(history, "get_evaluation_connection", return_value=evaluation_conn),
              patch.object(history, "acquire_self_evaluation_lock") as lock,
              patch.object(history, "_decode_preview_token", return_value=preview),
              patch.object(history, "_generation_plan", return_value=generation_plan, side_effect=plan_side_effect),
              patch.object(evaluation, "_get_or_create_campaign", return_value=4) as campaign,
              patch.object(evaluation, "_save_application", side_effect=save_side_effect, return_value={"application_id": 901}) as save):
            result = None
            error = None
            try:
                result = history.generate_historical_self_evaluations(payload, actor())
            except Exception as exc:
                error = exc
            return result, error, evaluation_conn, save, lock, campaign

    def test_existing_rows_preserved_and_metadata_recorded(self):
        result, error, conn, save, lock, campaign = self.run_generation(plan())
        self.assertIsNone(error)
        self.assertEqual((result["created"], result["skipped"]), (1, 1))
        save.assert_called_once()
        lock.assert_called_once()
        campaign.assert_called_once()
        conn.commit.assert_called_once()
        metadata = decode_generation_metadata(save.call_args.kwargs["observation"])
        self.assertEqual(metadata["actor_login"], actor().login)
        self.assertEqual(metadata["batch_id"], "batch")
        self.assertEqual(metadata["generation_policy"], GENERATION_POLICY_VERSION)
        self.assertEqual(metadata["score_10"], 9)
        self.assertEqual(metadata["teacher_code"], 12)
        self.assertEqual(metadata["teacher_name"], "Docente vinculado")
        self.assertEqual(metadata["teacher_cedula"], "0805755739")
        self.assertEqual(metadata["record_origin"], "ADMINISTRATIVO")
        self.assertEqual(metadata["actor_user_id"], 95)
        self.assertEqual(save.call_args.kwargs["evaluator_code"], 12)
        self.assertEqual(datetime.fromisoformat(metadata["created_at"]).year, datetime.now(timezone.utc).year)
        self.assertEqual(save.call_args.kwargs["origin_evaluator_table"], "SISACA.AUTO_DOCENTE_GENERADA")

    def test_teacher_deactivated_after_preview_prevents_confirmation_and_rolls_back(self):
        real_plan = history._generation_plan
        with (patch.object(history, "_validate_periods", return_value=[{"codigo_periodo": 101}]),
              patch.object(history, "_historical_teachers", return_value=[]),
              patch.object(history, "_historical_courses") as courses):
            result, error, conn, save, _lock, campaign = self.run_generation(None, plan_side_effect=real_plan)
        self.assertIsNone(result)
        self.assertEqual(error.status_code, 400)
        courses.assert_not_called()
        save.assert_not_called()
        campaign.assert_not_called()
        conn.commit.assert_not_called()
        conn.rollback.assert_called_once()

    def test_repeated_generation_skips_all_existing_rows(self):
        result, error, conn, save, _lock, _campaign = self.run_generation(plan(("EXISTENTE",)))
        self.assertIsNone(error)
        self.assertEqual((result["created"], result["skipped"]), (0, 1))
        save.assert_not_called()

    def test_failure_rolls_back_whole_batch(self):
        result, error, conn, _save, _lock, _campaign = self.run_generation(plan(), RuntimeError("Database failure"))
        self.assertIsNone(result)
        self.assertIsInstance(error, RuntimeError)
        conn.commit.assert_not_called()
        conn.rollback.assert_called_once()

    def test_changed_preview_never_writes(self):
        result, error, conn, save, _lock, _campaign = self.run_generation({**plan(), "fingerprint": "changed"})
        self.assertIsNone(result)
        self.assertEqual(error.status_code, 409)
        save.assert_not_called()
        conn.commit.assert_not_called()

    def test_campaign_created_once_for_multiple_subjects(self):
        _result, error, _conn, save, _lock, campaign = self.run_generation(plan(("PENDIENTE", "PENDIENTE")))
        self.assertIsNone(error)
        self.assertEqual(save.call_count, 2)
        campaign.assert_called_once()

    def test_bulk_insert_preserves_original_application_fields(self):
        cursor = MagicMock()
        cursor.fetchone.return_value = [901]
        metadata = encode_generation_metadata({"kind": "ADMINISTRATIVE_RANDOM_SELF_EVALUATION"})
        result = evaluation._save_application(cursor, flow="auto_docente", instrument={"Id_Instrumento": 7, "Id_Tipo_Evaluacion": 2},
                                             campaign_id=4, evaluator_code=12, evaluated_student_code=None, course=course(),
                                             answers=[evaluation.TeacherEvaluationAnswer(id_pregunta=1, puntaje=4)],
                                             origin_table="source", origin_evaluator_table="generated", origin_evaluated_table="teacher",
                                             observation=metadata, bulk_answers=True)
        self.assertEqual(result["application_id"], 901)
        self.assertIn(metadata, cursor.execute.call_args.args)
        params = cursor.execute.call_args.args
        self.assertEqual(params[0].count("?"), len(params) - 1)
        cursor.executemany.assert_called_once()
        self.assertEqual(cursor.executemany.call_args.args[1][0][:3], (901, 1, 4))

    def test_unbatched_generation_accepts_more_than_500_applications(self):
        result, error, conn, save, _lock, _campaign = self.run_generation(plan(("PENDIENTE",) * 1101))
        self.assertIsNone(error)
        self.assertEqual(result["created"], 1101)
        self.assertEqual(result["processed"], 1101)
        self.assertIsNone(result["next_offset"])
        self.assertEqual(save.call_count, 1101)
        conn.commit.assert_called_once()

    def test_internal_batches_process_the_entire_unlimited_selection(self):
        generation_plan = plan(("PENDIENTE",) * 701)
        offset = 0
        created = 0
        while True:
            result, error, conn, save, _lock, _campaign = self.run_generation(generation_plan, offset=offset)
            self.assertIsNone(error)
            self.assertEqual(result["total"], 701)
            self.assertEqual(result["batch_id"], "batch")
            self.assertLessEqual(save.call_count, history._GENERATION_BATCH_SIZE)
            self.assertEqual(save.call_args_list[0].kwargs["course"]["key"], str(offset))
            conn.commit.assert_called_once()
            created += result["created"]
            if result["next_offset"] is None:
                self.assertEqual(result["processed"], 701)
                self.assertIsNone(result["preview_token"])
                break
            self.assertGreater(result["next_offset"], offset)
            renewed = history._decode_preview_token(result["preview_token"], actor())
            self.assertEqual(renewed["jti"], "batch")
            self.assertEqual(renewed["seed"], "seed")
            self.assertEqual(renewed["fingerprint"], "valid")
            offset = result["next_offset"]
        self.assertEqual(created, 701)

    def test_retried_committed_chunk_is_skipped_without_duplicates(self):
        result, error, conn, save, _lock, _campaign = self.run_generation(plan(("EXISTENTE",) * 100 + ("PENDIENTE",) * 501), offset=0)
        self.assertIsNone(error)
        self.assertEqual((result["created"], result["skipped"], result["next_offset"]), (0, 100, 100))
        save.assert_not_called()
        conn.commit.assert_called_once()

    def test_invalid_offset_cannot_create_records(self):
        result, error, conn, save, _lock, campaign = self.run_generation(plan(), offset=3)
        self.assertIsNone(result)
        self.assertEqual(error.status_code, 400)
        save.assert_not_called()
        campaign.assert_not_called()
        conn.rollback.assert_called_once()

    def test_error_rolls_back_only_current_chunk(self):
        _result, first_error, first_conn, _save, _lock, _campaign = self.run_generation(plan(("PENDIENTE",) * 701), offset=0)
        self.assertIsNone(first_error)
        result, error, conn, _save, _lock, _campaign = self.run_generation(plan(("PENDIENTE",) * 701), RuntimeError("Database failure"), offset=100)
        self.assertIsNone(result)
        self.assertIsInstance(error, RuntimeError)
        first_conn.commit.assert_called_once()
        first_conn.rollback.assert_not_called()
        conn.commit.assert_not_called()
        conn.rollback.assert_called_once()


class UnlimitedSelectionTests(unittest.TestCase):
    def test_sql_chunks_preserve_all_ids_and_do_not_exceed_parameter_budget(self):
        values = list(range(1, 2502))
        chunks = history._selection_chunks(values)
        self.assertEqual([value for chunk in chunks for value in chunk], values)
        self.assertTrue(all(len(chunk) <= 500 for chunk in chunks))

    def test_large_teacher_query_checks_every_selected_teacher(self):
        cursor = MagicMock()
        cursor.fetchall.return_value = []
        values = list(range(1, 2502))
        history._historical_teachers(cursor, values)
        calls = cursor.execute.call_args_list
        self.assertEqual(len(calls), 6)
        self.assertTrue(all(len(call.args) - 1 <= 500 for call in calls))
        self.assertEqual([value for call in calls for value in call.args[1:]], values)

    def test_teacher_period_chunks_preserve_parameter_budget_and_merge_teacher_assignments(self):
        cursor = MagicMock()
        cursor.fetchall.side_effect = [
            [{"codigo_doc": 12, "docente": "Activo", "cedula_doc": "1712345678", "codigo_periodo": 1}],
            [{"codigo_doc": 12, "docente": "Activo", "cedula_doc": "1712345678", "codigo_periodo": 501}],
        ]
        with patch.object(evaluation, "_row_dict", side_effect=lambda _cursor, row: row):
            result = history._historical_teachers(cursor, [12], periods=list(range(1, 502)))
        self.assertEqual(result[0]["periods"], [1, 501])
        self.assertEqual(len(result), 1)
        self.assertEqual(cursor.execute.call_count, 2)
        self.assertTrue(all(len(call.args) - 1 <= 1000 for call in cursor.execute.call_args_list))

    def test_large_course_query_handles_all_period_teacher_chunk_combinations(self):
        cursor = MagicMock()
        cursor.fetchall.return_value = []
        periods, teachers = list(range(1, 1102)), list(range(1, 2502))
        self.assertEqual(history._historical_courses(cursor, periods, teachers), [])
        calls = cursor.execute.call_args_list
        self.assertEqual(len(calls), 18)
        self.assertTrue(all(len(call.args) - 1 <= 1000 for call in calls))
        self.assertEqual(sum(len(call.args) - 1 for call in calls), len(periods) * 6 + len(teachers) * 3)

    def test_large_duplicate_index_checks_all_periods(self):
        cursor = MagicMock()
        cursor.fetchall.return_value = []
        periods = list(range(1, 2502))
        self.assertEqual(history._existing_self_evaluation_index(cursor, periods, {"Id_Tipo_Evaluacion": 2}), {})
        calls = cursor.execute.call_args_list
        self.assertEqual(len(calls), 6)
        self.assertTrue(all(len(call.args) - 1 <= 501 for call in calls))
        self.assertEqual([int(value) for call in calls for value in call.args[2:]], periods)

    def test_preview_plan_accepts_more_than_500_applications(self):
        courses = [{**course(index + 1, key=str(index)), "key": str(index)} for index in range(701)]
        with (patch.object(history, "_validate_periods", return_value=[{"codigo_periodo": 101}]),
              patch.object(history, "_validate_teachers"),
              patch.object(history, "_historical_courses", return_value=courses),
              patch.object(evaluation, "_fetch_question_rows", return_value=({"Id_Instrumento": 7, "Id_Tipo_Evaluacion": 2}, questions(2))),
              patch.object(evaluation, "_row_dict", side_effect=lambda _cursor, row: row),
              patch.object(evaluation, "_question_from_row", side_effect=lambda row: row),
              patch.object(history, "_existing_self_evaluation_index", return_value={})):
            result = history._generation_plan(MagicMock(), MagicMock(), history.HistoricalSelfEvaluationSelection(periods=[101], teachers=[12]), "seed")
            with patch.object(history, "GENERATION_POLICY_VERSION", "different-rule"):
                changed = history._generation_plan(MagicMock(), MagicMock(), history.HistoricalSelfEvaluationSelection(periods=[101], teachers=[12]), "seed")
        self.assertEqual(len(result["items"]), 701)
        self.assertEqual(result["pending"], 701)
        self.assertTrue(all(9 <= item["score_10"] < 10 for item in result["items"]))
        self.assertNotEqual(result["fingerprint"], changed["fingerprint"])


class GenerationAccessAndReportTests(unittest.TestCase):
    def test_history_preserves_teacher_snapshot_actual_actor_and_legacy_scores(self):
        conn = connection()
        common = {"kind": "ADMINISTRATIVE_RANDOM_SELF_EVALUATION", "batch_id": "batch",
                  "actor_login": actor().login, "actor_name": actor().nombres,
                  "actor_user_id": 95, "created_at": "2026-09-16T18:00:00+00:00", "reason": "Motivo administrativo"}
        legacy = {**common, "score_10": 8.5}
        snapshot = {**common, "score_10": 9.5, **history._teacher_identity(course()), "record_origin": "ADMINISTRATIVO"}
        invalid_origin = {**snapshot, "record_origin": "DOCENTE"}
        rows = [{"Id_Aplicacion": index + 901, "Cod_Docente_Evaluado": "12",
                 "Observacion_General": encode_generation_metadata(metadata)}
                for index, metadata in enumerate((legacy, snapshot, invalid_origin))]
        rows.append({"Id_Aplicacion": 904, "Observacion_General": "Observación real"})
        conn.cursor.return_value.fetchall.return_value = rows
        with (patch.object(history, "get_evaluation_connection", return_value=conn),
              patch.object(evaluation, "_row_dict", side_effect=lambda _cursor, row: dict(row))):
            result = history.get_historical_self_evaluation_history(limit=500, current_user=actor())
        self.assertEqual(result["total"], 3)
        self.assertEqual(result["items"][0]["score_10"], 8.5)
        self.assertNotIn("teacher_cedula", result["items"][0])
        self.assertEqual(result["items"][1]["teacher_cedula"], "0805755739")
        self.assertEqual(result["items"][1]["teacher_name"], "Docente vinculado")
        for item in result["items"]:
            self.assertEqual(item["record_origin"], "ADMINISTRATIVO")
            self.assertEqual(item["actor_user_id"], 95)
            self.assertEqual(item["actor_login"], actor().login)
            self.assertEqual(item["created_at"], common["created_at"])
        self.assertEqual(decode_generation_metadata(rows[2]["Observacion_General"])["record_origin"], "DOCENTE")
        conn.commit.assert_not_called()
        self.assertTrue(conn.cursor.return_value.execute.call_args.args[0].lstrip().startswith("SELECT"))

    def test_screen_registered_and_default_administrator_only(self):
        page = "evaluacion-docente-historicas"
        self.assertIn(page, ALL_PAGES)
        self.assertIn(page, DEFAULT_ACCESS["ADMINISTRADOR"])
        self.assertNotIn(page, DEFAULT_ACCESS["DOCENTE"])
        self.assertNotIn(page, DEFAULT_ACCESS["ESTUDIANTE"])

    def test_teacher_cannot_use_generation_endpoint(self):
        app = FastAPI()
        app.include_router(history.router)
        app.dependency_overrides[get_current_user] = lambda: actor("DOCENTE")
        response = TestClient(app).post("/api/evaluacion-docente/admin/autoevaluaciones-historicas/vista-previa", json={"periods": [101], "teachers": [12]})
        self.assertEqual(response.status_code, 403)

    def test_unassigned_administrator_cannot_use_generation_endpoint(self):
        app = FastAPI()
        app.include_router(history.router)
        app.dependency_overrides[get_current_user] = actor
        with patch("app.services.screen_access.role_has_screen_access", return_value=False) as access, patch.object(history, "get_connection") as connection:
            app.dependency_overrides[history._ACCESS] = require_screen_access("evaluacion-docente-historicas")
            response = TestClient(app).get("/api/evaluacion-docente/admin/autoevaluaciones-historicas/catalogo")
        self.assertEqual(response.status_code, 403)
        access.assert_called_once_with("ADMINISTRADOR", "evaluacion-docente-historicas")
        connection.assert_not_called()

    def test_metadata_is_structured_and_legacy_observations_not_misclassified(self):
        metadata = {"kind": "ADMINISTRATIVE_RANDOM_SELF_EVALUATION", "reason": "Motivo"}
        self.assertEqual(decode_generation_metadata(encode_generation_metadata(metadata)), metadata)
        for value in (None, "Observación real", GENERATION_PREFIX + "[]", GENERATION_PREFIX + "invalid"):
            self.assertIsNone(decode_generation_metadata(value))

    def test_report_notices_deduplicate_equivalent_subject_rows(self):
        notice = {"application_id": 901, "batch_id": "batch"}
        self.assertEqual(generation_report_notices([{"autoevaluaciones_generadas": [notice]}] * 3), [notice])

    def test_pdf_discloses_administrative_origin_and_actor(self):
        notice = {"application_id": 901, "batch_id": "batch", "actor_login": actor().login,
                  "actor_name": "Administrador", "created_at": "2026-09-16T18:00:00+00:00", "reason": "Regularización administrativa"}
        row = {"Cod_Materia": "31", "materia": "Matemática", "carrera": "Software", "Paralelo": "PB1",
               "Promedio_Autoevaluacion": 85, "Puntaje_Final_360": 85, "autoevaluaciones_generadas": [notice]}
        report = {"periodo": "101", "periodo_detalle": "2023", "flow": "auto_docente", "weights": [],
                  "teachers": [{"teacher": {"codigo_doc": "12", "docente": "Docente", "cedula_doc": "1712345678"}, "rows": [row]}]}
        with patch.object(evaluation, "_template_page_image", return_value=None):
            pdf = evaluation._build_teacher_grade_pdf(report)
        text = " ".join(page.extract_text() for page in PdfReader(BytesIO(pdf)).pages)
        self.assertIn("GENERACIÓN ADMINISTRATIVA", text)
        self.assertIn("administrador@intec.edu.ec", text)
        self.assertIn("No corresponden a respuestas", text)
        self.assertIn("2026-09-16", text)
