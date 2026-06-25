#!/usr/bin/env python3
"""
session_distill.py — Distill substantive Hermes sessions into semantic digests.

Finds sessions from state.db that ended since a stored watermark, extracts
salient decisions/outcomes from their transcripts, and stores a digest per
session into Supabase via knowledge.py. These digests surface automatically
on future turns via B-full semantic retrieval at ≥0.80 score.

Called by cron (and can be run manually). Silent-by-default: prints nothing
if no new sessions qualify; prints a 1-line summary when sessions are distilled.
"""

import json
import os
import re
import sqlite3
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timedelta, timezone

# ── Paths ──────────────────────────────────────────────────────────────
STATE_DB = os.path.expanduser("~/.hermes/state.db")
KNOWLEDGE_SCRIPT = os.path.expanduser("~/.hermes/scripts/knowledge.py")
WATERMARK_FILE = os.path.expanduser(
    "~/.hermes/references/session-distill-watermark.json"
)

# ── Constants ──────────────────────────────────────────────────────────
MIN_UA_MESSAGES = 20       # minimum user+assistant messages to qualify
MAX_DIGEST_CHARS = 2000    # hard cap on digest length
MAX_WATERMARK_IDS = 500    # keep the processed_session_ids list trimmed
FIRST_RUN_LOOKBACK_DAYS = 7
TAGS = "session-digest,compaction-flush"
PRIORITY = "high"

# ── Helpers ────────────────────────────────────────────────────────────


def load_watermark():
    """Load watermark from JSON file. Returns (last_processed_ts, set_of_ids)."""
    if not os.path.exists(WATERMARK_FILE):
        return None, set()
    try:
        with open(WATERMARK_FILE) as f:
            data = json.load(f)
        ts = data.get("last_processed_ts")
        ids = set(data.get("processed_session_ids", []))
        return ts, ids
    except (json.JSONDecodeError, KeyError, ValueError):
        return None, set()


def save_watermark(last_processed_ts, processed_ids):
    """Save watermark to JSON file. Trims processed_ids to last MAX_WATERMARK_IDS."""
    os.makedirs(os.path.dirname(WATERMARK_FILE), exist_ok=True)
    ids_list = list(processed_ids)[-MAX_WATERMARK_IDS:]
    data = {
        "last_processed_ts": last_processed_ts,
        "processed_session_ids": ids_list,
    }
    with open(WATERMARK_FILE, "w") as f:
        json.dump(data, f, indent=2)
    return ids_list


def get_qualifying_sessions(since_ts, processed_ids):
    """Return sessions that qualify for distillation, ordered by ended_at asc.

    Criteria:
      - source contains 'telegram' or 'gateway' (case-insensitive substring)
      - end_reason = 'session_reset'
      - id does NOT start with 'cron_'
      - ≥20 user+assistant messages in the session
      - ended_at > since_ts (if since_ts is set)
      - id NOT in processed_ids
    """
    conn = sqlite3.connect(STATE_DB)
    conn.row_factory = sqlite3.Row
    cur = conn.execute(
        """
        SELECT s.id, s.source, s.title, s.ended_at, s.message_count
        FROM sessions s
        WHERE s.end_reason = 'session_reset'
          AND (LOWER(s.source) LIKE '%telegram%' OR LOWER(s.source) LIKE '%gateway%')
          AND s.id NOT LIKE 'cron_%'
          AND (? IS NULL OR s.ended_at > ?)
        ORDER BY s.ended_at ASC
        """,
        (since_ts, since_ts),
    )
    candidates = list(cur.fetchall())
    qualifying = []
    for row in candidates:
        sid = row["id"]
        if sid in processed_ids:
            continue
        # Count user+assistant messages
        ua_count = conn.execute(
            "SELECT COUNT(*) FROM messages WHERE session_id = ? AND role IN ('user', 'assistant')",
            (sid,),
        ).fetchone()[0]
        if ua_count >= MIN_UA_MESSAGES:
            qualifying.append(dict(row))
    conn.close()
    return qualifying


