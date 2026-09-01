import unittest
from unittest.mock import patch

from fastapi import HTTPException

from app.routers.teams import (
    _MOODLE_TEAMS_FIXED_OWNER,
    MoodleTeamsCourseRequest,
    TeamCreateClassroomRequest,
    _build_moodle_teams_graph_preview,
    _classify_moodle_course_users,
    _create_classroom_and_assign_teachers,
    _moodle_course_team_name,
    _resolve_moodle_teams_candidate,
    _select_moodle_teams_students,
)


def moodle_user(
    user_id: int,
    email: str,
    shortname: str,
    *,
    name: str = "Usuario de prueba",
    suspended: bool = False,
    confirmed: bool = True,
    status: str = "ACTIVO",
) -> dict[str, object]:
    return {
        "id": user_id,
        "fullname": name,
        "username": f"usuario{user_id}",
        "email": email,
        "suspended": suspended,
        "confirmed": confirmed,
        "status": status,
        "roles": [{"roleid": user_id, "name": shortname, "shortname": shortname}],
        "role_shortnames": [shortname],
    }


class MoodleTeamsClassificationTests(unittest.TestCase):
    def test_classifies_teachers_students_and_fixed_administrator(self) -> None:
        result = _classify_moodle_course_users(
            [
                moodle_user(1, "docente@intec.edu.ec", "editingteacher", name="Docente Uno"),
                moodle_user(2, "ESTUDIANTE@INTEC.EDU.EC", "student", name="Estudiante Uno"),
            ]
        )

        self.assertEqual(
            [item["email"] for item in result["owners"]],
            [_MOODLE_TEAMS_FIXED_OWNER, "docente@intec.edu.ec"],
        )
        self.assertTrue(result["owners"][0]["fixed_administrator"])
        self.assertEqual(result["students"][0]["email"], "estudiante@intec.edu.ec")
        self.assertEqual(result["students"][0]["role"], "student")
        self.assertEqual(result["ignored"], [])

    def test_teacher_precedence_prevents_duplicate_student_membership(self) -> None:
        result = _classify_moodle_course_users(
            [
                moodle_user(3, "doble@intec.edu.ec", "student"),
                moodle_user(3, "DOBLE@INTEC.EDU.EC", "teacher"),
                moodle_user(4, _MOODLE_TEAMS_FIXED_OWNER.upper(), "editingteacher"),
            ]
        )

        self.assertEqual(len(result["owners"]), 2)
        self.assertEqual(len(result["students"]), 0)
        fixed = next(item for item in result["owners"] if item["email"] == _MOODLE_TEAMS_FIXED_OWNER)
        self.assertTrue(fixed["fixed_administrator"])

    def test_ignores_suspended_unconfirmed_and_unknown_roles(self) -> None:
        result = _classify_moodle_course_users(
            [
                moodle_user(5, "suspendido@intec.edu.ec", "student", suspended=True),
                moodle_user(6, "pendiente@intec.edu.ec", "student", confirmed=False),
                moodle_user(7, "invitado@intec.edu.ec", "guest"),
            ]
        )

        self.assertEqual(len(result["students"]), 0)
        self.assertEqual(len(result["ignored"]), 3)
        self.assertTrue(all(item["status"] == "ignored" for item in result["ignored"]))

    def test_missing_status_remains_compatible_with_moodle_payloads(self) -> None:
        user = moodle_user(8, "activo@intec.edu.ec", "student")
        user.pop("status")

        result = _classify_moodle_course_users([user])

        self.assertEqual(len(result["students"]), 1)
        self.assertEqual(result["students"][0]["email"], "activo@intec.edu.ec")

    def test_team_name_uses_the_course_full_name_and_normalizes_spaces(self) -> None:
        name = _moodle_course_team_name(
            {
                "id": 91,
                "fullname": "  Programación   Web\nParalelo A  ",
                "shortname": "PW-A",
            }
        )

        self.assertEqual(name, "Programación Web Paralelo A")

    def test_team_name_accepts_exactly_256_characters(self) -> None:
        long_name = "A" * 256

        payload = MoodleTeamsCourseRequest(course_id=91, team_display_name=long_name)
        normalized = _moodle_course_team_name({"id": 91}, payload.team_display_name)

        self.assertEqual(normalized, long_name)
        self.assertEqual(len(normalized), 256)

    def test_team_name_rejects_more_than_256_characters(self) -> None:
        with self.assertRaises(ValueError):
            MoodleTeamsCourseRequest(course_id=91, team_display_name="A" * 257)

    def test_preview_marks_a_missing_team_as_a_new_education_class(self) -> None:
        users = [
            moodle_user(1, "docente@intec.edu.ec", "editingteacher", name="Docente Uno"),
            moodle_user(2, "estudiante@intec.edu.ec", "student", name="Estudiante Uno"),
        ]

        def resolve(candidate, **_kwargs):
            return {
                **candidate,
                "status": "ready",
                "status_label": "Listo",
                "graph_user_id": f"graph-{candidate['moodle_user_id']}",
            }

        with (
            patch("app.routers.teams._existing_classroom_team", return_value=None),
            patch("app.routers.teams._resolve_moodle_teams_candidate", side_effect=resolve),
        ):
            result = _build_moodle_teams_graph_preview(
                {"id": 91, "fullname": "Programación Web Paralelo A", "shortname": "PW-A"},
                users,
            )

        self.assertFalse(result["team"]["exists"])
        self.assertEqual(result["team"]["creation_action"], "create")
        self.assertEqual(result["team"]["template"], "educationClass")
        self.assertTrue(result["can_execute"])

    def test_preview_uses_the_custom_team_name_for_graph_lookup(self) -> None:
        users = [
            moodle_user(1, "docente@intec.edu.ec", "editingteacher", name="Docente Uno"),
            moodle_user(2, "estudiante@intec.edu.ec", "student", name="Estudiante Uno"),
        ]

        def resolve(candidate, **_kwargs):
            return {
                **candidate,
                "status": "ready",
                "status_label": "Listo",
                "graph_user_id": f"graph-{candidate['moodle_user_id']}",
            }

        with (
            patch("app.routers.teams._existing_classroom_team", return_value=None) as existing_team,
            patch("app.routers.teams._resolve_moodle_teams_candidate", side_effect=resolve),
        ):
            result = _build_moodle_teams_graph_preview(
                {"id": 91, "fullname": "Programación Web Paralelo A", "shortname": "PW-A"},
                users,
                team_display_name="  Aula   personalizada\n2026  ",
            )

        existing_team.assert_called_once_with("Aula personalizada 2026")
        self.assertEqual(result["team"]["display_name"], "Aula personalizada 2026")
        self.assertFalse(result["team"]["exists"])
        self.assertTrue(result["can_execute"])

    def test_creation_posts_an_education_class_and_returns_its_url(self) -> None:
        def resolve_teacher(teacher_input, _cache):
            local_part = teacher_input.split("@", 1)[0].replace(".", "-")
            return {
                "id": f"graph-{local_part}",
                "displayName": teacher_input,
                "mail": teacher_input,
                "userPrincipalName": teacher_input,
            }

        with (
            patch("app.routers.teams._resolve_graph_user_for_teacher", side_effect=resolve_teacher),
            patch("app.routers.teams._reserve_team_creation_slot", return_value="aula-prueba"),
            patch("app.routers.teams._release_team_creation_slot"),
            patch("app.routers.teams._existing_classroom_team", return_value=None),
            patch(
                "app.routers.teams._graph_post_with_meta_retry",
                return_value={"headers": {"Location": "/operations/create-team"}},
            ) as graph_post,
            patch("app.routers.teams._wait_for_team_creation", return_value="team-91"),
            patch(
                "app.routers.teams._wait_for_team_ready",
                return_value={
                    "group": {
                        "id": "team-91",
                        "displayName": "Programación Web Paralelo A",
                        "webUrl": "https://teams.microsoft.com/l/team-91",
                    },
                    "team": {"id": "team-91"},
                },
            ),
            patch("app.routers.teams._ensure_teachers_are_team_owners", return_value=[]),
            patch("app.routers.teams._save_team_additional_admins", return_value={"saved": 2}),
        ):
            result = _create_classroom_and_assign_teachers(
                TeamCreateClassroomRequest(
                    display_name="Programación Web Paralelo A",
                    courses=["PW-A"],
                    teacher_user_ids=[_MOODLE_TEAMS_FIXED_OWNER, "docente@intec.edu.ec"],
                    visibility="private",
                    description="Aula creada desde el curso Moodle 91",
                )
            )

        create_body = graph_post.call_args.args[1]
        self.assertEqual(
            create_body["template@odata.bind"],
            "https://graph.microsoft.com/v1.0/teamsTemplates('educationClass')",
        )
        self.assertEqual(create_body["displayName"], "Programación Web Paralelo A")
        self.assertEqual(create_body["members"][0]["roles"], ["owner"])
        self.assertTrue(result["created_new"])
        self.assertFalse(result["team_already_existed"])
        self.assertEqual(result["team_template"], "educationClass")
        self.assertEqual(result["team_web_url"], "https://teams.microsoft.com/l/team-91")

    @patch("app.routers.teams._resolve_graph_user_by_email")
    def test_graph_validation_accepts_exact_email_case_insensitively(self, resolve_user) -> None:
        resolve_user.return_value = {
            "id": "graph-user-1",
            "displayName": "Estudiante Uno",
            "mail": "ESTUDIANTE@INTEC.EDU.EC",
            "userPrincipalName": "estudiante@intec.edu.ec",
            "accountEnabled": True,
            "userType": "Member",
        }

        result = _resolve_moodle_teams_candidate(
            {
                "moodle_user_id": 10,
                "full_name": "Estudiante Uno",
                "email": "estudiante@intec.edu.ec",
                "moodle_username": "estudiante",
                "moodle_roles": ["student"],
                "role": "student",
                "fixed_administrator": False,
            },
            member_ids=set(),
            member_emails=set(),
            owner_ids=set(),
            owner_emails=set(),
        )

        self.assertEqual(result["status"], "ready")
        self.assertTrue(result["graph_account_enabled"])
        self.assertEqual(result["graph_user_type"], "Member")

    @patch("app.routers.teams._resolve_graph_user_by_email")
    def test_graph_validation_rejects_disabled_account(self, resolve_user) -> None:
        resolve_user.return_value = {
            "id": "graph-user-2",
            "displayName": "Estudiante Dos",
            "mail": "estudiante2@intec.edu.ec",
            "userPrincipalName": "estudiante2@intec.edu.ec",
            "accountEnabled": False,
            "userType": "Member",
        }

        result = _resolve_moodle_teams_candidate(
            {
                "moodle_user_id": 11,
                "full_name": "Estudiante Dos",
                "email": "estudiante2@intec.edu.ec",
                "moodle_username": "estudiante2",
                "moodle_roles": ["student"],
                "role": "student",
                "fixed_administrator": False,
            },
            member_ids=set(),
            member_emails=set(),
            owner_ids=set(),
            owner_emails=set(),
        )

        self.assertEqual(result["status"], "disabled_account")

    def test_selection_only_keeps_valid_students_from_current_course(self) -> None:
        preview = {
            "students": [
                {"moodle_user_id": 20, "email": "uno@intec.edu.ec", "status": "ready"},
                {"moodle_user_id": 21, "email": "dos@intec.edu.ec", "status": "already_in_team"},
                {"moodle_user_id": 22, "email": "tres@intec.edu.ec", "status": "not_found"},
            ],
            "summary": {"student_count": 3},
        }

        result = _select_moodle_teams_students(preview, [21, 20, 20])

        self.assertEqual([item["moodle_user_id"] for item in result["students"]], [20, 21])
        self.assertEqual(result["summary"]["selected_student_count"], 2)
        self.assertEqual(result["summary"]["selected_ready_count"], 1)
        self.assertEqual(result["summary"]["selected_existing_count"], 1)

    def test_selection_rejects_users_outside_course_or_invalid_in_graph(self) -> None:
        preview = {
            "students": [
                {"moodle_user_id": 30, "email": "valido@intec.edu.ec", "status": "ready"},
                {"moodle_user_id": 31, "email": "invalido@intec.edu.ec", "status": "not_found"},
            ],
            "summary": {"student_count": 2},
        }

        with self.assertRaises(HTTPException) as outside_context:
            _select_moodle_teams_students(preview, [99])
        self.assertEqual(outside_context.exception.status_code, 409)

        with self.assertRaises(HTTPException) as invalid_context:
            _select_moodle_teams_students(preview, [31])
        self.assertEqual(invalid_context.exception.status_code, 409)


if __name__ == "__main__":
    unittest.main()
