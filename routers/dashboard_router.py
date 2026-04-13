"""
routers/dashboard_router.py

The dashboard is a SERVER-SIDE admin control panel.
It runs on the same server as the backend and talks directly to KeyManager.
NO X-API-Key auth required — access is controlled by network/firewall
(only you can reach localhost:8000/dashboard).

All data endpoints are prefixed /dashboard/api/* and require NO auth header —
the browser dashboard JS calls them directly.

Purpose: generate API keys for CLIENTS and ADMINS who want to access
the RAG + LLM + web search agents.
"""

from datetime import datetime, UTC, timedelta
from collections import defaultdict, Counter
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from auth.key_manager import KeyManager
from auth.models      import ROLE_HIERARCHY

router = APIRouter(tags=["Dashboard"])
DASHBOARD_HTML = Path(__file__).resolve().parents[1] / "dashboard" / "dashboard.html"

# Direct KeyManager — no auth middleware, dashboard is internal only
_km = KeyManager()


# ── Serve dashboard HTML ──────────────────────────────────────────

@router.get("/dashboard", response_class=HTMLResponse, include_in_schema=False)
async def serve_dashboard():
    if not DASHBOARD_HTML.exists():
        return HTMLResponse(
            "<h2>dashboard.html not found in dashboard/</h2>",
            status_code=404,
        )
    return HTMLResponse(content=DASHBOARD_HTML.read_text(encoding="utf-8"))


# ── Stats ─────────────────────────────────────────────────────────

@router.get("/dashboard/api/stats")
async def stats():
    all_keys   = _km.list_keys(limit=1000)
    total      = len(all_keys)
    active     = sum(1 for k in all_keys if k.get("is_active"))
    admins     = sum(1 for k in all_keys if k.get("role") == "admin")
    clients    = sum(1 for k in all_keys if k.get("role") == "client")

    month_start = datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    new_month   = sum(1 for k in all_keys if _parse_dt(k.get("created_at","")) >= month_start)

    logs      = _km.get_usage(days=30, limit=10000)
    calls_30d = len(logs)
    avg_ms    = round(sum(l.get("response_ms",0) for l in logs) / max(calls_30d,1))

    return {
        "total": total, "active": active, "admins": admins,
        "clients": clients, "new_month": new_month,
        "calls_30d": calls_30d, "avg_ms": avg_ms,
    }


# ── All keys list ─────────────────────────────────────────────────

@router.get("/dashboard/api/keys")
async def list_keys(
    role:   Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
):
    keys = _km.list_keys(role=role, limit=500)
    if status == "active":  keys = [k for k in keys if k.get("is_active")]
    if status == "revoked": keys = [k for k in keys if not k.get("is_active")]
    if search:
        s = search.lower()
        keys = [k for k in keys if s in (k.get("label","")).lower() or s in (k.get("key_prefix","")).lower()]
    return {"keys": keys}


# ── Create key ────────────────────────────────────────────────────

class CreateKeyBody(BaseModel):
    role:            str
    label:           str
    expires_in_days: Optional[int]  = None
    monthly_limit:   Optional[int]  = None
    metadata:        Optional[dict] = None

@router.post("/dashboard/api/keys", status_code=201)
async def create_key(body: CreateKeyBody):
    if body.role not in ("admin", "client"):
        from fastapi import HTTPException
        raise HTTPException(400, "Dashboard only creates admin or client keys")
    result = _km.create_key(
        role            = body.role,
        label           = body.label,
        owner_id        = "dashboard",
        expires_in_days = body.expires_in_days,
        monthly_limit   = body.monthly_limit,
        metadata        = body.metadata or {},
    )
    return result   # includes the full key — shown once


# ── Revoke key ────────────────────────────────────────────────────

@router.post("/dashboard/api/keys/{key_id}/revoke")
async def revoke_key(key_id: str):
    ok = _km.revoke_key(key_id)
    if not ok:
        from fastapi import HTTPException
        raise HTTPException(404, "Key not found")
    return {"status": "revoked", "key_id": key_id}


# ── Rotate key ────────────────────────────────────────────────────

@router.post("/dashboard/api/keys/{key_id}/rotate")
async def rotate_key(key_id: str):
    result = _km.rotate_key(key_id)
    if not result:
        from fastapi import HTTPException
        raise HTTPException(404, "Key not found")
    return result   # new full key — shown once


# ── Update key ────────────────────────────────────────────────────

class UpdateKeyBody(BaseModel):
    label:         Optional[str]      = None
    expires_at:    Optional[datetime] = None
    monthly_limit: Optional[int]      = None
    is_active:     Optional[bool]     = None

@router.patch("/dashboard/api/keys/{key_id}")
async def update_key(key_id: str, body: UpdateKeyBody):
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    ok = _km.update_key(key_id, updates)
    return {"status": "updated" if ok else "no_change", "key_id": key_id}


# ── Usage chart — daily 14d ───────────────────────────────────────

@router.get("/dashboard/api/chart/daily")
async def chart_daily():
    logs   = _km.get_usage(days=14, limit=50000)
    counts: dict[str, int] = defaultdict(int)
    for l in logs:
        day = str(l.get("ts",""))[:10]
        if day: counts[day] += 1
    today  = datetime.now(UTC).date()
    labels, data = [], []
    for i in range(13, -1, -1):
        d = today - timedelta(days=i)
        labels.append(d.strftime("%b %d"))
        data.append(counts.get(str(d), 0))
    return {"labels": labels, "data": data}


# ── Usage chart — hourly today ────────────────────────────────────

@router.get("/dashboard/api/chart/hourly")
async def chart_hourly():
    logs      = _km.get_usage(days=1, limit=10000)
    today_str = str(datetime.now(UTC).date())
    counts: dict[int, int] = defaultdict(int)
    for l in logs:
        ts = str(l.get("ts",""))
        if ts[:10] == today_str:
            try: counts[int(ts[11:13])] += 1
            except: pass
    return {"labels": [f"{h}:00" for h in range(24)],
            "data":   [counts.get(h, 0) for h in range(24)]}


# ── Role breakdown ────────────────────────────────────────────────

@router.get("/dashboard/api/chart/roles")
async def chart_roles():
    keys = _km.list_keys(limit=1000)
    c    = Counter(k.get("role","?") for k in keys)
    return {"admin": c.get("admin",0), "client": c.get("client",0), "user": c.get("user",0)}


# ── Recent activity ───────────────────────────────────────────────

@router.get("/dashboard/api/activity")
async def activity(limit: int = 20):
    keys   = _km.list_keys(limit=200)
    events = []
    for k in keys:
        events.append({"event":"created","key_prefix":k.get("key_prefix",""),
                        "role":k.get("role",""),"label":k.get("label",""),
                        "ts":k.get("created_at","")})
        if not k.get("is_active") and k.get("revoked_at"):
            events.append({"event":"revoked","key_prefix":k.get("key_prefix",""),
                            "role":k.get("role",""),"label":k.get("label",""),
                            "ts":k.get("revoked_at","")})
    events.sort(key=lambda e: str(e.get("ts","")), reverse=True)
    return {"events": events[:limit]}


# ── Live request logs ─────────────────────────────────────────────

@router.get("/dashboard/api/logs")
async def logs(limit: int = 60):
    return {"logs": _km.get_usage(days=1, limit=limit)}


# ── helper ────────────────────────────────────────────────────────

def _parse_dt(value) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)
    except:
        return datetime.min.replace(tzinfo=UTC)