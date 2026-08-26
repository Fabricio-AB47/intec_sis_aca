import unittest
from unittest.mock import patch

from fastapi import HTTPException

from app.routers.integration_history import (
    _archive_folder_path,
    _validate_invoice_xml,
    _validate_ride_pdf,
    router,
)
from app.services.integration_history import (
    _flatten_teacher_compliance_events,
    _serialize_record,
    record_teacher_report_event,
    redact_sensitive_data,
)
from app.services.screen_access import ALL_PAGES, SCREEN_CATALOG


class IntegrationHistorySecurityTests(unittest.TestCase):
    def test_binary_database_values_are_json_safe(self) -> None:
        serialized = _serialize_record(
            {
                "HashEvento": b"\xff\x00\x81",
                "VersionFila": memoryview(b"\x01\x02"),
            }
        )

        self.assertEqual(serialized["HashEvento"], "0xff0081")
        self.assertEqual(serialized["VersionFila"], "0x0102")

    def test_sensitive_values_are_redacted_recursively(self) -> None:
        payload = {
            "usuario": "docente@intec.edu.ec",
            "password_nueva": "no-debe-salir",
            "detalle": {
                "token": "token-no-visible",
                "datos": [{"clave": "otra-clave"}, {"valor": "permitido"}],
            },
        }

        redacted = redact_sensitive_data(payload)

        self.assertEqual(redacted["password_nueva"], "[PROTEGIDO]")
        self.assertEqual(redacted["detalle"]["token"], "[PROTEGIDO]")
        self.assertEqual(redacted["detalle"]["datos"][0]["clave"], "[PROTEGIDO]")
        self.assertEqual(redacted["detalle"]["datos"][1]["valor"], "permitido")

    def test_report_history_never_interrupts_document_generation(self) -> None:
        with (
            patch(
                "app.services.integration_history.ensure_integration_history_schema",
                side_effect=RuntimeError("base no disponible"),
            ),
            patch("app.services.integration_history.logger.exception"),
        ):
            result = record_teacher_report_event(
                stage="GENERADO",
                teacher_code="42",
                metadata={"password": "dato-protegido"},
            )

        self.assertFalse(result)


class IntegrationHistoryRegistrationTests(unittest.TestCase):
    def test_history_is_an_assignable_screen(self) -> None:
        screen = next(
            item for item in SCREEN_CATALOG if item["page"] == "historico-integraciones"
        )

        self.assertIn("historico-integraciones", ALL_PAGES)
        self.assertEqual(screen["label"], "Movimientos de auditoría")
        self.assertEqual(screen["group"], "Auditoría")
        self.assertIn("informes docentes", screen["description"].lower())

    def test_router_exposes_summary_lists_and_detail(self) -> None:
        paths = {route.path for route in router.routes}

        self.assertEqual(
            paths,
            {
                "/api/integrations/history/summary",
                "/api/integrations/history/database-events",
                "/api/integrations/history/teacher-reports",
                "/api/integrations/history/compliance-documents",
                "/api/integrations/history/compliance-documents/{event_id}/invoice-backups",
                "/api/integrations/history/detail/{kind}/{event_id}",
            },
        )

    def test_compliance_documents_are_an_assignable_screen(self) -> None:
        screen = next(
            item for item in SCREEN_CATALOG if item["page"] == "informe-cumplimiento"
        )

        self.assertIn("informe-cumplimiento", ALL_PAGES)
        self.assertEqual(screen["group"], "Documentos")
        self.assertIn("contratos", screen["description"].lower())

    def test_archived_package_is_expanded_into_each_available_document(self) -> None:
        documents = _flatten_teacher_compliance_events(
            [
                {
                    "event_id": 18,
                    "fecha_utc": "2026-08-21T12:00:00",
                    "fecha_ecuador": "2026-08-21T07:00:00",
                    "codigo_docente": "42",
                    "cedula_docente": "1720000000",
                    "nombre_docente": "DOCENTE DE PRUEBA",
                    "codigo_materia": "VGA-01",
                    "nombre_materia": "Materia de prueba",
                    "periods_json": '["C1-2026"]',
                    "folder_path": "DOCENTES/DOCENTE DE PRUEBA/DOCUMENTOS FIRMADOS",
                    "folder_url": "https://example.test/folder",
                    "metadata_json": (
                        '{"archivos":['
                        '{"id":"1","nombre":"informe-cumplimiento-firmado.pdf","url":"https://example.test/1"},'
                        '{"id":"2","nombre":"reporte-notas-secretaria-firmado.pdf","url":"https://example.test/2"},'
                        '{"id":"3","nombre":"contrato-docente-firmado.pdf","url":"https://example.test/3"},'
                        '{"id":"4","nombre":"documentos-docente-firmados.zip","url":"https://example.test/4"},'
                        '{"id":"5","nombre":"comprobante.xml","url":"https://example.test/5","tipo_documento":"FACTURA_XML"},'
                        '{"id":"6","nombre":"representacion.pdf","url":"https://example.test/6","tipo_documento":"RIDE"}'
                        ']}'
                    ),
                }
            ]
        )

        self.assertEqual(len(documents), 6)
        self.assertEqual(
            {item["tipo_documento"] for item in documents},
            {"INFORME", "NOTAS", "CONTRATO", "PAQUETE", "FACTURA_XML", "RIDE"},
        )
        self.assertEqual(documents[0]["periodos"], ["C1-2026"])
        self.assertTrue(all(item["url_documento"] for item in documents))

    def test_invoice_backups_require_valid_xml_pdf_and_teacher_folder(self) -> None:
        self.assertEqual(
            _validate_invoice_xml("factura.xml", b'<?xml version="1.0"?><factura id="comprobante"/>'),
            "factura.xml",
        )
        self.assertEqual(
            _validate_ride_pdf("ride.pdf", b"%PDF-1.7\ncontenido"),
            "ride.pdf",
        )
        self.assertEqual(
            _archive_folder_path("DOCENTES/DOCENTE DE PRUEBA/DOCUMENTOS FIRMADOS"),
            "DOCENTES/DOCENTE DE PRUEBA/DOCUMENTOS FIRMADOS",
        )

        with self.assertRaises(HTTPException):
            _validate_invoice_xml("factura.xml", b"contenido que no es XML")
        with self.assertRaises(HTTPException):
            _validate_ride_pdf("ride.pdf", b"contenido que no es PDF")
        with self.assertRaises(HTTPException):
            _archive_folder_path("EXPEDIENTES ESTUDIANTILES/OTRA CARPETA")
        with self.assertRaises(HTTPException):
            _archive_folder_path("DOCENTES/DOCENTE DE PRUEBA/OTRA CARPETA")
        with self.assertRaises(HTTPException):
            _validate_invoice_xml(
                "factura.xml",
                b'<!DOCTYPE factura [<!ENTITY archivo SYSTEM "file:///etc/passwd">]><factura/>',
            )


if __name__ == "__main__":
    unittest.main()
