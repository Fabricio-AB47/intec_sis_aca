"""Read-only subject reconciliation for the enrollment audit, not enrollment writes."""

from dataclasses import dataclass
import re
import unicodedata

from app.services.moodle_grade_sync import (
    _alpha_code_match_quality, _course_code_match_score, canonical_course_code,
)


@dataclass(frozen=True)
class CodeParts:
    prefix: str
    year: str
    number: str


@dataclass
class SubjectResolution:
    code: str
    candidates: list[dict]
    method: str
    detail: str
    error: str = ""


def _canonical(value: str) -> str:
    return canonical_course_code(unicodedata.normalize("NFKC", str(value or "")))


def _parts(value: str, *, course: bool = False) -> CodeParts | None:
    text = _canonical(value)
    year = re.search(r"(?:19|20)\d{2}", text)
    if not year:
        return None
    prefix = text[:year.start()].strip("-").replace("-", "")
    if not re.fullmatch(r"[A-Z][A-Z01568]*", prefix):
        return None
    remainder = text[year.end():].lstrip("-")
    number = re.match(r"\d+", remainder)
    if not number:
        return None
    suffix = remainder[number.end():]
    if suffix and (not course or not (suffix.startswith("-") or re.match(r"[RH](?:\d|PLAN)", suffix))):
        return None
    return CodeParts(prefix, year.group(), number.group().lstrip("0") or "0")


def _one_typo(left: str, right: str) -> bool:
    if left == right:
        return False
    if len(left) == len(right):
        differences = [i for i, pair in enumerate(zip(left, right)) if pair[0] != pair[1]]
        return len(differences) == 1 or (
            len(differences) == 2 and differences[1] == differences[0] + 1
            and left[differences[0]] == right[differences[1]]
            and left[differences[1]] == right[differences[0]]
        )
    if len(left) > len(right):
        left, right = right, left
    return len(right) == len(left) + 1 and any(right[:i] + right[i + 1:] == left for i in range(len(right)))


class EnrollmentSubjectResolver:
    def __init__(self, subjects: list[dict]):
        self._field_cache: dict[str, tuple[set, set, set]] = {}
        self.groups: dict[CodeParts | str, list[dict]] = {}
        for subject in subjects:
            code = _canonical(subject["subject_code"])
            if code:
                key = _parts(code) or code
                self.groups.setdefault(key, []).append(subject)

    def _field(self, value: str) -> tuple[set, set, set]:
        value = _canonical(value)
        if not value:
            return set(), set(), set()
        if value not in self._field_cache:
            self._field_cache[value] = self._match_field(value)
        return self._field_cache[value]

    def _match_field(self, value: str) -> tuple[set, set, set]:
        """Return exact, similar and review-only families; numeric typos never pass."""
        exact, similar, suggestions = set(), set(), set()
        parsed = _parts(value, course=True)
        for key, rows in self.groups.items():
            if (parsed is not None and parsed == key) or any(
                _course_code_match_score({"shortname": value}, row["subject_code"]) >= 8_000
                for row in rows
            ):
                exact.add(key)
                continue
            if not parsed or not isinstance(key, CodeParts):
                continue
            quality = max(_alpha_code_match_quality([key.prefix], [parsed.prefix]),
                          _alpha_code_match_quality([parsed.prefix], [key.prefix]))
            if not quality and key.prefix.isalpha() and parsed.prefix.isalpha() and _one_typo(key.prefix, parsed.prefix):
                quality = 180
            if quality <= 0:
                continue
            if parsed.year == key.year and parsed.number == key.number:
                similar.add(key)
            elif quality == 300 and (
                (parsed.year == key.year and _one_typo(parsed.number, key.number))
                or (parsed.number == key.number and _one_typo(parsed.year, key.year))
            ):
                suggestions.add(key)
        return exact, similar, suggestions

    def _result(self, keys: set, method: str, detail: str, *, error: bool = False) -> SubjectResolution:
        candidates = sorted((row for key in keys for row in self.groups[key]),
                            key=lambda r: (r["subject_code"], r["career_code"], r["subject_id"]))
        codes = ", ".join(sorted({r["subject_code"] for r in candidates}))
        return SubjectResolution(codes, candidates, method, detail, detail if error else "")

    def resolve(self, course: dict) -> SubjectResolution:
        chosen, proposed = set(), set()
        fuzzy, unresolved_identifier = False, False
        for field in ("shortname", "idnumber"):
            value = course.get(field) or ""
            exact, similar, suggestions = self._field(value)
            found = exact or similar
            chosen.update(found)
            proposed.update(suggestions if not found else set())
            fuzzy |= bool(similar and not exact)
            # A structured but unrecognized identifier must not be silently ignored.
            unresolved_identifier |= bool(value and _parts(value, course=True) and not found)

        if len(chosen) > 1:
            return self._result(chosen | proposed, "Requiere revisión",
                                "Los identificadores de Moodle coinciden con varios códigos de PENSUM; no se eligió una materia por semejanza.", error=True)
        if chosen and unresolved_identifier:
            return self._result(chosen | proposed, "Requiere revisión",
                                "Un identificador Moodle coincide, pero el otro contiene un código de materia distinto o no reconocido.", error=True)
        if chosen:
            key = next(iter(chosen))
            raw_codes = {str(row["subject_code"]).strip().upper() for row in self.groups[key]}
            exact_text = len(raw_codes) == 1 and any(
                str(course.get(field) or "").strip().upper() in raw_codes for field in ("shortname", "idnumber")
            )
            method = "Similitud controlada" if fuzzy else "Exacta" if exact_text else "Normalizada"
            detail = (
                "Prefijo parecido con el mismo año y número de materia; existe una sola familia compatible en PENSUM. Revise los códigos originales."
                if fuzzy else "Código único identificado sin cambiar el año ni el número de materia; se normalizaron formato y sufijos del aula."
                if not exact_text else "Coincidencia exacta del código único de materia."
            )
            return self._result(chosen, method, detail)

        if proposed:
            return self._result(proposed, "Requiere revisión",
                                "Se encontraron códigos parecidos, pero cambia el año o el número de materia. Se muestran como candidatos, no como matrícula validada.", error=True)
        if not unresolved_identifier:
            # Course names are only an exact-code fallback, never a fuzzy subject-name match.
            fallback = set()
            for field in ("displayname", "fullname"):
                fallback.update(self._field(course.get(field) or "")[0])
            if len(fallback) == 1:
                return self._result(fallback, "Normalizada", "Código único completo encontrado en el nombre del aula Moodle.")
            if fallback:
                return self._result(fallback, "Requiere revisión", "El nombre del aula contiene varios códigos de materia.", error=True)
        return self._result(set(), "Sin coincidencia", "No se encontró un código único de PENSUM verificable en el curso Moodle.", error=True)
