:On Error exit

/*
Prompt 08 - TITULACION_INTEC todo en uno

Ejecutar con sqlcmd o SQL Server Management Studio en modo SQLCMD.

Ejemplo:
  cd backend\sql
  sqlcmd -S <servidor> -d TITULACION_INTEC -E -b -I -i TITULACION_INTEC_PROMPT_08_TODO_EN_UNO.sql

Este archivo aplica los scripts idempotentes del modulo en el orden operativo:
base, mecanismos, grupos/evaluadores, dashboard/rubricas/auditoria,
documentos/actas/titulos, correcciones y smoke test.
*/

PRINT 'Aplicando base TITULACION_INTEC Prompt 02...';
:r .\TITULACION_INTEC_PORTAL_COMPLETO_PROMPT_02.sql

PRINT 'Aplicando mecanismos, complexivo y defensa...';
:r .\TITULACION_INTEC_COMPLEMENTO_MECANISMOS_COMPLEXIVO_DEFENSA.sql

PRINT 'Aplicando grupos, integrantes y evaluadores...';
:r .\TITULACION_INTEC_COMPLEMENTO_PORTAL_GRUPOS_EVALUADORES.sql

PRINT 'Aplicando dashboard, rubricas y auditoria...';
:r .\TITULACION_INTEC_COMPLEMENTO_DASHBOARD_RUBRICAS_AUDITORIA.sql

PRINT 'Aplicando documentos, actas y titulos...';
:r .\TITULACION_INTEC_COMPLEMENTO_DOCUMENTOS_ACTAS_TITULOS.sql

PRINT 'Aplicando fix de numero de refrendacion...';
:r .\TITULACION_INTEC_FIX_NUMERO_REFRENDACION_DESDE_ACTA.sql

PRINT 'Aplicando cierre Prompt 08...';
:r .\TITULACION_INTEC_PROMPT_08_CIERRE.sql

PRINT 'Ejecutando smoke test SQL...';
:r .\TITULACION_INTEC_QA_SMOKE.sql

PRINT 'TITULACION_INTEC Prompt 08 aplicado correctamente.';
