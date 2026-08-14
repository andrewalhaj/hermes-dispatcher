"""
routes/hooks.py — Inbound webhook receivers
============================================
Registered in server.py as: include_router(hooks_router, prefix="/api")
All routes here are therefore under /api/hooks/*.

Current receivers:
  POST /api/hooks/knowledge   — Supabase INSERT trigger on public.knowledge;
                                mirrors the new row to Neo4j.
  POST /api/hooks/figma       — Figma webhook (file update, comment events).
  POST /api/hooks/github      — GitHub webhook (push, PR, issue, review events).
  POST /api/hooks/sentry      — Sentry alert webhook; creates/updates Linear issues
                                and can auto-close resolved issues.
  POST /api/hooks/linear      — Linear webhook (issue create/update/delete, comments).
  POST /api/hooks/kanban      — Kanban card events; syncs status changes to Linear
                                and triggers Sentry auto-close.
  POST /api/hooks/notion      — Notion page update events; syncs to knowledge store.
  POST /api/hooks/notion/sync — Notion poll-based sync trigger.
"""

import asyncio
import json
import os
import re
import subprocess
import uuid
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
HERMES_HOME = Path(os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes")))
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")

# ---------------------------------------------------------------------------
# Assignee validation
# ---------------------------------------------------------------------------
# Live worker profiles that can actually be dispatched. A Kanban card whose
# assignee is not in this set is UNDISPATCHABLE — it silently rots in the
# board. `ha-bot` (deleted 2026-06-25) landing here was exactly that failure
# mode; its home-automation work was folded into `coder` per the same
# decision. Any assignee that falls outside this set is rewritten to
# ASSIGNEE_FALLBACK with a logged warning so no card is ever written with a
# nonexistent profile.
KNOWN_ASSIGNEES = frozenset({"coder", "coder-b", "coder-c", "coder-d", "default"})
ASSIGNEE_FALLBACK = "coder"


def _valid_assignee(assignee: str | None) -> str:
    """Return a dispatchable assignee, coercing unknowns to ASSIGNEE_FALLBACK.

    Guards the Linear intake against writing a card assigned to a profile that
    no longer exists (e.g. the deleted `ha-bot`). Unknown / empty assignees are
    logged at WARNING and rewritten to the fallback so the card can dispatch.
    """
    if isinstance(assignee, str) and assignee in KNOWN_ASSIGNEES:
        return assignee
    logger.warning(
        "assignee %r is not a live worker profile %s — falling back to %r",
        assignee, sorted(KNOWN_ASSIGNEES), ASSIGNEE_FALLBACK,
    )
    return ASSIGNEE_FALLBACK

# Neo4j graph layer — mirrors knowledge facts for relationship traversal.
# Credentials from Hermes .env (NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD).
NEO4J_URI = os.environ.get("NEO4J_URI", "")
NEO4J_USERNAME = os.environ.get("NEO4J_USERNAME", "neo4j")
NEO4J_PASSWORD=os.environ.get("NEO4J_PASSWORD", "")
NEO4J_DATABASE = os.environ.get("NEO4J_DATABASE", "neo4j")
_neo4j_drv = None  # lazy-init singleton


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



# ---------------------------------------------------------------------------
# Neo4j graph layer — mirrors knowledge facts for relationship traversal.
# Creates (:Fact) nodes with [:RELATED_TO] edges to top-3 pgvector neighbors.
# Fire-and-forget: failures are logged, never block the response.
# ---------------------------------------------------------------------------

def _get_neo4j_driver():
    """Lazy-init Neo4j driver singleton."""
    global _neo4j_drv
    if _neo4j_drv is not None:
        return _neo4j_drv
    if not NEO4J_URI or not NEO4J_PASSWORD:
        logger.warning("Neo4j not configured (missing NEO4J_URI or NEO4J_PASSWORD)")
        return None
    try:
        from neo4j import GraphDatabase
        _neo4j_drv = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USERNAME, NEO4J_PASSWORD))
        _init_neo4j(_neo4j_drv)
        logger.info("Neo4j driver initialized: %s", NEO4J_URI)
        return _neo4j_drv
    except Exception as e:
        logger.error("Neo4j driver init failed: %s", e)
        _neo4j_drv = None
        return None


def _init_neo4j(drv) -> None:
    """Ensure Neo4j constraints exist (idempotent)."""
    try:
        with drv.session(database=NEO4J_DATABASE) as s:
            s.run("CREATE CONSTRAINT fact_id IF NOT EXISTS FOR (f:Fact) REQUIRE f.id IS UNIQUE")
            s.run("CREATE CONSTRAINT session_id IF NOT EXISTS FOR (s:Session) REQUIRE s.session_id IS UNIQUE")
            s.run("CREATE INDEX fact_tags IF NOT EXISTS FOR (f:Fact) ON f.tags")
    except Exception as e:
        logger.warning("Neo4j constraint init warning: %s", e)


def _find_similar_via_pgvector(text: str) -> list[dict]:
    """Return up to 3 similar facts with scores from pgvector via knowledge.py search.

    Returns list of {"text": str, "score": float} dicts.
    """
    try:
        clean = re.sub(r"\s+", " ", text.strip())[:80]
        result = subprocess.run(
            ["/usr/local/lib/hermes-agent/venv/bin/python3", str(HERMES_HOME / "scripts/knowledge.py"), "search", clean, "--limit", "3"],
            capture_output=True, text=True, timeout=8,
            env={**os.environ, "HERMES_HOME": str(HERMES_HOME)},
        )
        if result.returncode != 0:
            return []
        # Parse knowledge.py search output — lines with [score] [priority] text
        matches = []
        for line in result.stdout.splitlines():
            line = line.strip()
            # Format: [0.4742] [high] the actual fact text here
            if line.startswith("[") and "] [" in line:
                # Extract score from first bracket
                try:
                    score_str = line[1:].split("]", 1)[0].strip()
                    score = float(score_str)
                except (ValueError, IndexError):
                    score = 0.0
                # Extract text after the second bracket
                rest = line.split("] [", 2)[-1]
                if "] " in rest:
                    text_part = rest.split("] ", 1)[1].strip()
                    if text_part:
                        matches.append({"text": text_part, "score": score})
        return matches[:3]
    except Exception as e:
        logger.warning("pgvector similarity lookup failed: %s", e)
        return []


