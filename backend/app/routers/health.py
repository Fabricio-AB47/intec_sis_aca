from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str | bool]:
	return {"ok": True, "service": "backend"}
