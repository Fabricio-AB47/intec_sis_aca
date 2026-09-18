"""Resolve a unique student before creating academic or external accounts."""

from fastapi import HTTPException


def normalized_identification(value) -> str:
    return "".join(str(value or "").split()).replace("-", "").replace(".", "").upper()


def same_identification(left, right) -> bool:
    left, right = normalized_identification(left), normalized_identification(right)
    if not left or not right:
        return False
    return left == right or (left.isdigit() and right.isdigit() and int(left) == int(right))


def find_academic_student(cursor, identification: str, *, for_update: bool = False):
    identity = normalized_identification(identification)
    numeric = int(identity) if identity.isdigit() else 0
    locks = " WITH (UPDLOCK, HOLDLOCK)" if for_update else ""
    cursor.execute(
        f"""SELECT codigo_estud, Cedula_Est, Apellidos_nombre, Estado, correo, correointec
        FROM dbo.DATOS_ESTUD{locks}
        WHERE UPPER(REPLACE(REPLACE(REPLACE(LTRIM(RTRIM(Cedula_Est)), ' ', ''), '-', ''), '.', '')) = ?
           OR (? > 0 AND TRY_CONVERT(bigint, Cedula_Est) = ?)
           OR (? > 0 AND Cedula = ?)""", identity, numeric, numeric, numeric, numeric,
    )
    rows = cursor.fetchall()
    if len(rows) > 1:
        raise HTTPException(409, detail="La cédula está asociada a varios registros académicos. Revise la identidad; no se crearon usuarios.")
    if not rows:
        return None
    if not same_identification(rows[0].Cedula_Est, identity):
        raise HTTPException(409, detail="Cedula_Est y Cedula no identifican al mismo estudiante. Corrija los datos académicos antes de continuar.")
    return rows[0]
