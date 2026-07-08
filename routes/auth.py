"""
Authentication routes for the Hermes Dashboard.

Session model (per-session tokens, server-side expiry):
  - login() mints a fresh random token per session and stores it server-side in
    _SESSIONS with an expiry timestamp (TTL below). Each client gets its own token.
  - logout() removes the token server-side AND clears the client cookie — a real
    logout, not just a cookie wipe.
  - check() and the auth_gate middleware validate via session_valid(), which also
    lazily evicts expired tokens.
  - Tokens live in process memory, so a restart invalidates all sessions (clients
    re-login). For persistence across restarts, back _SESSIONS with state.db.
"""

import asyncio
import secrets
import time
from pathlib import Path

import bcrypt
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

# ---------------------------------------------------------------------------
# Session store — per-session tokens with server-side expiry
# ---------------------------------------------------------------------------
SESSION_TTL_SECONDS: int = 7 * 24 * 3600  # 7 days
_SESSIONS: dict[str, float] = {}          # token -> expiry epoch seconds


def _new_session() -> str:
    """Mint a fresh session token and register it with a TTL."""
    token = secrets.token_hex(32)
    _SESSIONS[token] = time.time() + SESSION_TTL_SECONDS
    return token


def session_valid(token: str | None) -> bool:
    """True if the token is known and unexpired. Lazily evicts expired tokens."""
    if not token:
        return False
    expiry = _SESSIONS.get(token)
    if expiry is None:
        return False
    if time.time() > expiry:
        _SESSIONS.pop(token, None)
        return False
    return True


def _end_session(token: str | None) -> None:
    """Invalidate a token server-side (used by logout)."""
    if token:
        _SESSIONS.pop(token, None)


# ---------------------------------------------------------------------------
# Password hash — read from file at import time
# ---------------------------------------------------------------------------
# .dashboard_passwd_hash is intentionally NOT tracked in git (it's a secret).
# A fresh clone won't have it — fail loud with a setup hint rather than a bare
# FileNotFoundError deep in the import chain.
# The file contains a bcrypt hash ($2b$12$...). Generate with:
#   python3 -c "import bcrypt; open('.dashboard_passwd_hash','wb').write(
#       bcrypt.hashpw(b'yourpassword', bcrypt.gensalt(rounds=12)))"
_HASH_FILE = Path(__file__).resolve().parent.parent / ".dashboard_passwd_hash"
try:
    _PASSWORD_HASH: bytes = _HASH_FILE.read_bytes().strip()
except FileNotFoundError as e:
    raise RuntimeError(
        f"Password hash file not found at {_HASH_FILE}. This file is git-ignored; "
        "create it before starting the server:\n"
        "  python3 -c \"import bcrypt; open('.dashboard_passwd_hash','wb').write("
        "bcrypt.hashpw(b'yourpassword', bcrypt.gensalt(rounds=12)))\""
    ) from e

router = APIRouter()


@router.post("/auth/login")
async def login(request: Request) -> JSONResponse:
    body = await request.json()
    submitted = body.get("password", "")
    if not bcrypt.checkpw(submitted.encode(), _PASSWORD_HASH):
        await asyncio.sleep(0.5)
        return JSONResponse({"ok": False, "error": "Invalid password"}, status_code=401)

    response = JSONResponse({"ok": True})
    response.set_cookie(
        key="hd_session",
        value=_new_session(),
        httponly=True,
        samesite="strict",
        path="/",
    )
    return response


@router.post("/auth/logout")
async def logout(request: Request) -> JSONResponse:
    _end_session(request.cookies.get("hd_session"))
    response = JSONResponse({"ok": True})
    response.delete_cookie(key="hd_session", path="/")
    return response


@router.get("/auth/check")
async def check(request: Request) -> JSONResponse:
    if session_valid(request.cookies.get("hd_session")):
        return JSONResponse({"authenticated": True})
    return JSONResponse({"authenticated": False})