def _write_to_neo4j(
    text: str,
    tags: list[str] | None = None,
    priority: str = "normal",
    source: str = "unknown",
    context_prefix: str = "",
    session_id: str | None = None,
) -> None:
    """Mirror a fact to Neo4j with [:RELATED_TO] edges to similar facts.

    Args:
        session_id: If provided, creates a [:LEARNED_IN] edge to a Session node.

    Called asynchronously from webhook handlers — never blocks the response.
    """
    drv = _get_neo4j_driver()
    if drv is None:
        return

    tag_list = tags or []
    if isinstance(tag_list, str):
        tag_list = [t.strip() for t in tag_list.split(",") if t.strip()]

    fact_id = hashlib.sha256(text.encode()).hexdigest()[:16]
    stored_at = datetime.now(timezone.utc).isoformat()

    try:
        with drv.session(database=NEO4J_DATABASE) as s:
            # Upsert the fact node (MATCH+CREATE to avoid MERGE constraint race)
            result = s.run(
                "MATCH (f:Fact {id: $id}) RETURN f",
                id=fact_id,
            )
            exists = result.single() is not None
            if exists:
                s.run(
                    """
                    MATCH (f:Fact {id: $id})
                    SET f.text = $text, f.tags = $tags, f.priority = $priority,
                        f.source = $source, f.context_prefix = $context_prefix,
                        f.stored_at = $stored_at
                    """,
                    id=fact_id, text=text, tags=tag_list, priority=priority,
                    source=source, context_prefix=context_prefix, stored_at=stored_at,
                )
            else:
                s.run(
                    """
                    CREATE (f:Fact {id: $id})
                    SET f.text = $text, f.tags = $tags, f.priority = $priority,
                        f.source = $source, f.context_prefix = $context_prefix,
                        f.stored_at = $stored_at
                    """,
                    id=fact_id, text=text, tags=tag_list, priority=priority,
                    source=source, context_prefix=context_prefix, stored_at=stored_at,
                )

            # Find similar facts via pgvector and create RELATED_TO edges
            similar = _find_similar_via_pgvector(text)
            for sim in similar:
                sim_text = sim["text"]
                sim_score = sim["score"]
                sim_id = hashlib.sha256(sim_text.encode()).hexdigest()[:16]
                if sim_id == fact_id:
                    continue
                # MATCH+CREATE for similar node to avoid MERGE constraint race
                sim_result = s.run("MATCH (similar:Fact {id: $id}) RETURN similar", id=sim_id)
                if sim_result.single() is None:
                    s.run("CREATE (similar:Fact {id: $id}) SET similar.text = $text",
                          id=sim_id, text=sim_text)
                # Create edge (MERGE on edge only, nodes already exist)
                s.run(
                    "MATCH (f:Fact {id: $fact_id}), (similar:Fact {id: $sim_id}) "
                    "MERGE (f)-[r:RELATED_TO]->(similar)",
                    fact_id=fact_id, sim_id=sim_id,
                )
                # Contradiction detection: high-similarity but text meaningfully differs
                if (sim_score > 0.85
                        and sim_text.strip().lower() not in text.strip().lower()
                        and text.strip().lower() not in sim_text.strip().lower()):
                    logger.warning(
                        "potential contradiction: new=%s (score=%.3f) vs existing=%s",
                        fact_id[:8], sim_score, sim_id[:8],
                    )

            # If tagged CORRECTION, link superseded facts
            if "CORRECTION" in (t.upper() for t in tag_list):
                for sim in similar:
                    sim_text = sim["text"]
                    sim_id = hashlib.sha256(sim_text.encode()).hexdigest()[:16]
                    if sim_id == fact_id:
                        continue
                    s.run(
                        "MATCH (f:Fact {id: $fact_id}), (old:Fact {id: $old_id}) "
                        "MERGE (f)-[r:SUPERSEDES]->(old)",
                        fact_id=fact_id, old_id=sim_id,
                    )

            # Create LEARNED_IN edge if session_id provided
            if session_id:
                s.run(
                    "MERGE (s:Session {session_id: $session_id}) "
                    "ON CREATE SET s.timestamp = $stored_at",
                    session_id=session_id, stored_at=stored_at,
                )
                s.run(
                    "MATCH (f:Fact {id: $fact_id}), (s:Session {session_id: $session_id}) "
                    "MERGE (f)-[:LEARNED_IN]->(s)",
                    fact_id=fact_id, session_id=session_id,
                )

        logger.info("neo4j: wrote fact %s with %d related", fact_id, len(similar))
    except Exception as e:
        logger.error("neo4j write failed for fact %s: %s", fact_id, e)


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

    Mirrors the new row to Neo4j for relationship traversal.
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

    logger.info(
        "knowledge webhook: row=%s ts=%s",
        row_id,
        datetime.now(timezone.utc).isoformat()
    )

    # Mirror to Neo4j graph layer (fire-and-forget)
    try:
        _write_to_neo4j(text=text, tags=tags, priority="normal", source="supabase-webhook",
                         context_prefix=str(row_id or ""))
    except Exception as e:
        logger.warning("neo4j mirror failed (non-fatal): %s", e)

    return {"status": "processed", "row_id": row_id}


# ---------------------------------------------------------------------------
# Figma webhook — receives FILE_UPDATE events, fetches design tokens.
#
# Auth: passcode in request body (Figma's shared-secret model).
# On FILE_UPDATE / FILE_VERSION_UPDATE: fetches file variables via REST API,
# stores tokens in knowledge store + Neo4j.
# The endpoint is exempt from the session-cookie auth gate.
# ---------------------------------------------------------------------------

FIGMA_ACCESS_TOKEN = os.environ.get("FIGMA_ACCESS_TOKEN", "")
FIGMA_WEBHOOK_PASSCODE=os.environ.get("FIGMA_WEBHOOK_PASSCODE", "")
FIGMA_API_BASE = "https://api.figma.com/v1"


@router.post("/figma")
async def figma_webhook(request: Request):
    """Receive Figma webhook events (FILE_UPDATE, FILE_VERSION_UPDATE, etc.)."""
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    event_type = payload.get("event_type", "")
    passcode = payload.get("passcode", "")

    # Verify passcode
    if not FIGMA_WEBHOOK_PASSCODE or not hmac.compare_digest(
        passcode.encode(), FIGMA_WEBHOOK_PASSCODE.encode()
    ):
        logger.warning("figma webhook: invalid passcode")
        raise HTTPException(status_code=401, detail="Invalid passcode")

    # PING — Figma's initial endpoint verification
    if event_type == "PING":
        logger.info("figma webhook: PING received")
        return {"status": "ok"}

    file_key = payload.get("file_key", "")
    file_name = payload.get("file_name", "")
    timestamp = payload.get("timestamp", "")

    logger.info("figma webhook: event=%s file=%s (%s)", event_type, file_name, file_key)

    # Only act on file update events
    if event_type not in ("FILE_UPDATE", "FILE_VERSION_UPDATE"):
        return {"status": "ignored", "event_type": event_type}

    # Fetch variables from Figma
    if not FIGMA_ACCESS_TOKEN:
        return {"status": "error", "reason": "FIGMA_ACCESS_TOKEN not configured"}

    try:
        tokens = await _fetch_figma_styles(file_key)
    except Exception as e:
        logger.error("figma webhook: fetch failed for %s: %s", file_key, e)
        return {"status": "error", "reason": str(e)[:200]}

    if not tokens:
        return {"status": "skipped", "reason": "no_variables"}

    # Store tokens in knowledge store + Neo4j
    try:
        summary = f"Figma design tokens from {file_name} ({file_key}) at {timestamp}: {tokens}"
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, lambda: subprocess.run(
            [
                "/usr/local/lib/hermes-agent/venv/bin/python3",
                str(HERMES_HOME / "scripts/knowledge.py"), "store",
                "--text", summary,
                "--tags", "figma,design-tokens",
                "--source", "figma-webhook",
                "--priority", "high",
            ],
            capture_output=True, text=True, timeout=15,
            env={**os.environ, "HERMES_HOME": str(HERMES_HOME)},
        ))
        store_id = result.stdout.strip() if result.returncode == 0 else None

        # Mirror to Neo4j
        _write_to_neo4j(
            text=summary, tags=["figma", "design-tokens"],
            priority="high", source="figma-webhook",
            context_prefix=file_key,
        )

        logger.info("figma webhook: stored tokens for %s id=%s", file_key, store_id)
        return {"status": "stored", "knowledge_id": store_id, "file_key": file_key}
    except Exception as e:
        logger.error("figma webhook: store failed: %s", e)
        return {"status": "error", "reason": str(e)[:200]}


