"""
routes/linear_sync.py — Bidirectional comment sync: Kanban ↔ Linear
====================================================================
Keeps the comment thread on a Kanban card and its originating Linear issue
in sync, in both directions:

  • Linear issue comment  → Kanban card comment   (INBOUND, webhook-driven)
  • Kanban card comment    → Linear issue comment  (OUTBOUND, poller-driven)

Mapping
-------
A Kanban task created from a Linear issue carries
``tasks.idempotency_key = "linear-<issueId>"`` (set by the Linear webhook
intake in routes/hooks.py). That single column is the join key in both
directions:

  kanban task  → linear issue : strip the ``linear-`` prefix off idempotency_key
  linear issue → kanban task  : SELECT id WHERE idempotency_key = "linear-<id>"

Loop prevention
---------------
Every synced comment carries a visible source-indicator footer:

  • a comment pushed Kanban → Linear ends with ``SYNC_MARKER_KANBAN``
  • a comment pulled Linear → Kanban ends with ``SYNC_MARKER_LINEAR``

Each side SKIPS any comment that already carries the *other* side's marker, so
an echo can never round-trip:

  INBOUND  drops Linear comments containing SYNC_MARKER_KANBAN
           (those are echoes of our own outbound push)
  OUTBOUND drops Kanban comments containing SYNC_MARKER_LINEAR
           (those are echoes of an inbound pull)

The OUTBOUND poller persists the last-synced ``task_comments.id`` to
``data/linear_sync_state.json`` so a dispatcher restart never re-pushes
already-synced comments.

Wiring
------
  • INBOUND  is called from the Comment/create branch of the Linear webhook
    handler in routes/hooks.py (``handle_inbound_linear_comment``).
  • OUTBOUND runs as a background asyncio task started from the FastAPI
    lifespan hook in server.py (``run_outbound_poller``).

Both paths are best-effort and never raise into their callers: a Linear API
hiccup or a malformed payload is logged, not propagated.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sqlite3
import time
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
DB_PATH = os.environ.get("KANBAN_DB", os.path.expanduser("~/.hermes/kanban.db"))
LINEAR_API_KEY = os.environ.get("LINEAR_API_KEY", "")
LINEAR_GRAPHQL = "https://api.linear.app/graphql"

# Where the outbound poller remembers the last comment id it pushed.
_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_SYNC_STATE_FILE = _DATA_DIR / "linear_sync_state.json"

# Source-indicator footers. Appended to synced comment bodies and used as the
# loop-prevention sentinel on the receiving side. Keep these stable + unique —
# changing them mid-flight re-opens the echo loop for in-flight comments.
SYNC_MARKER_KANBAN = "↪ via Kanban"   # tags comments pushed Kanban → Linear
SYNC_MARKER_LINEAR = "↪ via Linear"   # tags comments pulled Linear → Kanban

# Kanban author label used for comments that arrived from Linear.
_INBOUND_AUTHOR_PREFIX = "linear"

# Outbound poll cadence (seconds).
_POLL_INTERVAL = float(os.environ.get("LINEAR_SYNC_POLL_INTERVAL", "10"))


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB_PATH, check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c


def linear_issue_for_task(task_id: str) -> str | None:
    """Return the Linear issue id linked to a Kanban task, or None.

    The link is ``tasks.idempotency_key = "linear-<issueId>"``.
    """
    try:
        with _conn() as conn:
            row = conn.execute(
                "SELECT idempotency_key FROM tasks WHERE id = ?", (task_id,)
            ).fetchone()
    except Exception as e:  # pragma: no cover - defensive
        logger.warning("linear_sync: lookup issue for task %s failed: %s", task_id, e)
        return None
    if not row:
        return None
    key = row["idempotency_key"] or ""
    if key.startswith("linear-"):
        issue_id = key[len("linear-"):]
        return issue_id or None
    return None


def task_for_linear_issue(issue_id: str) -> str | None:
    """Return the Kanban task id linked to a Linear issue, or None."""
    if not issue_id:
        return None
    try:
        with _conn() as conn:
            row = conn.execute(
                "SELECT id FROM tasks WHERE idempotency_key = ? "
                "AND status != 'archived' ORDER BY created_at DESC LIMIT 1",
                (f"linear-{issue_id}",),
            ).fetchone()
    except Exception as e:  # pragma: no cover - defensive
        logger.warning("linear_sync: lookup task for issue %s failed: %s", issue_id, e)
        return None
    return row["id"] if row else None


def _add_kanban_comment(task_id: str, author: str, body: str) -> int | None:
    """Insert a comment into task_comments + emit the 'commented' event.

    Mirrors hermes_cli.kanban_db.add_comment so the dashboard and worker
    `kanban_show` see the inbound Linear comment exactly like a native one.
    """
    if not body or not body.strip():
        return None
    now = int(time.time())
    try:
        with _conn() as conn:
            cur = conn.execute(
                "INSERT INTO task_comments (task_id, author, body, created_at) "
                "VALUES (?, ?, ?, ?)",
                (task_id, author.strip(), body.strip(), now),
            )
            conn.execute(
                "INSERT INTO task_events (task_id, run_id, kind, payload, created_at) "
                "VALUES (?, NULL, 'commented', ?, ?)",
                (task_id, json.dumps({"author": author, "len": len(body)}), now),
            )
            conn.commit()
            return int(cur.lastrowid or 0)
    except Exception as e:
        logger.warning("linear_sync: add kanban comment to %s failed: %s", task_id, e)
        return None


# ---------------------------------------------------------------------------
# Linear API
# ---------------------------------------------------------------------------

_COMMENT_CREATE_MUTATION = """
mutation CommentCreate($input: CommentCreateInput!) {
  commentCreate(input: $input) {
    success
    comment { id url }
  }
}
"""


async def _linear_comment_create(issue_id: str, body: str) -> dict | None:
    """POST a comment to a Linear issue. Returns the created comment dict or None."""
    if not LINEAR_API_KEY:
        logger.warning("linear_sync: LINEAR_API_KEY not configured — cannot push comment")
        return None
    import aiohttp

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                LINEAR_GRAPHQL,
                headers={
                    "Authorization": LINEAR_API_KEY,
                    "Content-Type": "application/json",
                },
                json={
                    "query": _COMMENT_CREATE_MUTATION,
                    "variables": {"input": {"issueId": issue_id, "body": body}},
                },
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                payload = await resp.json()
    except Exception as e:
        logger.warning("linear_sync: commentCreate request failed for %s: %s", issue_id, e)
        return None

    if payload.get("errors"):
        msg = "; ".join(e.get("message", "?") for e in payload["errors"])
        logger.warning("linear_sync: commentCreate GraphQL error for %s: %s", issue_id, msg)
        return None

    result = (payload.get("data") or {}).get("commentCreate") or {}
    if not result.get("success"):
        logger.warning("linear_sync: commentCreate not successful for %s", issue_id)
        return None
    return result.get("comment") or {}


# ---------------------------------------------------------------------------
# INBOUND: Linear comment → Kanban card
# ---------------------------------------------------------------------------

def handle_inbound_linear_comment(data: dict, actor_name: str = "someone") -> dict:
    """Mirror a Linear issue comment onto the linked Kanban card.

    Called from the Comment/create branch of the Linear webhook handler.
    ``data`` is the Linear webhook ``data`` object for a Comment entity; it
    carries ``issueId`` and ``body``.

    Returns a small status dict (never raises) describing what happened.
    """
    try:
        body = (data.get("body") or "").strip() if isinstance(data, dict) else ""
        issue_id = data.get("issueId") or data.get("issue", {}).get("id") \
            if isinstance(data, dict) else None
    except Exception:
        return {"status": "skipped", "reason": "bad_payload"}

    if not body:
        return {"status": "skipped", "reason": "empty_body"}

    # Loop guard: this comment is an echo of one WE pushed Kanban → Linear.
    if SYNC_MARKER_KANBAN in body:
        return {"status": "skipped", "reason": "echo_of_outbound"}

    if not issue_id:
        return {"status": "skipped", "reason": "no_issue_id"}

    task_id = task_for_linear_issue(issue_id)
    if not task_id:
        return {"status": "skipped", "reason": "no_linked_task", "issue_id": issue_id}

    author = f"{_INBOUND_AUTHOR_PREFIX}:{actor_name}".strip().lower()
    synced_body = f"{body}\n\n{SYNC_MARKER_LINEAR}"
    comment_id = _add_kanban_comment(task_id, author, synced_body)
    if comment_id is None:
        return {"status": "error", "reason": "db_write_failed", "task_id": task_id}

    logger.info(
        "linear_sync INBOUND: linear issue %s comment by %s → kanban %s (comment #%s)",
        issue_id, actor_name, task_id, comment_id,
    )
    return {"status": "synced", "direction": "linear_to_kanban",
            "task_id": task_id, "comment_id": comment_id}


# ---------------------------------------------------------------------------
# OUTBOUND: Kanban card comment → Linear issue (background poller)
# ---------------------------------------------------------------------------

def _load_last_synced_id() -> int:
    try:
        if _SYNC_STATE_FILE.exists():
            data = json.loads(_SYNC_STATE_FILE.read_text(errors="ignore"))
            return int(data.get("last_synced_comment_id", 0))
    except Exception as e:
        logger.warning("linear_sync: could not read sync state: %s", e)
    return 0


def _save_last_synced_id(comment_id: int) -> None:
    try:
        _SYNC_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _SYNC_STATE_FILE.write_text(
            json.dumps({"last_synced_comment_id": int(comment_id)}, indent=2),
            encoding="utf-8",
        )
    except Exception as e:
        logger.warning("linear_sync: could not persist sync state: %s", e)


def _baseline_comment_id() -> int:
    """Highest existing comment id — the poller starts AFTER this on first run.

    On a fresh install (no state file) we don't want to replay the entire
    historical comment backlog into Linear; we only sync comments created from
    now on.
    """
    try:
        with _conn() as conn:
            row = conn.execute("SELECT MAX(id) AS mx FROM task_comments").fetchone()
            return int(row["mx"] or 0)
    except Exception:
        return 0


def _is_inbound_author(author: str) -> bool:
    """True if a comment author marks it as having come FROM Linear."""
    return (author or "").strip().lower().startswith(_INBOUND_AUTHOR_PREFIX + ":")


def _fetch_new_comments(after_id: int) -> list[sqlite3.Row]:
    try:
        with _conn() as conn:
            return conn.execute(
                "SELECT id, task_id, author, body FROM task_comments "
                "WHERE id > ? ORDER BY id ASC",
                (after_id,),
            ).fetchall()
    except Exception as e:
        logger.warning("linear_sync: fetch new comments failed: %s", e)
        return []


async def _sync_one_outbound(row: sqlite3.Row) -> str:
    """Push a single Kanban comment to its linked Linear issue.

    Returns one of: 'synced' | 'skipped' | 'no_link' | 'error'.
    """
    body = row["body"] or ""
    author = row["author"] or ""

    # Loop guard 1: this comment was itself pulled FROM Linear (inbound echo).
    if SYNC_MARKER_LINEAR in body or _is_inbound_author(author):
        return "skipped"

    # Loop guard 2: already carries our own outbound marker (defensive).
    if SYNC_MARKER_KANBAN in body:
        return "skipped"

    issue_id = linear_issue_for_task(row["task_id"])
    if not issue_id:
        return "no_link"

    synced_body = f"**{author}** commented on Kanban:\n\n{body}\n\n{SYNC_MARKER_KANBAN}"
    comment = await _linear_comment_create(issue_id, synced_body)
    if comment is None:
        return "error"

    logger.info(
        "linear_sync OUTBOUND: kanban %s comment by %s → linear issue %s (comment %s)",
        row["task_id"], author, issue_id, comment.get("id", "?"),
    )
    return "synced"


async def run_outbound_poller(stop_event: asyncio.Event | None = None) -> None:
    """Background loop: push new Kanban comments to their linked Linear issues.

    Started from server.py's lifespan hook. Runs until cancelled (or until
    ``stop_event`` is set). Each tick fetches comments with id greater than the
    last-synced id, pushes the eligible ones, and persists progress.

    On the very first run with no state file, it baselines to the current max
    comment id so historical comments are not replayed into Linear.
    """
    if not LINEAR_API_KEY:
        logger.info("linear_sync: LINEAR_API_KEY not set — outbound poller disabled")
        return

    last_id = _load_last_synced_id()
    if last_id == 0:
        last_id = _baseline_comment_id()
        _save_last_synced_id(last_id)
        logger.info("linear_sync: outbound poller baselined at comment id %s", last_id)
    else:
        logger.info("linear_sync: outbound poller resuming from comment id %s", last_id)

    while True:
        if stop_event is not None and stop_event.is_set():
            return
        try:
            rows = _fetch_new_comments(last_id)
            for row in rows:
                status = await _sync_one_outbound(row)
                # Advance the cursor on everything except a transient API error,
                # so a Linear outage doesn't permanently stall the cursor but a
                # failed push gets retried on the next tick.
                if status == "error":
                    # Stop advancing here; retry this + later comments next tick.
                    break
                last_id = row["id"]
                _save_last_synced_id(last_id)
        except Exception as e:  # pragma: no cover - defensive
            logger.warning("linear_sync: outbound poller tick failed: %s", e)

        try:
            if stop_event is not None:
                await asyncio.wait_for(stop_event.wait(), timeout=_POLL_INTERVAL)
                return  # event set during the wait
            else:
                await asyncio.sleep(_POLL_INTERVAL)
        except asyncio.TimeoutError:
            continue
