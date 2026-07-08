import os
import sqlite3
import time
from datetime import datetime
from pathlib import Path

import psutil
from fastapi import APIRouter, Query

router = APIRouter()

KANBAN_DB = Path(os.environ.get("KANBAN_DB", os.path.expanduser("~/.hermes/kanban.db")))
PROFILES_DIR = Path(os.environ.get("HERMES_PROFILES_DIR", os.path.expanduser("~/.hermes/profiles")))
HERMES_HOME = Path(os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes")))
MEMORY_FILE = HERMES_HOME / "memories" / "MEMORY.md"
USER_FILE = HERMES_HOME / "memories" / "USER.md"


def _open_ro() -> sqlite3.Connection:
    return sqlite3.connect(f"file:{KANBAN_DB}?mode=ro", uri=True)


def _count_entries(text: str) -> int:
    """Cheap count of discrete memory entries in a memory file."""
    if not text.strip():
        return 0
    # Primary Hermes format uses § as the entry delimiter.
    if "§" in text:
        return len([p for p in text.split("§") if p.strip()])
    # Fall back to markdown HR (---) separated blocks.
    if "\n---" in text:
        return len([p for p in text.split("\n---") if p.strip()])
    # Last resort: blank-line separated paragraphs.
    return len([p for p in text.split("\n\n") if p.strip()])


def _memory_count() -> int:
    total = 0
    for path in (MEMORY_FILE, USER_FILE):
        try:
            total += _count_entries(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError):
            continue
    return total


def _empty_summary() -> dict:
    return {"running": 0, "blocked": 0, "done_today": 0, "ready": 0}


def _agent_memory() -> list:
    try:
        results: dict[str, int] = {}
        for proc in psutil.process_iter(['pid', 'cmdline', 'memory_info']):
            try:
                cmdline = proc.info.get('cmdline') or []
                mem = proc.info.get('memory_info')
                if mem is None or not cmdline:
                    continue
                # Identify profile-based agents (-p / --profile flag).
                # Profile names are short identifiers (no spaces, ≤64 chars).
                label = None
                for i, part in enumerate(cmdline):
                    if part in ('-p', '--profile') and i + 1 < len(cmdline):
                        candidate = cmdline[i + 1]
                        if len(candidate) <= 64 and ' ' not in candidate:
                            label = candidate
                        break
                # Identify gateway process
                if label is None:
                    cmdstr = ' '.join(cmdline)
                    if 'gateway' in cmdstr and 'run' in cmdstr:
                        label = 'gateway'
                    elif any('hermes_cli' in p or 'hermes.main' in p for p in cmdline):
                        label = os.path.basename(cmdline[0])
                if label is None:
                    continue
                rss_mb = mem.rss // (1024 * 1024)
                results[label] = results.get(label, 0) + rss_mb
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        sorted_items = sorted(results.items(), key=lambda x: x[1], reverse=True)[:6]
        return [{'name': k, 'rss_mb': v} for k, v in sorted_items]
    except Exception:
        return []


@router.get("/overview")
async def get_overview(
    heatmap_window: str = Query(default="day", pattern="^(day|week|month)$"),
) -> dict:
    cpu = round(psutil.cpu_percent(interval=0.0), 1)
    mem = psutil.virtual_memory().percent
    disk = psutil.disk_usage("/").percent

    agent_memory = _agent_memory()

    now_epoch = int(time.time())
    today_dt = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    today_epoch = int(today_dt.timestamp())

    try:
        conn = _open_ro()
        try:
            cur = conn.cursor()

            summary = _empty_summary()
            cur.execute("SELECT status, COUNT(*) FROM tasks GROUP BY status")
            for status, count in cur.fetchall():
                if status in ("running", "blocked", "ready"):
                    summary[status] = count

            cur.execute(
                "SELECT COUNT(*) FROM tasks WHERE status='done' AND completed_at >= ?",
                (today_epoch,),
            )
            summary["done_today"] = cur.fetchone()[0]

            cur.execute(
                "SELECT COUNT(DISTINCT assignee) FROM tasks"
                " WHERE status='running' AND assignee IS NOT NULL"
            )
            active_agents: int = cur.fetchone()[0]

            cur.execute(
                "SELECT COUNT(DISTINCT tenant) FROM tasks WHERE tenant IS NOT NULL"
            )
            tenant_count: int = cur.fetchone()[0]

            cur.execute(
                "SELECT id, title, assignee, completed_at FROM tasks"
                " WHERE status='done' ORDER BY completed_at DESC LIMIT 5"
            )
            recent = [
                {"id": r[0], "title": r[1], "assignee": r[2], "completed_at": r[3]}
                for r in cur.fetchall()
            ]

            sparkline = []
            for i in range(24):
                bucket_start = now_epoch - (23 - i) * 3600
                bucket_end = bucket_start + 3600
                cur.execute(
                    "SELECT COUNT(*) FROM tasks"
                    " WHERE status='done' AND completed_at >= ? AND completed_at < ?",
                    (bucket_start, bucket_end),
                )
                sparkline.append({"hour": i, "count": cur.fetchone()[0]})

            cur.execute(
                "SELECT COUNT(*) FROM tasks WHERE started_at >= ?",
                (today_epoch,),
            )
            total_tasks: int = cur.fetchone()[0]

            cur.execute(
                "SELECT assignee, COUNT(*) as cnt FROM tasks"
                " WHERE assignee IS NOT NULL AND started_at >= ?"
                " GROUP BY assignee ORDER BY cnt DESC",
                (today_epoch,),
            )
            rows = cur.fetchall()

            agent_breakdown: list = []
            for assignee, cnt in rows:
                agent_breakdown.append({'name': assignee, 'count': cnt})

            top_agents = [item['name'] for item in agent_breakdown[:5]]
            agent_activity: list = []

            if heatmap_window == "day":
                num_buckets, bucket_size = 24, 3600
            elif heatmap_window == "week":
                num_buckets, bucket_size = 7, 86400
            else:  # month
                num_buckets, bucket_size = 30, 86400

            for profile in top_agents:
                buckets = []
                for i in range(num_buckets):
                    bucket_start = now_epoch - (num_buckets - 1 - i) * bucket_size
                    bucket_end = bucket_start + bucket_size
                    cur.execute(
                        "SELECT COUNT(*) FROM task_runs"
                        " WHERE profile=? AND started_at >= ? AND started_at < ?",
                        (profile, bucket_start, bucket_end),
                    )
                    buckets.append(cur.fetchone()[0])
                agent_activity.append({'name': profile, 'hours': buckets})

        finally:
            conn.close()

    except Exception:
        summary = _empty_summary()
        active_agents = 0
        tenant_count = 0
        recent = []
        sparkline = [{"hour": i, "count": 0} for i in range(24)]
        total_tasks = 0
        agent_breakdown = []
        agent_activity = []

    return {
        "kanban_summary": summary,
        "active_agents": active_agents,
        "tenant_count": tenant_count,
        "memory_count": _memory_count(),
        "system": {"cpu_pct": cpu, "mem_pct": mem, "disk_pct": disk},
        "recent_activity": recent,
        "sparkline": sparkline,
        "total_tasks": total_tasks,
        "agent_breakdown": agent_breakdown,
        "agent_activity": agent_activity,
        "agent_memory": agent_memory,
    }
