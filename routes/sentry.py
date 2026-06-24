"""Sentry alerts API — exposes sentry webhook events as a read-only "Sentry"
channel in the Chat panel.

Mounted with: app.include_router(sentry.router)  (router carries the /api/sentry prefix)

Data source:
  - /root/hermes-dispatcher/data/sentry_messages.json
    Array of {role, content, created_at, project, level, action, issue_url} objects.
    Appended by the sentry webhook handler in routes/hooks.py.
"""

import json
from pathlib import Path

from fastapi import APIRouter

router = APIRouter(prefix="/sentry")

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_MESSAGES_FILE = _DATA_DIR / "sentry_messages.json"


@router.get("/messages")
def sentry_messages():
    """Return recent sentry alert messages, newest-first."""
    if not _MESSAGES_FILE.exists():
        return []

    try:
        messages = json.loads(_MESSAGES_FILE.read_text(errors="ignore"))
    except Exception:
        return []

    if not isinstance(messages, list):
        return []

    # Sort newest-first by created_at
    messages.sort(key=lambda m: m.get("created_at", 0), reverse=True)
    return messages[:50]
