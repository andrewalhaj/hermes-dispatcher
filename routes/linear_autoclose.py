"""routes/linear_autoclose.py — Auto-close the Linear issue behind a Kanban card.

When a Kanban card transitions to ``done`` we want the originating Linear
issue marked *completed* and annotated with a back-link, closing the loop on
the Linear → Kanban intake funnel (see ``routes/hooks.py:linear_webhook``).

Two entry points feed this module:

  1. ``routes/kanban.py:patch_task`` — the dashboard "drag to Done" path.
  2. ``routes/hooks.py:kanban_webhook`` (POST /api/hooks/kanban) — a
     programmatic trigger usable by the kanban core / CLI / any automation
     that marks a card done outside the dashboard. This is what makes the
     feature work for *manually dispatched* cards as well as webhook-created
     ones.

Both call :func:`autoclose_for_card`, which is the single, idempotent,
exception-safe orchestrator. It never raises — every failure is logged and
returned as a structured dict so callers can fire-and-forget.

Linear issue reference resolution (in priority order):
  1. ``idempotency_key`` of the form ``linear-<uuid>``  → Linear issue *UUID*.
  2. A Linear issue *identifier* (e.g. ``HER-42``) found in the card body/title.
  3. A Linear issue URL (``https://linear.app/<org>/issue/HER-42/...``) in the body.

The Linear GraphQL API accepts either the UUID or the human identifier as the
``id`` argument to the ``issue`` query, so both resolve cleanly.
"""
from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

