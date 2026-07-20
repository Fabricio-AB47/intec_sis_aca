from __future__ import annotations

import ast
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
LEGACY_ROOT = REPO_ROOT / "SisAcademicoV1"
ROUTER_PATH = REPO_ROOT / "backend" / "app" / "routers" / "sisacademico_admin.py"
DOC_PATH = REPO_ROOT / "docs" / "SISACADEMICO_V1_FUNCIONALIDAD_COMPLETA.md"
JSON_PATH = REPO_ROOT / "docs" / "sisacademico_v1_inventory.json"

CONTROL_RE = re.compile(r"<asp:([A-Za-z0-9_]+)\b[^>]*\bID=\"([^\"]+)\"", re.IGNORECASE)
EVENT_RE = re.compile(r"\b(?:Protected|Private|Public)\s+Sub\s+([A-Za-z0-9_]+)\b", re.IGNORECASE)
SQL_OP_RE = re.compile(r"\b(SELECT|INSERT|UPDATE|DELETE|MERGE)\b", re.IGNORECASE)
TABLE_RE = re.compile(
    r"\b(?:FROM|JOIN|UPDATE|INTO|DELETE\s+FROM|INSERT\s+INTO)\s+"
    r"(?:dbo\.)?\[?([A-Za-z_][A-Za-z0-9_#$]*)\]?",
    re.IGNORECASE,
)
REPORT_RE = re.compile(r"([A-Za-z0-9_./\\ -]+\.rpt)", re.IGNORECASE)


def read_text(path: Path) -> str:
    for encoding in ("utf-8-sig", "utf-8", "latin-1", "cp1252"):
        try:
            return path.read_text(encoding=encoding, errors="strict")
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding="latin-1", errors="ignore")


def load_modules() -> list[dict[str, Any]]:
    tree = ast.parse(read_text(ROUTER_PATH))
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and getattr(node.target, "id", "") == "LEGACY_CLONE_MODULES":
            return ast.literal_eval(node.value)
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if getattr(target, "id", "") == "LEGACY_CLONE_MODULES":
                    return ast.literal_eval(node.value)
    raise RuntimeError("No se encontro LEGACY_CLONE_MODULES en sisacademico_admin.py")


def path_matches_source(relative_path: str, source: str) -> bool:
    normalized_path = relative_path.replace("\\", "/").lower()
    comparable_paths = [normalized_path]
    if normalized_path.endswith(".aspx.vb"):
        comparable_paths.append(normalized_path[:-3])
    normalized_source = source.replace("\\", "/").lower().rstrip("/")
    if not normalized_source:
        return False
    if normalized_source.endswith("*"):
        return any(path.startswith(normalized_source[:-1]) for path in comparable_paths)
    return any(path == normalized_source or path.startswith(f"{normalized_source}/") for path in comparable_paths)


def classify(relative_path: str, modules: list[dict[str, Any]]) -> dict[str, str]:
    normalized = relative_path.replace("\\", "/")
    lower_path = normalized.lower()
    extension = Path(normalized).suffix.lower().lstrip(".") or "archivo"
    for module in modules:
        for source in module.get("source_paths", []):
            if path_matches_source(normalized, str(source)):
                return {
                    "module_key": str(module["key"]),
                    "module_title": str(module["title"]),
                    "coverage": str(module["coverage"]),
                    "artifact_type": extension,
                }
    if "/static/" in lower_path or "/aspnet_client/" in lower_path or "/bin/" in lower_path:
        return {
            "module_key": "soporte_legacy_no_migrable",
            "module_title": "Soporte legacy no migrable",
            "coverage": "excluded",
            "artifact_type": extension,
        }
    if "/actualizar/" in lower_path or "/auxcambios/" in lower_path or "/pruebas/" in lower_path:
        return {
            "module_key": "mantenimiento_controlado",
            "module_title": "Mantenimiento controlado y operaciones sensibles",
            "coverage": "partial",
            "artifact_type": extension,
        }
    if "/reporteacad/" in lower_path or "/reportenotas/" in lower_path or "/reporteshtml/" in lower_path or lower_path.endswith(".rpt"):
        return {
            "module_key": "certificados",
            "module_title": "Certificados y reportes",
            "coverage": "base",
            "artifact_type": extension,
        }
    return {
        "module_key": "pendiente_clasificacion",
        "module_title": "Pendiente de clasificacion",
        "coverage": "pending",
        "artifact_type": extension,
    }


def unique_sorted(values: list[str] | set[str]) -> list[str]:
    return sorted({value.strip(" []\r\n\t") for value in values if value and value.strip()})