def get_session_messages(session_id):
    """Return all user and assistant messages for a session, ordered by id."""
    conn = sqlite3.connect(STATE_DB)
    conn.row_factory = sqlite3.Row
    cur = conn.execute(
        """
        SELECT id, role, content
        FROM messages
        WHERE session_id = ? AND role IN ('user', 'assistant')
        ORDER BY id ASC
        """,
        (session_id,),
    )
    messages = [dict(r) for r in cur.fetchall()]
    conn.close()
    return messages


def distill_session(session, messages):
    """Extract a curated digest from session messages.

    Returns a plain-text digest string, or None if not substantive enough.
    """
    title = (session.get("title") or "").strip()
    ended_at = session.get("ended_at")
    if ended_at:
        date_str = datetime.fromtimestamp(ended_at, tz=timezone.utc).strftime(
            "%Y-%m-%d"
        )
    else:
        date_str = "unknown-date"

    # Derive title from first user message if missing
    if not title:
        for m in messages:
            if m["role"] == "user":
                title = m["content"].strip()[:80]
                break
    if not title:
        title = "untitled"

    # Collect assistant content for extraction
    assistant_texts = [m["content"] for m in messages if m["role"] == "assistant"]
    all_assistant = "\n".join(assistant_texts)
    user_texts = [m["content"] for m in messages if m["role"] == "user"]
    all_user = "\n".join(user_texts)

    # ── Decisions: scan assistant turns for decision verbs ──
    # Strategy: find the sentence containing the keyword, not just the keyword.
    # Split on sentence boundaries, then filter for sentences containing decision signals.
    DECISION_SIGNALS = re.compile(
        r"(?i)\b(decided|verdict|greenlit|green-?lit|approved|proceeding|going ahead"
        r"|will (?:now )?(?:proceed|implement|build|deploy|install|create|add|update"
        r"|fix|patch|rewrite|refactor|migrate|remove|delete|configure|set up|switch)"
        r"|I(?:'ll| will) (?:build|implement|deploy|install|create|add|update|fix"
        r"|patch|rewrite|refactor|migrate|configure)"
        r"|verdict is|verdict:|SKIP|not installing|ruled out)\b"
    )
    decisions = set()
    for text in assistant_texts:
        # Split into sentences on . ! ? or newlines; keep delimiters via lookahead
        sentences = re.split(r"(?<=[.!?])\s+|\n+", text)
        for sent in sentences:
            sent = sent.strip()
            if not sent:
                continue
            if DECISION_SIGNALS.search(sent):
                # Take the sentence, capped at 160 chars
                decisions.add(sent[:160])

    # Also capture key user directives
    user_directives = set()
    for pat in [
        r"(?i)\b(?:please|can you|I need|I want|build|deploy|install|create|add|review|check|fix|update|migrate|configure)\s+(.+?)(?:[.;\n]|$)",
    ]:
        for m in re.finditer(pat, all_user):
            user_directives.add(m.group(0).strip()[:120])

    # ── Outcomes: tool results, files written, systems changed ──
    outcome_patterns = [
        r"(?i)\b(?:wrote|created|saved|written|built|deployed|installed|configured|patched|fixed|updated|migrated|refactored|rewrote|archived|removed|deleted)\s+(.+?)(?:[.;\n]|$)",
        r"(?i)\b(?:file|script|config|binary|endpoint|service|container|database|table|index)\s+(?:is|was|now|has been)\s+(.+?)(?:[.;\n]|$)",
        r"(?i)\b(?:verdict|verdict is|result|outcome)\s*:\s*(.+?)(?:[.;\n]|$)",
        r"(?i)\b(?:pass(?:ed)?|fail(?:ed)?|success|error|completed?|finished?|done)\b",
        r"(?i)\b(?:test(?:s)?\s+(?:pass|fail|green|red|succeed))\b",
    ]
    outcomes = set()
    for pat in outcome_patterns:
        for m in re.finditer(pat, all_assistant):
            outcomes.add(m.group(0).strip()[:150])

    # ── Skipped: things ruled out ──
    skip_patterns = [
        r"(?i)\b(?:skip(?:ping)?|SKIP|not installing|not building|ruled out|rejected|won't|will not|not going to|declined|passed on)\s+(.+?)(?:[.;\n]|$)",
    ]
    skipped = set()
    for pat in skip_patterns:
        for m in re.finditer(pat, all_assistant):
            skipped.add(m.group(0).strip()[:120])

    # ── Context: session arc summary ──
    # First user message as the opener, last assistant message conclusion hint
    opener = user_texts[0][:200].strip() if user_texts else ""
    closer = ""
    for m in reversed(assistant_texts):
        stripped = m.strip()
        if stripped:
            closer = stripped[:200]
            break

    # ── Build digest ──
    parts = []
    parts.append(f"Session: {title} | {date_str}")

    if decisions:
        parts.append(f"Decisions: {', '.join(sorted(decisions)[:8])}")
    if outcomes:
        parts.append(f"Outcomes: {', '.join(sorted(outcomes)[:6])}")
    if skipped:
        parts.append(f"Skipped: {', '.join(sorted(skipped)[:4])}")
    if user_directives:
        parts.append(f"Directives: {', '.join(sorted(user_directives)[:4])}")

    # Context summary
    context = f"Context: Session started with user asking to {opener[:120]}"
    if closer and closer != opener[:200]:
        context += f". Concluded with: {closer[:120]}"
    parts.append(context)

    digest = "\n".join(parts)

    # Truncate to max chars
    if len(digest) > MAX_DIGEST_CHARS:
        digest = digest[: MAX_DIGEST_CHARS - 3] + "..."

    # ── Substantive check: need at least 2 non-empty fields ──
    substantive_fields = sum(
        1
        for key in ["Decisions:", "Outcomes:", "Skipped:", "Directives:"]
        if key in digest and digest.split(key + " ", 1)[-1].split("\n")[0].strip()
    )
    if substantive_fields < 2:
        # Fallback: check if we can extract anything from the opener/closer
        if len(opener) > 10:
            substantive_fields += 1
        if substantive_fields < 1:
            return None

    return digest


