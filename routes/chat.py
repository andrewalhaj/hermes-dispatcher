# Mount with: app.include_router(chat_router)
import asyncio
import json
import os
import sqlite3
from pathlib import Path

import yaml
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

chat_router = APIRouter()

_ACTIVE: dict[str, asyncio.subprocess.Process] = {}

_HERMES_BIN_PATH = "/root/.local/bin/hermes"
HERMES_BIN = _HERMES_BIN_PATH if Path(_HERMES_BIN_PATH).exists() else "hermes"


def _hermes_home() -> str:
    return os.environ.get("HERMES_HOME", "/root/.hermes")


class SendRequest(BaseModel):
    session_id: str
    message: str
    profile: str = "default"
    model: str = ""


class CancelRequest(BaseModel):
    session_id: str


@chat_router.post("/api/chat/send")
async def chat_send(req: SendRequest):
    async def generate():
        cmd = [HERMES_BIN, "-Q", "-q", req.message, "--source", "webui"]
        if req.profile and req.profile not in ("default", ""):
            cmd += ["--profile", req.profile]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _ACTIVE[req.session_id] = proc

            while True:
                line = await proc.stdout.readline()
                if not line:
                    break
                text = line.decode("utf-8", errors="replace").rstrip("\n")
                if text:
                    yield f"data: {json.dumps({'type': 'delta', 'text': text})}\n\n"

            await proc.wait()
            _ACTIVE.pop(req.session_id, None)
            yield f"data: {json.dumps({'type': 'done', 'text': ''})}\n\n"

        except Exception as exc:
            _ACTIVE.pop(req.session_id, None)
            yield f"data: {json.dumps({'type': 'error', 'text': str(exc)})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@chat_router.post("/api/chat/cancel")
async def chat_cancel(req: CancelRequest):
    proc = _ACTIVE.get(req.session_id)
    if proc:
        try:
            proc.kill()
        except ProcessLookupError:
            pass
        _ACTIVE.pop(req.session_id, None)
        return {"ok": True, "cancelled": True}
    return {"ok": True, "cancelled": False}


@chat_router.get("/api/chat/sessions")
async def chat_sessions():
    db_path = Path(_hermes_home()) / "state.db"
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        cur = conn.cursor()
        cur.execute(
            "SELECT id, title, started_at FROM sessions"
            " WHERE archived = 0 ORDER BY started_at DESC LIMIT 20"
        )
        rows = cur.fetchall()
        conn.close()
        return [
            {"id": r[0], "title": r[1] or "Untitled session", "created_at": r[2]}
            for r in rows
        ]
    except Exception:
        return []


@chat_router.get("/api/profiles")
async def list_profiles():
    profiles_dir = Path(_hermes_home()) / "profiles"
    try:
        dirs = sorted(p.name for p in profiles_dir.iterdir() if p.is_dir())
        if "default" in dirs:
            dirs.remove("default")
        return ["default"] + dirs
    except Exception:
        return ["default"]


@chat_router.get("/api/models")
async def list_models():
    config_path = Path(_hermes_home()) / "config.yaml"
    static_catalog = ["claude-sonnet-4-6", "claude-opus-4-8", "claude-haiku-4"]
    try:
        with open(config_path) as f:
            config = yaml.safe_load(f)
        default_model = config.get("model", {}).get("default", "claude-sonnet-4-6")
        catalog = list(config.get("model", {}).get("catalog", static_catalog))
        if default_model not in catalog:
            catalog.insert(0, default_model)
        return {"default": default_model, "catalog": catalog}
    except Exception:
        return {"default": "claude-sonnet-4-6", "catalog": static_catalog}
