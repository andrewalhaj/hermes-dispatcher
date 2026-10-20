import os
import json
import sqlite3
import glob
import time
import logging
import traceback
from fastapi import APIRouter, HTTPException

router = APIRouter()
logger = logging.getLogger(__name__)

HERMES_HOME = os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes"))


def _kanban_db() -> str:
    return str(os.path.join(HERMES_HOME, "kanban.db"))


def _state_db() -> str:
    return str(os.path.join(HERMES_HOME, "state.db"))


def _state_dbs() -> list:
    """Default profile's state.db plus HERMES_HOME/profiles/*/state.db (dot-dirs skipped)."""
    paths = [_state_db()]
    paths += sorted(glob.glob(os.path.join(HERMES_HOME, "profiles", "[!.]*", "state.db")))
    return [p for p in paths if os.path.isfile(p)]


def _rows(path: str, sql: str, params: tuple = ()) -> list:
    """Read-only query; a missing/locked/corrupt DB logs and yields no rows."""
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=1, check_same_thread=False)
        try:
            return conn.execute(sql, params).fetchall()
        finally:
            conn.close()
    except Exception as e:
        logger.warning(f"insights query on {path}: {e}")
        return []


def _state_rows(sql: str, params: tuple = ()) -> list:
    return [r for p in _state_dbs() for r in _rows(p, sql, params)]


@router.get("/insights")
async def get_insights(days: int = 7) -> dict:
    """Usage analytics over the trailing window [now - days*86400, now].

    `days` must be 1, 3 or 7 (default 7); any other integer returns HTTP 400
    (non-integers fail FastAPI validation with 422). Sessions, messages, tokens
    and skill_view counts aggregate every state.db (default + each profile).
    """
    if days not in (1, 3, 7):
        raise HTTPException(status_code=400, detail="days must be 1, 3 or 7")
    now = int(time.time())
    since = now - days * 86400
    kb = _kanban_db()
    result: dict = {"days": days}

    def one(sql: str, params: tuple = ()) -> tuple:
        rows = _rows(kb, sql, params)
        return rows[0] if rows else (0,)

    result["tasks_started"] = one(
        "SELECT COUNT(*) FROM tasks WHERE started_at IS NOT NULL AND started_at >= ?", (since,))[0] or 0

    rows = _rows(kb, "SELECT COUNT(*), SUM(CASE WHEN outcome='completed' THEN 1 ELSE 0 END) "
                     "FROM task_runs WHERE ended_at >= ? AND outcome IS NOT NULL", (since,))
    total, completed = rows[0] if rows else (0, 0)
    result["success_rate"] = round(100.0 * (completed or 0) / total, 1) if total else 0.0

    val = one("SELECT AVG(ended_at - started_at) FROM task_runs WHERE ended_at >= ? "
              "AND started_at IS NOT NULL AND outcome='completed'", (since,))[0]
    result["avg_latency_s"] = round(float(val), 1) if val is not None else 0.0

    # by_profile: runs ended in window; running = tasks currently running (a live snapshot)
    runs = _rows(kb, "SELECT profile, SUM(outcome='completed'), COUNT(*) FROM task_runs "
                     "WHERE ended_at >= ? AND outcome IS NOT NULL GROUP BY profile", (since,))
    running = dict(_rows(kb, "SELECT assignee, COUNT(*) FROM tasks WHERE status='running' GROUP BY assignee"))
    by_profile = [
        {"profile": p, "completed": c or 0, "running": running.get(p, 0),
         "success_rate": round(100.0 * (c or 0) / t, 1) if t else 0.0}
        for p, c, t in runs
    ]
    by_profile.sort(key=lambda x: x["completed"], reverse=True)
    result["by_profile"] = by_profile[:15]

    result["sessions"] = sum(r[0] for r in _state_rows("SELECT COUNT(*) FROM sessions WHERE started_at >= ?", (since,)))
    result["messages"] = sum(r[0] for r in _state_rows("SELECT COUNT(*) FROM messages WHERE timestamp >= ?", (since,)))

    # kanban_throughput: trailing slices ending now (hourly for 1 day, else daily), oldest first
    step = 3600 if days == 1 else 86400
    fmt = "%H:00" if days == 1 else "%a"
    n = days * 86400 // step
    ends = _rows(kb, "SELECT ended_at FROM task_runs WHERE outcome='completed' AND ended_at >= ?", (since,))
    buckets = [0] * n
    for (e,) in ends:
        buckets[min(n - 1, (e - since) // step)] += 1
    result["kanban_throughput"] = [
        {"date": time.strftime(fmt, time.localtime(since + i * step)), "completed": c}
        for i, c in enumerate(buckets)
    ]

    # top_skills: skill_view results in window (all profile DBs); kanban tasks.skills as fallback
    skill_counts: dict = {}
    for (content,) in _state_rows(
        "SELECT content FROM messages WHERE tool_name = 'skill_view' AND timestamp >= ? "
        "AND content LIKE '%\"success\": true%'", (since,)):
        try:
            data = json.loads(content)
            if data.get("success") and data.get("name"):
                skill_counts[data["name"]] = skill_counts.get(data["name"], 0) + 1
        except Exception:
            pass
    if not skill_counts:
        for (skills_json,) in _rows(
            kb, "SELECT skills FROM tasks WHERE started_at >= ? AND skills IS NOT NULL "
                "AND skills != '' AND skills != '[]'", (since,)):
            try:
                for skill in json.loads(skills_json):
                    if isinstance(skill, str) and skill:
                        skill_counts[skill] = skill_counts.get(skill, 0) + 1
            except Exception:
                pass
    top = sorted(skill_counts.items(), key=lambda x: x[1], reverse=True)[:20]
    result["top_skills"] = [{"skill": s, "count": c} for s, c in top]

    # tokens: summed over sessions started in window (messages.token_count is never populated)
    tok = _state_rows("SELECT SUM(input_tokens), SUM(output_tokens) FROM sessions WHERE started_at >= ?", (since,))
    result["tokens_input"] = int(sum(r[0] or 0 for r in tok))
    result["tokens_output"] = int(sum(r[1] or 0 for r in tok))

    return result
