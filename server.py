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
    "/api/hooks/notify",
    "/api/kanban/tasks",
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
# Sentry ASGI middleware — applied last so it wraps all other middleware
# ---------------------------------------------------------------------------
from sentry_sdk.integrations.asgi import SentryAsgiMiddleware

app = SentryAsgiMiddleware(app)

# ---------------------------------------------------------------------------
# Entrypoint — graceful port-conflict (EADDRINUSE / Errno 98) handling
# ---------------------------------------------------------------------------
#
# The dispatcher previously called uvicorn.run() directly, so a port collision
# surfaced as an unhandled OSError(Errno 98) that crashed the process and was
# reported to Sentry (HERMES-DISPATCHER-8). The logic below probes the target
# socket before handing off to uvicorn and, on conflict:
#   1. logs a clear warning naming the address and the PID/command holding it,
#   2. retries with exponential backoff (the holder may be a stale instance
#      that is still shutting down),
#   3. optionally falls back to the next free port in a configurable range,
#   4. exits with a helpful, actionable message if nothing works.
#
# All knobs are environment-driven so behaviour can be tuned without code edits:
#   HERMES_DISPATCHER_HOST           bind host           (default 0.0.0.0)
#   HERMES_DISPATCHER_PORT           primary port        (default 8787)
#   HERMES_DISPATCHER_BIND_RETRIES   retries per port    (default 5)
#   HERMES_DISPATCHER_BIND_BACKOFF   base backoff secs   (default 0.5)
#   HERMES_DISPATCHER_FALLBACK_PORTS comma list and/or "lo-hi" ranges
#                                    (default "" — disabled)


def _port_holder(host: str, port: int) -> str:
    """Best-effort identification of the process bound to host:port.

    Returns a human-readable "pid <N> (<cmd>)" string, or "" if it can't be
    determined (e.g. insufficient privileges). Never raises.
    """
    try:
        import psutil  # type: ignore

        for conn in psutil.net_connections(kind="inet"):
            if conn.laddr and conn.laddr.port == port and conn.status == psutil.CONN_LISTEN:
                pid = conn.pid
                if pid:
                    try:
                        return f"pid {pid} ({psutil.Process(pid).name()})"
                    except Exception:
                        return f"pid {pid}"
                return "pid unknown"
    except Exception:
        pass

    # Fallback: parse `ss -tlnp` output (Linux). Needs privileges to see PIDs.
    try:
        import re
        import subprocess

        out = subprocess.run(
            ["ss", "-tlnp"], capture_output=True, text=True, timeout=3
        ).stdout
        for line in out.splitlines():
            # Local address column ends with ":<port>"
            if f":{port} " in line or line.rstrip().endswith(f":{port}"):
                m = re.search(r'pid=(\d+)', line)
                cmd = re.search(r'\(\("([^"]+)"', line)
                if m:
                    name = f" ({cmd.group(1)})" if cmd else ""
                    return f"pid {m.group(1)}{name}"
    except Exception:
        pass
    return ""


def _can_bind(host: str, port: int) -> bool:
    """True if we can bind host:port right now (probe socket, then release)."""
    import socket

    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        # No SO_REUSEADDR: we want the probe to fail exactly when uvicorn would.
        probe.bind((host, port))
        return True
    except OSError:
        return False
    finally:
        probe.close()


def _parse_fallback_ports(spec: str) -> list[int]:
    """Parse "8788,8790,8800-8805" into an ordered, de-duplicated port list."""
    ports: list[int] = []
    for chunk in spec.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "-" in chunk:
            try:
                lo, hi = (int(x) for x in chunk.split("-", 1))
            except ValueError:
                continue
            ports.extend(range(lo, hi + 1))
        else:
            try:
                ports.append(int(chunk))
            except ValueError:
                continue
    seen: set[int] = set()
    return [p for p in ports if not (p in seen or seen.add(p))]


def _resolve_bind_port(host: str, primary: int, retries: int, backoff: float,
                       fallbacks: list[int], log) -> int | None:
    """Return a bindable port, or None if every candidate is taken."""
    import time

    candidates = [primary] + [p for p in fallbacks if p != primary]
    for idx, port in enumerate(candidates):
        for attempt in range(1, retries + 1):
            if _can_bind(host, port):
                if port != primary:
                    log.warning(
                        "Dispatcher binding to FALLBACK port %s (primary %s was busy)",
                        port, primary,
                    )
                return port
            holder = _port_holder(host, port)
            holder_msg = f" — held by {holder}" if holder else ""
            if attempt < retries:
                delay = round(backoff * (2 ** (attempt - 1)), 2)
                log.warning(
                    "Port %s:%s already in use%s — retry %s/%s in %ss",
                    host, port, holder_msg, attempt, retries, delay,
                )
                time.sleep(delay)
            else:
                log.error(
                    "Port %s:%s still in use after %s attempts%s",
                    host, port, retries, holder_msg,
                )
        # exhausted retries for this candidate; try next fallback (if any)
        if idx < len(candidates) - 1:
            log.warning("Trying next fallback port after %s", port)
    return None


