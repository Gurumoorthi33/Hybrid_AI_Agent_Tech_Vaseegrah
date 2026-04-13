"""
auth/dependencies.py
FastAPI dependency functions for authentication and authorization.

Usage in route handlers:
    from auth.dependencies import require_auth, require_role, require_permission

    @app.post("/chat")
    async def chat(req: ChatRequest, key: APIKey = Depends(require_auth)):
        ...

    @app.post("/admin/keys")
    async def create_key(..., key: APIKey = Depends(require_role("admin"))):
        ...
"""

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader
from typing import Optional

from auth.models import APIKey, has_permission
from auth.key_manager import KeyManager

# Lazy singleton — one manager per process
_km: Optional[KeyManager] = None

def _get_km() -> KeyManager:
    global _km
    if _km is None:
        _km = KeyManager()
    return _km


# Header extractor — looks for   X-API-Key: ywk_live_...
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


# ── Base auth dependency ──────────────────────────────────────────

async def require_auth(
    raw_key: Optional[str] = Security(api_key_header),
) -> APIKey:
    """
    Validates the X-API-Key header.
    Returns the APIKey dataclass on success.
    Raises 401 on missing/invalid, 403 on expired/revoked.
    """
    if not raw_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key. Pass it in the X-API-Key header.",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    km  = _get_km()
    key = km.validate_key(raw_key)

    if key is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid, expired, or revoked API key.",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    return key


# ── Role guard factory ────────────────────────────────────────────

def require_role(*roles: str):
    """
    Usage:  Depends(require_role("admin"))
            Depends(require_role("admin", "client"))
    """
    async def _check(key: APIKey = Depends(require_auth)) -> APIKey:
        if key.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"This endpoint requires role: {' or '.join(roles)}. "
                       f"Your key has role: {key.role}",
            )
        return key
    return _check


# ── Permission guard factory ──────────────────────────────────────

def require_permission(permission: str):
    """
    Usage:  Depends(require_permission("key:create_any"))
    """
    async def _check(key: APIKey = Depends(require_auth)) -> APIKey:
        if not has_permission(key.role, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: '{permission}' is required.",
            )
        return key
    return _check


# ── Convenience: get KeyManager in route ─────────────────────────

def get_key_manager() -> KeyManager:
    return _get_km()