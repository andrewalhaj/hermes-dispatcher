# Mount with: app.include_router(router, prefix="/api")
import asyncio
import json
import os
import re
import sqlite3
from datetime import datetime
from pathlib import Path

import yaml
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

router = APIRouter()

_ACTIVE: dict[str, asyncio.subprocess.Process] = {}

_HERMES_BIN_PATH = os.path.expanduser("~/.local/bin/hermes")
HERMES_BIN = _HERMES_BIN_PATH if Path(_HERMES_BIN_PATH).exists() else "hermes"

# Linear team that Dashboard-Chat-created issues land in. Same team UUID the
# Linear webhook auto-routes from (routes/hooks.py).
LINEAR_API_KEY = os.environ.get("LINEAR_API_KEY", "")
LINEAR_TEAM_ID = "38a0c106-e9a8-4f65-84d2-ec8bdc61855d"


def _hermes_home() -> str:
    return os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes"))


class SendRequest(BaseModel):
    session_id: str
    message: str
    profile: str = "default"
    model: str = ""


class CancelRequest(BaseModel):
    session_id: str


class LinearCreateRequest(BaseModel):
    # Raw argument string after "/linear create", e.g.
    #   "Fix auth token expiration p:1 d:happens after 24h"
    text: str


# --- TG bridge: dashboard→telegram inject ---
# Andrew's Telegram user_id == DM chat_id. The gateway inject endpoint forges a
# real user MessageEvent for this DM and runs it through the live agent, so the
# reply lands on Telegram AND is written to state.db (which we poll below).
_INJECT_URL = "http://127.0.0.1:8643/inject"
_TG_CHAT_ID = "8878729385"
_POLL_INTERVAL = 1.0   # seconds between state.db polls
_POLL_TIMEOUT = 120.0  # max seconds to wait for the assistant reply


def _latest_telegram_session_id(conn: sqlite3.Connection):
    """Return the id of the most recently started, non-archived telegram session."""
    row = conn.execute(
        "SELECT id FROM sessions WHERE source = 'telegram' AND archived = 0"
        " ORDER BY started_at DESC LIMIT 1"
    ).fetchone()
    return row[0] if row else None


def _latest_assistant_row(conn: sqlite3.Connection, session_id: str):
    """Return (id, content) of the newest active assistant message with non-empty text.

    Skips empty-content rows (tool-call / streaming intermediate rows) which
    always have a higher id than the actual text reply and would cause the
    content-check to stall the poll indefinitely.
    """
    row = conn.execute(
        "SELECT id, content FROM messages"
        " WHERE session_id = ? AND role = 'assistant' AND active = 1"
        " AND content IS NOT NULL AND content != ''"
        " ORDER BY id DESC LIMIT 1",
        (session_id,),
    ).fetchone()
    return (row[0], row[1]) if row else None


