"""
Sessions API router for Hermes Dispatcher.
Backed by the real SQLite state.db.
"""

import os
import sqlite3
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/sessions")


def _db_path() -> Path:
    # The dispatcher dashboard reads the top-level Hermes state.db
    # (documented at ~/.hermes/state.db). HERMES_HOME may be
    # profile-scoped (e.g. ~/.hermes/profiles/<name>) in some runtimes,
    # which would point at a near-empty per-profile DB, so don't trust it.
    # Allow an explicit STATE_DB override for non-default deployments.
    override = os.environ.get("STATE_DB")
    if override:
        return Path(override)
    return Path(os.path.expanduser("~/.hermes/state.db"))


def _connect() -> sqlite3.Connection | None:
    p = _db_path()
    if not p.exists():
        return None
    conn = sqlite3.connect(str(p), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _row_to_session(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "title": row["title"] or row["id"],
        "profile": row["user_id"] or row["source"],
        "created_at": row["started_at"],
        "updated_at": row["ended_at"] if row["ended_at"] is not None else row["started_at"],
        "source": row["source"],
        "message_count": row["message_count"],
    }


_SESSION_COLS = (
    "id, title, user_id, source, started_at, ended_at, message_count"
)


@router.get("")
async def list_sessions() -> list[dict[str, Any]]:
    conn = _connect()
    if conn is None:
        return []
    try:
        cur = conn.cursor()
        cur.execute(
            f"SELECT {_SESSION_COLS} FROM sessions "
            "WHERE archived=0 ORDER BY started_at DESC LIMIT 100"
        )
        return [_row_to_session(r) for r in cur.fetchall()]
    finally:
        conn.close()


@router.get("/search")
async def search_sessions(q: str = Query(default="")) -> list[dict[str, Any]]:
    q = q.strip()
    if not q:
        return await list_sessions()
    conn = _connect()
    if conn is None:
        return []
    try:
        like = f"%{q}%"
        cur = conn.cursor()
        cur.execute(
            f"""
            SELECT DISTINCT s.{', s.'.join(_SESSION_COLS.split(', '))}
            FROM sessions s
            WHERE s.archived = 0
              AND (
                s.title LIKE ? COLLATE NOCASE
                OR s.id IN (
                  SELECT DISTINCT m.session_id FROM messages m
                  WHERE m.content LIKE ? COLLATE NOCASE
                )
              )
            ORDER BY s.started_at DESC
            LIMIT 100
            """,
            (like, like),
        )
        return [_row_to_session(r) for r in cur.fetchall()]
    finally:
        conn.close()


@router.get("/{session_id}/messages")
async def get_messages(session_id: str) -> list[dict[str, Any]]:
    conn = _connect()
    if conn is None:
        return []
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT role, content, timestamp FROM messages "
            "WHERE session_id=? AND active=1 ORDER BY timestamp DESC LIMIT 50",
            (session_id,),
        )
        rows = cur.fetchall()
        rows.reverse()
        return [
            {"role": r["role"], "content": r["content"] or "", "created_at": r["timestamp"]}
            for r in rows
        ]
    finally:
        conn.close()


@router.delete("/{session_id}")
async def delete_session(session_id: str) -> dict[str, Any]:
    conn = _connect()
    if conn is None:
        raise HTTPException(status_code=503, detail="Database unavailable")
    try:
        cur = conn.cursor()
        cur.execute("SELECT id FROM sessions WHERE id=?", (session_id,))
        if cur.fetchone() is None:
            raise HTTPException(status_code=404, detail="Session not found")
        cur.execute("DELETE FROM messages WHERE session_id=?", (session_id,))
        cur.execute("DELETE FROM sessions WHERE id=?", (session_id,))
        conn.commit()
        return {"deleted": session_id, "ok": True}
    finally:
        conn.close()
