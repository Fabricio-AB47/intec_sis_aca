from datetime import date
from io import BytesIO
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from openpyxl import Workbook

from app.routers.students import (
    _graduation_senescyt_analysis,
    _parse_graduation_senescyt_pdf_batch,
    _parse_graduation_senescyt_pdf_text,
    _parse_graduation_senescyt_workbook,
)


def _workbook_bytes(rows: list[list[object]]) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Registro de títulos"
    sheet.append(["REPORTE SENESCYT"])
    sheet.append([])
    sheet.append(
        [
            "NÚMERO\nDE\nIDENTIFICACIÓN",
            "FECHA DE GRADO",
            "FECHA DE EMISIÓN SENESCYT",
            "CÓDIGO DE REGISTRO",
            "NÓMINA #",
        ]
    )
    for row in rows:
        sheet.append(row)
    output = BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()


class _StudentCursor:
    def __init__(self, students: list[SimpleNamespace]) -> None:
        self.students = students
        self._result: list[SimpleNamespace] = []

    def execute(self, statement: str, *_params: object) -> None:
        if statement.lstrip().startswith("SELECT"):
            self._result = self.students
        else:
            self._result = []

    def fetchall(self) -> list[SimpleNamespace]:
        return self._result


def _student(code: str, identifier: str, name: str) -> SimpleNamespace:
    return SimpleNamespace(
        codigo_estud=code,
        cedula=identifier,
        nombres=name,
        fecha_grado=None,
        fecha_emision_senescyt=None,
        cod_registro="",
        nomina="",
    )


