"""
routes/hooks.py — Inbound webhook receivers
============================================
Registered in server.py as: include_router(hooks_router, prefix="/api")
All routes here are therefore under /api/hooks/*.

Current receivers:
  POST /api/hooks/knowledge  — Supabase INSERT trigger on public.knowledge
                               Appends a knowledge.py search pointer to MEMORY.md
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
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")


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
