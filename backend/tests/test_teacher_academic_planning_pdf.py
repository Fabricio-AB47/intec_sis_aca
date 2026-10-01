import unittest
from datetime import date
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from pypdf import PdfReader

from app.routers import portal_academico as portal
from app.routers.portal_academico import AcademicPlanningPayload, _teacher_academic_planning_pdf

PERIODS = [1032, 1028, 1025, 1022, 1016, 1060, 1051, 1027, 1024, 1023, 1020]


class TeacherAcademicPlanningPdfTests(unittest.TestCase):
    def make_payload(self, document_type: str, **overrides: object) -> AcademicPlanningPayload:
        return AcademicPlanningPayload.model_validate({
            "document_type": document_type,
            "codigo_periodos": [1060],
            "codigo_materia": "VGA-ID-2023-119",
            "paralelo": "A",
            "unidades": [{
                "nombre": "Unidad 1",
                "temas": [{
                    "tema": "Presentación",
                    "semana": 1,
                    "horas_docencia": 3,
                    "horas_practica": 1,
                    "horas_autonomo": 2,
                }],
            }],
            **overrides,
        })

    def render(self, payload: AcademicPlanningPayload) -> PdfReader:
        return PdfReader(BytesIO(_teacher_academic_planning_pdf(
            payload,
            {"docente": "Docente de prueba"},
            {
                "nombre_materia": "Inglés",
                "nombre_carrera": "Administración",
                "cod_materia": "VGA-ID-2023-119",
                "detalle_periodo": "C1-2026-PC",
                "semestre": 6,
            },
        )))

    def test_cover_and_overview_start_on_separate_pages_for_both_documents(self) -> None:
        for document_type in ("pea", "silabo"):
            with self.subTest(document_type=document_type):
                pdf = self.render(self.make_payload(
                    document_type,
                    horas_docencia=32,
                    horas_autonomo=76,
                    horas_practica=48,
                ))
                cover = pdf.pages[0].extract_text()
                overview = pdf.pages[1].extract_text()
                self.assertIn("CONTROL DE CAMBIOS", cover)
                self.assertNotIn("PROGRAMA DE ESTUDIOS DE ASIGNATURA", cover)
                self.assertIn("PROGRAMA DE ESTUDIOS DE ASIGNATURA", overview)
                self.assertIn("Docencia:", overview)
                self.assertIn("32", overview)
                self.assertIn("76", overview)
                self.assertIn("48", overview)

    def test_older_payloads_keep_topic_totals(self) -> None:
        overview = self.render(self.make_payload("pea")).pages[1].extract_text()
        for value in ("Docencia:", "3", "Trabajo Autónomo", "2", "Prácticas Aprendizaje", "1"):
            self.assertIn(value, overview)

    def test_planning_accepts_all_periods_but_requires_at_least_one(self):
        self.assertNotIn('maxItems', AcademicPlanningPayload.model_json_schema()['properties']['codigo_periodos'])
        for periods in (PERIODS, list(range(1, 2502))):
            for kind in ('pea', 'silabo'):
                payload = self.make_payload(kind, codigo_periodos=periods)
                self.assertEqual(payload.codigo_periodos, periods)
                self.assertEqual(AcademicPlanningPayload.model_validate_json(payload.model_dump_json()).codigo_periodos, periods)
        for periods in ([], ['invalid']):
            with self.assertRaises(ValidationError):
                self.make_payload('pea', codigo_periodos=periods)

    def client(self):
        app = FastAPI()
        app.include_router(portal.router)
        app.dependency_overrides[portal._TEACHER_ACCESS] = lambda: SimpleNamespace(codigo_doc=7)
        return TestClient(app)

    def meta(self):
        return {'nombre_materia': 'Asignatura de prueba', 'nombre_carrera': 'Carrera de prueba',
                'detalle_periodo': 'P1060', 'paralelo': 'Varios'}

    def test_http_preview_and_download_show_only_latest_period_for_both_documents(self):
        with self.client() as client, patch.object(portal, '_teacher_course_report_meta', return_value=self.meta()) as meta, patch.object(
            portal, 'teacher_profile', return_value={'teacher': {'docente': 'Docente de prueba'}}
        ):
            for kind in ('pea', 'silabo'):
                for preview in (False, True):
                    payload = self.make_payload(kind, codigo_periodos=PERIODS, paralelo='VARIOS')
                    response = client.post(f'/api/portal/teacher/academic-planning-pdf?preview={str(preview).lower()}', json=payload.model_dump(mode='json'))
                    self.assertEqual(response.status_code, 200, response.text[:200] if response.status_code != 200 else '')
                    self.assertIn('application/pdf', response.headers['content-type'])
                    self.assertIn('inline' if preview else 'attachment', response.headers['content-disposition'])
                    text = '\n'.join(page.extract_text() for page in PdfReader(BytesIO(response.content)).pages)
                    self.assertIn('P1060', text)
                    for code in PERIODS:
                        if code != 1060:
                            self.assertNotIn(f'P{code}', text)
                    self.assertEqual(meta.call_args.args[:4], (7, PERIODS, 'VGA-ID-2023-119', 'VARIOS'))

    def test_http_sign_accepts_eleven_periods_without_using_real_certificates(self):
        async def fake_sign(**kwargs):
            return kwargs['pdf_bytes']
        with self.client() as client, patch.object(portal, '_teacher_course_report_meta', return_value=self.meta()) as meta, patch.object(
            portal, 'teacher_profile', return_value={'teacher': {'docente': 'Docente de prueba'}}
        ), patch.object(portal, '_read_pkcs12_upload', new=AsyncMock(return_value=b'test-only')), patch.object(
            portal, '_sign_pdf_with_pkcs12', new=AsyncMock(side_effect=fake_sign)
        ) as signer:
            for kind in ('pea', 'silabo'):
                payload = self.make_payload(kind, codigo_periodos=PERIODS)
                response = client.post('/api/portal/teacher/academic-planning-sign',
                    data={'payload_json': payload.model_dump_json(), 'contrasena_certificado': 'test-only'},
                    files={'certificado': ('test.p12', b'test-only', 'application/octet-stream')})
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.content.startswith(b'%PDF'))
                self.assertEqual(meta.call_args.args[1], PERIODS)
                self.assertEqual(signer.call_args.kwargs['field_name'], f'FirmaDocente{kind.upper()}')

    def test_unassigned_subject_and_content_validation_remain_enforced(self):
        with self.client() as client, patch.object(portal, '_teacher_course_report_meta', return_value={}):
            payload = self.make_payload('pea', codigo_periodos=PERIODS).model_dump(mode='json')
            response = client.post('/api/portal/teacher/academic-planning-pdf', json=payload)
            self.assertEqual(response.status_code, 404)
            payload['evaluacion_tareas'] = 0
            self.assertEqual(client.post('/api/portal/teacher/academic-planning-pdf', json=payload).status_code, 400)
            payload['evaluacion_tareas'] = 30
            payload['unidades'][0]['temas'] = []
            self.assertEqual(client.post('/api/portal/teacher/academic-planning-pdf', json=payload).status_code, 400)

    def test_metadata_batches_all_periods_but_displays_one_and_keeps_teacher_scope(self):
        connection = MagicMock()
        connection.__enter__.return_value = connection
        cursor = connection.cursor.return_value
        def rows():
            return [SimpleNamespace(nombre_carrera='Carrera', codigo_materia='1', cod_materia='TEST',
                nombre_materia='Materia', codigo_periodo=code, detalle_periodo=f'P{code}', tipo_periodo='R',
                paralelo='A', cod_jornada=1, jornada='Matutina', semestre=1, unidad_curricular='', horas=32)
                for code in cursor.execute.call_args.args[6:-2]]
        cursor.fetchall.side_effect = rows
        with patch.object(portal, 'get_connection', return_value=connection):
            result = portal._teacher_course_report_meta(7, list(range(1, 2502)) + [1], 'TEST', 'VARIOS', None)
        self.assertEqual(cursor.execute.call_count, 6)
        self.assertEqual(result['detalle_periodo'], 'P2501')
        for call in cursor.execute.call_args_list:
            query, *params = call.args
            self.assertLessEqual(len(params), 507)
            self.assertNotIn('TOP (50)', query)
            self.assertIn('cxd.codigo_doc) = ?', query)
            self.assertEqual(params[0], 7)
            self.assertEqual(params[3:5], ['TEST', 'TEST'])
            self.assertEqual(query.count('?'), len(params))

    def test_metadata_chooses_largest_start_date_across_batches_not_largest_code(self):
        connection = MagicMock()
        connection.__enter__.return_value = connection
        cursor = connection.cursor.return_value

        def rows():
            result = []
            for code in cursor.execute.call_args.args[6:-2]:
                start = date(2026, 9, 7) if code in {10, 20} else date(2025, 1, 1)
                result.append(SimpleNamespace(
                    nombre_carrera='Carrera', codigo_materia='1', cod_materia='TEST',
                    nombre_materia='Materia', codigo_periodo=code, detalle_periodo=f'P{code}',
                    fecha_inicio_periodo=start, tipo_periodo='R', paralelo='A', cod_jornada=1,
                    jornada='Matutina', semestre=1, unidad_curricular='', horas=32,
                ))
            return result

        cursor.fetchall.side_effect = rows
        with patch.object(portal, 'get_connection', return_value=connection):
            result = portal._teacher_course_report_meta(7, list(range(1, 502)), 'TEST', 'VARIOS', None)
        self.assertEqual(cursor.execute.call_count, 2)
        self.assertEqual(result['detalle_periodo'], 'P20')


if __name__ == "__main__":
    unittest.main()
