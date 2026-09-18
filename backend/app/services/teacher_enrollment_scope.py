from pathlib import Path
from typing import Any


_SCHEMA_SQL = (Path(__file__).resolve().parents[2] / "sql" / "2026_09_18_matricula_docente_seleccion.sql").read_text(encoding="utf-8")


def ensure_teacher_selection_schema(cursor: Any) -> None:
    cursor.execute(_SCHEMA_SQL)


def teacher_selection_filter(cursor: Any, *, assignment: str = "cxd", student: str = "cxe") -> str:
    cursor.execute("SELECT OBJECT_ID(N'dbo.PORTAL_MATRICULA_DOCENTE_SELECCION', N'U')")
    row = cursor.fetchone()
    if row is None or not isinstance(row[0], int) or row[0] <= 0:
        return "1 = 1"

    course_filter = f"""
        selection.codigo_doc = TRY_CONVERT(int, {assignment}.codigo_doc)
        AND selection.cod_anio_basica = TRY_CONVERT(int, {assignment}.cod_Anio_Basica)
        AND selection.codigo_materia = TRY_CONVERT(int, {assignment}.codigo_materia)
        AND selection.codigo_periodo = TRY_CONVERT(int, {assignment}.codigo_periodo)
        AND selection.paralelo = UPPER(LTRIM(RTRIM(TRY_CONVERT(nvarchar(100), {assignment}.Paralelo))))
        AND selection.cod_jornada = COALESCE(TRY_CONVERT(int, {assignment}.Cod_Jornada), -1)
    """
    # Unscoped, pre-existing assignments retain their course-wide behavior.
    return f"""(
        NOT EXISTS (
            SELECT 1 FROM dbo.PORTAL_MATRICULA_DOCENTE_SELECCION selection
            WHERE {course_filter}
        )
        OR EXISTS (
            SELECT 1 FROM dbo.PORTAL_MATRICULA_DOCENTE_SELECCION selection
            WHERE {course_filter}
              AND selection.codigo_estud = TRY_CONVERT(int, {student}.codigo_estud)
              AND selection.cod_anio_basica = TRY_CONVERT(int, {student}.cod_anio_Basica)
              AND selection.codigo_materia = TRY_CONVERT(int, {student}.codigo_materia)
        )
    )"""


def save_teacher_selection(
    cursor: Any,
    *,
    codigo_doc: int,
    cod_anio_basica: int,
    codigo_materia: int,
    codigo_periodo: int,
    paralelo: str,
    cod_jornada: int,
    student_codes: list[int] | None,
) -> None:
    if student_codes == []:
        raise ValueError("Individual enrollment requires a nonempty student selection")
    ensure_teacher_selection_schema(cursor)
    course_params = (codigo_doc, cod_anio_basica, codigo_materia, codigo_periodo, paralelo, cod_jornada)
    course_where = """
        codigo_doc = ? AND cod_anio_basica = ? AND codigo_materia = ?
        AND codigo_periodo = ? AND paralelo = ? AND cod_jornada = ?
    """
    if student_codes is None:
        # Only an explicitly course-wide request removes an individual restriction.
        cursor.execute(f"DELETE FROM dbo.PORTAL_MATRICULA_DOCENTE_SELECCION WHERE {course_where}", *course_params)
        return
    for code in student_codes:
        cursor.execute(
            f"""
            INSERT INTO dbo.PORTAL_MATRICULA_DOCENTE_SELECCION (
                codigo_doc, cod_anio_basica, codigo_materia, codigo_periodo,
                paralelo, cod_jornada, codigo_estud, registrado_por
            )
            SELECT ?, ?, ?, ?, ?, ?, ?, COALESCE(TRY_CONVERT(nvarchar(256), SESSION_CONTEXT(N'app_user')), ORIGINAL_LOGIN())
            WHERE NOT EXISTS (
                SELECT 1 FROM dbo.PORTAL_MATRICULA_DOCENTE_SELECCION WITH (UPDLOCK, HOLDLOCK)
                WHERE {course_where} AND codigo_estud = ?
            )
            """,
            *course_params, code, *course_params, code,
        )
