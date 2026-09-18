from datetime import datetime
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pypdf import PdfReader
import pytest

from app.core.security import SessionUser
from app.routers import credential_generator as credentials, direct_admission as admission
from app.services import direct_admission_credentials as service
from app.services.direct_admission_receipt import build_receipt_pdf, platform_status


ADMIN = SessionUser(login="admin@example.test", rol="ADMINISTRADOR")
IDENTITY, EMAIL = "1724036536", "ana.perez@intec.edu.ec"
PROFILE = {"record": {"nivel": 1}, "identity": IDENTITY, "code": 123, "name": "PEREZ ANA",
           "period": 1060, "email": EMAIL, "correo_datos": EMAIL, "correo_credenciales": EMAIL}
RESULT = {"estado_graph": "CREADO_GRAPH", "estado_moodle": "CREADO_MOODLE", "correo_institucional": EMAIL,
          "estado_licencia": "ASIGNADA_ESTUDIANTE"}


def archived(**change):
    return SimpleNamespace(**{"id": 88, "cedula": IDENTITY, "correo_institucional": EMAIL,
        "tipo_persona": "ESTUDIANTE", "clave_cifrada": "mock-cipher", "fecha_creacion": datetime(2026, 9, 18, 9, 0), **change})


@pytest.mark.parametrize("status,label", [("CREADO_GRAPH", "Creado"), ("EXISTENTE_MOODLE", "Existente verificado"),
    ("ERROR_MOODLE", "Con novedades; no confirmado"), ("CONFLICTO_MOODLE", "Con novedades; no confirmado"),
    (None, "Pendiente de verificaci\u00f3n")])
def test_receipt_platform_labels_do_not_claim_unconfirmed_creation(status, label):
    assert platform_status(status) == label


def test_passwords_are_read_from_encrypted_archive_separately_for_each_platform():
    cursor = Mock()
    cursor.fetchone.side_effect = [[1], archived(), archived(id=99, clave_cifrada="another-cipher")]
    with patch.object(credentials, "_decrypt_credential_password", side_effect=["mock-office-key", "mock-moodle-key"]) as decrypt:
        passwords, dates, ids = service._issued_passwords(cursor, PROFILE, RESULT)
    assert passwords == {"office": "mock-office-key", "moodle": "mock-moodle-key"}
    assert ids == {88, 99} and len(dates) == 2 and decrypt.call_count == 2
    queries = cursor.execute.call_args_list[1:]
    assert queries[0].args[1:] == (IDENTITY, EMAIL, "CREADO_GRAPH")
    assert queries[1].args[1:] == (IDENTITY, EMAIL, "CREADO_MOODLE")
    assert "clave_emitida=1" in queries[0].args[0]
    assert "Password" not in " ".join(call.args[0] for call in queries)


@pytest.mark.parametrize("change", [{"cedula": "AB123456"}, {"correo_institucional": "other@intec.edu.ec"}, {"tipo_persona": "DOCENTE"}])
def test_another_persons_archived_password_cannot_be_downloaded(change):
    cursor = Mock()
    cursor.fetchone.side_effect = [[1], archived(**change)]
    with patch.object(credentials, "_decrypt_credential_password") as decrypt, pytest.raises(HTTPException) as error:
        service._issued_passwords(cursor, PROFILE, RESULT)
    assert error.value.status_code == 409
    decrypt.assert_not_called()


def test_accounts_without_archived_password_are_not_assigned_an_invented_one():
    cursor = Mock()
    cursor.fetchone.side_effect = [[1], None, None]
    with patch.object(credentials, "_decrypt_credential_password") as decrypt, patch.object(credentials, "_permanent_password") as invent:
        passwords, _, ids = service._issued_passwords(cursor, PROFILE, {**RESULT, "estado_graph": "EXISTENTE_GRAPH", "estado_moodle": "EXISTENTE_MOODLE"})
    assert not passwords and not ids
    decrypt.assert_not_called()
    invent.assert_not_called()


def test_unconfirmed_platform_does_not_disclose_its_old_password():
    cursor = Mock()
    cursor.fetchone.side_effect = [[1], archived()]
    with patch.object(credentials, "_decrypt_credential_password", return_value="mock-office-key"):
        passwords, _, _ = service._issued_passwords(cursor, PROFILE, {**RESULT, "estado_moodle": "ERROR_MOODLE"})
    assert passwords == {"office": "mock-office-key"} and len(cursor.execute.call_args_list) == 2


def test_missing_archive_stays_readonly_and_missing_cipher_key_fails_safely():
    cursor = Mock()
    cursor.fetchone.return_value = [None]
    assert service._issued_passwords(cursor, PROFILE, RESULT) == ({}, [], set())
    cursor.fetchone.side_effect = [[1], archived()]
    with patch.object(credentials, "_decrypt_credential_password", side_effect=RuntimeError("mock-error-secret")), pytest.raises(HTTPException) as error:
        service._issued_passwords(cursor, PROFILE, RESULT)
    assert error.value.status_code == 409 and "mock-error-secret" not in str(error.value.detail)


def item(**change):
    return {"request_id": str(uuid4()), "identity": IDENTITY, "name": "PEREZ LOPEZ ANA MAR\u00cdA", "code": 123,
        "career": "Ciberseguridad", "period": "C1-2026-PB", "level": 1, "email": EMAIL,
        "passwords": {"office": "mock-office<&>-key", "moodle": "mock-moodle-key"}, "email_synchronized": True, **RESULT, **change}


