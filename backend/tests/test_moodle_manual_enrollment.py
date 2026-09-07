import copy
import unittest
from types import SimpleNamespace

from app.integrations.moodle.client import (
    COURSES_FUNCTION,
    ENROLLED_USERS_FUNCTION,
    MANUAL_ENROL_USERS_FUNCTION,
    SITE_INFO_FUNCTION,
    USERS_BY_FIELD_FUNCTION,
    USERS_FUNCTION,
)
from app.integrations.moodle.exceptions import MoodleManualEnrollmentError
from app.services.moodle_manual_enrollment import MoodleManualEnrollmentService


def settings(**overrides: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "moodle_enabled": True,
        "moodle_reads_enabled": True,
        "moodle_writes_enabled": True,
        "moodle_manual_enrollment_enabled": True,
        "moodle_full_user_scan_enabled": True,
        "moodle_student_role_id": 5,
        "moodle_teacher_role_id": 3,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class FakeReadService:
    def __init__(self) -> None:
        self.courses = [
            {
                "id": 120,
                "fullname": "Seguridad en redes R30 - A",
                "shortname": "SEG-RED-R30-A",
                "idnumber": "SEG-RED-R30-A",
                "categoryname": "OFERTA/2027/REGULAR/R30",
                "visible": True,
            }
        ]
        self.users = [
            {
                "id": 10,
                "fullname": "Ana María De La Cruz Paredes",
                "firstname": "Ana María",
                "lastname": "De La Cruz Paredes",
                "email": "ana.delacruz@intec.edu.ec",
                "username": "ana.delacruz",
                "idnumber": "1711111111",
                "suspended": False,
                "confirmed": True,
            },
            {
                "id": 11,
                "fullname": "Ana María De La Cruz Gómez",
                "firstname": "Ana María",
                "lastname": "De La Cruz Gómez",
                "email": "ana.delacruz1@intec.edu.ec",
                "username": "ana.delacruz1",
                "idnumber": "1722222222",
                "suspended": False,
                "confirmed": True,
            },
            {
                "id": 12,
                "fullname": "José Luis De La Torre Vera",
                "firstname": "José Luis",
                "lastname": "De La Torre Vera",
                "email": "jose.delatorre@intec.edu.ec",
                "username": "jose.delatorre",
                "idnumber": "1733333333",
                "suspended": False,
                "confirmed": True,
            },
            {
                "id": 13,
                "fullname": "Docente Suspendido",
                "firstname": "Docente",
                "lastname": "Suspendido",
                "email": "docente.suspendido@intec.edu.ec",
                "username": "docente.suspendido",
                "idnumber": "1744444444",
                "suspended": True,
                "confirmed": True,
            },
        ]
        self.enrolled: list[dict] = [
            {
                **self.users[1],
                "roles": [{"roleid": 5, "shortname": "student", "name": "Estudiante"}],
            },
            {
                **self.users[2],
                "roles": [{"roleid": 5, "shortname": "student", "name": "Estudiante"}],
            },
        ]

    async def get_all_users(self, *, refresh: bool = False):
        return copy.deepcopy(self.users)

    async def get_users_by_ids(self, user_ids: list[int]):
        selected = set(user_ids)
        return copy.deepcopy([user for user in self.users if user["id"] in selected])

    async def get_all_courses(self, *, refresh: bool = False):
        return copy.deepcopy(self.courses)

    async def get_course_enrolled_users(self, course_id: int, *, refresh: bool = False):
        if course_id != 120:
            return []
        return copy.deepcopy(self.enrolled)


class FakeClient:
    def __init__(self, read_service: FakeReadService) -> None:
        self.read_service = read_service
        self.calls: list[list[dict]] = []

    async def get_site_info(self):
        return {
            "functions": [
                {"name": function}
                for function in (
                    SITE_INFO_FUNCTION,
                    USERS_FUNCTION,
                    USERS_BY_FIELD_FUNCTION,
                    COURSES_FUNCTION,
                    ENROLLED_USERS_FUNCTION,
                    MANUAL_ENROL_USERS_FUNCTION,
                )
            ]
        }

    async def manual_enrol_users(self, enrolments: list[dict]):
        self.calls.append(copy.deepcopy(enrolments))
        enrolled_by_id = {item["id"]: item for item in self.read_service.enrolled}
        users_by_id = {item["id"]: item for item in self.read_service.users}
        for enrolment in enrolments:
            user_id = enrolment["userid"]
            record = enrolled_by_id.get(user_id)
            if record is None:
                record = {**users_by_id[user_id], "roles": []}
                self.read_service.enrolled.append(record)
                enrolled_by_id[user_id] = record
            record.setdefault("roles", []).append(
                {
                    "roleid": enrolment["roleid"],
                    "shortname": "student" if enrolment["roleid"] == 5 else "editingteacher",
                    "name": "Estudiante" if enrolment["roleid"] == 5 else "Docente editor",
                }
            )


class MoodleManualEnrollmentServiceTests(unittest.IsolatedAsyncioTestCase):
    def service(self):
        read_service = FakeReadService()
        client = FakeClient(read_service)
        service = MoodleManualEnrollmentService(
            settings(),
            read_service,
            client=client,
            auditor=lambda _before, _after: True,
        )
        return service, read_service, client

    async def test_search_handles_compound_names_and_requires_ambiguous_selection(self) -> None:
        service, _read_service, _client = self.service()

        result = await service.search(
            course_id=120,
            role="student",
            names=[
                "Ana María De La Cruz Paredes",
                "Ana Maria De La Cruz",
                "jose.delatorre@intec.edu.ec",
            ],
        )

        self.assertEqual(result["queries"][0]["status"], "UNICO")
        self.assertEqual(result["queries"][0]["selected_user_id"], 10)
        self.assertEqual(result["queries"][1]["status"], "AMBIGUO")
        self.assertEqual({item["id"] for item in result["queries"][1]["candidates"]}, {10, 11})
        self.assertEqual(result["queries"][2]["selected_user_id"], 12)

    async def test_suspended_account_is_found_but_not_preselected(self) -> None:
        service, _read_service, _client = self.service()

        result = await service.search(
            course_id=120,
            role="teacher",
            names=["Docente Suspendido"],
        )

        query = result["queries"][0]
        self.assertEqual(query["status"], "UNICO")
        self.assertIsNone(query["selected_user_id"])
        self.assertFalse(query["candidates"][0]["selectable"])

    async def test_preview_distinguishes_existing_enrollment_and_role_addition(self) -> None:
        service, _read_service, _client = self.service()

        student_preview = await service.preview(
            course_id=120,
            role="student",
            user_ids=[10, 11],
        )
        teacher_preview = await service.preview(
            course_id=120,
            role="teacher",
            user_ids=[12],
        )

        self.assertEqual(student_preview["items"][0]["action"], "MATRICULAR")
        self.assertEqual(student_preview["items"][1]["status"], "EXISTENTE")
        self.assertEqual(student_preview["summary"]["existing"], 1)
        self.assertEqual(teacher_preview["items"][0]["action"], "ASIGNAR_ROL")

    async def test_suspended_course_enrollment_is_blocked(self) -> None:
        service, read_service, _client = self.service()
        read_service.enrolled[1]["suspended"] = True

        search = await service.search(
            course_id=120,
            role="teacher",
            names=["José Luis De La Torre Vera"],
        )
        preview = await service.preview(
            course_id=120,
            role="teacher",
            user_ids=[12],
        )

        self.assertEqual(search["queries"][0]["candidates"][0]["enrollment_status"], "SUSPENDIDA")
        self.assertFalse(search["queries"][0]["candidates"][0]["selectable"])
        self.assertEqual(preview["items"][0]["status"], "BLOQUEADO")

    async def test_apply_assigns_configured_teacher_role_and_verifies_it(self) -> None:
        service, _read_service, client = self.service()
        preview = await service.preview(
            course_id=120,
            role="teacher",
            user_ids=[12],
        )

        result = await service.apply(
            course_id=120,
            role="teacher",
            user_ids=[12],
            preview_fingerprint=preview["preview_fingerprint"],
            actor="admin@intec.edu.ec",
            actor_id=1,
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["summary"]["enrolled"], 1)
        self.assertEqual(client.calls[0][0]["roleid"], 3)
        self.assertEqual(result["items"][0]["status"], "MATRICULADO")

    async def test_apply_rejects_stale_preview(self) -> None:
        service, read_service, client = self.service()
        preview = await service.preview(
            course_id=120,
            role="student",
            user_ids=[10],
        )
        read_service.enrolled.append(
            {
                **read_service.users[0],
                "roles": [{"roleid": 5, "shortname": "student", "name": "Estudiante"}],
            }
        )

        with self.assertRaises(MoodleManualEnrollmentError):
            await service.apply(
                course_id=120,
                role="student",
                user_ids=[10],
                preview_fingerprint=preview["preview_fingerprint"],
                actor="admin@intec.edu.ec",
            )

        self.assertEqual(client.calls, [])


if __name__ == "__main__":
    unittest.main()
