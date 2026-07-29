import json
import unittest

from fastapi import HTTPException

from app.routers.portal_academico import _parse_teacher_teams_recordings


class TeacherComplianceTeamsEvidenceTests(unittest.TestCase):
    def test_parses_graph_recording_and_keeps_https_link(self):
        payload = json.dumps(
            [
                {
                    "team_id": "team-1",
                    "team_name": "Sistemas Operativos",
                    "recording_id": "recording-1",
                    "name": "Clase 1.mp4",
                    "date": "21/07/2026",
                    "start_hour": "7:30 PM",
                    "end_hour": "8:30 PM",
                    "call_duration": "01:00:00",
                    "recording_duration": "00:58:30",
                    "modified_by": "Docente Prueba",
                    "web_url": "https://example.sharepoint.com/recording",
                    "source": "Microsoft Graph",
                }
            ]
        )

        result = _parse_teacher_teams_recordings(payload)

        self.assertEqual(result[0]["name"], "Clase 1.mp4")
        self.assertEqual(result[0]["web_url"], "https://example.sharepoint.com/recording")

    def test_removes_non_https_link(self):
        payload = json.dumps([{"name": "Clase.mp4", "web_url": "javascript:alert(1)"}])

        result = _parse_teacher_teams_recordings(payload)

        self.assertEqual(result[0]["web_url"], "")

    def test_rejects_more_than_fifty_recordings(self):
        payload = json.dumps([{"name": f"Clase {index}.mp4"} for index in range(51)])

        with self.assertRaises(HTTPException) as context:
            _parse_teacher_teams_recordings(payload)

        self.assertEqual(context.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main()
