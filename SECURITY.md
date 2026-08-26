# Seguridad del repositorio

## Credenciales

- Las contraseñas, los secretos de sesión, las credenciales de base de datos y los secretos de Microsoft Graph se configuran mediante variables de entorno.
- Los archivos `.env`, certificados de firma y llaves privadas no deben versionarse.
- `backend/.env.example` contiene solamente nombres de variables y valores no sensibles.
- Los valores utilizados en pruebas deben generarse durante la ejecución y nunca corresponder a cuentas reales.

## Alertas de secretos

1. Confirme si el hallazgo pertenece al código vigente o solamente al historial.
2. Si el valor fue real, revóquelo y genere uno nuevo antes de cerrar la alerta.
3. Actualice el secreto exclusivamente en el entorno de despliegue o en el archivo `.env` local ignorado por Git.
4. Marque como falso positivo solo los identificadores internos o datos sintéticos comprobados.

## Producción

- Configure `SESSION_COOKIE_SECURE=true` cuando el sistema se publique exclusivamente mediante HTTPS.
- Después de migrar las contraseñas heredadas a Argon2, configure `AUTH_LEGACY_PLAINTEXT_ENABLED=false`.
- La eliminación de un secreto del código no lo invalida. Toda credencial real expuesta en el historial debe rotarse en el servicio correspondiente.

El flujo de integración ejecuta Gitleaks en cada `push` y `pull request` para impedir nuevas exposiciones.