class GraduationSenescytImportTests(unittest.TestCase):
    def test_parses_official_pdf_with_multiple_students(self) -> None:
        text = """
        NÓMINA DE GRADUADOS REGISTRADOS
        # Nómina 3048392924
        NÚMERO DE IDENTIFICACIÓN NOMBRES CÓDIGO DEL REGISTRO FECHA DE ACTA DE GRADO
        1722225602 BALDEON BALSECA ERICK SANTIAGO 3048-2025-3051788 2025-01-23 Ecuador
        1717708679 OBANDO ORTIZ CRISTIAN SANTIAGO 3048-2025-3051789 2025-01-23 Ecuador
        Fecha de emisión SENESCYT: 2025-02-11
        """

        parsed = _parse_graduation_senescyt_pdf_text("Nomina-3048392924.pdf", text)

        self.assertEqual(parsed["errors"], [])
        self.assertEqual(parsed["filas_detectadas"], 2)
        self.assertEqual(len(parsed["rows"]), 2)
        self.assertEqual(parsed["rows"][0]["identificacion"], "1722225602")
        self.assertEqual(parsed["rows"][0]["cod_registro"], "3048-2025-3051788")
        self.assertEqual(parsed["rows"][0]["fecha_grado"], date(2025, 1, 23))
        self.assertEqual(parsed["rows"][1]["nomina"], "3048392924")
        self.assertEqual(parsed["rows"][1]["fecha_emision_senescyt"], date(2025, 2, 11))

    @patch("app.routers.students._extract_graduation_pdf_text")
    def test_combines_multiple_official_pdfs(self, extract_text: object) -> None:
        document_one = """
        NÓMINA DE GRADUADOS REGISTRADOS # Nómina 10001
        NÚMERO DE IDENTIFICACIÓN NOMBRES CÓDIGO DEL REGISTRO FECHA DE ACTA DE GRADO
        1722225602 ESTUDIANTE UNO 3048-2025-3000001 2025-01-23 Ecuador
        Fecha de emisión SENESCYT: 2025-02-11
        """
        document_two = """
        NÓMINA DE GRADUADOS REGISTRADOS # Nómina 10002
        NÚMERO DE IDENTIFICACIÓN NOMBRES CÓDIGO DEL REGISTRO FECHA DE ACTA DE GRADO
        1717708679 ESTUDIANTE DOS 3048-2025-3000002 2025-01-24 Ecuador
        Fecha de emisión SENESCYT: 2025-02-12
        """
        extract_text.side_effect = [(document_one, "TEXTO_PDF"), (document_two, "OCR")]

        parsed = _parse_graduation_senescyt_pdf_batch(
            [("nomina-10001.pdf", b"pdf-1"), ("nomina-10002.pdf", b"pdf-2")]
        )

        self.assertEqual(parsed["errors"], [])
        self.assertEqual(parsed["archivos_detectados"], 2)
        self.assertEqual(parsed["archivos_procesados"], 2)
        self.assertEqual(len(parsed["rows"]), 2)
        self.assertEqual(parsed["rows"][0]["archivo"], "nomina-10001.pdf")
        self.assertEqual(parsed["rows"][1]["metodo_extraccion"], "OCR")

    def test_rejects_pdf_without_official_senescyt_structure(self) -> None:
        parsed = _parse_graduation_senescyt_pdf_text(
            "acta.pdf",
            "ACTA DE GRADO INSTITUCIONAL Cédula 1723602064 fecha 2026-06-06",
        )

        self.assertEqual(parsed["rows"], [])
        self.assertEqual(len(parsed["errors"]), 1)
        self.assertIn("no corresponde", parsed["errors"][0]["error"].lower())

    def test_rejects_pdf_missing_emission_date(self) -> None:
        text = """
        NÓMINA DE GRADUADOS REGISTRADOS
        # Nómina 3048392924
        1722225602 BALDEON BALSECA ERICK SANTIAGO 3048-2025-3051788 2025-01-23 Ecuador
        """

        parsed = _parse_graduation_senescyt_pdf_text("sin-emision.pdf", text)

        self.assertEqual(parsed["rows"], [])
        self.assertTrue(any("emisión" in item["error"].lower() for item in parsed["errors"]))

    def test_accepts_multiline_header_and_shared_roster(self) -> None:
        content = _workbook_bytes(
            [
                [605325323, "15 DE JULIO DE 2026", "20/07/2026", "REG-001", "12, 13"],
                ["1106128380", date(2026, 7, 15), date(2026, 7, 20), "REG-002", "12, 13"],
            ]
        )

        parsed = _parse_graduation_senescyt_workbook(content)

        self.assertEqual(parsed["hoja"], "Registro de títulos")
        self.assertEqual(parsed["fila_encabezado"], 3)
        self.assertEqual(parsed["errors"], [])
        self.assertEqual(parsed["rows"][0]["identificacion"], "0605325323")
        self.assertEqual(parsed["rows"][0]["fecha_grado"], date(2026, 7, 15))

        cursor = _StudentCursor(
            [
                _student("1", "0605325323", "ESTUDIANTE UNO"),
                _student("2", "1106128380", "ESTUDIANTE DOS"),
            ]
        )
        analysis, matched = _graduation_senescyt_analysis(cursor, parsed)

        self.assertTrue(analysis["puede_importar"])
        self.assertEqual(analysis["encontrados"], 2)
        self.assertEqual(analysis["nuevos"], 2)
        self.assertEqual(analysis["nominas_compartidas"], 1)
        self.assertEqual(len(matched), 2)

    def test_rejects_repeated_identification_not_repeated_roster(self) -> None:
        content = _workbook_bytes(
            [
                ["1106128380", "2026-07-15", "2026-07-20", "REG-001", "20"],
                ["1106128380", "2026-07-15", "2026-07-20", "REG-002", "20"],
            ]
        )

        parsed = _parse_graduation_senescyt_workbook(content)

        self.assertEqual(len(parsed["rows"]), 1)
        self.assertEqual(len(parsed["errors"]), 1)
        self.assertIn("duplicada", parsed["errors"][0]["error"].lower())

    def test_requires_all_document_columns(self) -> None:
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(["NÚMERO DE IDENTIFICACIÓN", "FECHA DE GRADO", "NÓMINA #"])
        output = BytesIO()
        workbook.save(output)
        workbook.close()

        with self.assertRaises(HTTPException) as context:
            _parse_graduation_senescyt_workbook(output.getvalue())

        self.assertEqual(context.exception.status_code, 400)
        self.assertIn("columnas requeridas", str(context.exception.detail).lower())
