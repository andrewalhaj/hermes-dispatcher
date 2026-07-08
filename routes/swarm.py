import os
import sqlite3
from pathlib import Path

from fastapi import APIRouter

DB_PATH = os.environ.get("KANBAN_DB", os.path.expanduser("~/.hermes/kanban.db"))
PROFILES_DIR = Path(os.environ.get("HERMES_PROFILES_DIR", os.path.expanduser("~/.hermes/profiles")))

router = APIRouter(prefix="/swarm")


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


def _humanize(name: str) -> str:
    if name == "default":
        return "Hermes"
    return name.replace("-", " ").title()


@router.get("")
def get_swarm():
    profiles = _profile_names()

    # Start with profile-based node ids; always include "default".
    node_ids: set[str] = set(profiles)
    node_ids.add("default")

    task_counts: dict[str, int] = {}
    running_counts: dict[str, int] = {}

    # Orchestrator edges: default -> assignee, weight = # active tasks for that assignee.
    orch_weights: dict[str, int] = {}

    # Dependency edges accumulated as (source_assignee, target_assignee) -> weight.
    dep_edges: dict[tuple[str, str], int] = {}

    conn = _open_db()

    if conn is not None:
        try:
            cur = conn.execute(
                """
                SELECT assignee,
                       COUNT(*) AS task_count,
                       SUM(CASE WHEN status='running' THEN 1 ELSE 0 END) AS running
                FROM tasks
                WHERE status NOT IN ('done', 'archived') AND assignee IS NOT NULL
                GROUP BY assignee
                """
            )
            for row in cur.fetchall():
                assignee = row["assignee"]
                node_ids.add(assignee)
                task_counts[assignee] = row["task_count"]
                running_counts[assignee] = row["running"] or 0
                if assignee != "default":
                    orch_weights[assignee] = row["task_count"]
        except Exception:
            pass

        try:
            cur = conn.execute(
                "SELECT id, assignee FROM tasks"
                " WHERE status NOT IN ('done', 'archived') AND assignee IS NOT NULL"
            )
            active_assignees: dict[str, str] = {row["id"]: row["assignee"] for row in cur.fetchall()}

            cur = conn.execute("SELECT parent_id, child_id FROM task_links")
            for row in cur.fetchall():
                src = active_assignees.get(row["parent_id"])
                tgt = active_assignees.get(row["child_id"])
                if src is None or tgt is None or src == tgt:
                    continue
                key = (src, tgt)
                dep_edges[key] = dep_edges.get(key, 0) + 1
        except Exception:
            pass

        conn.close()

    nodes = [
        {
            "id": nid,
            "label": _humanize(nid),
            "status": "running" if running_counts.get(nid, 0) > 0 else "idle",
            "tasks": task_counts.get(nid, 0),
            "running": running_counts.get(nid, 0),
        }
        for nid in sorted(node_ids)
    ]

    edges_map: dict[tuple[str, str], int] = {}

    for assignee, weight in orch_weights.items():
        key = ("default", assignee)
        edges_map[key] = edges_map.get(key, 0) + weight

    for (src, tgt), weight in dep_edges.items():
        key = (src, tgt)
        edges_map[key] = edges_map.get(key, 0) + weight

    edges = [
        {"source": src, "target": tgt, "weight": w}
        for (src, tgt), w in edges_map.items()
    ]

    return {"nodes": nodes, "edges": edges}