def analyze() -> dict[str, Any]:
    modules = load_modules()
    module_by_key = {module["key"]: module for module in modules}
    files = [
        path
        for path in LEGACY_ROOT.rglob("*")
        if path.is_file() and path.suffix.lower() in {".aspx", ".vb", ".rpt", ".config"}
    ]

    artifacts: list[dict[str, Any]] = []
    module_tables: dict[str, Counter[str]] = defaultdict(Counter)
    module_operations: dict[str, Counter[str]] = defaultdict(Counter)
    module_controls: dict[str, Counter[str]] = defaultdict(Counter)
    module_events: dict[str, set[str]] = defaultdict(set)
    module_reports: dict[str, set[str]] = defaultdict(set)
    risky_files: list[dict[str, Any]] = []

    for path in sorted(files):
        relative_path = path.relative_to(LEGACY_ROOT).as_posix()
        classification = classify(relative_path, modules)
        module_key = classification["module_key"]
        extension = path.suffix.lower().lstrip(".")
        text = "" if extension == "rpt" else read_text(path)
        operations = [operation.upper() for operation in SQL_OP_RE.findall(text)]
        tables = [table.upper() for table in TABLE_RE.findall(text)]
        controls = [f"{kind}:{control_id}" for kind, control_id in CONTROL_RE.findall(text)]
        events = EVENT_RE.findall(text)
        reports = [report.replace("\\", "/") for report in REPORT_RE.findall(text)]

        module_tables[module_key].update(tables)
        module_operations[module_key].update(operations)
        module_controls[module_key].update(controls)
        module_events[module_key].update(events)
        module_reports[module_key].update(reports)

        if "DELETE" in operations or relative_path.lower().startswith("actualizar/"):
            risky_files.append(
                {
                    "path": relative_path,
                    "module_key": module_key,
                    "operations": sorted(set(operations)),
                    "tables": unique_sorted(tables),
                }
            )

        artifacts.append(
            {
                "path": relative_path,
                "extension": extension,
                "size_bytes": path.stat().st_size,
                **classification,
                "sql_operations": dict(Counter(operations)),
                "tables": unique_sorted(tables),
                "controls": unique_sorted(controls),
                "events": sorted(set(events)),
                "report_references": unique_sorted(reports),
            }
        )

    modules_payload: list[dict[str, Any]] = []
    for module_key in sorted({artifact["module_key"] for artifact in artifacts} | set(module_by_key)):
        module = module_by_key.get(module_key, {})
        module_artifacts = [artifact for artifact in artifacts if artifact["module_key"] == module_key]
        modules_payload.append(
            {
                "key": module_key,
                "title": module.get("title") or (module_artifacts[0]["module_title"] if module_artifacts else module_key),
                "description": module.get("description", ""),
                "coverage": module.get("coverage") or (module_artifacts[0]["coverage"] if module_artifacts else "pending"),
                "modern_routes": module.get("modern_routes", []),
                "modern_sections": module.get("modern_sections", []),
                "source_paths": module.get("source_paths", []),
                "tables_configured": module.get("tables", []),
                "artifact_count": len(module_artifacts),
                "artifact_extensions": dict(Counter(artifact["extension"] for artifact in module_artifacts)),
                "detected_tables": [table for table, _ in module_tables[module_key].most_common()],
                "sql_operations": dict(module_operations[module_key]),
                "controls_count": sum(module_controls[module_key].values()),
                "top_controls": [control for control, _ in module_controls[module_key].most_common(25)],
                "events": sorted(module_events[module_key])[:80],
                "report_references": sorted(module_reports[module_key]),
                "notes": module.get("notes", ""),
            }
        )

    totals = {
        "artifacts": len(artifacts),
        "by_extension": dict(Counter(artifact["extension"] for artifact in artifacts)),
        "by_coverage": dict(Counter(artifact["coverage"] for artifact in artifacts)),
        "by_module": dict(Counter(artifact["module_key"] for artifact in artifacts)),
        "tables_detected": len({table for counter in module_tables.values() for table in counter}),
        "risky_files": len(risky_files),
    }

    return {
        "project": "SisAcademicoV1",
        "legacy_root": str(LEGACY_ROOT),
        "strategy": "Clonacion total funcional adaptada a FastAPI/React; Crystal Reports se reemplaza por generacion PDF/Excel/HTML por codigo.",
        "totals": totals,
        "modules": modules_payload,
        "artifacts": artifacts,
        "risky_files": risky_files,
    }


