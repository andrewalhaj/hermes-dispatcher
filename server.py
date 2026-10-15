import sentry_sdk

sentry_sdk.init(
    dsn="https://b8b278611e630a0baad50e7b7ce8c340@o4511599662399488.ingest.us.sentry.io/4511622655901696",
    environment="production",
    traces_sample_rate=0.1,
)

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
import asyncio as _asyncio
import logging as _logging
import mimetypes
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.routing import APIRouter

# ---------------------------------------------------------------------------
# Logging — configured at IMPORT time so it applies under the production
# ``uvicorn server:app`` entrypoint (which never runs the ``__main__`` block
# below, where basicConfig used to live). Without a root handler here, every
# ``routes.*`` logger.info/.warning/.error call was silently dropped — which is
# exactly why the Sentry→Linear leg could fail invisibly. Attach a StreamHandler
# to the root logger so all module loggers propagate to stdout → journald.
# Level is INFO by default; override with HERMES_DISPATCHER_LOG_LEVEL.
_log_level = os.environ.get("HERMES_DISPATCHER_LOG_LEVEL", "INFO").upper()
if not _logging.getLogger().handlers:
    _logging.basicConfig(
        level=getattr(_logging, _log_level, _logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
else:
    _logging.getLogger().setLevel(getattr(_logging, _log_level, _logging.INFO))

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
HERMES_HOME: str = os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes"))
KANBAN_DB: Path = Path(HERMES_HOME) / "kanban.db"
STATE_DB: Path = Path(HERMES_HOME) / "state.db"

APP_DIR: Path = Path(__file__).resolve().parent
DIST_DIR: Path = APP_DIR / "app" / "dist"

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    global _linear_sync_task, _reverse_sync_task
    try:
        from routes.linear_sync import run_outbound_poller
        _linear_sync_stop.clear()
        _linear_sync_task = _asyncio.create_task(
            run_outbound_poller(_linear_sync_stop)
        )
        print("[server] linear↔kanban outbound comment poller started")
    except Exception as _exc:  # never block startup on the poller
        print(f"[server] linear sync poller failed to start: {_exc}")

    # Reverse sync: Kanban card done → close linked Linear issue. Catches the
    # worker `kanban_complete` path, which writes status='done' straight into
    # kanban.db and fires no webhook. Polls the SQLite DB (kanban has no
    # outbound webhook) and closes each linked issue exactly once.
    try:
        from routes.kanban_linear_poller import run_reverse_sync_poller
        _reverse_sync_stop.clear()
        _reverse_sync_task = _asyncio.create_task(
            run_reverse_sync_poller(_reverse_sync_stop)
        )
        print("[server] kanban→linear reverse-sync poller started")
    except Exception as _exc:  # never block startup on the poller
        print(f"[server] reverse-sync poller failed to start: {_exc}")

    yield

    _linear_sync_stop.set()
    if _linear_sync_task is not None:
        try:
            await _asyncio.wait_for(_linear_sync_task, timeout=5)
        except Exception:
            _linear_sync_task.cancel()

    _reverse_sync_stop.set()
    if _reverse_sync_task is not None:
        try:
            await _asyncio.wait_for(_reverse_sync_task, timeout=5)
        except Exception:
            _reverse_sync_task.cancel()


app = FastAPI(title="Hermes Dispatcher", version="0.1.0", lifespan=lifespan)

# CORS allowlist. Defaults cover the known deployment origins (Cloudflare Tunnel
# public URL + Tailscale MagicDNS/IP + localhost). Override at deploy time via the
# DASHBOARD_CORS_ORIGINS env var (comma-separated). allow_credentials=True is
# required for the cookie-authed API and is INVALID with a "*" wildcard — so the
# allowlist must be explicit (this also fixes the prior wildcard+credentials bug,
# where cross-origin cookies silently failed and only same-origin requests worked).
_DEFAULT_CORS_ORIGINS = ",".join([
    "http://localhost:8787",
    "http://127.0.0.1:8787",
])
_cors_origins = [
    o.strip()
    for o in os.environ.get("DASHBOARD_CORS_ORIGINS", _DEFAULT_CORS_ORIGINS).split(",")
    if o.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Auth middleware
# ---------------------------------------------------------------------------
_AUTH_PREFIX = "/api/auth/"
_AUTH_EXEMPT = {
    _AUTH_PREFIX + "login",
    _AUTH_PREFIX + "logout",
    _AUTH_PREFIX + "check",
    "/api/health",
    "/api/hooks/knowledge",
    "/api/hooks/figma",
    "/api/hooks/github",
    "/api/hooks/sentry",
    "/api/hooks/linear",
    "/api/hooks/kanban",
    "/api/hooks/notion",
    "/api/hooks/notion/sync",
    # /api/hooks/notify removed — use send_telegram() directly; finding #3
    # /api/kanban/tasks removed — dashboard sends cookie; kanban routes require
    # the session cookie; there is no bearer check on kanban routes.
    "/",
    "/index.html",
    "/favicon.ico",
}

@app.middleware("http")
async def auth_gate(request: Request, call_next):
    from routes.auth import session_valid  # imported late to avoid circular import
    path = request.url.path

    # Exempt paths
    if path in _AUTH_EXEMPT or path.startswith("/assets/"):
        return await call_next(request)

    if session_valid(request.cookies.get("hd_session")):
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

from routes.swarm import router as swarm_router
app.include_router(swarm_router, prefix="/api")

from routes.overview import router as overview_router
app.include_router(overview_router, prefix="/api")

from routes.system import router as system_router
app.include_router(system_router, prefix="/api")

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

from routes.sentry import router as sentry_router
app.include_router(sentry_router, prefix="/api")

from routes.linear_reports import router as linear_reports_router
app.include_router(linear_reports_router, prefix="/api")

from routes.hooks import router as hooks_router
app.include_router(hooks_router, prefix="/api")

from routes.notify import router as notify_router
app.include_router(notify_router, prefix="/api")

from routes.linear import router as linear_router
app.include_router(linear_router, prefix="/api")

# ---------------------------------------------------------------------------
# Background: Linear ↔ Kanban outbound comment sync poller
# Pushes new Kanban card comments to their linked Linear issues. Inbound
# (Linear → Kanban) is webhook-driven in routes/hooks.py; this is the other
# half. Single uvicorn worker → exactly one poller, no duplication.
# ---------------------------------------------------------------------------
import asyncio as _asyncio

_linear_sync_stop = _asyncio.Event()
_linear_sync_task: "_asyncio.Task | None" = None

# Reverse-sync poller (Kanban card done → close linked Linear issue) lifecycle.
_reverse_sync_stop = _asyncio.Event()
_reverse_sync_task: "_asyncio.Task | None" = None


from routes.linear_triage import router as linear_triage_router
app.include_router(linear_triage_router, prefix="/api")

# ---------------------------------------------------------------------------
# SPA static file fallback
# Must be registered AFTER all /api routes.
# ---------------------------------------------------------------------------

@app.get("/{full_path:path}", include_in_schema=False, response_model=None)
async def spa_fallback(full_path: str) -> FileResponse | PlainTextResponse:
    index = DIST_DIR / "index.html"

    # Try to serve a real file from dist/ first (JS, CSS, assets, etc.)
    # resolve() blocks path traversal (finding #1): anything escaping DIST_DIR → index.html.
    _dist_real = DIST_DIR.resolve()
    candidate = (DIST_DIR / full_path).resolve()
    if candidate.is_relative_to(_dist_real) and candidate.is_file():
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
# Sentry ASGI middleware — applied last so it wraps all other middleware
# ---------------------------------------------------------------------------
from sentry_sdk.integrations.asgi import SentryAsgiMiddleware

app = SentryAsgiMiddleware(app)

# ---------------------------------------------------------------------------
# Entrypoint — bind the configured port and start uvicorn.
# Tunables (environment variables):
#   HERMES_DISPATCHER_HOST   bind host  (default 0.0.0.0)
#   HERMES_DISPATCHER_PORT   bind port  (default 8787)
# If the port is already in use uvicorn surfaces the OSError and exits — no
# silent fallback, no import-time sys.exit.
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn  # imported locally so it doesn't execute on import

    host = os.environ.get("HERMES_DISPATCHER_HOST", "0.0.0.0")
    port = int(os.environ.get("HERMES_DISPATCHER_PORT", "8787"))
    uvicorn.run(app, host=host, port=port)
