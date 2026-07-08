"""Linear Reports API — exposes routed Linear issues as a read-only
"Linear Reports" channel in the Chat panel.

Mounted with: app.include_router(linear_reports.router, prefix="/api")
(router carries the /linear-reports prefix → /api/linear-reports/messages)

Data source:
  - hermes-dispatcher/data/linear_reports.json
    Array of {role, content, created_at, title, priority, coder, issue_url}
    objects. Appended by the Linear webhook handler in routes/hooks.py when it
    dispatches a Kanban card.
"""

import json
from pathlib import Path

from fastapi import APIRouter

router = APIRouter(prefix="/linear-reports")

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_MESSAGES_FILE = _DATA_DIR / "linear_reports.json"


@router.get("/messages")
def linear_reports_messages():
    """Return recent Linear routing reports, newest-first."""
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