async def _fetch_figma_styles(file_key: str) -> str:
    """Fetch design styles (FILL colors + TEXT typography) from Figma REST API.
    Returns condensed token summary suitable for knowledge store storage."""
    import aiohttp

    headers = {"X-FIGMA-TOKEN": FIGMA_ACCESS_TOKEN}

    async with aiohttp.ClientSession() as session:
        # Step 1: list all styles
        async with session.get(
            f"{FIGMA_API_BASE}/files/{file_key}/styles",
            headers=headers, timeout=aiohttp.ClientTimeout(total=10)
        ) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise Exception(f"Figma styles list {resp.status}: {text[:200]}")
            styles_data = await resp.json()

        styles = styles_data.get("meta", {}).get("styles", [])
        if not styles:
            return ""

        # Collect node_ids that carry style values
        fill_node_ids: list[str] = []
        text_node_ids: list[str] = []
        id_to_name: dict[str, str] = {}
        id_to_type: dict[str, str] = {}

        for s in styles:
            nid = s.get("node_id", "")
            stype = s.get("style_type", "")
            name = s.get("name", nid)
            id_to_name[nid] = name
            id_to_type[nid] = stype
            if stype == "FILL":
                fill_node_ids.append(nid)
            elif stype == "TEXT":
                text_node_ids.append(nid)

        # Step 2: batch-fetch nodes for their resolved values
        tokens: list[str] = []

        if fill_node_ids:
            ids_param = ",".join(fill_node_ids[:20])
            async with session.get(
                f"{FIGMA_API_BASE}/files/{file_key}/nodes?ids={ids_param}",
                headers=headers, timeout=aiohttp.ClientTimeout(total=15)
            ) as resp:
                if resp.status == 200:
                    nodes_data = await resp.json()
                    for nid, ndata in nodes_data.get("nodes", {}).items():
                        doc = ndata.get("document", {})
                        fills = doc.get("fills", [])
                        for f in fills:
                            color = f.get("color")
                            if color:
                                rv = int(color.get("r", 0) * 255)
                                gv = int(color.get("g", 0) * 255)
                                bv = int(color.get("b", 0) * 255)
                                alpha = color.get("a", 1)
                                name = id_to_name.get(nid, nid)
                                tokens.append(f"{name}: #{rv:02x}{gv:02x}{bv:02x} (COLOR)")

        if text_node_ids:
            ids_param = ",".join(text_node_ids[:20])
            async with session.get(
                f"{FIGMA_API_BASE}/files/{file_key}/nodes?ids={ids_param}",
                headers=headers, timeout=aiohttp.ClientTimeout(total=15)
            ) as resp:
                if resp.status == 200:
                    nodes_data = await resp.json()
                    for nid, ndata in nodes_data.get("nodes", {}).items():
                        doc = ndata.get("document", {})
                        style = doc.get("style", {})
                        name = id_to_name.get(nid, nid)
                        font_family = style.get("fontFamily", "")
                        font_size = style.get("fontSize", "")
                        font_weight = style.get("fontWeight", "")
                        if font_family or font_size:
                            tokens.append(f"{name}: {font_family} {font_size}/{font_weight} (TEXT)")

        return "; ".join(tokens)


# ---------------------------------------------------------------------------
# GitHub webhook — receives issue, PR, and push events.
#
# Auth: X-Hub-Signature-256 (HMAC-SHA256 of raw body).
# Routes events to handlers that bridge into the agent ecosystem.
# The endpoint is exempt from the session-cookie auth gate.
# ---------------------------------------------------------------------------

GITHUB_WEBHOOK_SECRET = os.environ.get("GITHUB_WEBHOOK_SECRET", "")


@router.post("/github")
async def github_webhook(request: Request):
    """Receive GitHub webhook events."""
    event = request.headers.get("X-GitHub-Event", "")
    event_id = request.headers.get("X-GitHub-Delivery", "")
    signature = request.headers.get("X-Hub-Signature-256", "")

    # Verify signature
    if not GITHUB_WEBHOOK_SECRET:
        raise HTTPException(status_code=503, detail="GitHub webhook secret not configured")

    body = await request.body()
    expected = "sha256=" + hmac.new(
        GITHUB_WEBHOOK_SECRET.encode(), body, hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(expected, signature):
        logger.warning("github webhook: invalid signature for event %s id=%s", event, event_id)
        raise HTTPException(status_code=401, detail="Invalid signature")

    try:
        payload = json.loads(body)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    logger.info("github webhook: event=%s id=%s", event, event_id)

    if event == "ping":
        return {"status": "ok", "zen": payload.get("zen", "")}

    handler = _GITHUB_HANDLERS.get(event)
    if handler:
        return await handler(payload)

    return {"status": "unhandled", "event": event}


async def _handle_issues(payload: dict) -> dict:
    """GitHub issue event → knowledge store fact."""
    action = payload.get("action", "")
    issue = payload.get("issue", {})
    repo = payload.get("repository", {}).get("full_name", "")
    number = issue.get("number", "?")
    title = issue.get("title", "")
    url = issue.get("html_url", "")

    if action == "opened":
        fact = f"Issue #{number} opened in {repo}: {title}"
    elif action == "closed":
        fact = f"Issue #{number} closed in {repo}: {title}"
    elif action == "labeled":
        label = payload.get("label", {}).get("name", "")
        fact = f"Issue #{number} in {repo} labeled '{label}': {title}"
    else:
        fact = f"Issue #{number} {action} in {repo}: {title}"

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, lambda: subprocess.run(
        [
            "/usr/local/lib/hermes-agent/venv/bin/python3",
            str(HERMES_HOME / "scripts/knowledge.py"), "store",
            "--text", fact,
            "--tags", "github,issue",
            "--source", "github-webhook",
            "--priority", "normal",
            "--context-prefix", url,
        ],
        capture_output=True, text=True, timeout=10,
        env={**os.environ, "HERMES_HOME": str(HERMES_HOME)},
    ))
    logger.info("github webhook: stored issue #%s %s", number, action)
    return {"status": "stored", "issue": number, "action": action}


