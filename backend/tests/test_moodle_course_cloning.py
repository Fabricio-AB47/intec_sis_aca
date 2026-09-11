import unittest
from datetime import datetime
from types import SimpleNamespace

from app.integrations.moodle.exceptions import MoodleCourseCloningError
from app.services.moodle_course_cloning import (
    CLONING_REQUIRED_FUNCTIONS,
    MoodleCourseCloningService,
)


def cloning_settings(**overrides: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "moodle_enabled": True,
        "moodle_writes_enabled": True,
        "moodle_course_cloning_enabled": True,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class FakeCloningClient:
    def __init__(self) -> None:
        self.categories = [
            {"id": 1, "name": "CURSOS_BASE_PLANTILLAS", "idnumber": "CBP", "parent": 0, "visible": 1},
            {"id": 2, "name": "TICS", "idnumber": "CBP-TICS", "parent": 1, "visible": 1},
            {"id": 3, "name": "CIBERSEGURIDAD", "idnumber": "CBP-TICS-CIBER", "parent": 2, "visible": 1},
            {"id": 4, "name": "REGULAR", "idnumber": "CBP-TICS-CIBER-REG", "parent": 3, "visible": 1},
            {"id": 5, "name": "HOMOLOGACIÓN", "idnumber": "CBP-TICS-CIBER-HOM", "parent": 3, "visible": 1},
            {"id": 6, "name": "GENERAL", "idnumber": "CBP-GEN", "parent": 1, "visible": 1},
            {"id": 7, "name": "REGULAR", "idnumber": "CBP-GEN-REG", "parent": 6, "visible": 1},
            {"id": 8, "name": "HOMOLOGACIÓN", "idnumber": "CBP-GEN-HOM", "parent": 6, "visible": 1},
        ]
        self.courses = [
            {
                "id": 101,
                "fullname": "Seguridad en Redes PLANTILLA",
                "shortname": "VGA-CIB-001-RPLAN",
                "idnumber": "VGA-ID-CIB-001-RPLAN",
                "categoryid": 4,
                "visible": 0,
            },
            {
                "id": 102,
                "fullname": "Criptografía",
                "shortname": "VGA-CIB-002-RPLAN",
                "idnumber": "VGA-ID-CIB-002-RPLAN",
                "categoryid": 4,
                "visible": 0,
            },
            {
                "id": 201,
                "fullname": "Seguridad en Redes HPLAN",
                "shortname": "VGA-CIB-001-HPLAN",
                "idnumber": "VGA-ID-CIB-001-HPLAN",
                "categoryid": 5,
                "visible": 0,
            },
        ]
        self.created_categories: list[dict] = []
        self.duplicates: list[dict] = []
        self.updates: list[dict] = []
        self._category_id = 1000
        self._course_id = 2000

    async def get_site_info(self):
        return {"functions": [{"name": name} for name in CLONING_REQUIRED_FUNCTIONS]}

    async def get_course_categories(self):
        return [dict(item) for item in self.categories]

    async def get_all_courses(self):
        return [dict(item) for item in self.courses]

    async def create_course_category(self, *, name: str, parent: int, idnumber: str):
        self._category_id += 1
        category = {
            "id": self._category_id,
            "name": name,
            "parent": parent,
            "idnumber": idnumber,
            "visible": 1,
        }
        self.categories.append(category)
        self.created_categories.append(category)
        return dict(category)

    async def duplicate_course(
        self,
        *,
        course_id: int,
        fullname: str,
        shortname: str,
        category_id: int,
        visible: bool,
    ):
        self._course_id += 1
        course = {
            "id": self._course_id,
            "fullname": fullname,
            "shortname": shortname,
            "idnumber": "",
            "categoryid": category_id,
            "visible": 1 if visible else 0,
        }
        self.courses.append(course)
        self.duplicates.append({"template": course_id, **course})
        return dict(course)

    async def update_course(
        self,
        course_id: int,
        *,
        idnumber: str,
        startdate: int,
        enddate: int | None,
        visible: bool,
    ):
        update = {
            "id": course_id,
            "idnumber": idnumber,
            "startdate": startdate,
            "enddate": enddate,
            "visible": visible,
        }
        self.updates.append(update)
        course = next(item for item in self.courses if item["id"] == course_id)
        course.update(update)


class MoodleCourseCloningServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.client = FakeCloningClient()
        self.audit_events: list[tuple[dict, dict]] = []
        self.service = MoodleCourseCloningService(
            cloning_settings(),
            client=self.client,
            auditor=lambda before, after: not self.audit_events.append((before, after)),
        )

    @staticmethod
    def request(
        course_ids: list[int],
        *,
        offer_type: str = "REGULAR",
        period_name: str = "R30",
    ) -> dict:
        return {
            "template_course_ids": course_ids,
            "offer_type": offer_type,
            "period_name": period_name,
            "opening_at": datetime(2027, 1, 11, 8, 0),
            "closing_at": datetime(2027, 3, 12, 22, 0),
            "parallel": "",
        }

    async def test_catalog_classifies_templates_from_regular_and_homologation_branches(self) -> None:
        result = await self.service.catalog()

        self.assertTrue(result["catalog_ready"])
        self.assertTrue(result["capability"]["enabled"])
        self.assertEqual(result["summary"]["regular"], 2)
        self.assertEqual(result["summary"]["homologation"], 1)
        regular = next(item for item in result["templates"] if item["course_id"] == 101)
        self.assertEqual(regular["subject_name"], "Seguridad en Redes")
        self.assertEqual(regular["area"], "TICS")
        self.assertEqual(regular["career"], "CIBERSEGURIDAD")
        self.assertEqual(regular["category_route"], ["TICS", "CIBERSEGURIDAD"])

    async def test_catalog_refresh_detects_mode_before_dynamic_career(self) -> None:
        first = await self.service.catalog()
        self.assertNotIn(301, {item["course_id"] for item in first["templates"]})

        self.client.categories.extend(
            [
                {
                    "id": 20,
                    "name": "REGULAR",
                    "idnumber": "CBP-TICS-REG",
                    "parent": 2,
                    "visible": 1,
                },
                {
                    "id": 21,
                    "name": "Big Data",
                    "idnumber": "CBP-TICS-REG-BIGDATA",
                    "parent": 20,
                    "visible": 1,
                },
            ]
        )
        self.client.courses.append(
            {
                "id": 301,
                "fullname": "Minería de Datos PLANTILLA",
                "shortname": "VGA-BIG-301-RPLAN",
                "idnumber": "VGA-ID-BIG-301-RPLAN",
                "categoryid": 21,
                "visible": 0,
            }
        )

        refreshed = await self.service.catalog()
        template = next(item for item in refreshed["templates"] if item["course_id"] == 301)

        self.assertEqual(template["category_route"], ["TICS", "Big Data"])
        self.assertEqual(template["area"], "TICS")
        self.assertEqual(template["career"], "Big Data")
        self.assertEqual(template["offer_type"], "REGULAR")

        preview = await self.service.preview(self.request([301]))
        self.assertEqual(
            preview["courses"][0]["destination_path"],
            "OFERTA_ACADEMICA/TICS/Big Data/2027/REGULAR/R30",
        )

    async def test_preview_derives_year_and_builds_both_offer_type_branches(self) -> None:
        result = await self.service.preview(self.request([101, 102]))

        self.assertTrue(result["ready"])
        self.assertEqual(result["year"], 2027)
        paths = {item["path"] for item in result["categories"]}
        self.assertIn(
            "OFERTA_ACADEMICA/TICS/CIBERSEGURIDAD/2027/REGULAR/R30",
            paths,
        )
        self.assertIn(
            "OFERTA_ACADEMICA/TICS/CIBERSEGURIDAD/2027/HOMOLOGACION",
            paths,
        )
        self.assertEqual(result["courses"][0]["fullname"], "R30 - Seguridad en Redes")
        self.assertEqual(result["courses"][0]["shortname"], "VGA-CIB-001-R30")
        self.assertEqual(result["courses"][0]["idnumber"], "VGA-ID-CIB-001-R30")
        self.assertEqual(result["summary"]["to_clone"], 2)

    async def test_homologation_period_gets_opening_year(self) -> None:
        result = await self.service.preview(
            self.request([201], offer_type="HOMOLOGACION", period_name="H1")
        )

        self.assertEqual(result["period_name"], "H1 2027")
        self.assertEqual(
            result["courses"][0]["destination_path"],
            "OFERTA_ACADEMICA/TICS/CIBERSEGURIDAD/2027/HOMOLOGACION/H1 2027",
        )
        self.assertEqual(
            result["courses"][0]["fullname"],
            "H1 2027 - Seguridad en Redes",
        )
        self.assertEqual(
            result["courses"][0]["shortname"],
            "VGA-CIB-001-H12027",
        )
        self.assertEqual(
            result["courses"][0]["idnumber"],
            "VGA-ID-CIB-001-H12027",
        )

    async def test_homologation_also_accepts_rplan_as_source_marker(self) -> None:
        self.client.courses[2]["shortname"] = "VGA-CIB-001-RPLAN"
        self.client.courses[2]["idnumber"] = "VGA-ID-CIB-001-RPLAN"

        result = await self.service.preview(
            self.request([201], offer_type="HOMOLOGACION", period_name="H1")
        )

        self.assertEqual(result["courses"][0]["shortname"], "VGA-CIB-001-H12027")
        self.assertEqual(result["courses"][0]["idnumber"], "VGA-ID-CIB-001-H12027")

    async def test_apply_creates_hidden_course_without_repeating_it(self) -> None:
        first = await self.service.apply(
            self.request([101]), actor="admin", actor_id=1
        )
        second = await self.service.apply(
            self.request([101]), actor="admin", actor_id=1
        )

        self.assertEqual(first["created_count"], 1)
        self.assertEqual(second["created_count"], 0)
        self.assertEqual(second["skipped_count"], 1)
        self.assertEqual(len(self.client.duplicates), 1)
        self.assertFalse(self.client.duplicates[0]["visible"])
        self.assertFalse(self.client.updates[0]["visible"])
        created_names = {item["name"] for item in self.client.created_categories}
        self.assertIn("REGULAR", created_names)
        self.assertIn("HOMOLOGACION", created_names)
        self.assertEqual(len(self.audit_events), 1)

    async def test_rejects_template_from_another_offer_type(self) -> None:
        with self.assertRaises(MoodleCourseCloningError):
            await self.service.preview(self.request([201]))

    async def test_preview_blocks_category_code_assigned_to_another_name(self) -> None:
        self.client.categories.append(
            {
                "id": 900,
                "name": "OTRA_OFERTA",
                "idnumber": "OFA",
                "parent": 0,
                "visible": 1,
            }
        )

        result = await self.service.preview(self.request([101]))

        self.assertFalse(result["ready"])
        conflict = next(item for item in result["categories"] if item["status"] == "CONFLICTO")
        self.assertIn("otro nombre", conflict["conflict"])

    async def test_generated_category_codes_respect_moodle_limit(self) -> None:
        long_area = "ÁREA " + "EXTENSA " * 20
        self.client.categories[1]["name"] = long_area

        result = await self.service.preview(self.request([101]))

        self.assertTrue(result["ready"])
        self.assertTrue(all(len(item["idnumber"]) <= 100 for item in result["categories"]))

    async def test_preview_blocks_two_templates_with_same_generated_identity(self) -> None:
        self.client.courses[1]["shortname"] = "VGA-CIB-001-RPLAN"
        self.client.courses[1]["idnumber"] = "VGA-ID-CIB-001-RPLAN"

        result = await self.service.preview(self.request([101, 102]))

        self.assertFalse(result["ready"])
        self.assertEqual(result["summary"]["course_conflicts"], 2)
        self.assertTrue(all(item["status"] == "CONFLICTO" for item in result["courses"]))

    async def test_general_template_uses_general_without_career_segment(self) -> None:
        self.client.courses.append(
            {
                "id": 301,
                "fullname": "Pensamiento Crítico",
                "shortname": "VGA-GEN-001-RPLAN",
                "idnumber": "VGA-ID-GEN-001-RPLAN",
                "categoryid": 7,
                "visible": 0,
            }
        )

        result = await self.service.preview(self.request([301]))

        self.assertTrue(result["ready"])
        self.assertEqual(result["courses"][0]["career"], "")
        self.assertEqual(
            result["courses"][0]["destination_path"],
            "OFERTA_ACADEMICA/GENERAL/2027/REGULAR/R30",
        )

    async def test_preview_rejects_template_without_the_expected_plan_marker(self) -> None:
        self.client.courses[0]["shortname"] = "VGA-CIB-001"

        with self.assertRaisesRegex(MoodleCourseCloningError, "RPLAN"):
            await self.service.preview(self.request([101]))

    async def test_apply_requires_dedicated_feature_flag(self) -> None:
        service = MoodleCourseCloningService(
            cloning_settings(moodle_course_cloning_enabled=False),
            client=self.client,
            auditor=lambda _before, _after: True,
        )

        with self.assertRaises(MoodleCourseCloningError):
            await service.apply(self.request([101]), actor="admin", actor_id=1)

    async def test_apply_reports_missing_audit_as_warning(self) -> None:
        service = MoodleCourseCloningService(
            cloning_settings(),
            client=self.client,
            auditor=lambda _before, _after: False,
        )

        result = await service.apply(
            self.request([101]), actor="admin", actor_id=1
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["warning_count"], 1)
        self.assertEqual(result["courses"][0]["status"], "CREADO_CON_ADVERTENCIA")
        self.assertIn("auditoría", result["courses"][0]["message"])


if __name__ == "__main__":
    unittest.main()
