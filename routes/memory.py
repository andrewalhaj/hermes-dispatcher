import os
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

HERMES_HOME = Path(os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes")))
MEMORIES_DIR = HERMES_HOME / "memories"
REFS_DIR = HERMES_HOME / "references"

MEMORY_FILE = MEMORIES_DIR / "MEMORY.md"
USER_FILE = MEMORIES_DIR / "USER.md"
SOUL_FILE = HERMES_HOME / "SOUL.md"
AGENTS_FILE = HERMES_HOME / "AGENTS.md"

import yaml as _yaml


def _read_caps():
    try:
        cfg = _yaml.safe_load(open(str(HERMES_HOME / "config.yaml")))
        m = cfg.get("memory", {})
        return int(m.get("memory_char_limit", 3000)), int(m.get("user_char_limit", 2250))
    except Exception:
        return 3000, 2250

# The dashboard runs under its own .venv (routes/start-server.sh) which does NOT
# carry numpy / sentence-transformers. Those live in the parent Hermes agent venv.
# Prepend its site-packages so `import knowledge` resolves in-process.
AGENT_SITE_PACKAGES = "/usr/local/lib/hermes-agent/venv/lib/python3.11/site-packages"


def _ensure_agent_path() -> None:
    import sys
    for p in (AGENT_SITE_PACKAGES, "/usr/local/lib/hermes-agent"):
        if p not in sys.path:
            sys.path.insert(0, p)


router = APIRouter(prefix="/memory")


def _kb_tier(tags) -> str:
    """Map a knowledge-store row's tags to a galaxy sub-tier.

    Priority order (first match wins): user-profile -> session -> offload -> knowledge.
    Tolerates both a list of tags and a legacy comma-joined string.
    """
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(',')]
    tags = tags or []
    if 'user-profile' in tags:
        return 'user-profile'
    if 'session-digest' in tags:
        return 'session'
    if 'offload' in tags:
        return 'offload'
    return 'knowledge'


def _read_env() -> dict:
    """Parse ~/.hermes/.env into a dict (same pattern as knowledge.get_supabase)."""
    env: dict = {}
    try:
        for line in (HERMES_HOME / ".env").read_text().splitlines():
            line = line.strip()
            if '=' in line and not line.startswith('#'):
                k, v = line.split('=', 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    except Exception:
        pass
    return env



def _read_safe(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def _parse_entries(text: str, tier: str, id_prefix: str) -> list[dict]:
    """Split a memory file into node entries, trying multiple delimiters."""
    if not text.strip():
        return []

    parts: list[str] = []

    # 1. Try § delimiter (primary Hermes format)
    if "§" in text:
        candidates = [p.strip() for p in text.split("§") if p.strip()]
        if len(candidates) >= 1:
            parts = candidates

    # 2. Try "---" (markdown HR) if § didn't split anything meaningful
    if not parts:
        lines = text.split("\n")
        current: list[str] = []
        for line in lines:
            if line.strip() == "---":
                if current:
                    parts.append("\n".join(current).strip())
                    current = []
            else:
                current.append(line)
        if current:
            parts.append("\n".join(current).strip())
        parts = [p for p in parts if p.strip()]
        if len(parts) <= 1:
            parts = []

    # 3. Fall back to blank-line paragraph splitting
    if not parts:
        current = []
        for line in text.split("\n"):
            if line.strip():
                current.append(line)
            elif current:
                parts.append("\n".join(current).strip())
                current = []
        if current:
            parts.append("\n".join(current).strip())
        parts = [p for p in parts if p.strip()]

    # 4. Last resort: whole text as one entry
    if not parts:
        parts = [text.strip()]

    result = []
    for i, entry in enumerate(parts):
        single_line = " ".join(entry.split())
        label = single_line[:40]
        result.append({
            "id": f"{id_prefix}-{i}",
            "label": label,
            "tier": tier,
            "body": entry,
        })
    return result


@router.get("/files")
def get_files():
    memory_text = _read_safe(MEMORY_FILE)
    user_text = _read_safe(USER_FILE)
    soul_text = _read_safe(SOUL_FILE)
    agents_text = _read_safe(AGENTS_FILE)
    memory_cap, user_cap = _read_caps()
    return {
        "memory": memory_text,
        "user": user_text,
        "soul": soul_text,
        "agents": agents_text,
        "memory_chars": len(memory_text),
        "user_chars": len(user_text),
        "memory_cap": memory_cap,
        "user_cap": user_cap,
    }


class PutFilesBody(BaseModel):
    file: str
    content: str


@router.put("/files")
def put_files(body: PutFilesBody):
    if body.file not in ("memory", "user", "soul", "agents"):
        raise HTTPException(status_code=400, detail="file must be 'memory', 'user', 'soul', or 'agents'")

    targets = {
        "memory": MEMORY_FILE,
        "user": USER_FILE,
        "soul": SOUL_FILE,
        "agents": AGENTS_FILE,
    }
    target = targets[body.file]

    # Back up existing file before overwriting
    if target.exists():
        ts = int(time.time())
        bak = target.with_name(target.name + f".bak-{ts}")
        bak.write_text(target.read_text(encoding="utf-8"), encoding="utf-8")

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body.content, encoding="utf-8")

    return {"ok": True, "chars": len(body.content)}


@router.get("/galaxy")
def get_galaxy():
    user_text = _read_safe(USER_FILE)
    soul_text = _read_safe(SOUL_FILE)
    agents_text = _read_safe(AGENTS_FILE)

    nodes: list[dict] = []
    nodes.extend(_parse_entries(user_text, "warm", "usr"))
    nodes.extend(_parse_entries(soul_text, "soul", "soul"))
    nodes.extend(_parse_entries(agents_text, "agents", "agents"))

    # Supabase knowledge store facts — split into sub-tiers by tag
    try:
        import sys
        _ensure_agent_path()
        sys.path.insert(0, str(HERMES_HOME / "scripts"))
        import knowledge as kb
        kb_rows = kb.recent(500)  # raise cap — ~73 rows today, headroom for growth
        for row in kb_rows:
            text = row.get("text", "") or ""
            tier = _kb_tier(row.get("tags", []))
            priority = row.get("priority", "normal")
            nodes.append({
                "id": f"kb-{row['id'][:8]}",
                "label": text[:40],
                "tier": tier,
                "body": text[:300],
                "metadata": {"priority": priority, "stored_at": row.get("stored_at", "")},
            })
    except Exception:
        pass  # knowledge store unavailable — skip silently

    # Add all reference nodes from filenames only
    if REFS_DIR.exists():
        try:
            ref_files = sorted(
                f for f in REFS_DIR.iterdir() if f.is_file() and f.suffix == ".md"
            )
            for i, ref in enumerate(ref_files):
                nodes.append({
                    "id": f"ref-{i}",
                    "label": ref.name[:40],
                    "tier": "cold",
                    "body": ref.name,
                })
        except Exception:
            pass

    return {"nodes": nodes, "edges": []}


if __name__ == "__main__":
    # Standalone entry-point for direct invocation / manual testing only.
    # Production path: server.py imports this router and mounts it under /api.
    import uvicorn
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware

    _app = FastAPI()
    _app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
    _app.include_router(router, prefix="/api")
    uvicorn.run(_app, host="0.0.0.0", port=8787)
