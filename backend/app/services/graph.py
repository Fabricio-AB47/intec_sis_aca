from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Any, cast

import httpx
import msal  # type: ignore[import-untyped]

from app.core.config import get_settings

_JSON_CONTENT_TYPE = "application/json"
_DELEGATED_TOKENS: dict[str, dict[str, Any]] = {}
_APP_TOKEN_CACHE: dict[str, Any] = {}
_APP_TOKEN_LOCK = Lock()


_PLACEHOLDER_VALUES = {
    "tu-tenant-id",
    "your-tenant-id",
    "00000000-0000-0000-0000-000000000000",
    "replace-with-graph-client-secret",
    "change-me",
}


def _is_placeholder(value: str | None) -> bool:
    if value is None:
        return True

    normalized = value.strip().lower()
    return not normalized or normalized in _PLACEHOLDER_VALUES


def _get_msal_app():
    settings = get_settings()
    missing: list[str] = []
    if _is_placeholder(settings.tenant_id):
        missing.append("TENANT_ID")
    if _is_placeholder(settings.client_id):
        missing.append("CLIENT_ID")
    if _is_placeholder(settings.client_secret):
        missing.append("CLIENT_SECRET")

    if missing:
        raise RuntimeError(
            "Configuracion de Microsoft Graph incompleta o invalida. "
            f"Revisa: {', '.join(missing)}"
        )

    authority = f"https://login.microsoftonline.com/{settings.tenant_id}"
    try:
        return msal.ConfidentialClientApplication(
            client_id=settings.client_id,
            authority=authority,
            client_credential=settings.client_secret,
        )
    except ValueError as exc:
        raise RuntimeError(
            "No se pudo inicializar Microsoft Graph. Verifica TENANT_ID/CLIENT_ID/CLIENT_SECRET en .env"
        ) from exc


def get_delegate_scopes() -> list[str]:
    settings = get_settings()
    scopes = [scope.strip() for scope in settings.graph_delegate_scopes.split(",") if scope.strip()]
    return scopes if scopes else ["User.Read"]


def get_delegate_redirect_uri() -> str:
    settings = get_settings()
    return settings.graph_delegate_redirect_uri


def build_delegate_auth_url(state: str) -> str:
    app_msal = cast(Any, _get_msal_app())
    return str(
        app_msal.get_authorization_request_url(
            scopes=get_delegate_scopes(),
            state=state,
            redirect_uri=get_delegate_redirect_uri(),
            prompt="select_account",
        )
    )


def exchange_delegate_code(code: str) -> dict[str, Any]:
    app_msal = cast(Any, _get_msal_app())
    result_raw = app_msal.acquire_token_by_authorization_code(
        code=code,
        scopes=get_delegate_scopes(),
        redirect_uri=get_delegate_redirect_uri(),
    )
    result = cast(dict[str, Any], result_raw) if isinstance(result_raw, dict) else {}
    if "access_token" not in result:
        raise RuntimeError(str(result.get("error_description", "No se pudo obtener token delegado")))
    return result


def store_delegated_token(login: str, token_result: dict[str, Any]) -> None:
    expires_in = int(token_result.get("expires_in") or 3600)
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=max(60, expires_in - 60))
    _DELEGATED_TOKENS[login] = {
        "access_token": token_result.get("access_token"),
        "expires_at": expires_at,
        "scope": token_result.get("scope"),
    }


def delegated_token_cookie_payload(token_result: dict[str, Any]) -> tuple[str, int]:
    access_token = str(token_result.get("access_token") or "")
    expires_in = int(token_result.get("expires_in") or 3600)
    expires_epoch = int((datetime.now(timezone.utc) + timedelta(seconds=max(60, expires_in - 60))).timestamp())
    return access_token, expires_epoch


def hydrate_delegated_token_from_cookie(login: str, access_token: str | None, expires_epoch: str | None) -> bool:
    if not access_token or not expires_epoch:
        return False
    try:
        exp_int = int(expires_epoch)
    except ValueError:
        return False

    expires_at = datetime.fromtimestamp(exp_int, tz=timezone.utc)
    if datetime.now(timezone.utc) >= expires_at:
        return False

    _DELEGATED_TOKENS[login] = {
        "access_token": access_token,
        "expires_at": expires_at,
        "scope": "cookie",
    }
    return True


def delegated_token_available(login: str) -> bool:
    cached = _DELEGATED_TOKENS.get(login)
    if not cached:
        return False
    expires_at = cached.get("expires_at")
    if not isinstance(expires_at, datetime):
        return False
    return datetime.now(timezone.utc) < expires_at


