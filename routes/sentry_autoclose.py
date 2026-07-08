"""routes/sentry_autoclose.py — Auto-resolve the Sentry issue behind a Kanban card.

When a Kanban card that originated from a Sentry alert transitions to ``done``
we resolve the originating Sentry issue via the Sentry REST API, closing the
loop on the Sentry → Linear → Kanban intake funnel (see
``routes/hooks.py:sentry_webhook``).

This mirrors ``routes/linear_autoclose.py`` exactly, so the two closers behave
uniformly. Both are wired into the same two triggers:

  1. ``routes/kanban.py:patch_task`` — the dashboard "drag to Done" path.
  2. ``routes/hooks.py:kanban_webhook`` (POST /api/hooks/kanban) — a
     programmatic trigger usable by the kanban core / CLI / any automation
     that marks a card done outside the dashboard.

Both call :func:`autoclose_sentry_for_card`, which is the single, idempotent,
exception-safe orchestrator. It never raises — every failure is logged and
returned as a structured dict so callers can fire-and-forget. A bad token or a
network blip therefore can never break the status update the user just made.

Sentry issue reference resolution (in priority order):
  1. ``idempotency_key`` of the form ``sentry-<id>`` (if the card was created
     directly by the sentry handler).
  2. A ``Sentry Issue ID:`` marker embedded in the card body/title (the path
     used today: the sentry handler embeds the id in the Linear issue
     description, which flows verbatim into the Kanban card body).
  3. A Sentry issue URL (``https://sentry.io/.../issues/<id>/``) in the body.
"""
from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

