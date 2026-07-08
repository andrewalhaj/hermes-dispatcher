"""routes/linear_triage.py — Triage Linear issues from Dashboard Kanban cards.

Backs the right-click / action-menu triage on Kanban cards that are linked to a
Linear issue. A card is linked when its ``idempotency_key`` looks like
``linear-<issueId>`` (set by the Linear webhook intake in routes/hooks.py).

Endpoints (all mounted under /api by server.py):
  GET  /api/linear/triage/labels
        -> available workflow labels for the team {id,name,color}
  GET  /api/linear/triage/issue/{kanban_id}
        -> resolved Linear issue id + current priority / assignee / labelIds,
           plus the linked Kanban card's local priority/assignee
  POST /api/linear/triage/{kanban_id}
        body: {priority?: 0..4, assignee?: str|null, labelIds?: [str]}
        -> applies priority/labels to Linear via issueUpdate AND mirrors
           priority + assignee onto the local Kanban card.

Design notes:
  * This module is intentionally self-contained (its own key resolver, its own
    GraphQL helper, its own DB access) so it does not collide with the other
    Linear/Kanban route modules being edited concurrently.
  * "Reassign to different coder" maps to the local Kanban ``assignee`` only —
    the coder fleet (coder, coder-b, …) are Hermes profiles, not Linear users —
    so reassignment is a local mirror, never a Linear assigneeId mutation.
  * Priority mapping is Linear-native: 0=No priority, 1=Urgent, 2=High,
    3=Medium, 4=Low. The UI labels (Urgent/High/Medium/Low) map to 1/2/3/4.
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
import urllib.error
import urllib.request
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/linear/triage")

HERMES_HOME = Path(os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes")))
DB_PATH = os.environ.get("KANBAN_DB", str(HERMES_HOME / "kanban.db"))
LINEAR_API_URL = "https://api.linear.app/graphql"
LINEAR_TEAM_ID = os.environ.get(
    "LINEAR_TEAM_ID", "38a0c106-e9a8-4f65-84d2-ec8bdc61855d"
)  # Hermesjarvis

# UI priority label -> Linear native numeric priority.
PRIORITY_LABEL_TO_LINEAR = {"urgent": 1, "high": 2, "medium": 3, "low": 4, "none": 0}
LINEAR_PRIORITY_LABELS = {0: "No priority", 1: "Urgent", 2: "High", 3: "Medium", 4: "Low"}

# Linear native priority -> local Kanban dispatcher priority (higher = picked
# first). Mirrors the mapping used by the Linear webhook intake so the board
# stays coherent after a triage action. (Linear: 1=Urgent…4=Low, 0=No priority.)
LINEAR_TO_KANBAN_PRIORITY = {1: 50, 2: 30, 3: 10, 4: 5, 0: 1}

# Coder fleet allowed as reassignment targets (kanban-local profiles).
CODER_FLEET = ["coder", "coder-b", "coder-c", "coder-d"]

# Short cache for the team label list (rarely changes).
_label_cache: dict = {"ts": 0.0, "data": None}
_LABEL_TTL = 300


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _linear_api_key() -> str:
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


def _graphql(query: str, variables: dict) -> dict:
    """Run a Linear GraphQL request synchronously. Raises HTTPException on failure."""
    key = _linear_api_key()
    if not key:
        raise HTTPException(status_code=503, detail="LINEAR_API_KEY not configured")
    body = json.dumps({"query": query, "variables": variables}).encode()
    req = urllib.request.Request(
        LINEAR_API_URL,
        data=body,
        headers={"Content-Type": "application/json", "Authorization": key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            payload = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode()[:200]
        except Exception:
            pass
        logger.warning("linear triage: HTTP %s %s", e.code, detail)
        raise HTTPException(status_code=502, detail=f"Linear HTTP {e.code}")
    except Exception as e:  # network / timeout / JSON
        logger.warning("linear triage: request failed: %s", e)
        raise HTTPException(status_code=502, detail=f"Linear request failed: {e}")
    if payload.get("errors"):
        msg = "; ".join(e.get("message", "?") for e in payload["errors"])
        raise HTTPException(status_code=502, detail=f"Linear GraphQL error: {msg}")
    return payload.get("data", {}) or {}


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB_PATH, check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c


def _linear_issue_id(kanban_id: str) -> str:
    """Resolve a Kanban card's linked Linear issue id from its idempotency_key.

    The Linear webhook intake stores ``idempotency_key = "linear-<issueId>"``.
    Returns the bare Linear issue id, or "" if the card isn't linked / missing.
    """
    with _conn() as conn:
        row = conn.execute(
            "SELECT idempotency_key FROM tasks WHERE id = ?", (kanban_id,)
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="kanban task not found")
    key = (row["idempotency_key"] or "").strip()
    if not key.startswith("linear-"):
        return ""
    return key[len("linear-"):]


# --------------------------------------------------------------------------- #
# GET /labels — available team labels
# --------------------------------------------------------------------------- #
_LABELS_QUERY = """
query TeamLabels($teamId: String!) {
  team(id: $teamId) {
    labels(first: 100) {
      nodes { id name color }
    }
  }
}
"""


@router.get("/labels")
def get_labels() -> dict:
    """Return the team's available labels (cached 5 min)."""
    now = time.time()
    if _label_cache["data"] is not None and (now - _label_cache["ts"]) < _LABEL_TTL:
        return {"labels": _label_cache["data"], "cached": True}

    data = _graphql(_LABELS_QUERY, {"teamId": LINEAR_TEAM_ID})
    nodes = (
        (data.get("team") or {}).get("labels", {}) or {}
    ).get("nodes", []) or []
    labels = [
        {"id": n.get("id", ""), "name": n.get("name", ""), "color": n.get("color", "")}
        for n in nodes
        if n.get("id")
    ]
    _label_cache["ts"] = now
    _label_cache["data"] = labels
    return {"labels": labels, "cached": False}


