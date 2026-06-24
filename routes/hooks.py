"""
routes/hooks.py — Inbound webhook receivers
============================================
Registered in server.py as: include_router(hooks_router, prefix="/api")
All routes here are therefore under /api/hooks/*.

Current receivers:
  POST /api/hooks/knowledge  — Supabase INSERT trigger on public.knowledge
                               Appends a knowledge.py search pointer to MEMORY.md
  POST /api/hooks/honcho     — Honcho workspace webhook (conclusions, observations,
                               session summaries). Auth via HONCHO_WEBHOOK_SECRET.
"""

import os
import re
import hmac
import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Request, HTTPException, status

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/hooks", tags=["hooks"])

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
HERMES_HOME = Path(os.environ.get("HERMES_HOME", "/root/.hermes"))
MEMORY_PATH = HERMES_HOME / "memories" / "MEMORY.md"
USER_PATH = HERMES_HOME / "memories" / "USER.md"
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")
HONCHO_WEBHOOK_SECRET = os.environ.get("HONCHO_WEBHOOK_SECRET", os.environ.get("HONCHO_API_KEY", ""))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _verify_bearer(request: Request) -> None:
    """Reject requests whose Authorization header doesn't match WEBHOOK_SECRET."""
    if not WEBHOOK_SECRET:
        logger.error("WEBHOOK_SECRET not set — rejecting all webhook calls")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail="Webhook secret not configured")

    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Missing Bearer token")

    token = auth[len("Bearer "):]
    # Constant-time comparison to prevent timing attacks
    if not hmac.compare_digest(token.encode(), WEBHOOK_SECRET.encode()):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Invalid token")


def _derive_search_term(text: str, tags: list[str] | None) -> str:
    """
    Derive a MEMORY.md search term from the knowledge row.

    Strategy (in priority order):
    1. If tags are present, use the first 5 words of text + first tag.
    2. Otherwise use the first 8 words of text.
    Strips newlines and collapses whitespace.
    """
    clean = re.sub(r"\s+", " ", text.strip())
    words = clean.split()
    if tags:
        base = " ".join(words[:5])
        term = f"{base} {tags[0]}" if tags[0] not in base else base
    else:
        term = " ".join(words[:8])
    # Truncate to 80 chars so the pointer line stays readable
    return term[:80].rstrip()


def _pointer_line(term: str) -> str:
    return f'knowledge.py search "{term}".  [auto]\n'


def _already_present(memory_text: str, term: str) -> bool:
    """True if a pointer for this term (or a close prefix) already exists."""
    return term[:40] in memory_text


def _append_pointer(term: str) -> str:
    """
    Append a pointer line to MEMORY.md.
    Returns one of: 'appended' | 'duplicate' | 'memory_missing'
    """
    if not MEMORY_PATH.exists():
        logger.warning("MEMORY_PATH %s does not exist — skipping append", MEMORY_PATH)
        return "memory_missing"

    current = MEMORY_PATH.read_text(encoding="utf-8")

    if _already_present(current, term):
        return "duplicate"

    pointer = _pointer_line(term)
    # Insert before the closing §-delimiter block if present, otherwise append
    # MEMORY.md entries are separated by §\n — append after the last one
    if current.endswith("\n"):
        updated = current + "§\n" + pointer
    else:
        updated = current + "\n§\n" + pointer

    MEMORY_PATH.write_text(updated, encoding="utf-8")
    return "appended"


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/knowledge")
async def knowledge_insert_webhook(request: Request):
    """
    Receives Supabase INSERT events on public.knowledge.

    Payload shape (sent by the pg trigger):
        {
          "id":       <int>,
          "text":     <str, first 200 chars>,
          "tags":     <list[str] | null>,
          "source":   <str | null>,
          "priority": <int | null>
        }

    On success: appends a `knowledge.py search "..." [auto]` pointer to MEMORY.md.
    Always returns 200 — never 5xx on our logic errors, so Supabase doesn't retry-spam.
    """
    _verify_bearer(request)

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Invalid JSON payload")

    text = payload.get("text") or ""
    tags = payload.get("tags") or []
    row_id = payload.get("id")

    if not text:
        logger.info("knowledge webhook: empty text in row %s — skipping", row_id)
        return {"status": "skipped", "reason": "empty_text"}

    term = _derive_search_term(text, tags)
    result = _append_pointer(term)

    logger.info(
        "knowledge webhook: row=%s term=%r result=%s ts=%s",
        row_id, term, result,
        datetime.now(timezone.utc).isoformat()
    )

    return {"status": result, "term": term, "row_id": row_id}


# ---------------------------------------------------------------------------
# Honcho webhook — receives workspace events from Honcho's webhook system.
#
# Event types (inferred from Honcho v3 API spec and SDK types):
#   conclusion  → USER.md sync (peer card fact written)
#   observation → MEMORY.md pointer (behavioral pattern inferred)
#   session     → knowledge store INSERT (session summary ready)
#
# Auth: Bearer token matched against HONCHO_WEBHOOK_SECRET (fallback: HONCHO_API_KEY).
# The endpoint is exempt from the session-cookie auth gate (see server.py _AUTH_EXEMPT).
# ---------------------------------------------------------------------------

