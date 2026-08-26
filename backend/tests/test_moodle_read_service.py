import unittest
from types import SimpleNamespace

from pydantic import SecretStr

from app.integrations.moodle.exceptions import (
    MoodleCourseNotFoundError,
    MoodleFullScanDisabledError,
    MoodleInstitutionalEmailNotFoundError,
    MoodleResourceNotFoundError,
    MoodleResultLimitExceededError,
    MoodleSectionUpdateError,
    MoodleUserNotConfirmedError,
)
from app.services.moodle_read_service import MoodleReadService


def service_settings(**overrides: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "moodle_base_url": "https://moodle.example.edu",
        "moodle_token": SecretStr("token-de-prueba-no-real"),
        "moodle_enabled": True,
        "moodle_writes_enabled": True,
        "moodle_user_status_update_enabled": True,
        "moodle_section_updates_enabled": True,
        "moodle_cache_ttl_seconds": 120,
        "moodle_max_user_scan_items": 100,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class FakeMoodleClient:
    def __init__(self) -> None:
        self.user_calls = 0
        self.course_calls = 0
        self.content_calls = 0
        self.grade_calls = 0
        self.enrollment_calls = 0
        self.status_updates: list[tuple[int, bool]] = []
        self.section_updates: list[tuple[int, int, bool]] = []
        self.section_name_updates: list[tuple[int, str, str]] = []
        self.section_visible = True
        self.section_name = "Unidad 1"
        self.opened_files: list[str] = []

    async def get_site_info(self):
        return {
            "sitename": "Campus de prueba",
            "siteurl": "https://moodle.example.edu",
            "username": "servicio",
            "userid": 7,
            "release": "4.5",
            "version": "202410",
            "userissiteadmin": True,
            "functions": [
                {"name": "core_webservice_get_site_info"},
                {"name": "core_user_get_users"},
                {"name": "core_course_get_courses_by_field"},
                {"name": "core_course_get_contents"},
                {"name": "core_enrol_get_enrolled_users"},
                {"name": "gradereport_user_get_grade_items"},
                {"name": "core_user_update_users"},
                {"name": "core_course_edit_section"},
                {"name": "core_update_inplace_editable"},
            ],
            "userprivateaccesskey": "no-debe-salir",
        }

    async def get_all_users(self):
        self.user_calls += 1
        return [
            {
                "id": 2,
                "username": "suspendido",
                "firstname": "Álvaro",
                "lastname": "Pérez",
                "email": "alvaro@example.edu",
                "idnumber": "0100000002",
                "institution": "INTEC",
                "department": "Idiomas",
                "auth": "manual",
                "suspended": 1,
                "confirmed": 1,
                "password": "dato-sensible",
                "customfields": [{"name": "privado"}],
            },
            {
                "id": 1,
                "username": "activo",
                "firstname": "Ana",
                "lastname": "López",
                "email": "ana@example.edu",
                "auth": "oauth2",
                "suspended": 0,
                "confirmed": 1,
            },
            {
                "id": 3,
                "username": "pendiente",
                "firstname": "Carlos",
                "lastname": "Ruiz",
                "email": "carlos@example.edu",
                "auth": "manual",
                "suspended": 0,
                "confirmed": 0,
            },
        ]

    async def get_all_courses(self):
        self.course_calls += 1
        return [
            {
                "id": 12,
                "fullname": "Inglés A2",
                "displayname": "Inglés A2",
                "shortname": "ING-A2",
                "idnumber": "A2-2026",
                "categoryid": 4,
                "categoryname": "Escuela de Idiomas",
                "summary": "<p>Curso <strong>intermedio</strong>.</p><script>secreto()</script>",
                "format": "topics",
                "visible": 1,
                "startdate": 100,
                "enddate": 200,
                "enablecompletion": 1,
                "timecreated": 90,
                "timemodified": 150,
                "files": [{"url": "privado"}],
            },
            {
                "id": 11,
                "fullname": "Curso oculto",
                "shortname": "OCULTO",
                "categoryid": 8,
                "categoryname": "Pruebas",
                "visible": 0,
            },
        ]

    async def get_course_contents(self, course_id: int):
        self.content_calls += 1
        if course_id != 12:
            return []
        return [
            {
                "id": 30,
                "section": 1,
                "name": self.section_name,
                "summary": "<p>Introducción al curso.</p><script>privado()</script>",
                "visible": 1 if self.section_visible else 0,
                "uservisible": 1,
                "modules": [
                    {
                        "id": 44,
                        "url": "https://moodle.example.edu/mod/resource/view.php?id=44&wstoken=secreto",
                        "name": "Guía de estudio",
                        "instance": 70,
                        "contextid": 90,
                        "visible": 1,
                        "uservisible": 1,
                        "modname": "resource",
                        "modplural": "Archivos",
                        "description": "<p>Documento principal.</p>",
                        "dates": [{"label": "Entrega", "timestamp": 200, "dataid": "1"}],
                        "contents": [
                            {
                                "type": "file",
                                "filename": "guia.pdf",
                                "filepath": "/",
                                "filesize": 2048,
                                "fileurl": "https://moodle.example.edu/pluginfile.php/90/guia.pdf?forcedownload=1&token=secreto",
                                "timemodified": 150,
                                "mimetype": "application/pdf",
                                "author": "Docente",
                            }
                        ],
                        "customdata": "no-debe-salir",
                    }
                ],
            }
        ]

    async def get_course_enrolled_users(self, course_id: int):
        self.enrollment_calls += 1
        if course_id != 12:
            return []
        return [
            {
                "id": 31,
                "username": "estudiante",
                "firstname": "Estudiante",
                "lastname": "Prueba",
                "email": "ESTUDIANTE@INTEC.EDU.EC",
                "suspended": 0,
                "confirmed": 1,
            }
        ]

    async def get_course_grade_items(self, course_id: int):
        self.grade_calls += 1
        if course_id != 12:
            return []
        return [
            {
                "userid": 31,
                "gradeitems": [
                    {
                        "id": 77,
                        "itemname": "Cuestionario P1",
                        "itemmodule": "quiz",
                        "iteminstance": 71,
                        "graderaw": 9,
                        "grademax": 10,
                    }
                ],
            }
        ]

    async def update_user_suspension(self, user_id: int, *, suspended: bool) -> None:
        self.status_updates.append((user_id, suspended))

    async def edit_section_visibility(
        self,
        section_id: int,
        *,
        section_number: int,
        visible: bool,
    ) -> None:
        self.section_updates.append((section_id, section_number, visible))
        self.section_visible = visible

    async def edit_section_name(
        self,
        section_id: int,
        *,
        course_format: str,
        name: str,
    ) -> None:
        self.section_name_updates.append((section_id, course_format, name))
        self.section_name = name

    async def open_file(self, file_url: str):
        self.opened_files.append(file_url)
        return SimpleNamespace(marker="stream")


class MoodleReadServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.client = FakeMoodleClient()
        self.service = MoodleReadService(service_settings(), client=self.client)

    async def test_status_is_sanitized_and_reports_required_functions(self) -> None:
        result = await self.service.get_status()

        self.assertTrue(result["reachable"])
        self.assertEqual(result["site_name"], "Campus de prueba")
        self.assertEqual(result["missing_required_functions"], [])
        self.assertTrue(result["user_status_updates_enabled"])
        self.assertTrue(result["section_updates_enabled"])
        self.assertNotIn("userprivateaccesskey", result)
        self.assertNotIn("token", result)

    async def test_normalizes_users_and_removes_sensitive_fields(self) -> None:
        result = await self.service.list_users(page=1, page_size=10)
        users = {item["username"]: item for item in result["items"]}

        self.assertEqual(users["activo"]["status"], "ACTIVO")
        self.assertEqual(users["suspendido"]["status"], "SUSPENDIDO")
        self.assertEqual(users["pendiente"]["status"], "NO_CONFIRMADO")
        self.assertEqual(users["suspendido"]["fullname"], "Álvaro Pérez")
        self.assertNotIn("password", users["suspendido"])
        self.assertNotIn("customfields", users["suspendido"])

    async def test_user_search_uses_email_only_and_is_case_insensitive(self) -> None:
        result = await self.service.list_users(email="ALVARO@EXAMPLE.EDU")

        self.assertEqual(result["pagination"]["total_items"], 1)
        self.assertEqual(result["items"][0]["username"], "suspendido")

        name_result = await self.service.list_users(email="Álvaro Pérez")
        self.assertEqual(name_result["pagination"]["total_items"], 0)

    async def test_user_filters_and_pagination_are_local(self) -> None:
        first_page = await self.service.list_users(page=1, page_size=1, state="active")
        second_read = await self.service.list_users(page=1, page_size=10, state="all")

        self.assertEqual(first_page["pagination"]["total_items"], 1)
        self.assertEqual(first_page["items"][0]["username"], "activo")
        self.assertEqual(second_read["pagination"]["total_items"], 3)
        self.assertEqual(self.client.user_calls, 1)
        self.assertTrue(second_read["source"]["cached"])

    async def test_refresh_reloads_user_cache(self) -> None:
        await self.service.list_users()
        result = await self.service.list_users(refresh=True)

        self.assertEqual(self.client.user_calls, 2)
        self.assertFalse(result["source"]["cached"])

    async def test_normalizes_courses_and_sanitizes_summary(self) -> None:
        result = await self.service.list_courses(page_size=10)
        course = next(item for item in result["items"] if item["id"] == 12)

        self.assertEqual(course["summary"], "Curso intermedio .")
        self.assertTrue(course["visible"])
        self.assertNotIn("files", course)
        self.assertNotIn("script", course["summary"].lower())

    async def test_grade_items_are_scoped_to_evaluation_course_section(self) -> None:
        original_contents = self.client.get_course_contents

        async def contents_with_evaluation(course_id: int):
            sections = await original_contents(course_id)
            sections.append(
                {
                    "id": 31,
                    "section": 2,
                    "name": "Evaluación - Parcial 1",
                    "visible": 1,
                    "uservisible": 1,
                    "modules": [
                        {
                            "id": 45,
                            "name": "Cuestionario P1",
                            "instance": 71,
                            "visible": 1,
                            "uservisible": 1,
                            "modname": "quiz",
                        }
                    ],
                }
            )
            return sections

        self.client.get_course_contents = contents_with_evaluation

        result = await self.service.get_course_grade_items(12)
        grade_item = result[0]["gradeitems"][0]

        self.assertTrue(grade_item["evaluation_scope"])
        self.assertEqual(grade_item["course_section_name"], "Evaluación - Parcial 1")
        self.assertTrue(grade_item["course_section_visible"])
        self.assertTrue(grade_item["course_module_visible"])
        self.assertEqual(grade_item["course_module_order"], 1)
        self.assertEqual(self.client.grade_calls, 1)

    def test_similar_but_different_section_name_is_not_evaluation(self) -> None:
        self.assertFalse(MoodleReadService._is_evaluation_section_name("Autoevaluación"))
        self.assertTrue(MoodleReadService._is_evaluation_section_name("Evaluaciones P2"))
        self.assertFalse(
            MoodleReadService._is_evaluation_section_name("Evaluación de Recuperación")
        )

    def test_evaluation_block_includes_three_partials_and_excludes_other_sections(self) -> None:
        grade_groups = [
            {
                "userid": 7,
                "gradeitems": [
                    {"id": 1, "itemmodule": "quiz", "iteminstance": 500},
                    {"id": 2, "itemmodule": "quiz", "iteminstance": 501},
                    {"id": 3, "itemmodule": "assign", "iteminstance": 502},
                    {"id": 4, "itemmodule": "quiz", "iteminstance": 503},
                    {"id": 5, "itemmodule": "assign", "iteminstance": 504},
                    {"id": 6, "itemmodule": "quiz", "iteminstance": 505},
                    {"id": 7, "itemmodule": "assign", "iteminstance": 506},
                    {"id": 8, "itemmodule": "quiz", "iteminstance": 507},
                ],
            }
        ]
        sections = [
            {
                "id": 90,
                "section": 9,
                "name": "Simuladores",
                "visible": True,
                "uservisible": True,
                "modules": [
                    {
                        "id": 900,
                        "name": "Simulador Parcial 1",
                        "modname": "quiz",
                        "instance": 500,
                        "visible": True,
                        "uservisible": True,
                    }
                ],
            },
            {
                "id": 120,
                "section": 12,
                "name": "Evaluaciones",
                "visible": True,
                "uservisible": True,
                "modules": [
                    {
                        "id": 1200,
                        "name": "Primer parcial",
                        "modname": "label",
                        "instance": 700,
                        "visible": True,
                        "uservisible": True,
                    },
                    {
                        "id": 1201,
                        "name": "Cuestionario con nombre libre",
                        "modname": "quiz",
                        "instance": 501,
                        "visible": True,
                        "uservisible": True,
                    },
                    {
                        "id": 1202,
                        "name": "Tarea con nombre libre",
                        "modname": "assign",
                        "instance": 502,
                        "visible": True,
                        "uservisible": True,
                    },
                ],
            },
            {
                "id": 130,
                "section": 13,
                "name": "Segundo parcial",
                "visible": True,
                "uservisible": True,
                "modules": [
                    {
                        "id": 1301,
                        "name": "Cuestionario con nombre libre",
                        "modname": "quiz",
                        "instance": 503,
                        "visible": True,
                        "uservisible": True,
                    },
                    {
                        "id": 1302,
                        "name": "Tarea con nombre libre",
                        "modname": "assign",
                        "instance": 504,
                        "visible": True,
                        "uservisible": True,
                    },
                ],
            },
            {
                "id": 140,
                "section": 14,
                "name": "Tercer parcial",
                "visible": True,
                "uservisible": True,
                "modules": [
                    {
                        "id": 1401,
                        "name": "Cuestionario con nombre libre",
                        "modname": "quiz",
                        "instance": 505,
                        "visible": True,
                        "uservisible": True,
                    },
                    {
                        "id": 1402,
                        "name": "Tarea con nombre libre",
                        "modname": "assign",
                        "instance": 506,
                        "visible": True,
                        "uservisible": True,
                    },
                ],
            },
            {
                "id": 150,
                "section": 15,
                "name": "Evaluación de Recuperación",
                "visible": True,
                "uservisible": True,
                "modules": [
                    {
                        "id": 1501,
                        "name": "Recuperación",
                        "modname": "quiz",
                        "instance": 507,
                        "visible": True,
                        "uservisible": True,
                    }
                ],
            },
        ]

        enriched = MoodleReadService._grade_items_with_course_sections(
            grade_groups,
            sections,
        )
        items = {
            item["iteminstance"]: item
            for item in enriched[0]["gradeitems"]
        }

        self.assertFalse(items[500]["evaluation_scope"])
        self.assertFalse(items[507]["evaluation_scope"])
        for instance, partial in (
            (501, 1),
            (502, 1),
            (503, 2),
            (504, 2),
            (505, 3),
            (506, 3),
        ):
            self.assertTrue(items[instance]["evaluation_scope"])
            self.assertEqual(items[instance]["course_section_partial"], partial)

    def test_labels_keep_multiple_attempts_inside_the_same_partial(self) -> None:
        grade_groups = [
            {
                "userid": 9,
                "gradeitems": [
                    {"id": 21, "itemmodule": "quiz", "iteminstance": 801},
                    {"id": 22, "itemmodule": "quiz", "iteminstance": 802},
                    {"id": 23, "itemmodule": "assign", "iteminstance": 803},
                    {"id": 24, "itemmodule": "assign", "iteminstance": 804},
                ],
            }
        ]
        sections = [
            {
                "id": 612,
                "section": 12,
                "name": "Evaluaciones",
                "visible": True,
                "uservisible": True,
                "modules": [
                    {
                        "id": 800,
                        "name": "Primer parcial",
                        "modname": "label",
                        "instance": 800,
                        "visible": True,
                        "uservisible": True,
                    },
                    {
                        "id": 805,
                        "name": "Componente teórico",
                        "modname": "label",
                        "instance": 805,
                        "visible": True,
                        "uservisible": True,
                    },
                    {
                        "id": 801,
                        "name": "Evaluación Parcial No.1",
                        "modname": "quiz",
                        "instance": 801,
                        "visible": True,
                        "uservisible": True,
                    },
                    {
                        "id": 802,
                        "name": "Evaluación Parcial - 2da oportunidad personas que no rindieron",
                        "modname": "quiz",
                        "instance": 802,
                        "visible": True,
                        "uservisible": True,
                    },
                    {
                        "id": 806,
                        "name": "Componente práctico",
                        "modname": "label",
                        "instance": 806,
                        "visible": True,
                        "uservisible": True,
                    },
                    {
                        "id": 803,
                        "name": "DEBER",
                        "modname": "assign",
                        "instance": 803,
                        "visible": True,
                        "uservisible": True,
                    },
                    {
                        "id": 804,
                        "name": "DEBER - 2DA OPORTUNIDAD PERSONAS QUE NO RINDIERON",
                        "modname": "assign",
                        "instance": 804,
                        "visible": True,
                        "uservisible": True,
                    },
                ],
            }
        ]

        enriched = MoodleReadService._grade_items_with_course_sections(
            grade_groups,
            sections,
        )

        for item in enriched[0]["gradeitems"]:
            self.assertTrue(item["evaluation_scope"])
            self.assertEqual(item["course_section_partial"], 1)
            self.assertEqual(item["course_section_named_partial"], 0)
            self.assertEqual(item["course_label_partial"], 1)
            self.assertEqual(item["course_partial_label"], "Primer parcial")
            self.assertEqual(item["course_partial_label_module_id"], 800)
            self.assertEqual(item["course_partial_segment"], "section:612:label:800")

    def test_partial_is_detected_from_label_description(self) -> None:
        grade_groups = [
            {
                "userid": 12,
                "gradeitems": [
                    {"id": 31, "itemmodule": "quiz", "iteminstance": 901},
                    {"id": 32, "itemmodule": "assign", "iteminstance": 902},
                ],
            }
        ]
        sections = [
            {
                "id": 712,
                "section": 12,
                "name": "Bloque académico",
                "summary": "<p>Evaluaciones</p>",
                "visible": True,
                "uservisible": True,
                "modules": [
                    {
                        "id": 900,
                        "name": "Separador",
                        "description": "<strong>Segundo parcial</strong>",
                        "modname": "label",
                        "instance": 900,
                        "visible": True,
                        "uservisible": True,
                    },
                    {
                        "id": 901,
                        "name": "Cuestionario sin número",
                        "modname": "quiz",
                        "instance": 901,
                        "visible": True,
                        "uservisible": True,
                    },
                    {
                        "id": 902,
                        "name": "Tarea sin número",
                        "modname": "assign",
                        "instance": 902,
                        "visible": True,
                        "uservisible": True,
                    },
                ],
            }
        ]

        enriched = MoodleReadService._grade_items_with_course_sections(
            grade_groups,
            sections,
        )

        for item in enriched[0]["gradeitems"]:
            self.assertTrue(item["evaluation_scope"])
            self.assertEqual(item["course_section_partial"], 2)
            self.assertEqual(item["course_label_partial"], 2)
            self.assertEqual(item["course_partial_label"], "Segundo parcial")
            self.assertEqual(item["course_partial_segment"], "section:712:label:900")

    def test_unique_module_name_recovers_partial_when_iteminstance_differs(self) -> None:
        grade_groups = [
            {
                "userid": 15,
                "gradeitems": [
                    {
                        "id": 41,
                        "itemname": "Evaluación Parcial - 2da oportunidad",
                        "itemmodule": "quiz",
                        "iteminstance": 9999,
                    }
                ],
            }
        ]
        sections = [
            {
                "id": 812,
                "section": 12,
                "name": "Evaluaciones",
                "visible": True,
                "uservisible": True,
                "modules": [
                    {
                        "id": 1000,
                        "name": "Primer parcial",
                        "modname": "label",
                        "instance": 1000,
                        "visible": True,
                        "uservisible": True,
                    },
                    {
                        "id": 1001,
                        "name": "Evaluación Parcial - 2da oportunidad",
                        "modname": "quiz",
                        "instance": 1001,
                        "visible": True,
                        "uservisible": True,
                    },
                ],
            }
        ]

        enriched = MoodleReadService._grade_items_with_course_sections(
            grade_groups,
            sections,
        )
        item = enriched[0]["gradeitems"][0]

        self.assertTrue(item["evaluation_scope"])
        self.assertEqual(item["course_section_partial"], 1)
        self.assertEqual(item["course_label_partial"], 1)
        self.assertEqual(item["course_partial_segment"], "section:812:label:1000")

    def test_ambiguous_module_name_does_not_cross_partial_boundaries(self) -> None:
        grade_groups = [
            {
                "userid": 16,
                "gradeitems": [
                    {
                        "id": 42,
                        "itemname": "Cuestionario de evaluación",
                        "itemmodule": "quiz",
                        "iteminstance": 9998,
                    }
                ],
            }
        ]
        sections = [
            {
                "id": 912,
                "section": 12,
                "name": "Evaluaciones",
                "visible": True,
                "uservisible": True,
                "modules": [
                    {
                        "id": 1100,
                        "name": "Primer parcial",
                        "modname": "label",
                        "instance": 1100,
                        "visible": True,
                        "uservisible": True,
                    },
                    {
                        "id": 1101,
                        "name": "Cuestionario de evaluación",
                        "modname": "quiz",
                        "instance": 1101,
                        "visible": True,
                        "uservisible": True,
                    },
                    {
                        "id": 1200,
                        "name": "Segundo parcial",
                        "modname": "label",
                        "instance": 1200,
                        "visible": True,
                        "uservisible": True,
                    },
                    {
                        "id": 1201,
                        "name": "Cuestionario de evaluación",
                        "modname": "quiz",
                        "instance": 1201,
                        "visible": True,
                        "uservisible": True,
                    },
                ],
            }
        ]

        enriched = MoodleReadService._grade_items_with_course_sections(
            grade_groups,
            sections,
        )
        item = enriched[0]["gradeitems"][0]

        self.assertFalse(item["evaluation_scope"])
        self.assertEqual(item["course_section_partial"], 0)
        self.assertEqual(item["course_partial_segment"], "")

    async def test_course_search_visibility_category_and_pagination(self) -> None:
        visible = await self.service.list_courses(
            search="ingles",
            visibility="visible",
            category_id=4,
            page=1,
            page_size=1,
        )
        hidden = await self.service.list_courses(visibility="hidden", page_size=10)

        self.assertEqual(visible["pagination"]["total_items"], 1)
        self.assertEqual(visible["items"][0]["shortname"], "ING-A2")
        self.assertEqual(hidden["items"][0]["shortname"], "OCULTO")
        self.assertEqual(self.client.course_calls, 1)

    async def test_course_cache_and_refresh_are_independent(self) -> None:
        first = await self.service.list_courses(page=1, page_size=1)
        cached = await self.service.list_courses(page=2, page_size=1)
        refreshed = await self.service.list_courses(page=1, page_size=10, refresh=True)

        self.assertFalse(first["source"]["cached"])
        self.assertTrue(cached["source"]["cached"])
        self.assertFalse(refreshed["source"]["cached"])
        self.assertEqual(self.client.course_calls, 2)
        self.assertEqual(self.client.user_calls, 0)

    async def test_course_enrolled_emails_are_normalized_and_cached(self) -> None:
        first = await self.service.get_course_enrolled_emails(12)
        cached = await self.service.get_course_enrolled_emails(12)
        refreshed = await self.service.get_course_enrolled_emails(12, refresh=True)

        self.assertEqual(first, {"estudiante@intec.edu.ec"})
        self.assertEqual(cached, first)
        self.assertEqual(refreshed, first)
        self.assertEqual(self.client.enrollment_calls, 2)

    async def test_course_resources_are_normalized_and_tokens_are_removed(self) -> None:
        result = await self.service.get_course_resources(12)
        section = result["sections"][0]
        module = section["modules"][0]
        content = module["contents"][0]

        self.assertEqual(result["course"]["shortname"], "ING-A2")
        self.assertEqual(result["totals"], {
            "sections": 1,
            "modules": 1,
            "files": 1,
            "links": 0,
            "visible_modules": 1,
        })
        self.assertEqual(section["summary"], "Introducción al curso.")
        self.assertEqual(
            section["edit_url"],
            "https://moodle.example.edu/course/editsection.php?id=30&sr=1",
        )
        self.assertTrue(section["can_update_visibility"])
        self.assertTrue(section["can_update_name"])
        self.assertTrue(result["section_management"]["name_updates_enabled"])
        self.assertTrue(result["section_management"]["visibility_updates_enabled"])
        self.assertEqual(module["description"], "Documento principal.")
        self.assertNotIn("wstoken", module["url"])
        self.assertNotIn("token", content["fileurl"])
        self.assertIn("forcedownload=1", content["fileurl"])
        self.assertNotIn("customdata", module)

    def test_course_module_extracts_and_sanitizes_external_links(self) -> None:
        module = self.service._normalize_course_module(
            {
                "id": 45,
                "name": "Material complementario",
                "visible": 1,
                "modname": "page",
                "description": (
                    '<p><a href="https://drive.google.com/file/d/example?token=secret&usp=sharing">'
                    "Guía en Drive</a></p>"
                    '<iframe src="https://www.canva.com/design/example/view" '
                    'title="Presentación del curso"></iframe>'
                    '<a href="javascript:alert(1)">Enlace inseguro</a>'
                ),
            }
        )

        self.assertEqual(
            [link["provider"] for link in module["links"]],
            ["Google Drive", "Canva"],
        )
        self.assertEqual(module["links"][0]["name"], "Guía en Drive")
        self.assertNotIn("token=", module["links"][0]["url"])
        self.assertIn("usp=sharing", module["links"][0]["url"])
        self.assertTrue(all(link["url"].startswith("https://") for link in module["links"]))

    async def test_url_activity_is_enriched_from_optional_moodle_catalog(self) -> None:
        original_contents = self.client.get_course_contents

        async def contents_with_url(course_id: int):
            sections = await original_contents(course_id)
            sections[0]["modules"].append(
                {
                    "id": 45,
                    "instance": 71,
                    "name": "Presentación de la unidad",
                    "visible": 1,
                    "uservisible": 1,
                    "modname": "url",
                }
            )
            return sections

        async def external_urls(course_id: int):
            self.assertEqual(course_id, 12)
            return [
                {
                    "id": 71,
                    "coursemodule": 45,
                    "externalurl": "https://www.canva.com/design/example/view",
                    "intro": "Material visual",
                }
            ]

        self.client.get_course_contents = contents_with_url
        self.client.get_course_external_urls = external_urls

        result = await self.service.get_course_resources(12, refresh=True)
        module = result["sections"][0]["modules"][1]

        self.assertEqual(result["totals"]["links"], 1)
        self.assertEqual(module["links"][0]["provider"], "Canva")
        self.assertEqual(module["links"][0]["name"], "Presentación de la unidad")

    async def test_course_resource_file_is_scoped_to_course_and_module(self) -> None:
        metadata, stream = await self.service.open_course_resource_file(12, 44, 0)

        self.assertEqual(metadata["course_id"], 12)
        self.assertEqual(metadata["module_id"], 44)
        self.assertEqual(metadata["content"]["filename"], "guia.pdf")
        self.assertNotIn("fileurl", metadata["content"])
        self.assertEqual(stream.marker, "stream")
        self.assertIn("/pluginfile.php/90/guia.pdf", self.client.opened_files[0])

        with self.assertRaises(MoodleResourceNotFoundError):
            await self.service.open_course_resource_file(12, 999, 0)
        with self.assertRaises(MoodleResourceNotFoundError):
            await self.service.open_course_resource_file(12, 44, 2)

    async def test_section_visibility_updates_refreshes_and_audits(self) -> None:
        audits: list[tuple[dict, dict, dict]] = []

        def audit(before: dict, after: dict, course: dict) -> bool:
            audits.append((before, after, course))
            return True

        service = MoodleReadService(
            service_settings(),
            client=self.client,
            section_auditor=audit,
        )
        result = await service.set_section_visibility(12, 30, visible=False)

        self.assertTrue(result["changed"])
        self.assertFalse(result["section"]["visible"])
        self.assertTrue(result["audit_recorded"])
        self.assertEqual(self.client.section_updates, [(30, 1, False)])
        self.assertEqual(audits[0][0]["visible"], True)
        self.assertEqual(audits[0][1]["visible"], False)
        self.assertEqual(audits[0][2]["course_id"], 12)

    async def test_section_name_update_refreshes_and_audits(self) -> None:
        audits: list[tuple[dict, dict, dict]] = []

        def audit(before: dict, after: dict, course: dict) -> bool:
            audits.append((before, after, course))
            return True

        service = MoodleReadService(
            service_settings(),
            client=self.client,
            section_auditor=audit,
        )
        result = await service.set_section_name(12, 30, name="Unidad actualizada")

        self.assertTrue(result["changed"])
        self.assertEqual(result["section"]["name"], "Unidad actualizada")
        self.assertTrue(result["audit_recorded"])
        self.assertEqual(
            self.client.section_name_updates,
            [(30, "topics", "Unidad actualizada")],
        )
        self.assertEqual(audits[0][0]["name"], "Unidad 1")
        self.assertEqual(audits[0][1]["name"], "Unidad actualizada")
        self.assertEqual(audits[0][2]["course_id"], 12)

    async def test_section_name_update_is_idempotent(self) -> None:
        result = await self.service.set_section_name(12, 30, name="Unidad 1")

        self.assertFalse(result["changed"])
        self.assertEqual(self.client.section_name_updates, [])

    async def test_general_section_cannot_be_hidden(self) -> None:
        original = self.client.get_course_contents

        async def general_section(course_id: int):
            sections = await original(course_id)
            sections[0]["section"] = 0
            return sections

        self.client.get_course_contents = general_section
        with self.assertRaises(MoodleSectionUpdateError):
            await self.service.set_section_visibility(12, 30, visible=False)

    async def test_general_section_name_can_be_updated(self) -> None:
        original = self.client.get_course_contents

        async def general_section(course_id: int):
            sections = await original(course_id)
            sections[0]["section"] = 0
            return sections

        self.client.get_course_contents = general_section
        result = await self.service.set_section_name(
            12,
            30,
            name="Información general",
        )

        self.assertTrue(result["changed"])
        self.assertEqual(
            self.client.section_name_updates,
            [(30, "topics", "Información general")],
        )

    async def test_course_resources_use_independent_cache_and_refresh(self) -> None:
        first = await self.service.get_course_resources(12)
        cached = await self.service.get_course_resources(12)
        refreshed = await self.service.get_course_resources(12, refresh=True)

        self.assertFalse(first["source"]["cached"])
        self.assertTrue(cached["source"]["cached"])
        self.assertFalse(refreshed["source"]["cached"])
        self.assertEqual(self.client.content_calls, 2)

    async def test_unknown_course_cannot_load_resources(self) -> None:
        with self.assertRaises(MoodleCourseNotFoundError):
            await self.service.get_course_resources(999)

    async def test_user_result_limit_is_checked_by_the_service(self) -> None:
        service = MoodleReadService(
            service_settings(moodle_max_user_scan_items=2),
            client=self.client,
        )

        with self.assertRaises(MoodleResultLimitExceededError):
            await service.list_users()

    async def test_full_scan_error_is_propagated_without_fallback(self) -> None:
        class DisabledScanClient(FakeMoodleClient):
            async def get_all_users(self):
                raise MoodleFullScanDisabledError("Escaneo deshabilitado")

        service = MoodleReadService(service_settings(), client=DisabledScanClient())

        with self.assertRaises(MoodleFullScanDisabledError):
            await service.list_users()

    async def test_activates_user_only_after_institutional_email_validation(self) -> None:
        validations: list[str] = []
        audits: list[tuple[dict, dict, dict]] = []

        def validate(email: str) -> dict:
            validations.append(email)
            return {
                "validated": True,
                "codigo_estud": 22,
                "estudiante": "Álvaro Pérez",
                "correo_intec": email,
            }

        def audit(before: dict, after: dict, validation: dict) -> bool:
            audits.append((before, after, validation))
            return True

        service = MoodleReadService(
            service_settings(),
            client=self.client,
            institutional_email_validator=validate,
            status_auditor=audit,
        )

        result = await service.set_user_active(2, active=True)

        self.assertTrue(result["changed"])
        self.assertTrue(result["audit_recorded"])
        self.assertEqual(result["user"]["status"], "ACTIVO")
        self.assertEqual(validations, ["alvaro@example.edu"])
        self.assertEqual(self.client.status_updates, [(2, False)])
        self.assertEqual(audits[0][0]["status"], "SUSPENDIDO")
        self.assertEqual(audits[0][1]["status"], "ACTIVO")

    async def test_rejects_user_missing_from_institutional_email_table(self) -> None:
        def validate(_email: str) -> dict:
            raise MoodleInstitutionalEmailNotFoundError("Correo no encontrado")

        service = MoodleReadService(
            service_settings(),
            client=self.client,
            institutional_email_validator=validate,
        )

        with self.assertRaises(MoodleInstitutionalEmailNotFoundError):
            await service.set_user_active(2, active=True)

        self.assertEqual(self.client.status_updates, [])

    async def test_unconfirmed_user_cannot_be_activated(self) -> None:
        validation_called = False

        def validate(_email: str) -> dict:
            nonlocal validation_called
            validation_called = True
            return {}

        service = MoodleReadService(
            service_settings(),
            client=self.client,
            institutional_email_validator=validate,
        )

        with self.assertRaises(MoodleUserNotConfirmedError):
            await service.set_user_active(3, active=True)

        self.assertFalse(validation_called)
        self.assertEqual(self.client.status_updates, [])


if __name__ == "__main__":
    unittest.main()
