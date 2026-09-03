import pyodbc
from fastapi import APIRouter, HTTPException, status

from app.core.file_security import verify_antimalware_available
from app.core.rate_limit import RateLimitUnavailable, rate_limiter
from app.core.session_revocation import SessionRevocationUnavailable, session_revocations
from app.services.screen_access import warm_screen_access_catalog

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str | bool]:
    return {"ok": True, "service": "backend"}


@router.get("/health/ready")
def readiness() -> dict[str, str | bool]:
    """Confirms that navigation and security dependencies are ready."""
    try:
        warm_screen_access_catalog()
        rate_limiter.healthcheck()
        session_revocations.healthcheck()
        verify_antimalware_available()
    except (
        RuntimeError,
        pyodbc.Error,
        RateLimitUnavailable,
        SessionRevocationUnavailable,
    ) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Una dependencia requerida todavía no está disponible.",
        ) from exc
    return {"ok": True, "service": "backend", "navigation": "ready", "security": "ready"}
