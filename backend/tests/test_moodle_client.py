import json
import logging
import unittest
from types import SimpleNamespace
from urllib.parse import parse_qs

import httpx
from pydantic import SecretStr

from app.integrations.moodle.client import MoodleClient
from app.integrations.moodle.exceptions import (
    MoodleApiError,
    MoodleConfigurationError,
    MoodleConnectionError,
    MoodleDisabledError,
    MoodleFullScanDisabledError,
    MoodleFunctionNotAllowedError,
    MoodleInvalidResponseError,
    MoodleResultLimitExceededError,
    MoodleTimeoutError,
    MoodleWriteDisabledError,
)


SECRET = "token-de-prueba-no-real"


def moodle_settings(**overrides: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "moodle_base_url": "https://moodle.example.edu",
        "moodle_token": SecretStr(SECRET),
        "moodle_enabled": True,
        "moodle_reads_enabled": True,
        "moodle_writes_enabled": True,
        "moodle_user_status_update_enabled": True,
        "moodle_section_updates_enabled": True,
        "moodle_timeout_seconds": 5,
        "moodle_verify_tls": True,
        "moodle_full_user_scan_enabled": True,
        "moodle_max_user_scan_items": 100,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def json_response(request: httpx.Request, payload: object, status_code: int = 200) -> httpx.Response:
    return httpx.Response(status_code, json=payload, request=request)


class MoodleClientTests(unittest.IsolatedAsyncioTestCase):
    async def _client(self, handler, **settings_overrides: object) -> tuple[MoodleClient, httpx.AsyncClient]:
        http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        client = MoodleClient(moodle_settings(**settings_overrides), http_client=http_client)
        return client, http_client

    async def test_site_info_uses_post_form_without_token_in_url(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            form = parse_qs(request.content.decode("utf-8"))
            self.assertEqual(request.method, "POST")
            self.assertNotIn(SECRET, str(request.url))
            self.assertEqual(form["wstoken"], [SECRET])
            self.assertEqual(form["wsfunction"], ["core_webservice_get_site_info"])
            return json_response(request, {"sitename": "Campus de prueba"})

        client, http_client = await self._client(handler)
        try:
            result = await client.get_site_info()
        finally:
            await http_client.aclose()

        self.assertEqual(result["sitename"], "Campus de prueba")

    async def test_get_all_users(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            form = parse_qs(request.content.decode("utf-8"))
            self.assertEqual(form["wsfunction"], ["core_user_get_users"])
            self.assertEqual(form["criteria[0][key]"], ["email"])
            self.assertEqual(form["criteria[0][value]"], ["%"])
            return json_response(request, {"users": [{"id": 1, "username": "usuario"}]})

        client, http_client = await self._client(handler)
        try:
            users = await client.get_all_users()
        finally:
            await http_client.aclose()

        self.assertEqual(users, [{"id": 1, "username": "usuario"}])

    async def test_get_all_courses(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            form = parse_qs(request.content.decode("utf-8"), keep_blank_values=True)
            self.assertEqual(form["wsfunction"], ["core_course_get_courses_by_field"])
            self.assertEqual(form["field"], [""])
            self.assertEqual(form["value"], [""])
            return json_response(request, {"courses": [{"id": 8, "fullname": "Curso"}]})

        client, http_client = await self._client(handler)
        try:
            courses = await client.get_all_courses()
        finally:
            await http_client.aclose()

        self.assertEqual(courses[0]["id"], 8)

    async def test_get_course_contents(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            form = parse_qs(request.content.decode("utf-8"))
            self.assertEqual(form["wsfunction"], ["core_course_get_contents"])
            self.assertEqual(form["courseid"], ["12"])
            return json_response(request, [{"id": 3, "name": "Unidad 1"}])

        client, http_client = await self._client(handler)
        try:
            contents = await client.get_course_contents(12)
        finally:
            await http_client.aclose()

        self.assertEqual(contents, [{"id": 3, "name": "Unidad 1"}])

    async def test_get_course_external_urls(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            form = parse_qs(request.content.decode("utf-8"))
            self.assertEqual(form["wsfunction"], ["mod_url_get_urls_by_courses"])
            self.assertEqual(form["courseids[0]"], ["12"])
            return json_response(
                request,
                {
                    "urls": [
                        {
                            "id": 70,
                            "coursemodule": 44,
                            "externalurl": "https://drive.google.com/file/d/example",
                        }
                    ],
                    "warnings": [],
                },
            )

        client, http_client = await self._client(handler)
        try:
            urls = await client.get_course_external_urls(12)
        finally:
            await http_client.aclose()

        self.assertEqual(urls[0]["id"], 70)
        self.assertEqual(urls[0]["coursemodule"], 44)

    async def test_get_course_enrolled_users(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            form = parse_qs(request.content.decode("utf-8"))
            self.assertEqual(form["wsfunction"], ["core_enrol_get_enrolled_users"])
            self.assertEqual(form["courseid"], ["12"])
            return json_response(
                request,
                [{"id": 21, "email": "estudiante@intec.edu.ec"}],
            )

        client, http_client = await self._client(handler)
        try:
            users = await client.get_course_enrolled_users(12)
        finally:
            await http_client.aclose()

        self.assertEqual(users[0]["email"], "estudiante@intec.edu.ec")

    async def test_get_course_grade_items(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            form = parse_qs(request.content.decode("utf-8"))
            self.assertEqual(form["wsfunction"], ["gradereport_user_get_grade_items"])
            self.assertEqual(form["courseid"], ["12"])
            self.assertNotIn("userid", form)
            return json_response(
                request,
                {
                    "usergrades": [
                        {
                            "userid": 21,
                            "gradeitems": [
                                {
                                    "itemtype": "course",
                                    "graderaw": 8.5,
                                    "grademin": 0,
                                    "grademax": 10,
                                }
                            ],
                        }
                    ]
                },
            )

        client, http_client = await self._client(handler)
        try:
            grades = await client.get_course_grade_items(12)
        finally:
            await http_client.aclose()

        self.assertEqual(grades[0]["userid"], 21)
        self.assertEqual(grades[0]["gradeitems"][0]["graderaw"], 8.5)

    async def test_update_user_suspension_uses_only_authorized_function(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            form = parse_qs(request.content.decode("utf-8"))
            self.assertEqual(form["wsfunction"], ["core_user_update_users"])
            self.assertEqual(form["users[0][id]"], ["24"])
            self.assertEqual(form["users[0][suspended]"], ["1"])
            return json_response(request, None)

        client, http_client = await self._client(handler)
        try:
            await client.update_user_suspension(24, suspended=True)
        finally:
            await http_client.aclose()

    async def test_user_status_write_requires_global_write_flag(self) -> None:
        called = False

        async def handler(request: httpx.Request) -> httpx.Response:
            nonlocal called
            called = True
            return json_response(request, None)

        client, http_client = await self._client(handler, moodle_writes_enabled=False)
        try:
            with self.assertRaises(MoodleWriteDisabledError):
                await client.update_user_suspension(24, suspended=True)
        finally:
            await http_client.aclose()

        self.assertFalse(called)

    async def test_user_status_write_requires_dedicated_flag(self) -> None:
        called = False

        async def handler(request: httpx.Request) -> httpx.Response:
            nonlocal called
            called = True
            return json_response(request, None)

        client, http_client = await self._client(
            handler,
            moodle_user_status_update_enabled=False,
        )
        try:
            with self.assertRaises(MoodleWriteDisabledError):
                await client.update_user_suspension(24, suspended=False)
        finally:
            await http_client.aclose()

        self.assertFalse(called)

    async def test_edit_section_visibility_uses_authorized_function(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            form = parse_qs(request.content.decode("utf-8"))
            self.assertEqual(form["wsfunction"], ["core_course_edit_section"])
            self.assertEqual(form["action"], ["hide"])
            self.assertEqual(form["id"], ["30"])
            self.assertEqual(form["sectionreturn"], ["1"])
            return json_response(request, None)

        client, http_client = await self._client(handler)
        try:
            await client.edit_section_visibility(30, section_number=1, visible=False)
        finally:
            await http_client.aclose()

    async def test_edit_section_name_uses_inplace_editable_function(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            form = parse_qs(request.content.decode("utf-8"))
            self.assertEqual(form["wsfunction"], ["core_update_inplace_editable"])
            self.assertEqual(form["component"], ["format_topics"])
            self.assertEqual(form["itemtype"], ["sectionname"])
            self.assertEqual(form["itemid"], ["30"])
            self.assertEqual(form["value"], ["Unidad actualizada"])
            return json_response(
                request,
                {
                    "component": "format_topics",
                    "itemtype": "sectionname",
                    "itemid": "30",
                    "value": "Unidad actualizada",
                },
            )

        client, http_client = await self._client(handler)
        try:
            await client.edit_section_name(
                30,
                course_format="topics",
                name="Unidad actualizada",
            )
        finally:
            await http_client.aclose()

    async def test_section_visibility_requires_dedicated_flag(self) -> None:
        called = False

        async def handler(request: httpx.Request) -> httpx.Response:
            nonlocal called
            called = True
            return json_response(request, None)

        client, http_client = await self._client(
            handler,
            moodle_section_updates_enabled=False,
        )
        try:
            with self.assertRaises(MoodleWriteDisabledError):
                await client.edit_section_visibility(30, section_number=1, visible=True)
        finally:
            await http_client.aclose()

        self.assertFalse(called)

    async def test_section_name_requires_dedicated_flag(self) -> None:
        called = False

        async def handler(request: httpx.Request) -> httpx.Response:
            nonlocal called
            called = True
            return json_response(request, None)

        client, http_client = await self._client(
            handler,
            moodle_section_updates_enabled=False,
        )
        try:
            with self.assertRaises(MoodleWriteDisabledError):
                await client.edit_section_name(
                    30,
                    course_format="topics",
                    name="Unidad actualizada",
                )
        finally:
            await http_client.aclose()

        self.assertFalse(called)

    async def test_file_download_adds_server_token_and_removes_stale_tokens(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            query = parse_qs(request.url.query.decode("utf-8"))
            self.assertEqual(request.url.path, "/webservice/pluginfile.php/90/guia.pdf")
            self.assertEqual(query["token"], [SECRET])
            self.assertNotIn("wstoken", query)
            return httpx.Response(
                200,
                content=b"contenido-pdf",
                headers={"content-type": "application/pdf"},
                request=request,
            )

        client, http_client = await self._client(handler)
        try:
            stream = await client.open_file(
                "https://moodle.example.edu/pluginfile.php/90/guia.pdf"
                "?forcedownload=1&wstoken=obsoleto&token=obsoleto"
            )
            content = await stream.response.aread()
            await stream.close()
        finally:
            await http_client.aclose()

        self.assertEqual(content, b"contenido-pdf")

    async def test_file_download_rejects_another_origin(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=b"no-debe-llamarse", request=request)

        client, http_client = await self._client(handler)
        try:
            with self.assertRaises(MoodleConfigurationError):
                await client.open_file("https://files.example.net/pluginfile.php/90/guia.pdf")
        finally:
            await http_client.aclose()

    async def test_file_download_rejects_cross_origin_redirect(self) -> None:
        requests: list[str] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            requests.append(str(request.url))
            return httpx.Response(
                302,
                headers={"location": "https://files.example.net/guia.pdf"},
                request=request,
            )

        client, http_client = await self._client(handler)
        try:
            with self.assertRaises(MoodleConnectionError):
                await client.open_file("https://moodle.example.edu/pluginfile.php/90/guia.pdf")
        finally:
            await http_client.aclose()

        self.assertEqual(len(requests), 1)
        self.assertNotIn("files.example.net", requests[0])

    async def test_moodle_api_error_is_controlled(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return json_response(
                request,
                {"exception": "moodle_exception", "errorcode": "invalidparameter", "message": "Solicitud inválida"},
            )

        client, http_client = await self._client(handler)
        try:
            with self.assertRaises(MoodleApiError):
                await client.get_site_info()
        finally:
            await http_client.aclose()

    async def test_invalid_token_response_is_controlled(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return json_response(
                request,
                {"exception": "moodle_exception", "errorcode": "invalidtoken", "message": "Token inválido"},
            )

        client, http_client = await self._client(handler)
        try:
            with self.assertRaisesRegex(MoodleApiError, "invalidtoken"):
                await client.get_site_info()
        finally:
            await http_client.aclose()

    async def test_timeout_is_mapped(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("timeout", request=request)

        client, http_client = await self._client(handler)
        try:
            with self.assertRaises(MoodleTimeoutError):
                await client.get_site_info()
        finally:
            await http_client.aclose()

    async def test_http_error_is_mapped(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(503, request=request)

        client, http_client = await self._client(handler)
        try:
            with self.assertRaises(MoodleConnectionError):
                await client.get_site_info()
        finally:
            await http_client.aclose()

    async def test_non_json_response_is_rejected(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=b"no-json", request=request)

        client, http_client = await self._client(handler)
        try:
            with self.assertRaises(MoodleInvalidResponseError):
                await client.get_site_info()
        finally:
            await http_client.aclose()

    async def test_function_outside_allowlist_is_rejected_before_request(self) -> None:
        called = False

        async def handler(request: httpx.Request) -> httpx.Response:
            nonlocal called
            called = True
            return json_response(request, {})

        client, http_client = await self._client(handler)
        try:
            with self.assertRaises(MoodleFunctionNotAllowedError):
                await client._post("core_user_create_users")
        finally:
            await http_client.aclose()

        self.assertFalse(called)

    async def test_missing_token_is_controlled(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return json_response(request, {})

        client, http_client = await self._client(handler, moodle_token=None)
        try:
            with self.assertRaises(MoodleConfigurationError):
                await client.get_site_info()
        finally:
            await http_client.aclose()

    async def test_disabled_reads_are_rejected_before_request(self) -> None:
        called = False

        async def handler(request: httpx.Request) -> httpx.Response:
            nonlocal called
            called = True
            return json_response(request, {})

        client, http_client = await self._client(handler, moodle_reads_enabled=False)
        try:
            with self.assertRaises(MoodleDisabledError):
                await client.get_site_info()
        finally:
            await http_client.aclose()

        self.assertFalse(called)

    async def test_full_user_scan_must_be_explicitly_enabled(self) -> None:
        called = False

        async def handler(request: httpx.Request) -> httpx.Response:
            nonlocal called
            called = True
            return json_response(request, {"users": []})

        client, http_client = await self._client(handler, moodle_full_user_scan_enabled=False)
        try:
            with self.assertRaises(MoodleFullScanDisabledError):
                await client.get_all_users()
        finally:
            await http_client.aclose()

        self.assertFalse(called)

    async def test_user_result_limit_is_enforced(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return json_response(request, {"users": [{"id": 1}, {"id": 2}]})

        client, http_client = await self._client(handler, moodle_max_user_scan_items=1)
        try:
            with self.assertRaises(MoodleResultLimitExceededError):
                await client.get_all_users()
        finally:
            await http_client.aclose()

    async def test_token_is_removed_from_exception_and_logs(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            payload = {
                "exception": "moodle_exception",
                "errorcode": "invalidtoken",
                "message": f"La credencial {SECRET} fue rechazada",
            }
            return httpx.Response(200, content=json.dumps(payload).encode("utf-8"), request=request)

        client, http_client = await self._client(handler)
        logger_name = "app.integrations.moodle.client"
        try:
            with self.assertLogs(logger_name, level=logging.INFO) as captured:
                with self.assertRaises(MoodleApiError) as raised:
                    await client.get_site_info()
        finally:
            await http_client.aclose()

        self.assertNotIn(SECRET, str(raised.exception))
        self.assertNotIn(SECRET, "\n".join(captured.output))

    async def test_moodle_debuginfo_is_not_exposed(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return json_response(
                request,
                {
                    "exception": "moodle_exception",
                    "errorcode": "invalidparameter",
                    "message": "Solicitud inválida",
                    "debuginfo": "consulta SQL interna",
                },
            )

        client, http_client = await self._client(handler)
        try:
            with self.assertRaises(MoodleApiError) as raised:
                await client.get_site_info()
        finally:
            await http_client.aclose()

        self.assertNotIn("consulta SQL interna", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
