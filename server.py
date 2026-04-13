"""
server.py — YoWhats Agent API v3.1
Mounts all routers including the new dashboard router.
Visit http://localhost:8000/dashboard after starting the server.
"""

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
import os

from routers.chat_router      import router as chat_router
from routers.admin_router     import router as admin_router
from routers.client_router    import router as client_router
from routers.agentic_router   import router as agentic_router
from routers.dashboard_router import router as dashboard_router
from auth.dependencies        import require_auth, get_key_manager
from auth.models              import APIKey
from memory.mongo_memory      import MongoMemory

app = FastAPI(
    title       = "YoWhats RAG Agent API",
    description = (
        "VaseegrahVeda conversational AI platform.\n\n"
        "**Dashboard:** Visit `/dashboard` in your browser after starting the server.\n\n"
        "**Authentication:** Pass your API key in the `X-API-Key` header.\n"
        "Key format: `ywk_live_<role><hex>`\n\n"
        "**Roles:** `admin` > `client` > `user`"
    ),
    version  = "3.1.0",
    docs_url = "/docs",
    redoc_url= "/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins     = ["*"],
    allow_credentials = True,
    allow_methods     = ["*"],
    allow_headers     = ["*"],
)

# Mount all routers
app.include_router(dashboard_router)   # /dashboard (serves HTML + data endpoints)
app.include_router(chat_router)
app.include_router(admin_router)
app.include_router(client_router)
app.include_router(agentic_router)

_memory = MongoMemory()


@app.get("/", include_in_schema=False)
async def root_redirect():
    return RedirectResponse(url="/dashboard")


@app.get("/health", tags=["System"])
async def health():
    return {
        "status":  "ok",
        "service": "YoWhats RAG Agent",
        "version": "3.1.0",
    }


@app.get("/history/{user_id}", tags=["Chat"])
async def history(
    user_id: str,
    limit:   int    = 10,
    caller:  APIKey = Depends(require_auth),
):
    session_id = _memory.get_or_create_session(user_id)
    msgs       = _memory.get_history(user_id, session_id, limit=limit)
    return {"user_id": user_id, "session_id": session_id, "messages": msgs}


@app.on_event("startup")
async def startup():
    km = get_key_manager()
    km.bootstrap_root_admin()
    print("🚀 YoWhats Agent API v3.1 ready")
    print("📊 Dashboard: http://localhost:8000/dashboard")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)