HERMES_HOME = Path(os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes")))
KANBAN_DB = os.environ.get("KANBAN_DB", str(HERMES_HOME / "kanban.db"))
LINEAR_API_URL = "https://api.linear.app/graphql"
DASHBOARD_BASE = os.environ.get("DASHBOARD_PUBLIC_URL", "http://localhost:8787")

# Linear issue identifier, e.g. HER-42, ABC-1234. Word-boundary anchored so we
# don't match substrings inside longer tokens.
_IDENTIFIER_RE = re.compile(r"\b([A-Z][A-Z0-9]{1,9}-\d+)\b")
# Linear issue URL → capture the identifier segment.
_URL_RE = re.compile(r"linear\.app/[^/\s]+/issue/([A-Z][A-Z0-9]{1,9}-\d+)", re.IGNORECASE)
# idempotency_key written by the Linear intake webhook: "linear-<uuid>".
_IDEMPOTENCY_RE = re.compile(r"^linear-([0-9a-fA-F-]{8,})$")


# ---------------------------------------------------------------------------
# Linear API key resolution (mirrors routes/linear.py so behaviour is uniform)
# ---------------------------------------------------------------------------
def linear_api_key() -> str:
    """Resolve LINEAR_API_KEY from env, falling back to ~/.hermes/.env."""
    key = os.environ.get("LINEAR_API_KEY", "")
    if key:
        return key
    try:
        for line in (HERMES_HOME / ".env").read_text().splitlines():
            line = line.strip()
            if line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            if k.strip() == "LINEAR_API_KEY":
                return v.strip().strip('"').strip("'")
    except Exception:
        pass
    return ""


# ---------------------------------------------------------------------------
# Reference extraction
# ---------------------------------------------------------------------------
def extract_linear_ref(
    *,
    idempotency_key: Optional[str] = None,
    body: Optional[str] = None,
    title: Optional[str] = None,
) -> Optional[str]:
    """Return the best Linear issue reference for a card, or None.

    Returns a UUID (from idempotency_key) or a human identifier like ``HER-42``.
    Both are accepted by the Linear ``issue(id:)`` query.
    """
    if idempotency_key:
        m = _IDEMPOTENCY_RE.match(idempotency_key.strip())
        if m:
            return m.group(1)

    # A URL match is the strongest body signal (least chance of a false hit).
    for text in (body or "", title or ""):
        m = _URL_RE.search(text)
        if m:
            return m.group(1).upper()

    for text in (body or "", title or ""):
        m = _IDENTIFIER_RE.search(text)
        if m:
            return m.group(1).upper()

    return None


# ---------------------------------------------------------------------------
# Linear GraphQL calls (synchronous, urllib — no extra deps)
# ---------------------------------------------------------------------------
def _graphql(query: str, variables: dict, key: str, *, timeout: int = 15) -> dict:
    """POST a GraphQL request. Returns the parsed JSON. Raises on transport error."""
    payload = json.dumps({"query": query, "variables": variables}).encode()
    req = urllib.request.Request(
        LINEAR_API_URL,
        data=payload,
        headers={"Content-Type": "application/json", "Authorization": key},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


_ISSUE_QUERY = """
query IssueState($id: String!) {
  issue(id: $id) {
    id
    identifier
    url
    state { id name type }
    team { id }
  }
}
"""

_TEAM_STATES_QUERY = """
query TeamStates($teamId: String!) {
  team(id: $teamId) {
    states(first: 50) { nodes { id name type } }
  }
}
"""

_UPDATE_MUTATION = """
mutation CloseIssue($id: String!, $stateId: String!) {
  issueUpdate(id: $id, input: { stateId: $stateId }) {
    success
    issue { id identifier state { id name type } }
  }
}
"""

_COMMENT_MUTATION = """
mutation Comment($issueId: String!, $body: String!) {
  commentCreate(input: { issueId: $issueId, body: $body }) {
    success
    comment { id }
  }
}
"""


def _find_completed_state_id(team_id: str, key: str) -> Optional[str]:
    """Query a team's workflow states and return the id of a 'completed' state."""
    data = _graphql(_TEAM_STATES_QUERY, {"teamId": team_id}, key)
    if "errors" in data:
        logger.warning("linear autoclose: team states error: %s", data["errors"][:1])
        return None
    nodes = (
        data.get("data", {}).get("team", {}).get("states", {}).get("nodes", [])
        if data.get("data", {}).get("team")
        else []
    )
    completed = [n for n in nodes if n.get("type") == "completed"]
    if not completed:
        return None
    # Prefer a state literally named "Done", else first completed-type state.
    for n in completed:
        if (n.get("name") or "").strip().lower() == "done":
            return n["id"]
    return completed[0]["id"]


def card_link(task_id: str) -> str:
    """Build a dashboard deep-link to a Kanban card."""
    base = DASHBOARD_BASE.rstrip("/")
    return f"{base}/?task={task_id}"


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------
def close_linear_issue(issue_ref: str, *, task_id: str, key: Optional[str] = None) -> dict:
    """Mark a Linear issue completed and add a back-link comment.

    Idempotent: if the issue is already in a completed-type state, the state
    update is skipped (but the comment is still suppressed to avoid spam).
    Never raises — returns a structured result dict.
    """
    key = key or linear_api_key()
    if not key:
        return {"status": "skipped", "reason": "no_api_key", "ref": issue_ref}

    try:
        issue_data = _graphql(_ISSUE_QUERY, {"id": issue_ref}, key)
    except urllib.error.HTTPError as e:
        return {"status": "error", "reason": f"HTTP {e.code}", "ref": issue_ref}
    except Exception as e:  # noqa: BLE001 — fire-and-forget contract
        return {"status": "error", "reason": str(e)[:160], "ref": issue_ref}

    if "errors" in issue_data:
        return {"status": "error", "reason": "issue_lookup_failed",
                "detail": str(issue_data["errors"][:1])[:160], "ref": issue_ref}

    issue = (issue_data.get("data") or {}).get("issue")
    if not issue:
        return {"status": "not_found", "ref": issue_ref}

    issue_id = issue["id"]
    identifier = issue.get("identifier", issue_ref)
    cur_state = issue.get("state") or {}
    team_id = (issue.get("team") or {}).get("id")

    already_done = cur_state.get("type") == "completed"

    state_result = "already_completed" if already_done else "pending"
    if not already_done:
        if not team_id:
            return {"status": "error", "reason": "no_team_id", "ref": identifier}
        try:
            state_id = _find_completed_state_id(team_id, key)
        except Exception as e:  # noqa: BLE001
            return {"status": "error", "reason": f"states_query: {str(e)[:120]}",
                    "ref": identifier}
        if not state_id:
            return {"status": "error", "reason": "no_completed_state", "ref": identifier}
        try:
            upd = _graphql(_UPDATE_MUTATION, {"id": issue_id, "stateId": state_id}, key)
        except Exception as e:  # noqa: BLE001
            return {"status": "error", "reason": f"update: {str(e)[:120]}",
                    "ref": identifier}
        if "errors" in upd or not (upd.get("data", {}).get("issueUpdate", {}) or {}).get("success"):
            return {"status": "error", "reason": "update_failed",
                    "detail": str(upd.get("errors", ""))[:160], "ref": identifier}
        state_result = "completed"

    # Add a back-link comment (only when we actually closed it — avoids spamming
    # a comment on every duplicate done event for an already-completed issue).
    comment_result = "skipped"
    if state_result == "completed":
        link = card_link(task_id)
        comment_body = f"Completed via Kanban — [{task_id}]({link})"
        try:
            cmt = _graphql(_COMMENT_MUTATION, {"issueId": issue_id, "body": comment_body}, key)
            if "errors" in cmt or not (cmt.get("data", {}).get("commentCreate", {}) or {}).get("success"):
                comment_result = "comment_failed"
            else:
                comment_result = "commented"
        except Exception as e:  # noqa: BLE001
            logger.warning("linear autoclose: comment failed for %s: %s", identifier, e)
            comment_result = "comment_error"

    logger.info("linear autoclose: issue=%s state=%s comment=%s (card=%s)",
                identifier, state_result, comment_result, task_id)
    return {"status": "ok", "ref": identifier, "issue_id": issue_id,
            "state": state_result, "comment": comment_result}


# ---------------------------------------------------------------------------
# DB-backed card resolver — looks the card up by id, extracts the ref, closes.
# ---------------------------------------------------------------------------
def _read_card(task_id: str) -> Optional[dict]:
    """Read a Kanban card's body/title/idempotency_key from the DB."""
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
        logger.warning("linear autoclose: card read failed for %s: %s", task_id, e)
        return None
    return dict(row) if row else None


def autoclose_for_card(task_id: str, *, require_done: bool = True) -> dict:
    """Resolve the Linear issue for a card and close it. Never raises.

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

    ref = extract_linear_ref(
        idempotency_key=card.get("idempotency_key"),
        body=card.get("body"),
        title=card.get("title"),
    )
    if not ref:
        return {"status": "skipped", "reason": "no_linear_ref", "task_id": task_id}

    result = close_linear_issue(ref, task_id=task_id)
    result["task_id"] = task_id
    return result
