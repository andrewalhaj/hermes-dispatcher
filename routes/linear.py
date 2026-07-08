"""routes/linear.py — Live Linear issue counts for the Dashboard Overview tile.

Exposes GET /api/linear/issues returning the open / urgent / stale counts for
the Hermesjarvis Linear team, fetched via the Linear GraphQL API.

The Linear API is hit at most once every CACHE_TTL seconds (5 min) regardless
of how often the frontend polls — a module-level cache holds the last good
result so frequent dashboard polls are cheap and never rate-limit Linear.

Counts:
  open   — issues whose workflow state.type is backlog/unstarted/started/triage
  urgent — open issues with priority 0 or 1 (per task spec)
  stale  — open issues whose updatedAt is older than 7 days
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter

logger = logging.getLogger(__name__)

router = APIRouter()

HERMES_HOME = Path(os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes")))
LINEAR_API_URL = "https://api.linear.app/graphql"
LINEAR_TEAM_ID = os.environ.get(
    "LINEAR_TEAM_ID", "38a0c106-e9a8-4f65-84d2-ec8bdc61855d"
)  # Hermesjarvis
CACHE_TTL = 300  # 5 minutes
STALE_SECONDS = 7 * 86400  # 7 days

# Open issues are those in a non-terminal workflow state.
_OPEN_STATE_TYPES = ["backlog", "unstarted", "started", "triage"]

_QUERY = """
query OpenIssues($teamId: ID!, $after: String) {
  issues(
    first: 100
    after: $after
    filter: {
      team: { id: { eq: $teamId } }
      state: { type: { in: %s } }
    }
  ) {
    pageInfo { hasNextPage endCursor }
    nodes { id priority updatedAt }
  }
}
""" % json.dumps(_OPEN_STATE_TYPES)

# Module-level cache: {"ts": epoch, "data": {...}}
_cache: dict = {"ts": 0.0, "data": None}


def _linear_api_key() -> str:
    """Resolve LINEAR_API_KEY from the environment, falling back to ~/.hermes/.env."""
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


def _parse_iso(iso: str) -> float:
    """Parse a Linear ISO-8601 timestamp (e.g. '2026-06-25T18:46:57.823Z') to epoch."""
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()
    except Exception:
        return time.time()  # treat unparseable as fresh (never falsely stale)


def _fetch_counts() -> dict:
    """Synchronously page through the Linear API and compute open/urgent/stale.

    Returns a dict with the counts plus an ``error`` key (None on success).
    Raises nothing — all failures are caught and surfaced via the error field.
    """
    key = _linear_api_key()
    if not key:
        return {"open": 0, "urgent": 0, "stale": 0, "error": "LINEAR_API_KEY not set"}

    nodes: list[dict] = []
    after = None
    try:
        while True:
            body = json.dumps(
                {"query": _QUERY, "variables": {"teamId": LINEAR_TEAM_ID, "after": after}}
            ).encode()
            req = urllib.request.Request(
                LINEAR_API_URL,
                data=body,
                headers={"Content-Type": "application/json", "Authorization": key},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                payload = json.loads(resp.read())
            if "errors" in payload:
                msg = payload["errors"][0].get("message", "GraphQL error")
                logger.warning("linear issues: GraphQL error: %s", msg)
                return {"open": 0, "urgent": 0, "stale": 0, "error": msg}
            conn = payload["data"]["issues"]
            nodes.extend(conn["nodes"])
            if conn["pageInfo"]["hasNextPage"]:
                after = conn["pageInfo"]["endCursor"]
            else:
                break
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode()[:200]
        except Exception:
            pass
        logger.warning("linear issues: HTTP %s %s", e.code, detail)
        return {"open": 0, "urgent": 0, "stale": 0, "error": f"HTTP {e.code}"}
    except Exception as e:
        logger.warning("linear issues: fetch failed: %s", e)
        return {"open": 0, "urgent": 0, "stale": 0, "error": str(e)[:120]}

    stale_cutoff = time.time() - STALE_SECONDS
    open_count = len(nodes)
    # Urgent per task spec: priority 0 (No priority) or 1 (Urgent).
    urgent = sum(1 for n in nodes if n.get("priority") in (0, 1))
    stale = sum(1 for n in nodes if _parse_iso(n.get("updatedAt", "")) < stale_cutoff)
    return {"open": open_count, "urgent": urgent, "stale": stale, "error": None}


@router.get("/linear/issues")
async def linear_issues() -> dict:
    """Return live Linear issue counts, served from a 5-minute cache.

    Always 200. On upstream failure, returns the last good cached value (if any)
    with a fresh ``error`` field, or zeros + error when no cache exists yet.
    """
    now = time.time()
    if _cache["data"] is not None and (now - _cache["ts"]) < CACHE_TTL:
        cached = dict(_cache["data"])
        cached["cached"] = True
        cached["updated_at"] = int(_cache["ts"])
        return cached

    result = await asyncio.to_thread(_fetch_counts)

    if result.get("error") and _cache["data"] is not None:
        # Upstream hiccup — keep serving the last good counts, flag the error.
        stale_data = dict(_cache["data"])
        stale_data["cached"] = True
        stale_data["updated_at"] = int(_cache["ts"])
        stale_data["error"] = result["error"]
        return stale_data

    if not result.get("error"):
        _cache["ts"] = now
        _cache["data"] = {k: result[k] for k in ("open", "urgent", "stale", "error")}

    result["cached"] = False
    result["updated_at"] = int(now)
    return result


# ---------------------------------------------------------------------------
# Issue search — backs the `/linear search <query>` Dashboard Chat command.
# ---------------------------------------------------------------------------

_SEARCH_QUERY = """
query Search($term: String!, $first: Int!) {
  searchIssues(term: $term, first: $first) {
    nodes {
      identifier
      title
      url
      priority
      priorityLabel
      state { name type }
    }
  }
}
"""


def _normalise_issue(node: dict) -> dict:
    """Flatten a Linear issue node into the shape the Chat frontend renders."""
    state = node.get("state") or {}
    return {
        "identifier": node.get("identifier") or "",
        "title": node.get("title") or "",
        "url": node.get("url") or "",
        "priority": node.get("priority", 0),
        "priority_label": node.get("priorityLabel") or "No priority",
        "status": state.get("name") or "",
        "status_type": state.get("type") or "",
    }


def _search_issues(q: str, first: int) -> dict:
    """Run Linear issueSearch synchronously. Returns {issues|error}."""
    key = _linear_api_key()
    if not key:
        return {"issues": [], "error": "LINEAR_API_KEY not set"}
    body = json.dumps(
        {"query": _SEARCH_QUERY, "variables": {"term": q, "first": first}}
    ).encode()
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
        logger.warning("linear search: HTTP %s %s", e.code, detail)
        return {"issues": [], "error": f"HTTP {e.code}"}
    except Exception as e:
        logger.warning("linear search: fetch failed: %s", e)
        return {"issues": [], "error": str(e)[:120]}

    if "errors" in payload:
        msg = payload["errors"][0].get("message", "GraphQL error")
        logger.warning("linear search: GraphQL error: %s", msg)
        return {"issues": [], "error": msg}

    nodes = (
        (payload.get("data") or {}).get("searchIssues", {}).get("nodes", [])
    ) or []
    return {"issues": [_normalise_issue(n) for n in nodes], "error": None}


@router.get("/linear/search")
async def linear_search(q: str = "", limit: int = 10) -> dict:
    """Search Linear issues by free-text query for the Chat slash command."""
    q = (q or "").strip()
    if not q:
        return {"query": q, "issues": [], "error": None}
    limit = max(1, min(int(limit), 50))
    result = await asyncio.to_thread(_search_issues, q, limit)
    return {"query": q, "issues": result["issues"], "error": result.get("error")}

