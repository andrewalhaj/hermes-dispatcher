"""Unified search: sessions (FTS5) + references + skills."""
import json
import os
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Query

router = APIRouter(prefix="/search")

STATE_DB = Path(os.environ.get("STATE_DB", os.path.expanduser("~/.hermes/state.db")))
REFS_DIR = Path(os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes"))) / "references"
SKILLS_DIR = Path(os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes"))) / "skills"

EMPTY = {"sessions": [], "references": [], "skills": []}


def _iso(ts) -> str:
    """Convert an epoch (REAL/int) or pre-formatted value to ISO 8601."""
    if ts is None:
        return ""
    try:
        return datetime.fromtimestamp(float(ts), tz=timezone.utc).isoformat()
    except (TypeError, ValueError, OSError):
        return str(ts)


def _search_sessions(q: str) -> list[dict]:
    """FTS5 search over messages_fts. Returns [] on any error (bad MATCH syntax)."""
    if not STATE_DB.exists():
        return []
    conn = None
    try:
        conn = sqlite3.connect(str(STATE_DB), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT m.session_id   AS session_id,
                   s.title        AS title,
                   s.started_at   AS started_at,
                   snippet(messages_fts, 0, '**', '**', '...', 20) AS snippet,
                   m.role         AS role
            FROM messages_fts
            JOIN messages m ON messages_fts.rowid = m.rowid
            JOIN sessions s ON m.session_id = s.id
            WHERE messages_fts MATCH ?
              AND s.archived = 0
              AND m.role IN ('user', 'assistant')
            ORDER BY rank
            LIMIT 20
            """,
            (q,),
        ).fetchall()
    except Exception:
        return []
    finally:
        if conn is not None:
            conn.close()

    out = []
    for r in rows:
        snip = r["snippet"] or ""
        if len(snip) > 200:
            snip = snip[:200]
        out.append(
            {
                "session_id": r["session_id"],
                "session_title": r["title"] or r["session_id"],
                "snippet": snip,
                "message_role": r["role"],
                "timestamp": _iso(r["started_at"]),
            }
        )
    return out


def _ripgrep(q: str, target_dir: Path, max_results: int) -> list[dict]:
    """Run ripgrep --json against target_dir. Returns parsed match dicts."""
    if not target_dir.exists():
        return []
    cmd = [
        "rg", "--json", "-i", "-m", "3", "--max-count=3",
        "-g", "!*.bak*", "-g", "!_archive/**",
        "--", q, str(target_dir),
    ]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=10
        )
    except Exception:
        return []

    matches = []
    for line in proc.stdout.splitlines():
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if obj.get("type") != "match":
            continue
        data = obj.get("data", {})
        path = data.get("path", {}).get("text", "")
        text = data.get("lines", {}).get("text", "").rstrip("\n")
        line_no = data.get("line_number", 0)
        matches.append({"path": path, "text": text, "line": line_no})
        if len(matches) >= max_results:
            break
    return matches


def _search_references(q: str) -> list[dict]:
    """References: ripgrep over REFS_DIR, grouped per file (up to 3 lines)."""
    raw = _ripgrep(q, REFS_DIR, max_results=45)
    by_file: dict[str, dict] = {}
    for m in raw:
        path = m["path"]
        entry = by_file.get(path)
        if entry is None:
            entry = {
                "file": Path(path).name,
                "path": path,
                "lines": [],
                "line": m["line"],
            }
            by_file[path] = entry
        if len(entry["lines"]) < 3:
            entry["lines"].append(m["text"])
        if len(by_file) >= 15 and path not in by_file:
            break

    out = []
    for entry in list(by_file.values())[:15]:
        out.append(
            {
                "file": entry["file"],
                "path": entry["path"],
                "snippet": "\n".join(entry["lines"]),
                "line": entry["line"],
            }
        )
    return out


def _skill_name(path: str) -> str:
    """Derive a skill name from a matched file path."""
    p = Path(path)
    if p.name == "SKILL.md":
        return p.parent.name
    return p.stem


def _search_skills(q: str) -> list[dict]:
    """Skills: ripgrep over SKILLS_DIR, grouped per skill dir (cap 10)."""
    raw = _ripgrep(q, SKILLS_DIR, max_results=40)
    by_skill: dict[str, dict] = {}
    for m in raw:
        path = m["path"]
        # group by containing skill (parent dir of SKILL.md, else the file)
        p = Path(path)
        key = str(p.parent) if p.name == "SKILL.md" else path
        if key in by_skill:
            continue
        by_skill[key] = {
            "name": _skill_name(path),
            "path": path,
            "snippet": (m["text"] or "")[:200],
        }
        if len(by_skill) >= 10:
            break
    return list(by_skill.values())[:10]


@router.get("")
async def unified_search(q: str = Query("", description="Search query")) -> dict:
    q = (q or "").strip()
    if len(q) < 2:
        return {"query": q, **EMPTY}
    return {
        "query": q,
        "sessions": _search_sessions(q),
        "references": _search_references(q),
        "skills": _search_skills(q),
    }
