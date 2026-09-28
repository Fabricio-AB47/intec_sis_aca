"""Protect process affinity for the in-memory Moodle validation workflow."""
import re
import unittest
from pathlib import Path
from xml.etree import ElementTree


class MoodleValidationIisRoutingTests(unittest.TestCase):
    def setUp(self):
        config = Path(__file__).resolve().parents[2] / "frontend/public/web.config"
        self.rules = ElementTree.parse(config).findall("./system.webServer/rewrite/rules/rule")

    def destination(self, path):
        # HTTPS requests skip the preceding HTTP redirect rule.
        for rule in self.rules:
            action = rule.find("action")
            if action.get("type") != "Rewrite":
                continue
            if re.search(rule.find("match").get("url"), path):
                return rule, action
        self.fail(f"No rewrite rule for {path}")

    def test_entire_validation_workflow_reaches_single_worker(self):
        for suffix in ("", "/catalog", "/academic", "/academic/test-job",
                       "/preview", "/reports/test-report/xlsx", "/reports/test-report/pdf"):
            with self.subTest(suffix=suffix):
                rule, action = self.destination("api/moodle/enrollment-validation" + suffix)
                self.assertEqual(rule.get("stopProcessing"), "true")
                self.assertEqual(action.get("url"), "http://127.0.0.1:8002/{R:0}")
                self.assertEqual(action.get("appendQueryString", "true"), "true")

    def test_other_endpoints_keep_main_backend(self):
        for path in ("api/moodle/enrollment-validation-other", "api/moodle/courses",
                     "api/auth/me", "api/students/matricula-acad/bulk/preview"):
            with self.subTest(path=path):
                _, action = self.destination(path)
                self.assertEqual(action.get("url"), "http://sistema_academico_backend/api/{R:1}")

    def test_auxiliary_backend_explicitly_uses_one_worker(self):
        script = Path(__file__).resolve().parents[1] / "scripts/ensure_backend_8002.ps1"
        self.assertRegex(script.read_text(encoding="utf-8"), r"'--workers',\s*'1'")


if __name__ == "__main__":
    unittest.main()
