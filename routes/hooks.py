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

import json
import os
import re
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
HERMES_HOME = Path(os.environ.get("HERMES_HOME", "/root/.hermes"))
MEMORY_PATH = HERMES_HOME / "memories" / "MEMORY.md"
USER_PATH = HERMES_HOME / "memories" / "USER.md"
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")
HONCHO_WEBHOOK_SECRET = os.environ.get("HONCHO_WEBHOOK_SECRET", os.environ.get("HONCHO_API_KEY", ""))

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


def _find_similar_via_pgvector(text: str) -> list[str]:
    """Return up to 3 similar fact texts from pgvector via knowledge.py search."""
    try:
        import subprocess
        clean = re.sub(r"\s+", " ", text.strip())[:80]
        result = subprocess.run(
            ["/usr/local/lib/hermes-agent/venv/bin/python3", "/root/.hermes/scripts/knowledge.py", "search", clean, "--limit", "3"],
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
                # Extract text after the second bracket
                rest = line.split("] [", 2)[-1]
                if "] " in rest:
                    text_part = rest.split("] ", 1)[1].strip()
                    if text_part:
                        matches.append(text_part)
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
) -> None:
    """Mirror a fact to Neo4j with [:RELATED_TO] edges to similar facts.

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
            for sim_text in similar:
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

            # If tagged CORRECTION, link superseded facts
            if "CORRECTION" in (t.upper() for t in tag_list):
                for sim_text in similar:
                    sim_id = hashlib.sha256(sim_text.encode()).hexdigest()[:16]
                    if sim_id == fact_id:
                        continue
                    s.run(
                        "MATCH (f:Fact {id: $fact_id}), (old:Fact {id: $old_id}) "
                        "MERGE (f)-[r:SUPERSEDES]->(old)",
                        fact_id=fact_id, old_id=sim_id,
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

    # Mirror to Neo4j graph layer (fire-and-forget)
    try:
        _write_to_neo4j(text=text, tags=tags, priority="normal", source="supabase-webhook",
                         context_prefix=str(row_id or ""))
    except Exception as e:
        logger.warning("neo4j mirror failed (non-fatal): %s", e)

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
    body = await _verify_honcho(request)

    try:
        payload = json.loads(body)
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

async def _verify_honcho(request: Request) -> bytes:
    """Verify Honcho webhook via HMAC-SHA256 signature. Returns raw body bytes.

    Honcho signs the JSON payload with HMAC-SHA256 using the signing secret
    and sends the hex digest in the X-Honcho-Signature header.
    See: plastic-labs/honcho src/webhooks/webhook_delivery.py
    """
    if not HONCHO_WEBHOOK_SECRET:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail="Honcho webhook secret not configured")

    signature = request.headers.get("X-Honcho-Signature", "")
    if not signature:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Missing X-Honcho-Signature header")

    body = await request.body()
    expected = hmac.new(
        HONCHO_WEBHOOK_SECRET.encode("utf-8"),
        body,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected, signature):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Invalid signature")

    return body


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

            # Mirror to Neo4j
            try:
                _write_to_neo4j(text=fact, tags=["honcho", "conclusion"],
                                 priority="high", source="honcho-webhook")
            except Exception as e:
                logger.warning("neo4j mirror failed (non-fatal): %s", e)

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
        import subprocess
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

            # Mirror to Neo4j
            try:
                _write_to_neo4j(text=summary, tags=["honcho", "session"],
                                 priority="normal", source="honcho-webhook",
                                 context_prefix=session_id)
            except Exception as e:
                logger.warning("neo4j mirror failed (non-fatal): %s", e)

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
        import subprocess
        result = subprocess.run(
            [
                "/usr/local/lib/hermes-agent/venv/bin/python3",
                "/root/.hermes/scripts/knowledge.py", "store",
                "--text", summary,
                "--tags", "figma,design-tokens",
                "--source", "figma-webhook",
                "--priority", "high",
            ],
            capture_output=True, text=True, timeout=15,
            env={**os.environ, "HERMES_HOME": str(HERMES_HOME)},
        )
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

    import subprocess
    subprocess.run(
        [
            "/usr/local/lib/hermes-agent/venv/bin/python3",
            "/root/.hermes/scripts/knowledge.py", "store",
            "--text", fact,
            "--tags", "github,issue",
            "--source", "github-webhook",
            "--priority", "normal",
            "--context-prefix", url,
        ],
        capture_output=True, text=True, timeout=10,
        env={**os.environ, "HERMES_HOME": str(HERMES_HOME)},
    )
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

    import subprocess
    subprocess.run(
        [
            "/usr/local/lib/hermes-agent/venv/bin/python3",
            "/root/.hermes/scripts/knowledge.py", "store",
            "--text", fact,
            "--tags", "github,pr",
            "--source", "github-webhook",
            "--priority", "high" if merged else "normal",
            "--context-prefix", url,
        ],
        capture_output=True, text=True, timeout=10,
        env={**os.environ, "HERMES_HOME": str(HERMES_HOME)},
    )
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

    import subprocess
    subprocess.run(
        [
            "/usr/local/lib/hermes-agent/venv/bin/python3",
            "/root/.hermes/scripts/knowledge.py", "store",
            "--text", fact,
            "--tags", "github,push",
            "--source", "github-webhook",
            "--priority", "low",
            "--context-prefix", f"{repo}/{ref}",
        ],
        capture_output=True, text=True, timeout=10,
        env={**os.environ, "HERMES_HOME": str(HERMES_HOME)},
    )
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
    event_data = data.get("event", data.get("issue", {})) if isinstance(data, dict) else {}

    issue_title = event_data.get("title", "") or data.get("issue", {}).get("title", "")
    issue_url = data.get("issue_url", "") or event_data.get("web_url", "")
    project = data.get("project_name", "") or event_data.get("project", {}).get("name", "")
    level = event_data.get("level", "error")

    logger.info("sentry webhook: action=%s project=%s title=%s", action, project, issue_title[:80])

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

    # Store to knowledge store (fire-and-forget, don't block the pipeline)
    try:
        import subprocess
        subprocess.run(
            [
                "/usr/local/lib/hermes-agent/venv/bin/python3",
                "/root/.hermes/scripts/knowledge.py", "store",
                "--text", fact,
                "--tags", "sentry,alert",
                "--source", "sentry-webhook",
                "--priority", "high",
                "--context-prefix", issue_url or "",
            ],
            capture_output=True, text=True, timeout=5,
            env={**os.environ, "HERMES_HOME": str(HERMES_HOME)},
        )
    except Exception:
        pass

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
    if action == "created":
        try:
            import aiohttp
            linear_query = """
            mutation($input: IssueCreateInput!) {
              issueCreate(input: $input) {
                success
                issue { id identifier title url }
              }
            }
            """
            async with aiohttp.ClientSession() as session:
                await session.post(
                    "https://api.linear.app/graphql",
                    headers={
                        "Authorization": LINEAR_API_KEY,
                        "Content-Type": "application/json",
                    },
                    json={
                        "query": linear_query,
                        "variables": {
                            "input": {
                                "teamId": "38a0c106-e9a8-4f65-84d2-ec8bdc61855d",
                                "title": f"[Sentry] {project}: {issue_title}" if project else f"[Sentry] {issue_title}",
                                "description": f"**Sentry Alert**\n\n- **Project:** {project}\n- **Level:** {level}\n- **URL:** {issue_url}",
                                "priority": 1,  # High — Sentry alerts are urgent
                            }
                        },
                    },
                    timeout=aiohttp.ClientTimeout(total=5),
                )
        except Exception as exc:
            logger.warning("sentry webhook: Linear issue creation failed: %s", exc)

    # Fire-and-forget to Telegram via the dashboard's notify endpoint
    if SENTRY_TELEGRAM_CHAT:
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                await session.post(
                    f"http://127.0.0.1:8787/api/hooks/notify",
                    json={
                        "chat_id": SENTRY_TELEGRAM_CHAT,
                        "text": telegram_msg,
                        "parse_mode": "Markdown",
                    },
                    timeout=aiohttp.ClientTimeout(total=5),
                )
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
        logger.warning("linear webhook: invalid signature (delivery=%s)", delivery)
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

    # Store to knowledge store (fire-and-forget, don't block the pipeline)
    try:
        import subprocess
        subprocess.run(
            [
                "/usr/local/lib/hermes-agent/venv/bin/python3",
                "/root/.hermes/scripts/knowledge.py", "store",
                "--text", fact,
                "--tags", "linear,webhook",
                "--source", "linear-webhook",
                "--priority", "normal",
                "--context-prefix", url or "",
            ],
            capture_output=True, text=True, timeout=5,
            env={**os.environ, "HERMES_HOME": str(HERMES_HOME)},
        )
    except Exception:
        pass  # Don't let knowledge store failures block routing

    # Auto-create and dispatch Kanban card for new issues
    # Linear acts as the intake funnel — all issues route autonomously (Pattern B)
    if entity_type == "Issue" and action == "create" and entity_title:
        # Map Linear priority to Kanban priority (higher = picked first by dispatcher)
        linear_priority = data.get("priority", 4) if isinstance(data, dict) else 4
        # Linear: 0=urgent, 1=high, 2=medium, 3=low, 4=none
        # Kanban: higher = first. Map: 0→50, 1→30, 2→10, 3→5, 4→1
        kanban_priority = {0: 50, 1: 30, 2: 10, 3: 5}.get(linear_priority, 1)

        # Round-robin across coder fleet
        import subprocess as sp
        import random
        coders = ["coder", "coder-b", "coder-c", "coder-d"]
        assignee = random.choice(coders)

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
            _task_id = "t_" + uuid.uuid4().hex[:8]
            _now = int(datetime.now(timezone.utc).timestamp())
            _db_path = os.environ.get("KANBAN_DB", "/root/.hermes/kanban.db")
            _conn = _sqlite3.connect(_db_path)
            try:
                _conn.execute(
                    "INSERT INTO tasks (id, title, body, status, priority, created_by, created_at, tenant, assignee) "
                    "VALUES (?, ?, ?, 'triage', 4, 'dashboard', ?, ?, NULL)",
                    (_task_id, entity_title, kanban_body, _now, "internal"),
                )
                _conn.commit()
                logger.info("linear webhook: dispatched '%s' (id=%s priority %d)",
                           entity_title[:60], _task_id, kanban_priority)
            finally:
                _conn.close()
        except Exception as exc:
            logger.warning("linear webhook: kanban dispatch failed: %s", exc)

    # Fire-and-forget to Telegram
    if LINEAR_TELEGRAM_CHAT:
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                await session.post(
                    "http://127.0.0.1:8787/api/hooks/notify",
                    json={"chat_id": LINEAR_TELEGRAM_CHAT, "text": telegram_msg, "parse_mode": "Markdown"},
                    timeout=aiohttp.ClientTimeout(total=5),
                )
        except Exception as exc:
            logger.warning("linear webhook: telegram notify failed: %s", exc)

    return {"status": "stored", "action": action, "type": entity_type}

