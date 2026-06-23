"""
Authentication routes for the Hermes Dashboard.
SESSION_TOKEN is generated once at startup — ephemeral by design.
"""

import asyncio
import hashlib
import secrets
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

# ---------------------------------------------------------------------------
# Session token — generated once per process lifetime
# ---------------------------------------------------------------------------
SESSION_TOKEN: str = secrets.token_hex(32)

# ---------------------------------------------------------------------------
# Password hash — read from file at import time
# ---------------------------------------------------------------------------
_HASH_FILE = Path(__file__).resolve().parent.parent / ".dashboard_passwd_hash"
_PASSWORD_HASH: str = _HASH_FILE.read_text().strip()

router = APIRouter()


@router.post("/auth/login")
async def login(request: Request) -> JSONResponse:
    body = await request.json()
    submitted = body.get("password", "")
    hashed = hashlib.sha256(submitted.encode()).hexdigest()

    if hashed != _PASSWORD_HASH:
        await asyncio.sleep(0.5)
        return JSONResponse({"ok": False, "error": "Invalid password"}, status_code=401)

    response = JSONResponse({"ok": True})
    response.set_cookie(
        key="hd_session",
        value=SESSION_TOKEN,
        httponly=True,
        samesite="strict",
        path="/",
    )
    return response


@router.post("/auth/logout")
async def logout() -> JSONResponse:
    response = JSONResponse({"ok": True})
    response.delete_cookie(key="hd_session", path="/")
    return response


@router.get("/auth/check")
async def check(request: Request) -> JSONResponse:
    cookie = request.cookies.get("hd_session")
    if cookie and cookie == SESSION_TOKEN:
        return JSONResponse({"authenticated": True})
    return JSONResponse({"authenticated": False})
