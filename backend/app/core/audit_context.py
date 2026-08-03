from contextvars import ContextVar, Token
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AuditContext:
    user: str = "SISTEMA"
    role: str = "SISTEMA"
    user_id: str = ""
    origin: str = "API"
    request_id: str = ""
    method: str = ""
    path: str = ""
    client_ip: str = ""


_AUDIT_CONTEXT: ContextVar[AuditContext] = ContextVar(
    "database_audit_context",
    default=AuditContext(),
)


def get_audit_context() -> AuditContext:
    return _AUDIT_CONTEXT.get()


def set_audit_context(context: AuditContext) -> Token[AuditContext]:
    return _AUDIT_CONTEXT.set(context)


def reset_audit_context(token: Token[AuditContext]) -> None:
    _AUDIT_CONTEXT.reset(token)