# --------------------------------------------------------------------------- #
# GET /issue/{kanban_id} — current Linear + local state for the card
# --------------------------------------------------------------------------- #
_ISSUE_QUERY = """
query Issue($id: String!) {
  issue(id: $id) {
    id
    identifier
    title
    url
    priority
    priorityLabel
    assignee { id name }
    labels(first: 50) { nodes { id name color } }
  }
}
"""


@router.get("/issue/{kanban_id}")
def get_issue(kanban_id: str) -> dict:
    """Resolve the linked Linear issue + the local Kanban card's triage state."""
    with _conn() as conn:
        row = conn.execute(
            "SELECT id, priority, assignee, idempotency_key FROM tasks WHERE id = ?",
            (kanban_id,),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="kanban task not found")

    key = (row["idempotency_key"] or "").strip()
    linked = key.startswith("linear-")
    local = {
        "priority": int(row["priority"]) if row["priority"] is not None else 0,
        "assignee": row["assignee"],
    }
    if not linked:
        return {"linked": False, "coderFleet": CODER_FLEET, "local": local}

    issue_id = key[len("linear-"):]
    data = _graphql(_ISSUE_QUERY, {"id": issue_id})
    issue = data.get("issue") or {}
    label_nodes = (issue.get("labels") or {}).get("nodes", []) or []
    return {
        "linked": True,
        "coderFleet": CODER_FLEET,
        "local": local,
        "issue": {
            "id": issue.get("id", issue_id),
            "identifier": issue.get("identifier", ""),
            "title": issue.get("title", ""),
            "url": issue.get("url", ""),
            "priority": issue.get("priority", 0),
            "priorityLabel": issue.get("priorityLabel", "No priority"),
            "assignee": (issue.get("assignee") or {}).get("name"),
            "labels": [
                {"id": n.get("id", ""), "name": n.get("name", ""), "color": n.get("color", "")}
                for n in label_nodes
                if n.get("id")
            ],
        },
    }


# --------------------------------------------------------------------------- #
# POST /{kanban_id} — apply triage
# --------------------------------------------------------------------------- #
_UPDATE_MUTATION = """
mutation IssueUpdate($id: String!, $input: IssueUpdateInput!) {
  issueUpdate(id: $id, input: $input) {
    success
    issue { id priority priorityLabel labels(first: 50) { nodes { id name } } }
  }
}
"""


class TriageBody(BaseModel):
    priority: int | None = None          # Linear native 0..4
    assignee: str | None = None          # kanban-local coder profile
    set_assignee: bool = False           # distinguish "clear" (null) from "unchanged"
    labelIds: list[str] | None = None    # full desired label-id set


@router.post("/{kanban_id}")
def apply_triage(kanban_id: str, body: TriageBody) -> dict:
    """Apply a triage action to a Linear-linked Kanban card.

    Priority + labels go to Linear via issueUpdate; priority + assignee are
    mirrored onto the local Kanban card so the board reflects the change
    immediately (no wait for the Linear webhook round-trip).
    """
    with _conn() as conn:
        row = conn.execute(
            "SELECT id, idempotency_key FROM tasks WHERE id = ?", (kanban_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="kanban task not found")
        key = (row["idempotency_key"] or "").strip()

    linked = key.startswith("linear-")
    issue_id = key[len("linear-"):] if linked else ""

    # Validate inputs.
    if body.priority is not None and body.priority not in (0, 1, 2, 3, 4):
        raise HTTPException(status_code=400, detail="priority must be 0..4")
    if body.set_assignee and body.assignee is not None and body.assignee not in CODER_FLEET:
        raise HTTPException(
            status_code=400, detail=f"assignee must be one of {CODER_FLEET} or null"
        )

    applied: dict = {"linear": False, "local": []}

    # --- Linear mutation (priority / labels) — only when the card is linked ---
    # Labels are Linear-only (no local equivalent), so they REQUIRE a link.
    if body.labelIds is not None and not linked:
        raise HTTPException(
            status_code=409,
            detail="card is not linked to a Linear issue (labels need a link)",
        )
    linear_input: dict = {}
    if linked and body.priority is not None:
        linear_input["priority"] = body.priority
    if linked and body.labelIds is not None:
        linear_input["labelIds"] = body.labelIds
    if linear_input:
        data = _graphql(_UPDATE_MUTATION, {"id": issue_id, "input": linear_input})
        result = data.get("issueUpdate") or {}
        if not result.get("success"):
            raise HTTPException(status_code=502, detail="Linear issueUpdate failed")
        applied["linear"] = True
        applied["issue"] = result.get("issue") or {}

    # --- Local Kanban mirror (priority + assignee) — always applied ---
    sets, params = [], []
    if body.priority is not None:
        sets.append("priority = ?")
        params.append(LINEAR_TO_KANBAN_PRIORITY.get(body.priority, 1))
        applied["local"].append("priority")
    if body.set_assignee:
        sets.append("assignee = ?")
        params.append(body.assignee)
        applied["local"].append("assignee")
    if sets:
        params.append(kanban_id)
        with _conn() as conn:
            conn.execute(f"UPDATE tasks SET {', '.join(sets)} WHERE id = ?", params)
            conn.commit()

    if body.priority is None and not body.set_assignee and body.labelIds is None:
        raise HTTPException(status_code=400, detail="no triage fields provided")

    logger.info(
        "linear triage: card=%s linear=%s local=%s", kanban_id, applied["linear"], applied["local"]
    )
    return {"ok": True, "applied": applied}
