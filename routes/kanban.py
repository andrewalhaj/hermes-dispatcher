import asyncio
import json
import os
import sqlite3
import time
import uuid
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

DB_PATH = os.environ.get("KANBAN_DB", "/root/.hermes/kanban.db")

VALID_STATUSES = {"triage", "todo", "ready", "running", "blocked", "done"}

router = APIRouter(prefix="/api/kanban")


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
        cur = conn.execute("SELECT id FROM tasks WHERE id = ?", (task_id,))
        if cur.fetchone() is None:
            raise HTTPException(status_code=404, detail="task not found")
        conn.execute(
            "UPDATE tasks SET status = ? WHERE id = ?", (body.status, task_id)
        )
        conn.commit()
        cur2 = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
        return _row_to_task(cur2.fetchone())


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