@router.post("/honcho")
async def honcho_webhook(request: Request):
    """
    Receives Honcho workspace webhook events.

    Expected payload (exact shape depends on event type):
        {
          "event": "conclusion" | "observation" | "session_summary",
          "data": { ... }
        }

    A — conclusion → updates USER.md with new peer card facts.
    B — observation → appends MEMORY.md pointer.
    C — session_summary → inserts into knowledge store (via local import).
    """
    _verify_honcho(request)

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Invalid JSON payload")

    event_type = (payload.get("event") or payload.get("type") or "").lower()
    data = payload.get("data") or payload

    if not event_type:
        # Best-effort: try to classify from payload shape
        event_type = _classify_honcho_payload(payload)

    logger.info("honcho webhook: event=%s keys=%s", event_type, list(data.keys())[:6])

    if event_type in ("conclusion", "peer_card"):
        return await _handle_honcho_conclusion(data)
    elif event_type in ("observation", "inference"):
        return await _handle_honcho_observation(data)
    elif event_type in ("session_summary", "session"):
        return await _handle_honcho_session(data)
    else:
        logger.info("honcho webhook: unknown event type %r — accepted but unhandled", event_type)
        return {"status": "unhandled", "event_type": event_type}


# ---------------------------------------------------------------------------
# Honcho auth
# ---------------------------------------------------------------------------

def _verify_honcho(request: Request) -> None:
    """Verify the Honcho webhook request using HONCHO_WEBHOOK_SECRET."""
    if not HONCHO_WEBHOOK_SECRET:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail="Honcho webhook secret not configured")

    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Missing Bearer token")

    token = auth[len("Bearer "):]
    if not hmac.compare_digest(token.encode(), HONCHO_WEBHOOK_SECRET.encode()):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Invalid token")


# ---------------------------------------------------------------------------
# Honcho event handlers
# ---------------------------------------------------------------------------

async def _handle_honcho_conclusion(data: dict) -> dict:
    """A conclusion was written about the user — sync to USER.md."""
    text = data.get("content") or data.get("text") or ""
    if not text:
        return {"status": "skipped", "reason": "empty_content"}

    # Append to USER.md as a new fact line
    if USER_PATH.exists():
        current = USER_PATH.read_text(encoding="utf-8")
        fact = text.strip()
        if fact not in current:
            updated = current.rstrip() + "\n" + fact + "\n"
            USER_PATH.write_text(updated, encoding="utf-8")
            logger.info("honcho conclusion: appended to USER.md: %s", fact[:80])
            return {"status": "appended", "fact": fact[:120]}
        return {"status": "duplicate", "fact": fact[:120]}
    return {"status": "user_file_missing"}


async def _handle_honcho_observation(data: dict) -> dict:
    """An observation was inferred — append pointer to MEMORY.md."""
    text = data.get("content") or data.get("text") or data.get("observation") or ""
    if not text:
        return {"status": "skipped", "reason": "empty_content"}

    clean = re.sub(r"\s+", " ", text.strip())
    term = clean[:80].rstrip()
    result = _append_pointer(term)
    return {"status": result, "term": term}


async def _handle_honcho_session(data: dict) -> dict:
    """A session summary is ready — insert into knowledge store."""
    summary = data.get("summary") or data.get("text") or ""
    session_id = data.get("session_id") or data.get("id") or "unknown"

    if not summary:
        return {"status": "skipped", "reason": "empty_summary"}

    # Call knowledge.py via subprocess (it lives in Hermes home, not dispatcher venv)
    try:
        import subprocess, json as _json
        result = subprocess.run(
            [
                "/root/.hermes/.venv/bin/python3", "-m", "knowledge",
                "store",
                "--text", summary,
                "--tags", "honcho,session",
                "--source", "honcho-webhook",
                "--priority", "normal",
                "--context-prefix", session_id,
            ],
            capture_output=True, text=True, timeout=10,
            env={**__import__("os").environ, "HERMES_HOME": str(HERMES_HOME)},
        )
        if result.returncode == 0:
            store_id = result.stdout.strip()
            logger.info("honcho session: stored to knowledge store id=%s", store_id)
            return {"status": "stored", "knowledge_id": store_id, "session_id": session_id}
        else:
            logger.error("honcho session: knowledge store error: %s", result.stderr[:200])
            return {"status": "error", "reason": result.stderr[:200]}
    except Exception as e:
        logger.error("honcho session: knowledge store error: %s", e)
        return {"status": "error", "reason": str(e)[:200]}


def _classify_honcho_payload(payload: dict) -> str:
    """Best-effort classification when no 'event' field is present."""
    keys = set(payload.keys())
    if "conclusion" in payload or "conclusion_id" in keys:
        return "conclusion"
    if "observation" in payload or "observation_id" in keys:
        return "observation"
    if "session" in payload or "session_id" in keys or "summary" in keys:
        return "session_summary"
    return "unknown"