HERMES_HOME = Path(os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes")))
KANBAN_DB = os.environ.get("KANBAN_DB", str(HERMES_HOME / "kanban.db"))
SENTRY_API_BASE = os.environ.get("SENTRY_API_BASE", "https://sentry.io/api/0")
SENTRY_ORG_SLUG = os.environ.get("SENTRY_ORG_SLUG", "andrew-ol")

# Sentry numeric issue id (Sentry issue ids are large integers as strings).
_MARKER_RE = re.compile(r"Sentry\s*Issue\s*ID[:=]\s*([0-9]{4,})", re.IGNORECASE)
# Sentry issue URL → capture the numeric id segment.
_URL_RE = re.compile(r"sentry\.io/(?:organizations/[^/\s]+/)?issues/([0-9]{4,})", re.IGNORECASE)
# idempotency_key written if a card is ever created directly: "sentry-<id>".
_IDEMPOTENCY_RE = re.compile(r"^sentry-([0-9]{4,})$")


# ---------------------------------------------------------------------------
# Sentry API key resolution (mirrors linear_api_key so behaviour is uniform)
# ---------------------------------------------------------------------------
def sentry_api_key() -> str:
    """Resolve SENTRY_API_KEY from env, falling back to ~/.hermes/.env then the
    dispatcher's own .env."""
    key = os.environ.get("SENTRY_API_KEY", "")
    if key:
        return key
    for env_path in (HERMES_HOME / ".env", Path(__file__).resolve().parent.parent / ".env"):
        try:
            for line in env_path.read_text().splitlines():
                line = line.strip()
                if line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                if k.strip() == "SENTRY_API_KEY":
                    val = v.strip().strip('"').strip("'")
                    if val:
                        return val
        except Exception:
            continue
    return ""


# ---------------------------------------------------------------------------
# Reference extraction
# ---------------------------------------------------------------------------
def extract_sentry_ref(
    *,
    idempotency_key: Optional[str] = None,
    body: Optional[str] = None,
    title: Optional[str] = None,
) -> Optional[str]:
    """Return the Sentry issue id for a card, or None."""
    if idempotency_key:
        m = _IDEMPOTENCY_RE.match(idempotency_key.strip())
        if m:
            return m.group(1)

    # An explicit marker is the strongest body signal.
    for text in (body or "", title or ""):
        m = _MARKER_RE.search(text)
        if m:
            return m.group(1)

    # A URL match is the next strongest (least chance of a false hit).
    for text in (body or "", title or ""):
        m = _URL_RE.search(text)
        if m:
            return m.group(1)

    return None


# ---------------------------------------------------------------------------
# Sentry REST call (synchronous, urllib — no extra deps)
# ---------------------------------------------------------------------------
def _patch_issue(issue_id: str, key: str, *, timeout: int = 15) -> dict:
    """PATCH an issue to status=resolved. Returns parsed JSON body.

    Raises urllib.error.HTTPError on a non-2xx response so the caller can map it
    to a structured error.
    """
    url = f"{SENTRY_API_BASE}/issues/{issue_id}/"
    payload = json.dumps({"status": "resolved"}).encode()
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        method="PATCH",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
        try:
            return json.loads(raw) if raw else {}
        except Exception:
            return {}


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------
def resolve_sentry_issue(issue_id: str, *, task_id: str, key: Optional[str] = None) -> dict:
    """Mark a Sentry issue resolved via the REST API.

    Idempotent: PATCHing an already-resolved issue to ``resolved`` is a no-op on
    Sentry's side and returns 200, so re-firing a duplicate done event is safe.
    Never raises — returns a structured result dict.
    """
    key = key or sentry_api_key()
    if not key:
        return {"status": "skipped", "reason": "no_api_key", "ref": issue_id}

    try:
        body = _patch_issue(issue_id, key)
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode(errors="ignore")[:160]
        except Exception:
            pass
        logger.warning("sentry autoclose: issue=%s HTTP %s %s (card=%s)",
                       issue_id, e.code, detail, task_id)
        return {"status": "error", "reason": f"HTTP {e.code}", "detail": detail,
                "ref": issue_id, "task_id": task_id}
    except Exception as e:  # noqa: BLE001 — fire-and-forget contract
        logger.warning("sentry autoclose: issue=%s error %s (card=%s)",
                       issue_id, str(e)[:160], task_id)
        return {"status": "error", "reason": str(e)[:160], "ref": issue_id,
                "task_id": task_id}

    new_status = body.get("status") if isinstance(body, dict) else None
    logger.info("sentry autoclose: issue=%s resolved (status=%s card=%s)",
                issue_id, new_status, task_id)
    return {"status": "ok", "ref": issue_id, "sentry_status": new_status or "resolved",
            "task_id": task_id}


# ---------------------------------------------------------------------------
# DB-backed card resolver — looks the card up by id, extracts the ref, resolves.
# ---------------------------------------------------------------------------
def _read_card(task_id: str) -> Optional[dict]:
    """Read a Kanban card's body/title/status/idempotency_key from the DB."""
    try:
        conn = sqlite3.connect(KANBAN_DB)
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                "SELECT id, title, body, status, idempotency_key FROM tasks WHERE id = ?",
                (task_id,),
            ).fetchone()
        finally:
            conn.close()
    except Exception as e:  # noqa: BLE001
        logger.warning("sentry autoclose: card read failed for %s: %s", task_id, e)
        return None
    return dict(row) if row else None


def autoclose_sentry_for_card(task_id: str, *, require_done: bool = True) -> dict:
    """Resolve the Sentry issue for a card and close it. Never raises.

    ``require_done`` (default True) gates on the card's current status being
    ``done`` — protects the webhook path against being called for a card that
    isn't actually complete. The dashboard ``patch_task`` path calls this only
    after committing the done transition, so the guard is satisfied there too.
    """
    if not task_id:
        return {"status": "skipped", "reason": "no_task_id"}

    card = _read_card(task_id)
    if card is None:
        return {"status": "not_found", "reason": "card_missing", "task_id": task_id}

    if require_done and card.get("status") != "done":
        return {"status": "skipped", "reason": "card_not_done",
                "task_id": task_id, "card_status": card.get("status")}

    ref = extract_sentry_ref(
        idempotency_key=card.get("idempotency_key"),
        body=card.get("body"),
        title=card.get("title"),
    )
    if not ref:
        return {"status": "skipped", "reason": "no_sentry_ref", "task_id": task_id}

    result = resolve_sentry_issue(ref, task_id=task_id)
    result["task_id"] = task_id
    return result
