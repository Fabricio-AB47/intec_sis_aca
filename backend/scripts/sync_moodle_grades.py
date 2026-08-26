from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import get_settings
from app.services.moodle_grade_sync import MoodleGradeSyncService
from app.services.moodle_read_service import MoodleReadService


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Revisa y sincroniza las notas prácticas de Moodle con INTECBDD.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Aplica los cambios seguros. Sin esta opción solo genera una vista previa.",
    )
    parser.add_argument(
        "--actor",
        default="TAREA_MOODLE_0000",
        help="Identificador de auditoría para la ejecución automática.",
    )
    return parser.parse_args()


async def run(*, apply: bool, actor: str) -> dict[str, object]:
    settings = get_settings()
    moodle = MoodleReadService(settings)
    service = MoodleGradeSyncService(moodle, settings)
    return await service.run_configured(
        apply=apply,
        actor=actor,
    )


def main() -> int:
    args = parse_args()
    try:
        result = asyncio.run(run(apply=bool(args.apply), actor=str(args.actor)))
    except Exception as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "mode": "apply" if args.apply else "preview",
                    "error": str(exc),
                },
                ensure_ascii=False,
            )
        )
        return 1

    print(json.dumps(result, ensure_ascii=False, default=str))
    return 1 if int(result.get("failed") or 0) > 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