def _assert_port_free(host: str, port: int) -> None:
    """Raise SystemExit(1) with an actionable message if host:port is taken.

    This is the core of the pre-flight: a single probe via ``_can_bind``,
    then — on conflict — a clear, remediation-rich error and a non-zero exit
    so uvicorn never attempts its own bind. Pulled out of
    ``_preflight_port_check`` (which only adds the env/opt-out gating) so it
    can be unit-tested directly without tripping the import-time guards.
    """
    import logging

    if _can_bind(host, port):
        return

    log = logging.getLogger("hermes.dispatcher")
    holder = _port_holder(host, port)
    holder_hint = f" The port is held by {holder}." if holder else ""
    log.error(
        "Hermes Dispatcher pre-flight check FAILED: %s:%s is already in "
        "use.%s\n"
        "Refusing to start (this avoids the unhandled Errno 98 bind crash, "
        "Sentry HERMES-DISPATCHER-8).\n"
        "To fix, either:\n"
        "  1. Stop the conflicting process — find it with "
        "`ss -tlnp | grep %s` and kill the listed PID "
        "(e.g. `kill <PID>`); or\n"
        "  2. Run the dispatcher on a different port by setting "
        "HERMES_DISPATCHER_PORT=<free-port> (and updating the bind port "
        "uvicorn is launched with), then restart.",
        host, port, holder_hint, port,
    )
    raise SystemExit(1)


def _preflight_port_check() -> None:
    """Fail fast at import time if the dispatcher's bind port is already taken.

    WHY THIS RUNS AT IMPORT (not under ``if __name__ == '__main__'``):
    production launches via ``python server.py`` (see ``start-server.sh``),
    which DOES execute the ``__main__`` block. However, the systemd unit
    ``hermes-dashboard.service`` uses ``uvicorn server:app`` directly, which
    imports this module without reaching ``__main__``. Running the check at
    import time means it fires on both launch paths. A port collision
    therefore surfaced as an unhandled OSError(Errno 98) from deep inside
    uvicorn and was reported to Sentry (HERMES-DISPATCHER-8). Probing here,
    before uvicorn ever calls bind(), lets us exit early with an actionable
    message instead.

    Behaviour:
      • Reads the same env knobs as the ``__main__`` path
        (HERMES_DISPATCHER_HOST / HERMES_DISPATCHER_PORT).
      • If the port is bindable → returns silently; uvicorn proceeds.
      • If the port is taken → delegates to ``_assert_port_free`` which logs a
        clear error naming the address and the PID/command holding it, then
        raises SystemExit(1) so uvicorn never attempts its own bind.

    Opt-out (so importing this module in tests / tooling can't abort the
    process or false-positive on a port that's legitimately in use):
      • HERMES_DISPATCHER_SKIP_PREFLIGHT truthy, or
      • running under pytest (PYTEST_CURRENT_TEST set / pytest imported).

    There is a small TOCTOU window between this probe and uvicorn's real
    bind (the probe binds with no SO_REUSEADDR, then releases). That is an
    accepted trade-off: it converts the overwhelmingly common "stale/duplicate
    instance already listening" case into a clean early exit. A genuine race
    against a *simultaneously* starting process still falls through to
    uvicorn's own OSError, which is no worse than today.
    """
    import sys

    skip = os.environ.get("HERMES_DISPATCHER_SKIP_PREFLIGHT", "").strip().lower()
    if skip in {"1", "true", "yes", "on"}:
        return
    # Don't abort a test process that merely imports this module.
    if os.environ.get("PYTEST_CURRENT_TEST") or "pytest" in sys.modules:
        return

    host = os.environ.get("HERMES_DISPATCHER_HOST", "0.0.0.0")
    try:
        port = int(os.environ.get("HERMES_DISPATCHER_PORT", "8787"))
    except ValueError:
        # Malformed override — let uvicorn surface its own error downstream.
        return

    _assert_port_free(host, port)


# Run the pre-flight as a side effect of importing this module, so it guards
# the production ``uvicorn server:app`` entrypoint (which never reaches the
# ``__main__`` block below). Guarded internally for test/import safety.
_preflight_port_check()


if __name__ == "__main__":
    import logging
    import sys

    import uvicorn  # imported locally so it doesn't execute on import

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    log = logging.getLogger("hermes.dispatcher")

    host = os.environ.get("HERMES_DISPATCHER_HOST", "0.0.0.0")
    port = int(os.environ.get("HERMES_DISPATCHER_PORT", "8787"))
    retries = max(1, int(os.environ.get("HERMES_DISPATCHER_BIND_RETRIES", "5")))
    backoff = max(0.0, float(os.environ.get("HERMES_DISPATCHER_BIND_BACKOFF", "0.5")))
    fallbacks = _parse_fallback_ports(os.environ.get("HERMES_DISPATCHER_FALLBACK_PORTS", ""))

    chosen = _resolve_bind_port(host, port, retries, backoff, fallbacks, log)
    if chosen is None:
        holder = _port_holder(host, port)
        holder_hint = f" Conflicting listener: {holder}." if holder else ""
        log.error(
            "Could not bind the Hermes Dispatcher to %s:%s (or any configured "
            "fallback).%s Free the port (e.g. `ss -tlnp | grep %s`, then stop "
            "the listed PID) or set HERMES_DISPATCHER_PORT / "
            "HERMES_DISPATCHER_FALLBACK_PORTS to an open port, and restart.",
            host, port, holder_hint, port,
        )
        sys.exit(1)

    log.info("Hermes Dispatcher starting on %s:%s", host, chosen)
    uvicorn.run(app, host=host, port=chosen)
