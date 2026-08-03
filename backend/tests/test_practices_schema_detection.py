import unittest
from unittest.mock import patch

from app.routers.practicas_institucionales import _use_legacy_schema


class PracticesSchemaDetectionTests(unittest.TestCase):
    @staticmethod
    def _objects(*names: str):
        available = set(names)
        return lambda _cursor, name: name in available

    def test_prefers_complete_pp_schema_when_modern_responsible_table_is_missing(self) -> None:
        objects = self._objects(
            "cat.tipo_proceso",
            "cat.tipo_documento_practica",
            "pp.expediente_practica",
            "pp.responsable_proceso",
            "cat.TipoProceso",
            "cat.TipoDocumento",
            "exp.Expediente",
        )
        with patch("app.routers.practicas_institucionales._has_object", side_effect=objects):
            self.assertTrue(_use_legacy_schema(object()))

    def test_uses_modern_schema_only_when_all_modern_objects_exist(self) -> None:
        objects = self._objects(
            "cat.TipoProceso",
            "cat.TipoDocumento",
            "exp.Expediente",
            "resp.ResponsableProceso",
        )
        with patch("app.routers.practicas_institucionales._has_object", side_effect=objects):
            self.assertFalse(_use_legacy_schema(object()))

    def test_rejects_partial_database_instead_of_querying_missing_tables(self) -> None:
        objects = self._objects("cat.TipoProceso", "exp.Expediente")
        with patch("app.routers.practicas_institucionales._has_object", side_effect=objects):
            with self.assertRaisesRegex(RuntimeError, "estructura operativa completa"):
                _use_legacy_schema(object())


if __name__ == "__main__":
    unittest.main()
