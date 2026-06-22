import os
import re
import sqlite3
import time
from pathlib import Path

from fastapi import APIRouter

router = APIRouter(prefix="/api/agents")

# Note: HERMES_HOME may point at a single profile subdir in worker contexts,
# so resolve the profiles root explicitly rather than deriving from it.
PROFILES_DIR = Path(os.environ.get("HERMES_PROFILES_DIR", "/root/.hermes/profiles"))
DB_PATH = os.environ.get("KANBAN_DB", "/root/.hermes/kanban.db")
PALETTE = ["#5eead4", "#5aa2f0", "#9b8cff", "#4ade80", "#f0a85a", "#f06a9b", "#2dd4bf", "#facc15"]


def _role(name: str) -> str:
    if name == "default":
        return "Orchestrator"
    if name.startswith("coder"):
        return "Coding"
    if name == "ha-bot":
        return "Home Automation"
    if name.startswith("swarm-"):
        return "Swarm worker"
    if name == "executor":
        return "Executor"
    return "Worker"


def _model_default(config_path: Path) -> str:
    """Extract model.default from a YAML config without PyYAML."""
    try:
        lines = config_path.read_text(encoding="utf-8").splitlines()
        in_model = False
        for line in lines:
            if line.rstrip() == "model:":
                in_model = True
                continue
            if in_model:
                if line and not line[0].isspace():
                    break
                m = re.match(r"^\s+default:\s+(.+)$", line)
                if m:
                    return m.group(1).strip()
        return "unknown"
    except Exception:
        return "unknown"


def _gateway_running() -> bool:
    try:
        for entry in os.listdir("/proc"):
            if not entry.isdigit():
                continue
            try:
                with open(f"/proc/{entry}/cmdline", "rb") as f:
                    cmdline = f.read().replace(b"\x00", b" ").decode("utf-8", errors="ignore")
                if "hermes_cli.main" in cmdline and "gateway" in cmdline and "run" in cmdline:
                    return True
            except OSError:
                continue
        return False
    except Exception:
        return False


def _today_midnight() -> int:
    ls = time.localtime()
    return int(time.mktime(time.struct_time((
        ls.tm_year, ls.tm_mon, ls.tm_mday, 0, 0, 0,
        ls.tm_wday, ls.tm_yday, ls.tm_isdst,
    ))))


def _relative_time(epoch) -> str:
    if epoch is None:
        return "never"
    diff = int(time.time()) - int(epoch)
    if diff < 60:
        return "just now"
    if diff < 3600:
        return f"{diff // 60}m ago"
    if diff < 86400:
        return f"{diff // 3600}h ago"
    return f"{diff // 86400}d ago"


def _open_db():
    try:
        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn
    except Exception:
        return None


def _profile_names() -> list[str]:
    try:
        return sorted(p.name for p in PROFILES_DIR.iterdir() if p.is_dir())
    except Exception:
        return []


@router.get("")
def get_agents():
    profiles = _profile_names()
    gateway_up = _gateway_running()
    midnight = _today_midnight()
    conn = _open_db()

    results = []
    for i, name in enumerate(profiles):
        color = PALETTE[i % len(PALETTE)]
        config_path = PROFILES_DIR / name / "config.yaml"
        model = _model_default(config_path) if config_path.exists() else "unknown"

        busy = False
        today = 0
        completed = 0
        total = 0
        success = 100
        last_active = "never"

        if conn is not None:
            try:
                cur = conn.execute(
                    "SELECT 1 FROM tasks WHERE assignee=? AND current_run_id IS NOT NULL LIMIT 1",
                    (name,),
                )
                busy = cur.fetchone() is not None

                cur = conn.execute(
                    "SELECT COUNT(*) FROM task_runs WHERE profile=? AND started_at >= ?",
                    (name, midnight),
                )
                today = cur.fetchone()[0]

                cur = conn.execute("SELECT COUNT(*) FROM tasks WHERE assignee=?", (name,))
                total = cur.fetchone()[0]

                cur = conn.execute(
                    "SELECT COUNT(*) FROM tasks WHERE assignee=? AND status='done'",
                    (name,),
                )
                completed = cur.fetchone()[0]

                cur = conn.execute(
                    "SELECT COUNT(*) as total,"
                    " SUM(CASE WHEN outcome='completed' THEN 1 ELSE 0 END) as ok"
                    " FROM task_runs WHERE profile=?",
                    (name,),
                )
                row = cur.fetchone()
                total_runs, ok_runs = row[0], (row[1] or 0)
                success = round(100 * ok_runs / total_runs) if total_runs > 0 else 100

                cur = conn.execute(
                    "SELECT MAX(ended_at) FROM task_runs"
                    " WHERE profile=? AND ended_at IS NOT NULL",
                    (name,),
                )
                last_active = _relative_time(cur.fetchone()[0])

            except Exception:
                pass

        if busy:
            status = "busy"
        elif gateway_up:
            status = "online"
        else:
            status = "idle"

        results.append({
            "name": name,
            "role": _role(name),
            "model": model,
            "avatar": name[0].upper(),
            "color": color,
            "status": status,
            "today": today,
            "completed": completed,
            "total": total,
            "success": success,
            "lastActive": last_active,
        })

    if conn is not None:
        conn.close()

    return results


@router.get("/fleet")
def get_fleet():
    profiles = _profile_names()
    midnight = _today_midnight()
    conn = _open_db()

    n_agents = len(profiles)
    n_busy = 0
    tasks_today = 0
    success_pct = "100%"
    avg_latency = "—"

    if conn is not None:
        try:
            cur = conn.execute(
                "SELECT COUNT(DISTINCT assignee) FROM tasks"
                " WHERE current_run_id IS NOT NULL AND assignee IS NOT NULL"
            )
            n_busy = cur.fetchone()[0]

            cur = conn.execute(
                "SELECT COUNT(*) FROM task_runs WHERE started_at >= ?",
                (midnight,),
            )
            tasks_today = cur.fetchone()[0]

            cur = conn.execute(
                "SELECT COUNT(*) as total,"
                " SUM(CASE WHEN outcome='completed' THEN 1 ELSE 0 END) as ok"
                " FROM task_runs"
            )
            row = cur.fetchone()
            total_runs, ok_runs = row[0], (row[1] or 0)
            pct = round(100 * ok_runs / total_runs) if total_runs > 0 else 100
            success_pct = f"{pct}%"

            cur = conn.execute(
                "SELECT AVG(ended_at - started_at) FROM task_runs"
                " WHERE ended_at IS NOT NULL AND started_at IS NOT NULL AND ended_at > started_at"
            )
            avg_sec = cur.fetchone()[0]
            if avg_sec is not None:
                avg_sec = float(avg_sec)
                if avg_sec < 60:
                    avg_latency = f"{avg_sec:.1f}s"
                elif avg_sec < 3600:
                    avg_latency = f"{avg_sec / 60:.1f}m"
                else:
                    avg_latency = f"{avg_sec / 3600:.1f}h"

        except Exception:
            pass

        conn.close()

    return [
        {"value": str(n_agents), "label": "Agents", "color": "#5eead4"},
        {"value": str(n_busy), "label": "Active now", "color": "#2dd4bf"},
        {"value": str(tasks_today), "label": "Tasks today", "color": "#5aa2f0"},
        {"value": success_pct, "label": "Success rate", "color": "#4ade80"},
        {"value": avg_latency, "label": "Avg latency", "color": "#9b8cff"},
    ]
