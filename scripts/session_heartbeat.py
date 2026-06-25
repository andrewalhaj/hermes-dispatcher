#!/usr/bin/env python3
"""
session_heartbeat.py — incremental, mid-session fact capture → Supabase.

Runs frequently (cron). Queries state.db for new messages since the last
watermark, extracts facts from assistant turns, deduplicates against Supabase,
and stores to the knowledge store. Sessions don't need to end — this catches
decisions/config changes/commands in real time.

Called by: cron (every 15 min recommended)
Watermark: ~/.hermes/references/session-heartbeat-watermark.json
"""

import json
import os
import re
import sqlite3
import sys
import time
from datetime import datetime, timezone

# ── Paths ──────────────────────────────────────────────────────────────
HERMES_HOME = os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes"))
STATE_DB = os.path.join(HERMES_HOME, "state.db")
SCRIPTS_DIR = os.path.join(HERMES_HOME, "scripts")
WATERMARK_FILE = os.path.join(HERMES_HOME, "references", "session-heartbeat-watermark.json")
AUDIT_LOG = os.path.join(HERMES_HOME, "references", "session-heartbeat-audit.md")

sys.path.insert(0, SCRIPTS_DIR)
from knowledge import store, search
from session_capture import extract_facts, MIN_FACT_LENGTH

# ── Config ─────────────────────────────────────────────────────────────
SIMILARITY_THRESHOLD = 0.92
MAX_FACTS_PER_RUN = 20       # cap to avoid flooding Supabase
MAX_MESSAGES_PER_SESSION = 50  # don't process ancient sessions in one go
MIN_MESSAGE_ID = 1             # messages.id is an autoincrement integer

# ── Watermark ──────────────────────────────────────────────────────────

def load_watermark() -> dict:
    """Return {session_id: last_processed_message_id}."""
    try:
        with open(WATERMARK_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_watermark(wm: dict) -> None:
    os.makedirs(os.path.dirname(WATERMARK_FILE), exist_ok=True)
    with open(WATERMARK_FILE, "w") as f:
        json.dump(wm, f, indent=2)


# ── Audit ──────────────────────────────────────────────────────────────

def audit(msg: str) -> None:
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    line = f"- {ts}: {msg}"
    try:
        os.makedirs(os.path.dirname(AUDIT_LOG), exist_ok=True)
        with open(AUDIT_LOG, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


# ── Core ───────────────────────────────────────────────────────────────

def get_active_sessions(db: sqlite3.Connection) -> list[tuple[str, str]]:
    """Return [(session_id, source), ...] for sessions still in progress."""
    rows = db.execute(
        "SELECT id, source FROM sessions "
        "WHERE ended_at IS NULL AND source NOT IN ('subagent', 'batch') "
        "ORDER BY started_at DESC"
    ).fetchall()
    return [(r[0], r[1]) for r in rows]


def get_new_messages(
    db: sqlite3.Connection,
    session_id: str,
    after_id: int,
) -> list[dict]:
    """Return assistant messages since after_id, capped."""
    rows = db.execute(
        "SELECT id, role, content FROM messages "
        "WHERE session_id = ? AND id > ? AND role = 'assistant' "
        "ORDER BY id ASC LIMIT ?",
        (session_id, after_id, MAX_MESSAGES_PER_SESSION),
    ).fetchall()
    return [{"id": r[0], "role": r[1], "content": r[2]} for r in rows]


def is_duplicate(text: str) -> bool:
    """Check semantic dedup against Supabase."""
    try:
        existing = search(text, top_k=3)
        if not existing:
            return False
        best = existing[0].get("score", 0)
        return best > SIMILARITY_THRESHOLD
    except Exception:
        return False  # if Supabase is down, store anyway


def process_session(
    db: sqlite3.Connection,
    session_id: str,
    source: str,
    watermark: dict,
) -> tuple[int, int, int]:
    """Extract facts from new messages in this session. Returns (stored, skipped, last_id)."""
    last_id = watermark.get(session_id, 0)
    messages = get_new_messages(db, session_id, last_id)

    if not messages:
        return 0, 0, last_id

    # Collect text from all new messages
    combined = "\n".join(m.get("content", "") or "" for m in messages)
    if not combined.strip():
        return 0, 0, messages[-1]["id"]

    facts = extract_facts(combined)
    stored = skipped = 0

    for fact, tag in facts:
        if len(fact) < MIN_FACT_LENGTH:
            continue
        if is_duplicate(fact):
            skipped += 1
            continue
        try:
            store(
                fact,
                tags=[tag, "session-heartbeat", source],
                priority="normal",
                context_prefix=session_id,
            )
            stored += 1
        except Exception:
            skipped += 1

    return stored, skipped, messages[-1]["id"]


# ── Main ───────────────────────────────────────────────────────────────

def main() -> None:
    wm = load_watermark()
    db = sqlite3.connect(STATE_DB)

    try:
        sessions = get_active_sessions(db)
    except Exception as exc:
        audit(f"ERROR reading sessions: {exc}")
        db.close()
        return

    if not sessions:
        db.close()
        return  # silent — nothing active

    total_stored = total_skipped = total_sessions = 0

    for session_id, source in sessions:
        try:
            stored, skipped, last_id = process_session(db, session_id, source, wm)
        except Exception as exc:
            audit(f"ERROR session {session_id}: {exc}")
            continue

        if stored or skipped:
            wm[session_id] = last_id
            total_stored += stored
            total_skipped += skipped
            total_sessions += 1

        # Cap total facts per run
        if total_stored + total_skipped >= MAX_FACTS_PER_RUN:
            break

    db.close()

    if total_stored or total_skipped:
        save_watermark(wm)
        audit(
            f"processed {total_sessions} session(s): "
            f"{total_stored} stored, {total_skipped} skipped"
        )


if __name__ == "__main__":
    main()
