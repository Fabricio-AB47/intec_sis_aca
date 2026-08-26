from __future__ import annotations

import unicodedata
from typing import Any


_INVISIBLE_FORMAT_CHARACTERS = str.maketrans(
    {
        "\u200b": None,
        "\u200c": None,
        "\u200d": None,
        "\u2060": None,
        "\ufeff": None,
    }
)


def normalize_email_identity(value: Any) -> str:
    """Return a strict, case-insensitive identity key for an email address."""

    if value is None:
        return ""

    email = unicodedata.normalize("NFKC", str(value))
    email = email.translate(_INVISIBLE_FORMAT_CHARACTERS).strip().casefold()
    if (
        not email
        or len(email) > 254
        or email.count("@") != 1
        or any(character.isspace() for character in email)
    ):
        return ""

    local_part, domain = email.split("@", 1)
    if not local_part or not domain or domain.startswith(".") or domain.endswith("."):
        return ""
    return email


__all__ = ["normalize_email_identity"]
