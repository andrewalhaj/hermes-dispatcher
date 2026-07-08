import asyncio
import json
import os
import re
import sqlite3
import time
import uuid
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

DB_PATH = os.environ.get("KANBAN_DB", os.path.expanduser("~/.hermes/kanban.db"))

LINEAR_API_KEY = os.environ.get("LINEAR_API_KEY", "")
LINEAR_API_URL = "https://api.linear.app/graphql"

# Matches a Linear issue URL and captures the human identifier (e.g. ENG-123).
# Linear URLs look like: https://linear.app/<workspace>/issue/<IDENTIFIER>/<slug>
_LINEAR_URL_RE = re.compile(
    r"https?://linear\.app/[^/\s]+/issue/([A-Za-z0-9]+-\d+)", re.IGNORECASE
)

VALID_STATUSES = {"triage", "todo", "ready", "running", "blocked", "done"}

router = APIRouter(prefix="/kanban")


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB_PATH, check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c


def _blocked_reasons(conn: sqlite3.Connection) -> dict:
    """Return mapping of task_id -> latest blocked-event reason string."""
    cur = conn.execute(
        "SELECT task_id, payload FROM task_events WHERE kind='blocked' ORDER BY created_at ASC"
    )
    reasons: dict = {}
    for row in cur.fetchall():
        try:
            payload = json.loads(row["payload"] or "")
            reasons[row["task_id"]] = payload.get("reason", "")
        except Exception:
            pass
    return reasons


def _row_to_task(row: sqlite3.Row, block_reason: str = "") -> dict:
    now = int(time.time())
    started_at = row["started_at"]
    created_at = row["created_at"]

    if started_at is not None:
        age_sec = max(0, now - int(started_at))
    elif created_at is not None:
        age_sec = max(0, now - int(created_at))
    else:
        age_sec = 0

    raw_skills = row["skills"]
    if raw_skills:
        try:
            skills = json.loads(raw_skills)
            if not isinstance(skills, list):
                skills = []
        except Exception:
            skills = []
    else:
        skills = []

    tenant = row["tenant"] if row["tenant"] is not None else "internal"

    return {
        "id": row["id"],
        "title": row["title"] or "",
        "priority": int(row["priority"]) if row["priority"] is not None else 0,
        "ageSec": age_sec,
        "status": row["status"],
        "tenant": tenant,
        "assignee": row["assignee"],
        "skills": skills,
        "branch": row["branch_name"] or "",
        "desc": row["body"] or "",
        "blockReason": block_reason,
    }


def _fetch_tasks(conn: sqlite3.Connection) -> list[dict]:
    reasons = _blocked_reasons(conn)
    cur = conn.execute(
        "SELECT * FROM tasks WHERE status != 'archived' ORDER BY created_at DESC"
    )
    return [_row_to_task(r, reasons.get(r["id"], "")) for r in cur.fetchall()]


def _signature(conn: sqlite3.Connection) -> int:
    cur = conn.execute(
        """
        SELECT COUNT(*) as cnt,
               MAX(COALESCE(last_heartbeat_at, completed_at, started_at, created_at, 0)) as mx
        FROM tasks WHERE status != 'archived'
        """
    )
    row = cur.fetchone()
    return (row["cnt"] or 0) + (row["mx"] or 0)


@router.get("/tasks")
def get_tasks():
    with _conn() as conn:
        return _fetch_tasks(conn)


class StatusBody(BaseModel):
    status: str


@router.patch("/tasks/{task_id}")
def patch_task(task_id: str, body: StatusBody):
    if body.status == "running":
        raise HTTPException(status_code=409, detail="running is dispatcher-owned")
    if body.status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"invalid status: {body.status!r}")

    with _conn() as conn:
        cur = conn.execute("SELECT status FROM tasks WHERE id = ?", (task_id,))
        prev = cur.fetchone()
        if prev is None:
            raise HTTPException(status_code=404, detail="task not found")
        prev_status = prev["status"]
        conn.execute(
            "UPDATE tasks SET status = ? WHERE id = ?", (body.status, task_id)
        )
        conn.commit()
        cur2 = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
        task = _row_to_task(cur2.fetchone())

    # On a fresh transition into `done`, auto-close the originating Linear
    # issue (if this card carries a Linear reference). Fire-and-forget: the
    # autoclose orchestrator never raises and logs its own failures, so a
    # Linear hiccup can never break the status update the user just made.
    if body.status == "done" and prev_status != "done":
        try:
            from routes.linear_autoclose import autoclose_for_card
            result = autoclose_for_card(task_id)
            if result.get("status") not in ("ok", "skipped"):
                import logging
                logging.getLogger(__name__).warning(
                    "linear autoclose for %s returned: %s", task_id, result
                )
        except Exception as exc:  # noqa: BLE001 — never break the PATCH
            import logging
            logging.getLogger(__name__).warning(
                "linear autoclose dispatch failed for %s: %s", task_id, exc
            )

        # Sentry sibling: if the card carries a Sentry issue reference, resolve
        # the Sentry issue too. Independent of the Linear close above and
        # likewise fire-and-forget — a bad token or network blip is logged but
        # can never break the status update the user just made.
        try:
            from routes.sentry_autoclose import autoclose_sentry_for_card
            s_result = autoclose_sentry_for_card(task_id)
            if s_result.get("status") not in ("ok", "skipped"):
                import logging
                logging.getLogger(__name__).warning(
                    "sentry autoclose for %s returned: %s", task_id, s_result
                )
        except Exception as exc:  # noqa: BLE001 — never break the PATCH
            import logging
            logging.getLogger(__name__).warning(
                "sentry autoclose dispatch failed for %s: %s", task_id, exc
            )

    return task