async def _handle_pull_request(payload: dict) -> dict:
    """GitHub PR event → knowledge store fact."""
    action = payload.get("action", "")
    pr = payload.get("pull_request", {})
    repo = payload.get("repository", {}).get("full_name", "")
    number = pr.get("number", "?")
    title = pr.get("title", "")
    url = pr.get("html_url", "")
    merged = pr.get("merged", False)

    if action == "opened":
        fact = f"PR #{number} opened in {repo}: {title}"
    elif action == "closed" and merged:
        fact = f"PR #{number} merged in {repo}: {title}"
    elif action == "closed":
        fact = f"PR #{number} closed without merge in {repo}: {title}"
    else:
        fact = f"PR #{number} {action} in {repo}: {title}"

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, lambda: subprocess.run(
        [
            "/usr/local/lib/hermes-agent/venv/bin/python3",
            str(HERMES_HOME / "scripts/knowledge.py"), "store",
            "--text", fact,
            "--tags", "github,pr",
            "--source", "github-webhook",
            "--priority", "high" if merged else "normal",
            "--context-prefix", url,
        ],
        capture_output=True, text=True, timeout=10,
        env={**os.environ, "HERMES_HOME": str(HERMES_HOME)},
    ))
    logger.info("github webhook: stored PR #%s %s", number, action)
    return {"status": "stored", "pr": number, "action": action}


async def _handle_push(payload: dict) -> dict:
    """GitHub push event → knowledge store fact."""
    ref = payload.get("ref", "").replace("refs/heads/", "")
    repo = payload.get("repository", {}).get("full_name", "")
    commits = payload.get("commits", [])
    pusher = payload.get("pusher", {}).get("name", "unknown")
    count = len(commits)

    if count == 0:
        return {"status": "skipped", "reason": "no_commits"}

    latest = commits[-1].get("message", "").split("\n")[0][:80]
    fact = f"Push to {repo}/{ref}: {count} commit(s) by {pusher} — {latest}"

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, lambda: subprocess.run(
        [
            "/usr/local/lib/hermes-agent/venv/bin/python3",
            str(HERMES_HOME / "scripts/knowledge.py"), "store",
            "--text", fact,
            "--tags", "github,push",
            "--source", "github-webhook",
            "--priority", "low",
            "--context-prefix", f"{repo}/{ref}",
        ],
        capture_output=True, text=True, timeout=10,
        env={**os.environ, "HERMES_HOME": str(HERMES_HOME)},
    ))
    logger.info("github webhook: stored push to %s/%s", repo, ref)
    return {"status": "stored", "repo": repo, "ref": ref, "commits": count}


_GITHUB_HANDLERS = {
    "issues": _handle_issues,
    "pull_request": _handle_pull_request,
    "push": _handle_push,
}


# ---------------------------------------------------------------------------
# Sentry webhook — receives issue alert events.
#
# Auth: Sentry-Hook-Signature (HMAC-SHA256 of raw body).
# On issue events (created, resolved, assigned, etc.), stores to knowledge
# store and delivers to Telegram via the dispatcher's notify channel.
# ---------------------------------------------------------------------------

_SKEY = "SENTRY" + "_WEBHOOK_SECRET"
SENTRY_WEBHOOK_SECRET = os.environ.get(_SKEY, "")
_TCHAT = "SENTRY_TELEGRAM_CHAT"
# Default: empty string — Andrew must set SENTRY_TELEGRAM_CHAT in .env to a new
# Telegram group/chat ID dedicated to sentry alerts.  The old cron-notify chat
# (-1003947663220) should NOT be reused; create a separate Telegram group for
# sentry alerts and put its chat ID here.
SENTRY_TELEGRAM_CHAT = os.environ.get(_TCHAT, "")
LINEAR_API_KEY = os.environ.get("LINEAR_API_KEY", "")
_SENTRY_MSGS_FILE = Path(__file__).resolve().parent.parent / "data" / "sentry_messages.json"
_SENTRY_LINEAR_MAP_FILE = Path(__file__).resolve().parent.parent / "data" / "sentry_linear_map.json"
_LINEAR_TEAM_ID = "38a0c106-e9a8-4f65-84d2-ec8bdc61855d"
_LINEAR_REPORTS_FILE = Path(__file__).resolve().parent.parent / "data" / "linear_reports.json"


def _append_linear_report(msg: dict) -> None:
    """Append a routed-Linear-issue report to the JSON file (dashboard data source)."""
    try:
        _LINEAR_REPORTS_FILE.parent.mkdir(parents=True, exist_ok=True)
        messages: list = []
        if _LINEAR_REPORTS_FILE.exists():
            try:
                messages = json.loads(_LINEAR_REPORTS_FILE.read_text(errors="ignore"))
            except Exception:
                messages = []
        if not isinstance(messages, list):
            messages = []
        messages.append(msg)
        # Keep the last 200 messages
        if len(messages) > 200:
            messages = messages[-200:]
        _LINEAR_REPORTS_FILE.write_text(json.dumps(messages, indent=2), encoding="utf-8")
    except Exception as e:
        logger.warning("linear webhook: failed to append report to %s: %s",
                       _LINEAR_REPORTS_FILE, e)


def _append_sentry_message(msg: dict) -> None:
    """Append a sentry alert message to the JSON file (dashboard data source)."""
    try:
        _SENTRY_MSGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        messages: list = []
        if _SENTRY_MSGS_FILE.exists():
            try:
                messages = json.loads(_SENTRY_MSGS_FILE.read_text(errors="ignore"))
            except Exception:
                messages = []
        if not isinstance(messages, list):
            messages = []
        messages.append(msg)
        # Keep the last 200 messages
        if len(messages) > 200:
            messages = messages[-200:]
        _SENTRY_MSGS_FILE.write_text(json.dumps(messages, indent=2), encoding="utf-8")
    except Exception as e:
        logger.warning("sentry webhook: failed to append message to %s: %s",
                       _SENTRY_MSGS_FILE, e)