@router.post("/chat/send")
async def chat_send(req: SendRequest):
    async def generate():
        db_path = Path(_hermes_home()) / "state.db"

        # Tell the client we've accepted the message and are working.
        yield f"data: {json.dumps({'type': 'thinking'})}\n\n"

        # 1) Snapshot the active telegram session + last assistant id BEFORE
        #    injecting, so we know which reply is new.
        session_id = None
        baseline_id = -1
        try:
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, check_same_thread=False)
            session_id = _latest_telegram_session_id(conn)
            if session_id:
                last = _latest_assistant_row(conn, session_id)
                baseline_id = last[0] if last else -1
            conn.close()
        except Exception:
            session_id = None

        # 2) POST the message to the gateway inject endpoint. aiohttp is present
        #    in the dashboard venv (used by the /chat/linear route); use it for a
        #    non-blocking async POST.
        try:
            import aiohttp
            async with aiohttp.ClientSession() as http:
                resp = await http.post(
                    _INJECT_URL,
                    json={
                        "message": req.message,
                        "chat_id": _TG_CHAT_ID,
                        "user_id": _TG_CHAT_ID,
                    },
                    timeout=aiohttp.ClientTimeout(total=15),
                )
                inj = await resp.json()
            if not inj.get("ok", False):
                yield f"data: {json.dumps({'type': 'error', 'text': inj.get('error', 'inject failed')})}\n\n"
                return
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'text': f'gateway inject failed: {exc}'})}\n\n"
            return

        # 3) Poll state.db for a NEW assistant row (id > baseline). Stream a
        #    keepalive comment each tick so the SSE connection stays alive.
        waited = 0.0
        last_content = ""
        while waited < _POLL_TIMEOUT:
            await asyncio.sleep(_POLL_INTERVAL)
            waited += _POLL_INTERVAL
            yield ": keepalive\n\n"

            try:
                conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, check_same_thread=False)
                # Re-resolve the session each tick: a brand-new telegram session
                # may have been created by the inject if none existed before.
                sid = session_id or _latest_telegram_session_id(conn)
                row = _latest_assistant_row(conn, sid) if sid else None
                conn.close()
            except Exception:
                row = None

            if row and row[0] > baseline_id and row[1]:
                last_content = row[1]
                break

        if last_content:
            yield f"data: {json.dumps({'type': 'delta', 'text': last_content})}\n\n"
            yield f"data: {json.dumps({'type': 'done', 'text': ''})}\n\n"
        else:
            yield f"data: {json.dumps({'type': 'error', 'text': 'timed out waiting for reply'})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/chat/cancel")
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


def _parse_linear_args(text: str) -> dict:
    """Parse '/linear create' argument string.

    Supports trailing flags ``p:<priority>`` (0-4 or urgent/high/medium/low/none)
    and ``d:<description>``. Everything not consumed by a flag becomes the title.

    Example: "Fix auth token expiration p:1 d:happens after 24h"
      -> {title: "Fix auth token expiration", priority: 1, description: "happens after 24h"}
    """
    priority = None
    description = None

    # Linear-native priority scale: 1=Urgent, 2=High, 3=Medium, 4=Low, 0=None.
    # Must match routes/linear_triage.py and the /linear create p:<n> help text
    # (p:1 == Urgent), otherwise word flags would set the wrong Linear priority.
    pri_words = {"urgent": 1, "high": 2, "medium": 3, "low": 4, "none": 0}

    # d:<...> runs to end of string (descriptions can contain spaces). Pull it
    # out first so its contents don't get scanned for a p: flag.
    dmatch = re.search(r"\bd:(.+)$", text)
    if dmatch:
        description = dmatch.group(1).strip()
        text = text[: dmatch.start()].rstrip()

    def _take_priority(m):
        nonlocal priority
        raw = m.group(1).lower()
        if raw.isdigit():
            priority = max(0, min(4, int(raw)))
        elif raw in pri_words:
            priority = pri_words[raw]
        return ""

    text = re.sub(r"\bp:(\S+)", _take_priority, text)

    title = re.sub(r"\s+", " ", text).strip()
    return {"title": title, "priority": priority, "description": description}