def test_pdf_contains_student_password_and_truthful_platform_and_sync_states():
    content = build_receipt_pdf([item()], ADMIN.login)
    reader = PdfReader(BytesIO(content))
    text = reader.pages[0].extract_text()
    assert len(reader.pages) == 1
    for value in [IDENTITY, EMAIL, "mock-office<&>-key", "mock-moodle-key", "Ciberseguridad", "Office 365", "Moodle", "CorreosEstudIntec", "Contrase\u00f1a emitida", ADMIN.login]:
        assert value in text
    assert "Creado" in text and "cifradas" in text and "Confidencial" in text


def test_pdf_has_one_page_per_student_even_with_long_names_and_errors():
    items = [item(name="ESTUDIANTE " * 7, career="CARRERA " * 25, errors=["Error " * 250]),
             item(identity="AB123456", passwords={}, estado_graph="EXISTENTE_GRAPH", estado_moodle="ERROR_MOODLE", email_synchronized=False)]
    reader = PdfReader(BytesIO(build_receipt_pdf(items, ADMIN.login)))
    assert len(reader.pages) == 2
    second = reader.pages[1].extract_text()
    assert "No disponible en el registro cifrado" in second and "Existente verificado" in second
    assert "no confirmado" in second and "Sincronizaci\u00f3n pendiente" in second and "mock-office" not in second


def test_pdf_renders_a_nonblank_document_with_project_brand():
    import pypdfium2 as pdfium
    content = build_receipt_pdf([item()], ADMIN.login)
    pdf = pdfium.PdfDocument(content)
    page = pdf[0]
    bitmap = page.render(scale=1.3)
    preview = bitmap.to_pil()
    try:
        with preview.resize((120, 170)) as thumbnail:
            assert len(set(thumbnail.tobytes())) > 20
        folder = Path(__file__).resolve().parents[2] / ".runlogs"
        folder.mkdir(exist_ok=True)
        preview.save(folder / "direct-admission-receipt.png")
    finally:
        preview.close()
        bitmap.close()
        page.close()
        pdf.close()


def test_combined_receipts_reject_unauthorized_profiles_before_reading_credentials():
    with patch.object(service, "get_connection") as db, pytest.raises(HTTPException) as error:
        service.admission_receipts([uuid4()], SessionUser(login="academic@example.test", rol="ACADEMICO"))
    assert error.value.status_code == 403
    db.assert_not_called()


def test_combined_download_checks_each_student_and_audits_each_used_credential_only_once():
    connection = MagicMock()
    connection.__enter__.return_value = connection
    connection.cursor.return_value.fetchone.return_value = SimpleNamespace(Nombre_Basica="Ciberseguridad", Detalle_Periodo="C1-2026-PB")
    first, second = uuid4(), uuid4()
    with patch.object(service, "get_connection", return_value=connection), \
         patch.object(service, "_profile", return_value=PROFILE) as profile, \
         patch.object(service, "_read_state", return_value={"result": RESULT}), \
         patch.object(service, "_issued_passwords", return_value=({"office": "mock"}, [], {88})), \
         patch.object(service, "build_receipt_pdf", return_value=b"%PDF-mock") as render:
        content = service.admission_receipts([first, second, first], ADMIN)
    assert content == b"%PDF-mock" and profile.call_count == 2
    assert len(render.call_args.args[0]) == 2
    updates = [call for call in connection.cursor.return_value.execute.call_args_list if "numero_descargas" in call.args[0]]
    assert len(updates) == 1 and updates[0].args[1:] == (ADMIN.login, 88)
    connection.commit.assert_called_once()


def test_changed_academic_email_blocks_old_credential_disclosure():
    connection = MagicMock()
    connection.__enter__.return_value = connection
    with patch.object(service, "get_connection", return_value=connection), patch.object(service, "_profile", return_value=PROFILE), \
         patch.object(service, "_read_state", return_value={"result": {**RESULT, "correo_institucional": "other@intec.edu.ec"}}), \
         patch.object(service, "_issued_passwords") as secrets, pytest.raises(HTTPException) as error:
        service.admission_receipts([uuid4()], ADMIN)
    assert error.value.status_code == 409
    secrets.assert_not_called()
    connection.commit.assert_not_called()


def test_receipt_http_routes_are_private_and_validate_uuid_and_nonempty_batch():
    app = FastAPI()
    app.include_router(admission.router)
    app.dependency_overrides[admission._ACCESS] = lambda: ADMIN
    identifier = uuid4()
    with TestClient(app) as client, patch.object(admission, "admission_receipts", return_value=b"%PDF-mock") as generate:
        for response in [client.get(f"/api/students/ingreso-directo/{identifier}/comprobante"),
                         client.post("/api/students/ingreso-directo/comprobantes", json={"solicitud_ids": [str(identifier)]})]:
            assert response.status_code == 200 and response.headers["content-type"] == "application/pdf"
            assert response.headers["cache-control"] == "no-store, private" and response.headers["pragma"] == "no-cache"
        assert generate.call_count == 2
        for body in [{"solicitud_ids": []}, {"solicitud_ids": ["invalid"]}, {"solicitud_ids": [str(identifier)], "password": "not-accepted"}]:
            assert client.post("/api/students/ingreso-directo/comprobantes", json=body).status_code == 422
        assert generate.call_count == 2