@router.post("/sentry")
async def sentry_webhook(request: Request):
    """Receive Sentry issue alert webhook events."""
    signature = request.headers.get("Sentry-Hook-Signature", "")

    if not SENTRY_WEBHOOK_SECRET:
        raise HTTPException(status_code=503, detail="Sentry webhook secret not configured")

    body = await request.body()
    expected = hmac.new(
        SENTRY_WEBHOOK_SECRET.encode(), body, hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(expected, signature):
        logger.warning("sentry webhook: invalid signature")
        raise HTTPException(status_code=401, detail="Invalid signature")

    try:
        payload = json.loads(body)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    action = payload.get("action", "")
    data = payload.get("data", {})
    event_data = data.get("event", data.get("issue", data.get("error", {}))) if isinstance(data, dict) else {}

    tags = event_data.get("tags", []) if isinstance(event_data, dict) else []

    # Sentry issue id — propagated into the Linear issue description so it flows
    # verbatim into the Kanban card body, where routes/sentry_autoclose.py picks
    # it up at card-completion time to resolve the issue. Sentry nests the issue
    # under different keys depending on resource (issue vs event/error payloads).
    sentry_issue_id = (
        (event_data.get("issue", {}) or {}).get("id")
        if isinstance(event_data, dict) else None
    )
    sentry_issue_id = (
        sentry_issue_id
        or (data.get("issue", {}) or {}).get("id")
        or event_data.get("issue_id")
        or event_data.get("groupID")
        or event_data.get("id")
        or ""
    )
    sentry_issue_id = str(sentry_issue_id).strip()

    issue_title = (
        event_data.get("title", "")
        or data.get("issue", {}).get("title", "")
        or event_data.get("culprit", "")
        or (event_data.get("exception") or {}).get("values", [{}])[0].get("value", "")
        or next((v for k, v in tags if k == "transaction"), "")
        or "Unknown error"
    )
    issue_url = data.get("issue_url", "") or event_data.get("web_url", "")

    raw_project = data.get("project_name", "")
    project_obj = event_data.get("project", {})
    if isinstance(project_obj, dict):
        raw_project = raw_project or project_obj.get("name", "")
    project = (
        raw_project
        or next((v for k, v in tags if k == "server_name"), "")
        or "hermes"
    )

    level = event_data.get("level", "") or next((v for k, v in tags if k == "level"), "error")

    logger.info("sentry webhook: action=%s project=%s title=%s", action, project, issue_title[:80])

    if not project or not issue_title:
        logger.warning("sentry webhook: empty project/title, raw payload: %s", json.dumps(payload)[:2000])

    # Build fact + telegram message
    if action == "created":
        emoji = "🚨"
        fact = f"Sentry alert in {project}: {issue_title} ({level})"
    elif action == "resolved":
        emoji = "✅"
        fact = f"Sentry resolved in {project}: {issue_title}"
    elif action == "assigned":
        assignee = event_data.get("assignedTo", {}).get("name", "someone")
        emoji = "👤"
        fact = f"Sentry assigned to {assignee}: {issue_title}"
    elif action == "archived":
        emoji = "📦"
        fact = f"Sentry archived in {project}: {issue_title}"
    else:
        emoji = "📊"
        fact = f"Sentry {action} in {project}: {issue_title}"

    telegram_msg = f"{emoji} **Sentry** — {project}\n{issue_title}\n{issue_url}" if issue_url else f"{emoji} **Sentry** — {project}\n{issue_title}"

    # Append to sentry_messages.json for dashboard Chat panel "Sentry" channel
    _append_sentry_message({
        "role": "agent",
        "content": f"{emoji} **{project}** — {action}: {issue_title}",
        "created_at": datetime.now(timezone.utc).timestamp(),
        "project": project or "",
        "level": level,
        "action": action,
        "issue_url": issue_url or "",
    })

    # Route NEW Sentry issues through Linear → webhook → Kanban for clean cards + auto-dispatch
    # Deduplicate by Sentry issue ID: if a Linear issue already exists for this
    # Sentry issue, add a comment instead of creating a duplicate.
    if action == "created" and sentry_issue_id:
        try:
            # Load the Sentry→Linear issue ID map
            try:
                with open(_SENTRY_LINEAR_MAP_FILE, "r") as _f:
                    _sentry_linear_map = json.load(_f)
            except (FileNotFoundError, json.JSONDecodeError):
                _sentry_linear_map = {}

            existing_linear_id = _sentry_linear_map.get(sentry_issue_id)

            import aiohttp
            async with aiohttp.ClientSession() as session:
                if existing_linear_id:
                    # Issue already exists — add a comment with the new occurrence info
                    comment_query = """
                    mutation($input: CommentCreateInput!) {
                      commentCreate(input: $input) {
                        success
                        comment { id }
                      }
                    }
                    """
                    async with session.post(
                        "https://api.linear.app/graphql",
                        headers={
                            "Authorization": LINEAR_API_KEY,
                            "Content-Type": "application/json",
                        },
                        json={
                            "query": comment_query,
                            "variables": {
                                "input": {
                                    "issueId": existing_linear_id,
                                    "body": f"**New occurrence** — {issue_title} ({level})\n- **URL:** {issue_url}",
                                }
                            },
                        },
                        timeout=aiohttp.ClientTimeout(total=5),
                    ) as resp:
                        # Linear returns HTTP 200 even for application-level
                        # failures (rate/usage limits, validation): the error is
                        # carried in the GraphQL ``errors`` array, not the status
                        # code. Inspect it explicitly so failures are never
                        # silently swallowed.
                        c_result = await resp.json()
                    c_errors = c_result.get("errors")
                    c_ok = ((c_result.get("data") or {}).get("commentCreate") or {}).get("success")
                    if c_errors or not c_ok:
                        logger.error(
                            "sentry webhook: Linear commentCreate FAILED for Sentry issue %s (existing Linear %s, http=%s): %s",
                            sentry_issue_id, existing_linear_id, resp.status,
                            json.dumps(c_errors or c_result)[:1000],
                        )
                    else:
                        logger.info("sentry webhook: added comment to existing Linear issue %s for Sentry issue %s", existing_linear_id, sentry_issue_id)
                else:
                    # No existing issue — create a new one
                    linear_query = """
                    mutation($input: IssueCreateInput!) {
                      issueCreate(input: $input) {
                        success
                        issue { id identifier title url }
                      }
                    }
                    """
                    async with session.post(
                        "https://api.linear.app/graphql",
                        headers={
                            "Authorization": LINEAR_API_KEY,
                            "Content-Type": "application/json",
                        },
                        json={
                            "query": linear_query,
                            "variables": {
                                "input": {
                                    "teamId": _LINEAR_TEAM_ID,
                                    "title": f"[Sentry] {project}: {issue_title}" if project else f"[Sentry] {issue_title}",
                                    "description": f"**Sentry Alert**\n\n- **Project:** {project}\n- **Level:** {level}\n- **URL:** {issue_url}" + (f"\n\nsentry-issue-id:{sentry_issue_id}" if sentry_issue_id else ""),
                                    "priority": 1,  # High — Sentry alerts are urgent
                                }
                            },
                        },
                        timeout=aiohttp.ClientTimeout(total=5),
                    ) as resp:
                        result = await resp.json()
                        # Linear returns HTTP 200 even when the mutation fails:
                        # usage/rate limits and validation errors arrive as a
                        # GraphQL ``errors`` array with ``data: null``. Reading
                        # only result["data"] silently drops these (the original
                        # bug — an over-quota workspace returned USAGE_LIMIT_EXCEEDED
                        # and nothing was ever logged or mapped).
                        errors = result.get("errors")
                        new_issue = ((result.get("data") or {}).get("issueCreate") or {}).get("issue") or {}
                        if new_issue and new_issue.get("id"):
                            _sentry_linear_map[sentry_issue_id] = new_issue["id"]
                            with open(_SENTRY_LINEAR_MAP_FILE, "w") as _f:
                                json.dump(_sentry_linear_map, _f)
                            logger.info("sentry webhook: created Linear issue %s for Sentry issue %s", new_issue["id"], sentry_issue_id)
                        else:
                            logger.error(
                                "sentry webhook: Linear issueCreate FAILED for Sentry issue %s (project=%s, http=%s) — NO issue created, NO map entry: %s",
                                sentry_issue_id, project, resp.status,
                                json.dumps(errors or result)[:1000],
                            )
        except Exception as exc:
            logger.warning("sentry webhook: Linear issue creation failed: %s", exc)

    # Fire-and-forget to Telegram via the dashboard's notify endpoint
    if SENTRY_TELEGRAM_CHAT:
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"http://127.0.0.1:8787/api/hooks/notify",
                    json={
                        "chat_id": SENTRY_TELEGRAM_CHAT,
                        "text": telegram_msg,
                        "parse_mode": "Markdown",
                    },
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as resp:
                    # Consume/release the response body so the connection is
                    # returned cleanly to the pool.
                    await resp.read()
        except Exception as exc:
            logger.warning("sentry webhook: telegram notify failed: %s", exc)

    return {"status": "stored", "action": action, "project": project}

# ---------------------------------------------------------------------------
# LINEAR webhook
# Receives issue/comment/project events from Linear, stores to knowledge
# store, optionally creates Kanban cards, and delivers to Telegram.
# ---------------------------------------------------------------------------

_LKEY = "LINEAR" + "_WEBHOOK_SECRET"
LINEAR_WEBHOOK_SECRET = os.environ.get(_LKEY, "")
_LTCHAT = "LINEAR_TELEGRAM_CHAT"
LINEAR_TELEGRAM_CHAT = os.environ.get(_LTCHAT, "")

LINEAR_TIMESTAMP_WINDOW = 120  # seconds


@router.post("/linear")
async def linear_webhook(request: Request):
    """Receive Linear webhook events."""
    signature = request.headers.get("Linear-Signature", "")
    delivery = request.headers.get("Linear-Delivery", "unknown")

    if not LINEAR_WEBHOOK_SECRET:
        raise HTTPException(status_code=503, detail="Linear webhook secret not configured")

    body = await request.body()
    expected = hmac.new(
        LINEAR_WEBHOOK_SECRET.encode(), body, hashlib.sha256
    ).hexdigest()

    # Linear sends hex-encoded HMAC — compare hex strings
    if not hmac.compare_digest(expected.encode(), signature.encode()):
        logger.warning("linear webhook: invalid signature (delivery=%s, expected=%s...%s, got=%s...%s)",
                       delivery, expected[:8], expected[-8:], signature[:8] if len(signature)>=8 else signature, signature[-8:] if len(signature)>=8 else signature)
        raise HTTPException(status_code=401, detail="Invalid signature")

    try:
        payload = json.loads(body)
    except Exception:
        logger.warning("linear webhook: invalid JSON (delivery=%s)", delivery)
        raise HTTPException(status_code=400, detail="Invalid JSON")

    # Timestamp check — guard against replay attacks
    ts = payload.get("webhookTimestamp", 0)
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    if abs(now_ms - ts) > LINEAR_TIMESTAMP_WINDOW * 1000:
        logger.warning("linear webhook: stale timestamp (delivery=%s, diff=%dms)",
                       delivery, abs(now_ms - ts))
        raise HTTPException(status_code=401, detail="Stale timestamp")

    action = payload.get("action", "")
    entity_type = payload.get("type", "")
    data = payload.get("data", {})
    actor = payload.get("actor", {})
    url = payload.get("url", "")

    actor_name = actor.get("name", "someone") if isinstance(actor, dict) else str(actor)
    entity_title = data.get("title", "") if isinstance(data, dict) else ""

    logger.info("linear webhook: action=%s type=%s title=%s (delivery=%s)",
                action, entity_type, entity_title[:80], delivery)

    # Build fact + telegram message
    if entity_type == "Issue" and action == "create":
        emoji = "🟣"
        fact = f"Linear issue created: {entity_title}"
    elif entity_type == "Issue" and action == "update":
        emoji = "🔄"
        fact = f"Linear issue updated: {entity_title}"
    elif entity_type == "Issue" and action == "remove":
        emoji = "🗑️"
        fact = f"Linear issue removed: {entity_title}"
    elif entity_type == "Comment" and action == "create":
        body_snippet = (data.get("body", "") or "")[:100] if isinstance(data, dict) else ""
        emoji = "💬"
        fact = f"Linear comment: {body_snippet}"
    elif entity_type == "Project" and action == "create":
        emoji = "📁"
        fact = f"Linear project created: {entity_title}"
    else:
        emoji = "📊"
        fact = f"Linear {action} {entity_type}: {entity_title}"

    telegram_msg = f"{emoji} **Linear** — {entity_type}\n{entity_title or fact}\n{url}" if url else f"{emoji} **Linear**\n{fact}"

    # Bidirectional comment sync: mirror a NEW Linear issue comment onto the
    # linked Kanban card. handle_inbound_linear_comment is loop-safe (it skips
    # comments that carry our own outbound marker) and never raises.
    if entity_type == "Comment" and action == "create":
        try:
            from routes.linear_sync import handle_inbound_linear_comment
            sync_result = handle_inbound_linear_comment(data, actor_name)
            logger.info("linear webhook: comment sync → %s", sync_result)
        except Exception as exc:
            logger.warning("linear webhook: inbound comment sync failed: %s", exc)

    # Linear acts as the intake funnel — all issues route autonomously (Pattern B)
    if entity_type == "Issue" and action == "create" and entity_title:
        # Map Linear priority to Kanban priority (higher = picked first by dispatcher)
        linear_priority = data.get("priority", 4) if isinstance(data, dict) else 4
        # Linear: 0=urgent, 1=high, 2=medium, 3=low, 4=none
        # Kanban: higher = first. Map: 0→50, 1→30, 2→10, 3→5, 4→1
        kanban_priority = {0: 50, 1: 30, 2: 10, 3: 5}.get(linear_priority, 1)

        # Round-robin across coder fleet. Draw only from KNOWN_ASSIGNEES so the
        # pool can never drift out of the dispatchable set, then pass through the
        # validation guard as a belt-and-suspenders check before the card is
        # written (no card may carry a nonexistent profile — see _valid_assignee).
        import random
        coders = [p for p in ("coder", "coder-b", "coder-c", "coder-d") if p in KNOWN_ASSIGNEES]
        assignee = _valid_assignee(random.choice(coders) if coders else ASSIGNEE_FALLBACK)

        description = data.get("description", "") if isinstance(data, dict) else ""
        kanban_body = (
            f"**Linear Issue** (autonomous intake)\n\n"
            f"- **Title:** {entity_title}\n"
            f"- **Author:** {actor_name}\n"
            f"- **Priority:** {kanban_priority}\n"
            f"- **URL:** {url}\n"
            f"- **Assignee:** {assignee}\n"
        )
        if description:
            kanban_body += f"\n{description[:500]}"

        try:
            import sqlite3 as _sqlite3

            # idempotency: one Linear issue = one Kanban card
            linear_issue_id = data.get("id", "") if isinstance(data, dict) else ""
            idempotency_key = f"linear-{linear_issue_id}" if linear_issue_id else ""

            _task_id = "t_" + uuid.uuid4().hex[:8]
            _now = int(datetime.now(timezone.utc).timestamp())
            _db_path = os.environ.get("KANBAN_DB", os.path.expanduser("~/.hermes/kanban.db"))
            _conn = _sqlite3.connect(_db_path)
            try:
                if idempotency_key:
                    existing = _conn.execute(
                        "SELECT id FROM tasks WHERE idempotency_key = ? AND status NOT IN ('done','archived')",
                        (idempotency_key,),
                    ).fetchone()
                    if existing:
                        logger.info("linear webhook: duplicate '%s' (existing=%s key=%s)",
                                   entity_title[:60], existing[0], idempotency_key)
                        return {"status": "duplicate", "existing_id": existing[0]}

                _conn.execute(
                    "INSERT INTO tasks (id, title, body, status, priority, created_by, created_at, tenant, assignee, idempotency_key) "
                    "VALUES (?, ?, ?, 'triage', ?, 'linear-webhook', ?, NULL, ?, ?)",
                    (_task_id, entity_title, kanban_body, kanban_priority, _now, assignee, idempotency_key or None),
                )
                _conn.commit()
                logger.info("linear webhook: dispatched '%s' (id=%s priority %d)",
                           entity_title[:60], _task_id, kanban_priority)
                # Post to the dashboard "Linear Reports" chat channel
                _append_linear_report({
                    "role": "agent",
                    "content": f"🟣 **{entity_title}** → {assignee} (priority {kanban_priority})",
                    "created_at": datetime.now(timezone.utc).timestamp(),
                    "title": entity_title,
                    "priority": kanban_priority,
                    "coder": assignee,
                    "issue_url": url or "",
                    "task_id": _task_id,
                })
            finally:
                _conn.close()
        except Exception as exc:
            logger.warning("linear webhook: kanban dispatch failed: %s", exc)

    # Fire-and-forget to Telegram
    if LINEAR_TELEGRAM_CHAT:
        try:
            import aiohttp
            # Bind the response in `async with` so its underlying connection is
            # released back to the connector BEFORE the session closes. Without
            # this, `await session.post(...)` leaves the response (and its socket)
            # unreleased, and aiohttp emits "Unclosed connection" when the session
            # tears down — the leak Sentry reported as HERMES-DISPATCHER-6.
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "http://127.0.0.1:8787/api/hooks/notify",
                    json={"chat_id": LINEAR_TELEGRAM_CHAT, "text": telegram_msg, "parse_mode": "Markdown"},
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as resp:
                    # Consume/release the response body so the connection is
                    # returned cleanly to the pool.
                    await resp.read()
            logger.debug("linear webhook: telegram notify connection released (delivery=%s)", delivery)
        except Exception as exc:
            logger.warning("linear webhook: telegram notify failed: %s", exc)

    return {"status": "stored", "action": action, "type": entity_type}


# ---------------------------------------------------------------------------
# KANBAN webhook — fires when a Kanban card transitions to "done".
# Auto-closes the originating Linear issue (the reverse direction of the
# Linear → Kanban intake funnel above). Works for BOTH webhook-created cards
# (idempotency_key = "linear-<uuid>") and manually dispatched cards (Linear
# identifier or URL embedded in the card body/title).
#
# This endpoint is the programmatic trigger for any automation that marks a
# card done outside the dashboard (the kanban core / CLI / cron). The
# dashboard's own "drag to Done" path calls the same orchestrator directly
# from routes/kanban.py:patch_task, so both surfaces converge on one
# idempotent, exception-safe closer (routes/linear_autoclose.py).
#
# Auth: Bearer token matched against WEBHOOK_SECRET (same gate as /knowledge).
# Always returns 200 on our own logic errors so the caller never retry-spams.
# ---------------------------------------------------------------------------

@router.post("/kanban")
async def kanban_webhook(request: Request):
    """Receive a Kanban card status-change event and auto-close Linear.

    Expected payload:
        {
          "task_id": "t_abc123",        # required
          "status":  "done",            # optional; defaults to "done"
          "event":   "completed"        # optional alias for status
        }

    Only ``status == "done"`` (or ``event in {completed, done}``) triggers the
    Linear close. Anything else is accepted but ignored, so the caller can fire
    this on every status change without filtering.
    """
    _verify_bearer(request)

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Invalid JSON payload")

    task_id = (payload.get("task_id") or payload.get("id") or "").strip()
    new_status = (payload.get("status") or "").strip().lower()
    event = (payload.get("event") or "").strip().lower()

    if not task_id:
        return {"status": "skipped", "reason": "missing_task_id"}

    is_done = new_status == "done" or event in ("completed", "done")
    if not is_done:
        return {"status": "ignored", "reason": "not_a_done_event",
                "task_id": task_id, "received_status": new_status or event}

    try:
        from routes.linear_autoclose import autoclose_for_card
        result = autoclose_for_card(task_id)
    except Exception as exc:  # noqa: BLE001 — always 200 to the caller
        logger.warning("kanban webhook: autoclose failed for %s: %s", task_id, exc)
        return {"status": "error", "reason": str(exc)[:160], "task_id": task_id}

    # Sentry sibling: resolve the Sentry issue behind the card too (independent
    # of the Linear close — a card may carry one, both, or neither reference).
    sentry_result = None
    try:
        from routes.sentry_autoclose import autoclose_sentry_for_card
        sentry_result = autoclose_sentry_for_card(task_id)
    except Exception as exc:  # noqa: BLE001 — always 200 to the caller
        logger.warning("kanban webhook: sentry autoclose failed for %s: %s", task_id, exc)
        sentry_result = {"status": "error", "reason": str(exc)[:160]}

    logger.info("kanban webhook: task=%s autoclose=%s sentry=%s",
                task_id, result.get("status"),
                (sentry_result or {}).get("status"))
    if sentry_result is not None:
        result["sentry"] = sentry_result
    return result


# ---------------------------------------------------------------------------
# Notion webhook — receives page update events, syncs to knowledge store.
#
# As of 2025, Notion supports outgoing webhooks. This endpoint accepts:
#   - Manual POST from Hermes agents when they update Notion pages
#   - Poll-based sync triggers that fetch recently-edited pages
#   - Genuine Notion outgoing webhook payloads
#
# Auth: Bearer token (NOTION_WEBHOOK_SECRET).
# ---------------------------------------------------------------------------

NOTION_API_KEY = os.environ.get("NOTION_API_KEY", "")
NOTION_WEBHOOK_SECRET = os.environ.get("NOTION_WEBHOOK_SECRET", os.environ.get("NOTION_API_KEY", ""))
NOTION_API_BASE = "https://api.notion.com/v1"
NOTION_VERSION = "2025-09-03"


@router.post("/notion")
async def notion_webhook(request: Request):
    """Receive Notion page update events or manual sync triggers.

    Payload:
        {
          "action": "page_updated" | "sync" | "ping",
          "page_id": "<uuid>",
          "page_title": "<str>",
          "url": "<str>"
        }
    """
    _verify_notion(request)

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    action = payload.get("action", "")
    page_id = payload.get("page_id", "")
    page_title = payload.get("page_title", "")
    url = payload.get("url", "")

    logger.info("notion webhook: action=%s page=%s title=%s",
                action, page_id, page_title[:80] if page_title else "(none)")

    # PING — health check
    if action == "ping":
        return {"status": "ok", "workspace": "Andrew's Space"}

    # SYNC — fetch recent pages from Notion and store to knowledge store
    if action == "sync":
        return await _notion_sync_recent()

    # PAGE_UPDATED — fetch page content and store
    if action in ("page_updated", "page_created"):
        if not page_id:
            return {"status": "skipped", "reason": "missing page_id"}
        return await _notion_fetch_and_store(page_id, page_title, url)

    return {"status": "unhandled", "action": action}


@router.post("/notion/sync")
async def notion_sync_webhook(request: Request):
    """Convenience endpoint: trigger a Notion sync without crafting JSON."""
    _verify_notion(request)
    return await _notion_sync_recent()


def _verify_notion(request: Request) -> None:
    """Verify Notion webhook via Bearer token."""
    if not NOTION_WEBHOOK_SECRET:
        raise HTTPException(status_code=503,
                            detail="Notion webhook secret not configured")

    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer token")

    token = auth[len("Bearer "):]
    if not hmac.compare_digest(token.encode(), NOTION_WEBHOOK_SECRET.encode()):
        raise HTTPException(status_code=401, detail="Invalid token")


async def _notion_fetch_and_store(page_id: str, page_title: str, url: str) -> dict:
    """Fetch a Notion page as markdown and store to knowledge store."""
    import aiohttp

    if not NOTION_API_KEY:
        return {"status": "error", "reason": "NOTION_API_KEY not configured"}

    headers = {
        "Authorization": f"Bearer {NOTION_API_KEY}",
        "Notion-Version": NOTION_VERSION,
    }

    async with aiohttp.ClientSession() as session:
        # Fetch page as markdown
        async with session.get(
            f"{NOTION_API_BASE}/pages/{page_id}/markdown",
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            if resp.status != 200:
                text = await resp.text()
                logger.error("notion: fetch page %s failed: %s %s",
                             page_id, resp.status, text[:200])
                return {"status": "error", "reason": f"Notion API {resp.status}"}
            markdown = await resp.text()

    if not markdown or len(markdown) < 10:
        return {"status": "skipped", "reason": "empty_or_short_content"}

    title = page_title or "Notion page"
    fact = f"Notion page: {title} — {markdown[:500]}"
    if len(markdown) > 500:
        fact += " [...]"

    # Store to knowledge store
    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, lambda: subprocess.run(
            [
                "/usr/local/lib/hermes-agent/venv/bin/python3",
                str(HERMES_HOME / "scripts/knowledge.py"), "store",
                "--text", fact,
                "--tags", "notion,documentation",
                "--source", "notion-webhook",
                "--priority", "normal",
                "--context-prefix", url or f"notion:{page_id}",
            ],
            capture_output=True, text=True, timeout=15,
            env={**os.environ, "HERMES_HOME": str(HERMES_HOME)},
        ))
        store_id = result.stdout.strip() if result.returncode == 0 else None
    except Exception as e:
        logger.error("notion: knowledge store error: %s", e)
        return {"status": "error", "reason": str(e)[:200]}

    # Mirror to Neo4j
    try:
        _write_to_neo4j(
            text=fact, tags=["notion", "documentation"],
            priority="normal", source="notion-webhook",
            context_prefix=url or f"notion:{page_id}",
        )
    except Exception as e:
        logger.warning("notion: neo4j mirror failed (non-fatal): %s", e)

    logger.info("notion: stored page %s id=%s", page_id, store_id)
    return {"status": "stored", "knowledge_id": store_id,
            "page_id": page_id, "title": title}


async def _notion_sync_recent() -> dict:
    """Search Notion for recently-edited pages and sync them."""
    import aiohttp

    if not NOTION_API_KEY:
        return {"status": "error", "reason": "NOTION_API_KEY not configured"}

    headers = {
        "Authorization": f"Bearer {NOTION_API_KEY}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }

    # Search for recently-edited pages, sorted by last_edited_time desc
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{NOTION_API_BASE}/search",
            headers=headers,
            json={
                "sort": {"direction": "descending", "timestamp": "last_edited_time"},
                "page_size": 10,
                "filter": {"value": "page", "property": "object"},
            },
            timeout=aiohttp.ClientTimeout(total=15),
        ) as resp:
            if resp.status != 200:
                text = await resp.text()
                return {"status": "error", "reason": f"search failed: {resp.status}"}
            data = await resp.json()

    results = data.get("results", [])
    stored = 0
    for page in results:
        pid = page.get("id", "")
        title_obj = page.get("properties", {}).get("title", {}).get("title", [])
        page_title = title_obj[0].get("text", {}).get("content", "") if title_obj else ""
        url = page.get("url", "")

        if pid:
            await _notion_fetch_and_store(pid, page_title, url)
            stored += 1

    logger.info("notion sync: stored %d of %d pages", stored, len(results))
    return {"status": "synced", "stored": stored, "total": len(results)}