def render_markdown(payload: dict[str, Any]) -> str:
    lines: list[str] = []
    totals = payload["totals"]
    lines.extend(
        [
            "# SisAcademicoV1 - Funcionalidad completa para clonacion",
            "",
            "## Objetivo",
            "",
            "Este documento consolida la informacion extraida directamente del proyecto `SisAcademicoV1` para completar la clonacion funcional dentro del sistema moderno.",
            "",
            "Regla principal: no se ejecuta Crystal Reports. Los `.rpt` quedan como referencia y los documentos se generan por codigo usando PDF/Excel/HTML desde backend.",
            "",
            "## Totales detectados",
            "",
            "| Indicador | Valor |",
            "|---|---:|",
            f"| Artefactos revisados | {totals['artifacts']} |",
        ]
    )
    for extension, count in sorted(totals["by_extension"].items()):
        lines.append(f"| Archivos `{extension}` | {count} |")
    for coverage, count in sorted(totals["by_coverage"].items()):
        lines.append(f"| Estado `{coverage}` | {count} |")
    lines.extend(
        [
            f"| Tablas SQL detectadas | {totals['tables_detected']} |",
            f"| Archivos con riesgo DELETE/mantenimiento | {totals['risky_files']} |",
            "",
            "## Mapa de modulos",
            "",
            "| Modulo | Estado | Artefactos | Tablas detectadas | Operaciones | Frontend/backend moderno |",
            "|---|---|---:|---|---|---|",
        ]
    )
    for module in payload["modules"]:
        tables = ", ".join(module["detected_tables"][:10]) or "-"
        operations = ", ".join(f"{key}:{value}" for key, value in sorted(module["sql_operations"].items())) or "-"
        modern = ", ".join(module["modern_routes"] + module["modern_sections"]) or "-"
        lines.append(
            f"| {module['title']} | {module['coverage']} | {module['artifact_count']} | {tables} | {operations} | {modern} |"
        )

    lines.extend(["", "## Detalle por modulo", ""])
    for module in payload["modules"]:
        lines.extend(
            [
                f"### {module['title']}",
                "",
                f"- Clave: `{module['key']}`",
                f"- Estado: `{module['coverage']}`",
                f"- Artefactos: `{module['artifact_count']}`",
                f"- Rutas backend modernas: {', '.join(module['modern_routes']) or '-'}",
                f"- Secciones frontend/admin modernas: {', '.join(module['modern_sections']) or '-'}",
                f"- Tablas configuradas: {', '.join(module['tables_configured']) or '-'}",
                f"- Tablas detectadas: {', '.join(module['detected_tables'][:40]) or '-'}",
                f"- Operaciones SQL: {', '.join(f'{key}:{value}' for key, value in sorted(module['sql_operations'].items())) or '-'}",
                f"- Referencias de reporte: {', '.join(module['report_references'][:20]) or '-'}",
                f"- Nota: {module['notes'] or '-'}",
                "",
            ]
        )

    lines.extend(
        [
            "## Archivos de mantenimiento sensible",
            "",
            "Estos archivos no deben clonarse como botones directos. Deben convertirse en operaciones auditadas, con confirmacion y permisos altos.",
            "",
            "| Archivo | Modulo | Operaciones | Tablas |",
            "|---|---|---|---|",
        ]
    )
    for item in payload["risky_files"][:120]:
        lines.append(
            f"| `{item['path']}` | {item['module_key']} | {', '.join(item['operations']) or '-'} | {', '.join(item['tables'][:12]) or '-'} |"
        )

    lines.extend(
        [
            "",
            "## Plan para documentos PDF sin Crystal Reports",
            "",
            "1. Tomar cada familia `.rpt` como referencia de columnas, filtros y layout.",
            "2. Reconstruir el dataset en SQL parametrizado dentro de FastAPI.",
            "3. Generar PDF con reportlab o equivalente ya usado por el backend.",
            "4. Generar Excel con openpyxl cuando el reporte sea tabular.",
            "5. Validar visualmente contra formatos de Secretaria, Financiero o Coordinacion.",
            "6. Mantener endpoints antiguos solo como alias de compatibilidad, nunca como ejecucion Crystal.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    payload = analyze()
    JSON_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    DOC_PATH.write_text(render_markdown(payload), encoding="utf-8")
    print(f"Inventario generado: {JSON_PATH.relative_to(REPO_ROOT)}")
    print(f"Documento generado: {DOC_PATH.relative_to(REPO_ROOT)}")
    print(json.dumps(payload["totals"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
