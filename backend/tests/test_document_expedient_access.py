import unittest

from fastapi import HTTPException

from app.core.security import SessionUser
from app.routers.document_expedients import _ACCESS


class DocumentExpedientAccessTests(unittest.TestCase):
    def test_student_is_rejected(self) -> None:
        student = SessionUser(login="estudiante@intec.edu.ec", rol="ESTUDIANTE")

        with self.assertRaises(HTTPException) as context:
            _ACCESS(student)

        self.assertEqual(context.exception.status_code, 403)

    def test_authorized_profiles_are_accepted(self) -> None:
        for role in ("ACADEMICO", "SECRETARIA", "ADMINISTRADOR"):
            with self.subTest(role=role):
                user = SessionUser(login="usuario@intec.edu.ec", rol=role)
                self.assertIs(_ACCESS(user), user)


if __name__ == "__main__":
    unittest.main()
