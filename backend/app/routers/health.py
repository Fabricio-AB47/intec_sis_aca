import pyodbc
from fastapi import APIRouter, HTTPException, status

from app.services.screen_access import warm_screen_access_catalog

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str | bool]:
	return {"ok": True, "service": "backend"}


@router.get("/health/ready")
def readiness() -> dict[str, str | bool]:
    """Confirms that the navigation catalog is ready for authenticated users."""
    try:
        warm_screen_access_catalog()
    except (RuntimeError, pyodbc.Error) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="El catalogo de navegacion todavia no esta disponible.",
        ) from exc
    return {"ok": True, "service": "backend", "navigation": "ready"}
