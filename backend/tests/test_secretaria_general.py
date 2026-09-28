import unittest
from xml.etree.ElementTree import fromstring
from unittest.mock import MagicMock, patch

from fastapi import HTTPException

from app.core.security import SessionUser
from app.routers.secretaria_general import (
    RequirementReviewPayload,
    _applicable_column,
    _candidate_codes_with_missing_documents,
    _document,
    _enrollment_type,
    _homologation_article_code,
    _query_candidates,
    review_secretaria_requirement,
    secretaria_candidates,
)


def profile() -> SessionUser:
    return SessionUser(
        login="secretaria@intec.edu.ec",
        nombres="Secretaría de prueba",
        email="secretaria@intec.edu.ec",
        rol="SECRETARIA",
    )


class SecretariaGeneralRulesTests(unittest.TestCase):
    def test_document_normalization_removes_formatting(self) -> None:
        self.assertEqual(_document(" 17-123.456 789 "), "17123456789")

    def test_stage_uses_a_fixed_template_column(self) -> None:
        self.assertEqual(_applicable_column("PROXIMO"), "AplicaProximo")
        self.assertEqual(_applicable_column("EGRESADO"), "AplicaEgresado")
        self.assertEqual(_applicable_column("GRADUADO"), "AplicaGraduado")
        with self.assertRaises(KeyError):
            _applicable_column("OTRO")

    def test_enrollment_type_maps_normal_and_homologation_values(self) -> None:
        self.assertEqual(_enrollment_type("N", "C1-2026-PB"), "R")
        self.assertEqual(_enrollment_type("R", "R30"), "R")
        self.assertEqual(_enrollment_type("H", "1060"), "H")
        self.assertEqual(_enrollment_type("", "C1-HOMO-2026-PB"), "H")

    def test_homologation_classification_selects_only_its_article(self) -> None:
        self.assertEqual(_homologation_article_code("INTERNA_ART81"), "HOMOLOGACION_ARTICULO_81")
        self.assertEqual(_homologation_article_code("EXTERNA_ART82"), "HOMOLOGACION_ARTICULO_82")
        self.assertEqual(_homologation_article_code("EXTERNA_ART83"), "HOMOLOGACION_ARTICULO_83")
        self.assertIsNone(_homologation_article_code(""))

    @patch("app.routers.secretaria_general.get_secretaria_connection")
    def test_missing_document_filter_returns_affected_students(self, connection_factory: MagicMock) -> None:
        connection = MagicMock()
        cursor = MagicMock()
        connection.__enter__.return_value = connection
        connection.cursor.return_value = cursor
        cursor.fetchall.return_value = [(101,), (202,), (None,)]
        connection_factory.return_value = connection

        self.assertEqual(_candidate_codes_with_missing_documents(), [101, 202])

    @patch("app.routers.secretaria_general.get_connection")
    def test_empty_missing_document_filter_skips_academic_query(self, connection_factory: MagicMock) -> None:
        self.assertEqual(_query_candidates(candidate_codes=[]), ([], 0))
        connection_factory.assert_not_called()

    @patch("app.routers.secretaria_general._case_summaries", return_value={})
    @patch("app.routers.secretaria_general._query_candidates", return_value=([], 0))
    @patch("app.routers.secretaria_general._candidate_codes_with_missing_documents", return_value=[101, 202])
    def test_candidates_endpoint_applies_missing_document_submenu(
        self,
        missing_codes: MagicMock,
        query_candidates: MagicMock,
        _case_summaries: MagicMock,
    ) -> None:
        result = secretaria_candidates(
            profile(),
            search="",
            stage="TODOS",
            only_missing_documents=True,
            page=1,
            page_size=25,
        )

        missing_codes.assert_called_once_with()
        query_candidates.assert_called_once_with(
            search="",
            stage="TODOS",
            page=1,
            page_size=25,
            candidate_codes=[101, 202],
        )
        self.assertEqual(result["total"], 0)

    @patch("app.routers.secretaria_general.get_connection")
    def test_large_missing_document_filter_uses_one_structured_parameter(self, connection_factory):
        cursor = connection_factory.return_value.__enter__.return_value.cursor.return_value
        cursor.description = []
        cursor.fetchall.return_value = []
        _query_candidates(candidate_codes=list(range(1, 3002)) + [1, 2])
        sql, *parameters = cursor.execute.call_args.args
        self.assertIn("CAST(? AS xml)", sql)
        self.assertEqual(len(parameters), 12)
        self.assertTrue(sql.startswith('DECLARE @candidate_codes xml'))
        self.assertIn("FROM @candidate_codes.nodes('/codes/code')", sql)
        codes = fromstring(parameters[0])
        self.assertEqual(len(codes), 3001)
        self.assertEqual(codes[0].text, '1')
        self.assertEqual(codes[-1].text, '3001')

    @patch("app.routers.secretaria_general._case_summaries", return_value={})
    @patch("app.routers.secretaria_general._query_candidates")
    def test_empty_later_page_refreshes_first_page_instead_of_false_zero(self, query, _summaries):
        query.side_effect = [([], 0), ([{'codigo_estud': 101}], 1)]
        result = secretaria_candidates(profile(), page=3)
        self.assertEqual(result['page'], 1)
        self.assertEqual(result['total'], 1)
        self.assertEqual(query.call_count, 2)

    def test_observation_requires_a_useful_reason(self) -> None:
        payload = RequirementReviewPayload(estado="OBSERVADO", observacion="x")

        with self.assertRaises(HTTPException) as context:
            review_secretaria_requirement(1, 1, payload, profile())

        self.assertEqual(context.exception.status_code, 422)

    @patch("app.routers.secretaria_general.get_secretaria_connection")
    def test_validation_requires_linked_evidence(self, connection_factory: MagicMock) -> None:
        connection = MagicMock()
        cursor = MagicMock()
        connection.__enter__.return_value = connection
        connection.cursor.return_value = cursor
        cursor.fetchone.side_effect = [MagicMock(EstadoCodigo="PRESENTE"), None]
        connection_factory.return_value = connection
        payload = RequirementReviewPayload(estado="VALIDADO", observacion="Documento legible")

        with self.assertRaises(HTTPException) as context:
            review_secretaria_requirement(10, 20, payload, profile())

        self.assertEqual(context.exception.status_code, 409)
        connection.commit.assert_not_called()


if __name__ == "__main__":
    unittest.main()
