import hashlib
import json
import random
from typing import Any


GENERATION_PREFIX = "AUTO_DOCENTE_GENERADA_V1:"
GENERATION_POLICY_VERSION = "9_UNDER_10_V1"


def generation_fingerprint(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def generate_self_evaluation_answers(questions: list[dict[str, Any]], seed: str, key: str) -> dict[str, Any]:
    if not questions:
        raise ValueError("El instrumento no tiene preguntas activas.")
    ids = [int(question["id_pregunta"]) for question in questions]
    if len(ids) != len(set(ids)):
        raise ValueError("El instrumento contiene preguntas duplicadas.")
    if any(float(question["puntaje_min"]) != 1 or float(question["puntaje_max"]) != 5 for question in questions):
        raise ValueError("La generación requiere un instrumento con escala de 1 a 5; no se modificará su escala.")

    count = len(questions)
    if count < 2:
        raise ValueError("Se requieren al menos dos preguntas para obtener una nota desde 9 y menor que 10 con escala de 1 a 5.")

    rng = random.Random(generation_fingerprint([seed, key]))
    # Keep the average below 4.995 so rounding to two decimals cannot produce 5.00.
    min_fours = count // 200 + 1
    fives = rng.randint((count + 1) // 2, count - min_fours)
    scores = [5] * fives + [4] * (count - fives)
    rng.shuffle(scores)
    answers = [{"id_pregunta": question_id, "puntaje": score} for question_id, score in zip(ids, scores)]
    score_100 = round(sum(scores) / count * 20, 2)
    return {"answers": answers, "score_10": round(score_100 / 10, 2)}


def encode_generation_metadata(metadata: dict[str, Any]) -> str:
    return GENERATION_PREFIX + json.dumps(metadata, ensure_ascii=True, separators=(",", ":"))


def decode_generation_metadata(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, str) or not value.startswith(GENERATION_PREFIX):
        return None
    try:
        metadata = json.loads(value[len(GENERATION_PREFIX):])
    except (ValueError, TypeError):
        return None
    if not isinstance(metadata, dict) or metadata.get("kind") != "ADMINISTRATIVE_RANDOM_SELF_EVALUATION":
        return None
    return metadata


def acquire_self_evaluation_lock(cursor: Any) -> None:
    from fastapi import HTTPException

    cursor.execute(
        """
        SET NOCOUNT ON;
        IF @@TRANCOUNT = 0 BEGIN TRANSACTION;
        DECLARE @result int;
        EXEC @result = sys.sp_getapplock
            @Resource = N'SISACA_AUTO_DOCENTE', @LockMode = 'Exclusive',
            @LockOwner = 'Transaction', @LockTimeout = 10000;
        SELECT @result;
        """
    )
    row = cursor.fetchone()
    if not row or int(row[0]) < 0:
        raise HTTPException(status_code=409, detail="Otra autoevaluación se está guardando. Intente nuevamente.")


def generation_report_notices(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    notices: dict[int, dict[str, Any]] = {}
    for row in rows:
        for notice in row.get("autoevaluaciones_generadas") or []:
            notices[int(notice["application_id"])] = notice
    return list(notices.values())
