"""
routes/kanban_linear_poller.py — Reverse sync: Kanban card done → close Linear issue
====================================================================================
Closes the loop on the Sentry → Linear → Kanban pipeline.

The FORWARD leg already exists: a Linear webhook creates a Kanban card
(``routes/hooks.py:linear_webhook``), stamping the pair as
``tasks.idempotency_key = "linear-<issueUuid>"``.

The REVERSE leg has two existing triggers, both *event*-driven:
  1. Dashboard "drag to Done"      → routes/kanban.py:patch_task
  2. POST /api/hooks/kanban        → routes/hooks.py:kanban_webhook
Both call routes/linear_autoclose.py:autoclose_for_card.

But the most common completion path — a dispatched worker calling
``kanban_complete`` (which writes ``status='done'`` straight into kanban.db) —
fires NO webhook. Those linked Linear issues rot in Backlog forever (we just
hand-closed 16 of them). Kanban has no outbound webhook, so the honest path is
to POLL the SQLite DB.

This module is that poller. Every ``_POLL_INTERVAL`` seconds it:

  • SELECTs Kanban tasks that are ``status='done'`` AND linear-mapped
    (``idempotency_key LIKE 'linear-%'``) AND not yet reverse-synced,
  • closes each linked Linear issue via the shared, idempotent
    ``autoclose_for_card`` orchestrator (dynamic completed-state resolution,
    back-link comment, never-raises contract),
  • records the outcome in a dedicated crash-safe SQLite table so a closed
    issue is never touched twice and a restart never replays.

Design choices (stated per the task brief):
  • State store: a SEPARATE SQLite file ``data/linear_reverse_sync.db`` (NOT a
    new table inside the externally-owned kanban.db). SQLite gives us atomic,
    crash-safe idempotency (UPSERT keyed on task_id) — strictly better than a
    JSON temp+rename for the "close exactly once" guarantee under concurrent
    ticks. ``data/`` is gitignored, so no runtime state leaks into the repo.
  • Archive ≠ resolved: the candidate query filters on ``status='done'`` only,
    so an archived-without-completion card is never picked up. If a card that
    was ALREADY synced later flips to archived, that's fine — it stays synced.
  • Error handling: a Linear API error (or any non-terminal outcome) is logged
    and NOT marked synced, so it's retried on the next tick. The loop itself
    never crashes — every tick is wrapped.

Wiring: started as a background asyncio task from server.py's lifespan hook
(``run_reverse_sync_poller``). Single uvicorn worker → exactly one poller.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sqlite3
import time
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
HERMES_HOME = Path(os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes")))
KANBAN_DB = os.environ.get("KANBAN_DB", str(HERMES_HOME / "kanban.db"))

# Dedicated sync-state DB (gitignored data/ dir alongside the other runtime
# state files). Overridable so tests can point it at scratch space.
_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
REVERSE_SYNC_DB = os.environ.get(
    "LINEAR_REVERSE_SYNC_DB", str(_DATA_DIR / "linear_reverse_sync.db")
)

# Poll cadence (seconds). Task brief suggests ~60s.
_POLL_INTERVAL = float(os.environ.get("KANBAN_LINEAR_SYNC_POLL_INTERVAL", "60"))

# Outcomes from autoclose_for_card that mean "terminal — never retry".
# Everything else (notably status='error') is left unmarked for retry.
_TERMINAL_OK_STATES = {"completed", "already_completed"}


# ---------------------------------------------------------------------------
# Sync-state store (dedicated SQLite file)
# ---------------------------------------------------------------------------
def _sync_conn() -> sqlite3.Connection:
    Path(REVERSE_SYNC_DB).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(REVERSE_SYNC_DB, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_schema() -> None:
    """Create the reverse_sync table if it doesn't exist. Idempotent."""
    with _sync_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS reverse_sync (
                task_id      TEXT PRIMARY KEY,
                linear_ref   TEXT,
                linear_state TEXT,
                synced_at    INTEGER,
                attempts     INTEGER NOT NULL DEFAULT 0,
                last_error   TEXT
            )
            """
        )
        conn.commit()


def _already_synced_ids() -> set[str]:
    """task_ids that have been terminally reverse-synced (never touch again)."""
    try:
        with _sync_conn() as conn:
            rows = conn.execute(
                "SELECT task_id FROM reverse_sync WHERE synced_at IS NOT NULL"
            ).fetchall()
        return {r["task_id"] for r in rows}
    except Exception as e:  # pragma: no cover - defensive
        logger.warning("reverse_sync: read synced ids failed: %s", e)
        return set()


def _mark_synced(task_id: str, linear_ref: str, linear_state: str) -> None:
    """Record a terminal, successful close. UPSERT keyed on task_id."""
    now = int(time.time())
    try:
        with _sync_conn() as conn:
            conn.execute(
                """
                INSERT INTO reverse_sync
                    (task_id, linear_ref, linear_state, synced_at, attempts, last_error)
                VALUES (?, ?, ?, ?, 1, NULL)
                ON CONFLICT(task_id) DO UPDATE SET
                    linear_ref   = excluded.linear_ref,
                    linear_state = excluded.linear_state,
                    synced_at    = excluded.synced_at,
                    attempts     = reverse_sync.attempts + 1,
                    last_error   = NULL
                """,
                (task_id, linear_ref, linear_state, now),
            )
            conn.commit()
    except Exception as e:  # pragma: no cover - defensive
        logger.warning("reverse_sync: mark synced %s failed: %s", task_id, e)


def _mark_attempt(task_id: str, err: str) -> None:
    """Record a non-terminal attempt (leaves synced_at NULL so it retries)."""
    try:
        with _sync_conn() as conn:
            conn.execute(
                """
                INSERT INTO reverse_sync
                    (task_id, linear_ref, linear_state, synced_at, attempts, last_error)
                VALUES (?, NULL, NULL, NULL, 1, ?)
                ON CONFLICT(task_id) DO UPDATE SET
                    attempts   = reverse_sync.attempts + 1,
                    last_error = excluded.last_error
                """,
                (task_id, (err or "")[:200]),
            )
            conn.commit()
    except Exception as e:  # pragma: no cover - defensive
        logger.warning("reverse_sync: mark attempt %s failed: %s", task_id, e)


# ---------------------------------------------------------------------------
# Kanban candidate query
# ---------------------------------------------------------------------------
def _kanban_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(KANBAN_DB, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _done_linear_task_ids() -> list[str]:
    """Kanban task ids that are done AND linear-mapped.

    Archive ≠ resolved: we filter on status='done' exactly, so a card archived
    without completion is never a candidate.
    """
    try:
        with _kanban_conn() as conn:
            rows = conn.execute(
                "SELECT id FROM tasks "
                "WHERE status = 'done' AND idempotency_key LIKE 'linear-%' "
                "ORDER BY completed_at ASC"
            ).fetchall()
        return [r["id"] for r in rows]
    except Exception as e:
        logger.warning("reverse_sync: candidate query failed: %s", e)
        return []


def _pending_task_ids() -> list[str]:
    """done+linear task ids not yet terminally reverse-synced."""
    synced = _already_synced_ids()
    return [tid for tid in _done_linear_task_ids() if tid not in synced]


# ---------------------------------------------------------------------------
# One card → close its Linear issue
# ---------------------------------------------------------------------------
def _sync_one(task_id: str) -> str:
    """Close the Linear issue behind one done card. Returns a status word.

    Reuses routes.linear_autoclose.autoclose_for_card — the single idempotent,
    exception-safe orchestrator shared with the dashboard and webhook paths. It
    resolves the completed-type workflow state dynamically (never hardcoded),
    posts a back-link comment, and never raises.

    Returns one of:
      'closed'          — issue transitioned to a completed state (marked synced)
      'already'         — issue was already completed (marked synced)
      'not_found'       — issue missing on Linear (marked synced; nothing to do)
      'no_ref'          — card carries no resolvable Linear ref (marked synced)
      'retry'           — transient error / no api key (left for next tick)
    """
    from routes.linear_autoclose import autoclose_for_card

    result = autoclose_for_card(task_id)  # sync; called via to_thread by caller
    status = result.get("status")
    ref = result.get("ref") or result.get("task_id") or ""

    if status == "ok":
        state = result.get("state", "")
        if state == "completed":
            _mark_synced(task_id, ref, "completed")
            logger.info("reverse_sync: closed Linear issue %s for card %s", ref, task_id)
            return "closed"
        if state == "already_completed":
            _mark_synced(task_id, ref, "already_completed")
            logger.info(
                "reverse_sync: Linear issue %s already completed for card %s (marked synced)",
                ref, task_id,
            )
            return "already"
        # Unexpected 'ok' without a terminal state — retry to be safe.
        _mark_attempt(task_id, f"ok_but_state={state}")
        return "retry"

    if status == "not_found":
        # Issue was deleted/merged on the Linear side — nothing to close, and
        # retrying forever is pointless. Mark synced so it drops out.
        _mark_synced(task_id, ref, "not_found")
        logger.info(
            "reverse_sync: Linear issue %s not found for card %s (marked synced)",
            ref, task_id,
        )
        return "not_found"

    if status == "skipped" and result.get("reason") == "no_linear_ref":
        # Card is linear-mapped by idempotency_key yet no ref resolved — should
        # not happen, but if it does, marking synced avoids an infinite retry.
        _mark_synced(task_id, ref, "no_ref")
        logger.warning("reverse_sync: card %s linear-mapped but no ref resolved", task_id)
        return "no_ref"

    # Everything else (status='error', 'skipped'/no_api_key, etc.) is transient
    # or config-level: log, record the attempt, retry next tick. Never crash.
    reason = result.get("reason") or status or "unknown"
    _mark_attempt(task_id, str(reason))
    logger.warning(
        "reverse_sync: card %s close deferred (status=%s reason=%s) — retry next tick",
        task_id, status, reason,
    )
    return "retry"


def _tick() -> dict:
    """Run one poll pass synchronously. Returns a small counters dict.

    Never raises — a bad card or a Linear hiccup is isolated to that card.
    """
    _ensure_schema()
    pending = _pending_task_ids()
    counts = {"scanned": len(pending), "closed": 0, "already": 0,
              "not_found": 0, "no_ref": 0, "retry": 0}
    for task_id in pending:
        try:
            outcome = _sync_one(task_id)
        except Exception as e:  # noqa: BLE001 — isolate per-card failures
            logger.warning("reverse_sync: card %s raised: %s", task_id, e)
            _mark_attempt(task_id, str(e))
            outcome = "retry"
        counts[outcome] = counts.get(outcome, 0) + 1
    return counts


# ---------------------------------------------------------------------------
# Background poller
# ---------------------------------------------------------------------------
async def run_reverse_sync_poller(stop_event: asyncio.Event | None = None) -> None:
    """Background loop: close Linear issues behind done Kanban cards.

    Started from server.py's lifespan hook. Runs until cancelled (or until
    ``stop_event`` is set). The blocking DB + Linear work runs in a thread so
    the event loop is never stalled.
    """
    from routes.linear_autoclose import linear_api_key

    if not linear_api_key():
        logger.info(
            "reverse_sync: LINEAR_API_KEY not set — reverse-sync poller disabled"
        )
        return

    try:
        _ensure_schema()
    except Exception as e:  # pragma: no cover - defensive
        logger.warning("reverse_sync: schema init failed: %s", e)

    logger.info(
        "reverse_sync: poller started (interval=%ss, db=%s)",
        _POLL_INTERVAL, REVERSE_SYNC_DB,
    )

    while True:
        if stop_event is not None and stop_event.is_set():
            return
        try:
            counts = await asyncio.to_thread(_tick)
            if counts.get("scanned"):
                logger.info("reverse_sync: tick %s", counts)
        except Exception as e:  # pragma: no cover - defensive
            logger.warning("reverse_sync: tick failed: %s", e)

        try:
            if stop_event is not None:
                await asyncio.wait_for(stop_event.wait(), timeout=_POLL_INTERVAL)
                return  # event set during the wait
            await asyncio.sleep(_POLL_INTERVAL)
        except asyncio.TimeoutError:
            continue
