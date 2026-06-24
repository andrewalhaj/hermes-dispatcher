"""
Hermes Dispatcher — FastAPI backend
====================================
Serves the built React/Vite SPA from app/dist/ and exposes a JSON API
under /api/*.

Routing convention: every router in routes/ declares bare paths (e.g.
"/tasks", "/stream"). The single /api prefix is applied here in server.py
via include_router(..., prefix="/api"). Never bake the /api prefix into a
router file — keeping it here is what makes any route URL predictable from
this file alone.
"""

import os
import mimetypes
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.routing import APIRouter

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
HERMES_HOME: str = os.environ.get("HERMES_HOME", "/root/.hermes")
KANBAN_DB: Path = Path(HERMES_HOME) / "kanban.db"
STATE_DB: Path = Path(HERMES_HOME) / "state.db"

APP_DIR: Path = Path(__file__).resolve().parent
DIST_DIR: Path = APP_DIR / "app" / "dist"

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(title="Hermes Dispatcher", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    # allow_origins=["*"]: intentional for a single-user, locally-deployed dashboard
    # served over Tailscale/localhost. Cookie is samesite="strict" + httponly=True,
    # which limits CSRF risk in a trusted-network context. To tighten for a
    # publicly-exposed instance, replace "*" with an explicit origin allowlist
    # (greenlight-gated — requires knowing the deployment origin at config time).
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Auth middleware
# ---------------------------------------------------------------------------
_AUTH_EXEMPT = {"/api/auth/login", "/api/auth/logout", "/api/auth/check", "/", "/index.html", "/favicon.ico"}

@app.middleware("http")
async def auth_gate(request: Request, call_next):
    from routes.auth import SESSION_TOKEN  # imported late to avoid circular import
    path = request.url.path

    # Exempt paths
    if path in _AUTH_EXEMPT or path.startswith("/assets/"):
        return await call_next(request)

    cookie = request.cookies.get("hd_session")
    if cookie and cookie == SESSION_TOKEN:
        return await call_next(request)

    # Block: API paths get 401 JSON, SPA paths redirect to /
    if path.startswith("/api/"):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    return RedirectResponse("/", status_code=302)

# ---------------------------------------------------------------------------
# Auth router — registered BEFORE other routers
# ---------------------------------------------------------------------------
from routes.auth import router as auth_router
app.include_router(auth_router, prefix="/api")

# ---------------------------------------------------------------------------
# /api router
# ---------------------------------------------------------------------------
api_router = APIRouter(prefix="/api")


@api_router.get("/health")
async def health() -> dict:
    return {"ok": True}


# Register /api routes BEFORE the catch-all so they are never shadowed.
app.include_router(api_router)

from routes.logs import router as logs_router
app.include_router(logs_router, prefix="/api")

from routes.settings import router as settings_router
app.include_router(settings_router, prefix="/api")

from routes.insights import router as insights_router
app.include_router(insights_router, prefix="/api")

from routes.skills import router as skills_router
app.include_router(skills_router, prefix="/api")

from routes.sessions import router as sessions_router
app.include_router(sessions_router, prefix="/api")

from routes.search import router as search_router
app.include_router(search_router, prefix="/api")

from routes.agents import router as agents_router
app.include_router(agents_router, prefix="/api")

from routes.overview import router as overview_router
app.include_router(overview_router, prefix="/api")

from routes.system import router as system_router
app.include_router(system_router, prefix="/api")

from routes.workspace import router as workspace_router
app.include_router(workspace_router, prefix="/api")

from routes.memory import router as memory_router
app.include_router(memory_router, prefix="/api")

from routes.chat import router as chat_router
app.include_router(chat_router, prefix="/api")

# upload route requires python-multipart; guard so a missing optional dep
# (peer task still in flight) can't crash app import for every other route.
try:
    from routes.upload import router as upload_router
    app.include_router(upload_router, prefix="/api")
except (ImportError, RuntimeError) as _upload_err:
    print(f"[server] upload route disabled: {_upload_err}")

from routes.kanban import router as kanban_router
app.include_router(kanban_router, prefix="/api")

from routes.media import router as media_router
app.include_router(media_router, prefix="/api")

from routes.cron import router as cron_router
app.include_router(cron_router, prefix="/api")

# ---------------------------------------------------------------------------
# SPA static file fallback
# Must be registered AFTER all /api routes.
# ---------------------------------------------------------------------------

@app.get("/{full_path:path}", include_in_schema=False, response_model=None)
async def spa_fallback(full_path: str) -> FileResponse | PlainTextResponse:
    index = DIST_DIR / "index.html"

    # Try to serve a real file from dist/ first (JS, CSS, assets, etc.)
    candidate = DIST_DIR / full_path
    if candidate.is_file():
        media_type, _ = mimetypes.guess_type(str(candidate))
        return FileResponse(candidate, media_type=media_type or "application/octet-stream")

    # Always fall back to index.html for client-side routing
    if index.is_file():
        return FileResponse(index, media_type="text/html")

    return PlainTextResponse(
        "Frontend not built yet — run: cd app && npm install && npm run build",
        status_code=503,
    )


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn  # imported locally so it doesn't execute on import

    uvicorn.run(app, host="0.0.0.0", port=8787)