@router.post("/chat/linear")
async def chat_linear_create(req: LinearCreateRequest):
    """Create a Linear issue from Dashboard Chat (`/linear create ...`).

    Calls Linear's ``issueCreate`` mutation. The existing Linear webhook
    (routes/hooks.py) auto-creates + dispatches a Kanban card for new issues,
    so after creating we briefly poll the Kanban DB to learn which coder the
    card was routed to, then return a confirmation string for the Chat panel.
    """
    if not LINEAR_API_KEY:
        return {"ok": False, "error": "LINEAR_API_KEY not configured on the server."}

    parsed = _parse_linear_args(req.text or "")
    title = parsed["title"]
    if not title:
        return {"ok": False, "error": "Usage: /linear create <title> [p:<0-4>] [d:<description>]"}

    variables_input = {"teamId": LINEAR_TEAM_ID, "title": title}
    if parsed["priority"] is not None:
        variables_input["priority"] = parsed["priority"]
    if parsed["description"]:
        variables_input["description"] = parsed["description"]

    mutation = """
    mutation($input: IssueCreateInput!) {
      issueCreate(input: $input) {
        success
        issue { id identifier title url }
      }
    }
    """

    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            resp = await session.post(
                "https://api.linear.app/graphql",
                headers={
                    "Authorization": LINEAR_API_KEY,
                    "Content-Type": "application/json",
                },
                json={"query": mutation, "variables": {"input": variables_input}},
                timeout=aiohttp.ClientTimeout(total=15),
            )
            result = await resp.json()
    except Exception as exc:
        return {"ok": False, "error": f"Linear API request failed: {exc}"}

    if result.get("errors"):
        msg = "; ".join(e.get("message", "") for e in result["errors"]) or "unknown error"
        return {"ok": False, "error": f"Linear rejected the issue: {msg}"}

    payload = (result.get("data") or {}).get("issueCreate") or {}
    if not payload.get("success") or not payload.get("issue"):
        return {"ok": False, "error": "Linear did not return a created issue."}

    issue = payload["issue"]
    identifier = issue.get("identifier", "")
    url = issue.get("url", "")
    issue_id = issue.get("id", "")

    # The Linear webhook creates the Kanban card asynchronously (idempotency key
    # = linear-<issue_id>). Poll the DB briefly to learn the assigned coder.
    assignee = None
    db_path = os.environ.get("KANBAN_DB", os.path.expanduser("~/.hermes/kanban.db"))
    idempotency_key = f"linear-{issue_id}" if issue_id else ""
    if idempotency_key:
        for _ in range(20):  # up to ~6s
            await asyncio.sleep(0.3)
            try:
                conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
                row = conn.execute(
                    "SELECT assignee FROM tasks WHERE idempotency_key = ? "
                    "ORDER BY created_at DESC LIMIT 1",
                    (idempotency_key,),
                ).fetchone()
                conn.close()
            except Exception:
                row = None
            if row and row[0]:
                assignee = row[0]
                break

    if assignee:
        confirm = f"{identifier} created \u2192 dispatched to {assignee}"
    else:
        # Webhook may not have fired yet (e.g. webhook not configured); still a success.
        confirm = f"{identifier} created"

    return {
        "ok": True,
        "identifier": identifier,
        "url": url,
        "assignee": assignee,
        "confirm": confirm,
    }


@router.get("/chat/sessions")
async def chat_sessions():
    db_path = Path(_hermes_home()) / "state.db"
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, check_same_thread=False)
        cur = conn.cursor()
        cur.execute(
            "SELECT s.id, s.title, s.started_at, MAX(m.timestamp) as last_msg"
            " FROM sessions s"
            " LEFT JOIN messages m ON m.session_id = s.id"
            " WHERE s.archived = 0 AND s.source = 'telegram'"
            " GROUP BY s.id"
            " ORDER BY COALESCE(MAX(m.timestamp), s.started_at) DESC LIMIT 20"
        )
        rows = cur.fetchall()
        conn.close()
        return [
            {"id": r[0], "title": r[1] or "Untitled session", "created_at": r[3] or r[2]}
            for r in rows
        ]
    except Exception:
        return []


@router.get("/chat/sessions/{session_id}/messages")
async def chat_session_messages(session_id: str):
    db_path = Path(_hermes_home()) / "state.db"
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        cur = conn.cursor()
        cur.execute(
            "SELECT id, role, content, timestamp FROM messages"
            " WHERE session_id = ? AND role IN ('user', 'assistant')"
            " ORDER BY timestamp ASC",
            (session_id,),
        )
        rows = cur.fetchall()
        conn.close()
        result = []
        for msg_id, role, content, ts in rows:
            try:
                at = datetime.fromtimestamp(float(ts)).strftime("%H:%M")
            except Exception:
                at = "--:--"
            result.append({
                "id": msg_id,
                "role": "agent" if role == "assistant" else "user",
                "text": content or "",
                "at": at,
            })
        return result
    except Exception:
        return []


@router.get("/profiles")
async def list_profiles():
    profiles_dir = Path(_hermes_home()) / "profiles"
    try:
        dirs = sorted(p.name for p in profiles_dir.iterdir() if p.is_dir())
        if "default" in dirs:
            dirs.remove("default")
        return ["default"] + dirs
    except Exception:
        return ["default"]


@router.get("/models")
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