def store_digest(digest):
    """Store a digest in Supabase via knowledge.py. Returns True on success."""
    env = os.environ.copy()
    env["KNOWLEDGE_TAGS"] = TAGS
    env["KNOWLEDGE_PRIORITY"] = PRIORITY

    try:
        result = subprocess.run(
            [sys.executable, KNOWLEDGE_SCRIPT, "store", digest],
            capture_output=True,
            text=True,
            timeout=120,
            env=env,
        )
        if result.returncode == 0 and "Stored:" in result.stdout:
            return True
        else:
            print(
                f"[session_distill] knowledge.py store failed: "
                f"rc={result.returncode} stderr={result.stderr[:200]}",
                file=sys.stderr,
            )
            return False
    except subprocess.TimeoutExpired:
        print("[session_distill] knowledge.py store timed out", file=sys.stderr)
        return False
    except Exception as e:
        print(f"[session_distill] knowledge.py store error: {e}", file=sys.stderr)
        return False


def main():
    watermark_ts, processed_ids = load_watermark()

    # First run: watermark absent → look back 7 days only
    if watermark_ts is None:
        watermark_ts = (
            datetime.now(timezone.utc) - timedelta(days=FIRST_RUN_LOOKBACK_DAYS)
        ).timestamp()

    sessions = get_qualifying_sessions(watermark_ts, processed_ids)

    if not sessions:
        # Silent exit — nothing to do
        return 0

    distilled = 0
    max_ts = watermark_ts
    new_ids = processed_ids.copy()

    for session in sessions:
        sid = session["id"]
        messages = get_session_messages(sid)
        if not messages:
            continue

        digest = distill_session(session, messages)
        if digest is None:
            # Not substantive enough — still mark as processed
            new_ids.add(sid)
            if session["ended_at"] and session["ended_at"] > max_ts:
                max_ts = session["ended_at"]
            continue

        if store_digest(digest):
            distilled += 1
            new_ids.add(sid)
            if session["ended_at"] and session["ended_at"] > max_ts:
                max_ts = session["ended_at"]
        else:
            # Store failed — don't mark as processed so it retries next run
            print(
                f"[session_distill] Failed to store digest for session {sid}",
                file=sys.stderr,
            )

    # Save watermark
    if distilled > 0 or max_ts > watermark_ts:
        save_watermark(max_ts, new_ids)

    if distilled > 0:
        print(f"Distilled {distilled} sessions → Supabase")

    return 0


if __name__ == "__main__":
    sys.exit(main())