def get_delegated_access_token(login: str) -> str:
    if not delegated_token_available(login):
        raise RuntimeError("Debes conectar Microsoft para usar envio delegado en Teams.")
    cached = _DELEGATED_TOKENS[login]
    return str(cached.get("access_token") or "")


def graph_post_delegated(login: str, url: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    token = get_delegated_access_token(login)
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": _JSON_CONTENT_TYPE,
    }
    with httpx.Client(timeout=30.0) as client:
        response = client.post(url, headers=headers, json=payload)
        response.raise_for_status()

        if not response.content:
            return {"ok": True}

        return response.json()


def get_graph_token() -> str:
    cached_token = str(_APP_TOKEN_CACHE.get("access_token") or "")
    cached_expires_at = _APP_TOKEN_CACHE.get("expires_at")
    if cached_token and isinstance(cached_expires_at, datetime) and datetime.now(timezone.utc) < cached_expires_at:
        return cached_token

    with _APP_TOKEN_LOCK:
        cached_token = str(_APP_TOKEN_CACHE.get("access_token") or "")
        cached_expires_at = _APP_TOKEN_CACHE.get("expires_at")
        if cached_token and isinstance(cached_expires_at, datetime) and datetime.now(timezone.utc) < cached_expires_at:
            return cached_token

        settings = get_settings()
        scope = [settings.graph_scope]
        app_msal = _get_msal_app()
        result_raw = app_msal.acquire_token_for_client(scopes=scope)  # type: ignore[no-untyped-call]
        result = cast(dict[str, Any], result_raw) if isinstance(result_raw, dict) else {}
        if "access_token" not in result:
            raise RuntimeError(str(result.get("error_description", "No se pudo obtener token")))

        expires_in = int(result.get("expires_in") or 3600)
        token = str(result["access_token"])
        _APP_TOKEN_CACHE["access_token"] = token
        _APP_TOKEN_CACHE["expires_at"] = datetime.now(timezone.utc) + timedelta(seconds=max(60, expires_in - 120))
        return token


def graph_get(url: str) -> dict[str, Any]:
    token = get_graph_token()
    headers = {"Authorization": f"Bearer {token}"}
    with httpx.Client(timeout=30.0) as client:
        response = client.get(url, headers=headers)
        response.raise_for_status()
        return response.json()


def graph_get_all(url: str, max_items: int | None = None) -> dict[str, Any]:
    token = get_graph_token()
    headers = {"Authorization": f"Bearer {token}"}
    items: list[dict[str, Any]] = []
    next_url: str | None = url

    with httpx.Client(timeout=30.0) as client:
        while next_url:
            response = client.get(next_url, headers=headers)
            response.raise_for_status()
            payload = cast(dict[str, Any], response.json())

            page_items = cast(list[Any], payload.get("value") or [])
            page_dicts = [cast(dict[str, Any], item) for item in page_items if isinstance(item, dict)]
            items.extend(page_dicts)
            if max_items is not None and len(items) >= max_items:
                items = items[:max_items]
                break

            next_link = payload.get("@odata.nextLink")
            next_url = str(next_link) if next_link else None

    return {"value": items, "count": len(items)}


def graph_post(url: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    token = get_graph_token()
    headers = {
        "Authorization": f"Bearer {token}",
            "Content-Type": _JSON_CONTENT_TYPE,
    }
    with httpx.Client(timeout=30.0) as client:
        response = client.post(url, headers=headers, json=payload)
        response.raise_for_status()

        if not response.content:
            return {"ok": True}

        return response.json()


def graph_post_with_meta(url: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    token = get_graph_token()
    headers = {
        "Authorization": f"Bearer {token}",
            "Content-Type": _JSON_CONTENT_TYPE,
    }
    with httpx.Client(timeout=30.0) as client:
        response = client.post(url, headers=headers, json=payload)
        response.raise_for_status()

        body: dict[str, Any] = {}
        if response.content:
            body = cast(dict[str, Any], response.json())

        return {
            "status_code": response.status_code,
            "headers": dict(response.headers),
            "body": body,
        }


def graph_patch(url: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    token = get_graph_token()
    headers = {
        "Authorization": f"Bearer {token}",
            "Content-Type": _JSON_CONTENT_TYPE,
    }
    with httpx.Client(timeout=30.0) as client:
        response = client.patch(url, headers=headers, json=payload)
        response.raise_for_status()

        if not response.content:
            return {"ok": True}

        return response.json()
