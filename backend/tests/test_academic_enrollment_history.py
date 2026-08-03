import unittest
from datetime import date
from types import SimpleNamespace

from app.routers.academic_enrollment import _academic_history_groups


def subject_row(**overrides: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "codigo_materia": 101,
        "cod_materia": "MAT-101",
        "Nomb_Materia": "Matematica aplicada",
        "Semestre": 1,
        "Creditos": 3,
        "Num_Creditos": 3,
        "paralelo": "A",
        "NumGrupo": 1,
        "Num_Matricula": 1,
        "Fecha_Matricula": date(2026, 5, 1),
        "TipoMatricula": "R",
        "Promedio": 8,
        "PromedioFinal": 8,
        "Recuperacion": None,
        "Asistencia": 95,
        "caprueba": "A",
        "ControlAprueba": "A",
        "tiene_notas": 1,
        "cod_anio_Basica": 8,
        "codigo_periodo": 1034,
        "Nombre_Basica": "Desarrollo de Software",
        "Detalle_Periodo": "C1-2026-PC-BS MAYO 2026 - SEPTIEMBRE 2026",
        "fechain": date(2026, 5, 1),
        "fechafin": date(2026, 9, 30),
        "PeriodoTipoMatricula": "R",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class AcademicEnrollmentHistoryTests(unittest.TestCase):
    def test_groups_periods_and_deduplicates_subjects(self) -> None:
        headers = [
            {
                "codigo_periodo": "1034",
                "periodo": "C1-2026-PC-BS MAYO 2026 - SEPTIEMBRE 2026",
                "fecha_inicio_periodo": "2026-05-01",
                "fecha_fin_periodo": "2026-09-30",
                "tipo_periodo": "R",
                "cod_anio_basica": "8",
                "carrera": "Desarrollo de Software",
                "num_matricula": "1",
                "jornada": "NOCTURNO",
            }
        ]
        rows = [subject_row(), subject_row(PromedioFinal=9)]

        history = _academic_history_groups(headers, rows)

        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["total_materias"], 1)
        self.assertEqual(history[0]["materias"][0]["promedio_final"], 9.0)
        self.assertEqual(history[0]["materias"][0]["estado"], "Aprobada")

    def test_includes_subject_period_without_enrollment_header(self) -> None:
        history = _academic_history_groups(
            [],
            [
                subject_row(
                    codigo_periodo=1016,
                    Detalle_Periodo="C1-HOMO-2024-PB",
                    PeriodoTipoMatricula="H",
                    TipoMatricula="H",
                    PromedioFinal=6.5,
                )
            ],
        )

        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["codigo_periodo"], "1016")
        self.assertEqual(history[0]["tipo_periodo"], "H")
        self.assertEqual(history[0]["materias"][0]["estado"], "Reprobada")


if __name__ == "__main__":
    unittest.main()