class CreateBody(BaseModel):
    title: str
    tenant: str = "internal"
    desc: str = ""


@router.post("/tasks", status_code=201)
def create_task(body: CreateBody):
    task_id = "t_" + uuid.uuid4().hex[:8]
    now = int(time.time())
    tenant = body.tenant or "internal"

    with _conn() as conn:
        conn.execute(
            """
            INSERT INTO tasks (id, title, body, status, priority, created_by, created_at, tenant, assignee)
            VALUES (?, ?, ?, 'triage', 4, 'dashboard', ?, ?, NULL)
            """,
            (task_id, body.title, body.desc, now, tenant),
        )
        conn.commit()
        cur = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
        return _row_to_task(cur.fetchone())


def _linear_id_from_text(text: str) -> str | None:
    """Extract the first Linear issue identifier (e.g. ENG-123) from text."""
    if not text:
        return None
    m = _LINEAR_URL_RE.search(text)
    return m.group(1).upper() if m else None


_LINEAR_ISSUE_QUERY = """
query IssueDetail($id: String!) {
  issue(id: $id) {
    identifier
    title
    description
    url
    priority
    priorityLabel
    state { name color type }
    labels { nodes { name color } }
    comments(first: 50) {
      nodes {
        body
        createdAt
        user { name displayName }
      }
    }
  }
}
"""


@router.get("/linear-issue")
async def linear_issue(url: str = Query(..., description="Linear issue URL or identifier")):
    """Fetch a Linear issue's full detail (body, comments, labels, priority).

    Accepts either a full Linear issue URL or a bare identifier (ENG-123).
    The dashboard calls this when a card created from a Linear issue is opened.
    """
    if not LINEAR_API_KEY:
        raise HTTPException(status_code=503, detail="Linear API key not configured")

    identifier = _linear_id_from_text(url)
    if identifier is None:
        # Maybe the caller passed a bare identifier already.
        bare = url.strip().upper()
        if re.fullmatch(r"[A-Z0-9]+-\d+", bare):
            identifier = bare
        else:
            raise HTTPException(status_code=400, detail="No Linear issue identifier found")

    try:
        import aiohttp

        async with aiohttp.ClientSession() as session:
            async with session.post(
                LINEAR_API_URL,
                headers={
                    "Authorization": LINEAR_API_KEY,
                    "Content-Type": "application/json",
                },
                json={"query": _LINEAR_ISSUE_QUERY, "variables": {"id": identifier}},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise HTTPException(
                        status_code=502,
                        detail=f"Linear API returned {resp.status}: {text[:200]}",
                    )
                payload = await resp.json()
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Linear API request failed: {exc}")

    if payload.get("errors"):
        raise HTTPException(
            status_code=502, detail=f"Linear API error: {payload['errors']}"
        )

    issue = (payload.get("data") or {}).get("issue")
    if not issue:
        raise HTTPException(status_code=404, detail=f"Linear issue {identifier} not found")

    labels = [
        {"name": n.get("name", ""), "color": n.get("color", "")}
        for n in ((issue.get("labels") or {}).get("nodes") or [])
    ]
    comments = []
    for c in ((issue.get("comments") or {}).get("nodes") or []):
        user = c.get("user") or {}
        comments.append(
            {
                "body": c.get("body", ""),
                "createdAt": c.get("createdAt", ""),
                "author": user.get("displayName") or user.get("name") or "Unknown",
            }
        )
    state = issue.get("state") or {}

    return {
        "identifier": issue.get("identifier", identifier),
        "title": issue.get("title", ""),
        "description": issue.get("description") or "",
        "url": issue.get("url", ""),
        "priority": issue.get("priority"),
        "priorityLabel": issue.get("priorityLabel") or "",
        "state": {"name": state.get("name", ""), "color": state.get("color", "")},
        "labels": labels,
        "comments": comments,
    }


@router.get("/stream")
async def stream_tasks():
    async def event_generator() -> AsyncGenerator[str, None]:
        last_sig: int | None = None

        while True:
            try:
                conn = _conn()
                try:
                    sig = _signature(conn)
                    if last_sig is None or sig != last_sig:
                        tasks = _fetch_tasks(conn)
                        payload = json.dumps({"tasks": tasks})
                        yield f"data: {payload}\n\n"
                        last_sig = sig
                    else:
                        yield ": keepalive\n\n"
                finally:
                    conn.close()
            except Exception:
                yield ": keepalive\n\n"

            await asyncio.sleep(3)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/agent-reports/{profile}")
def agent_reports(profile: str):
    """Return an agent's recent Kanban task reports as chat messages."""
    conn = _conn()
    try:
        rows = conn.execute(
            """
            SELECT tr.summary, tr.outcome, tr.ended_at, t.title, tr.task_id
            FROM task_runs tr
            LEFT JOIN tasks t ON tr.task_id = t.id
            WHERE tr.profile = ?
              AND tr.summary IS NOT NULL
              AND tr.summary != ''
            ORDER BY tr.ended_at DESC
            LIMIT 40
            """,
            (profile,),
        ).fetchall()
    finally:
        conn.close()

    messages = []
    for r in reversed(rows):  # oldest-first so the feed reads top-to-bottom
        outcome = r["outcome"] or "done"
        icon = "✅" if outcome == "completed" else "⚠️" if outcome == "blocked" else "•"
        title = r["title"] or r["task_id"] or "task"
        body = f"{icon} **{title}**\n\n{r['summary']}"
        messages.append({
            "role": "agent",
            "content": body,
            "created_at": r["ended_at"],
            "task_id": r["task_id"],
            "outcome": outcome,
        })
    return messages
