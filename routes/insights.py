import os
import json
import sqlite3
import datetime
import logging
import traceback
from fastapi import APIRouter

router = APIRouter()
logger = logging.getLogger(__name__)

HERMES_HOME = os.environ.get("HERMES_HOME", "/root/.hermes")


def _kanban_db() -> str:
    return str(os.path.join(HERMES_HOME, "kanban.db"))


def _state_db() -> str:
    return str(os.path.join(HERMES_HOME, "state.db"))


def _midnight_today() -> int:
    now = datetime.datetime.now()
    return int(now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp())


def _week_ago() -> int:
    return int(datetime.datetime.now().timestamp()) - 7 * 86400


@router.get("/insights")
async def get_insights() -> dict:
    today_midnight = _midnight_today()
    week_ago = _week_ago()
    result: dict = {}

    # tasks_today
    try:
        with sqlite3.connect(f"file:{_kanban_db()}?mode=ro", uri=True, check_same_thread=False) as conn:
            cur = conn.execute(
                "SELECT COUNT(*) FROM tasks WHERE started_at IS NOT NULL AND started_at >= ?",
                (today_midnight,),
            )
            result["tasks_today"] = cur.fetchone()[0]
    except Exception as e:
        logger.error(f"tasks_today: {e}", exc_info=True)
        result["tasks_today"] = 0

    # tasks_week
    try:
        with sqlite3.connect(f"file:{_kanban_db()}?mode=ro", uri=True, check_same_thread=False) as conn:
            cur = conn.execute(
                "SELECT COUNT(*) FROM tasks WHERE started_at IS NOT NULL AND started_at >= ?",
                (week_ago,),
            )
            result["tasks_week"] = cur.fetchone()[0]
    except Exception as e:
        logger.error(f"tasks_week: {e}", exc_info=True)
        result["tasks_week"] = 0

    # success_rate
    try:
        with sqlite3.connect(f"file:{_kanban_db()}?mode=ro", uri=True, check_same_thread=False) as conn:
            cur = conn.execute(
                "SELECT COUNT(*), SUM(CASE WHEN outcome='completed' THEN 1 ELSE 0 END) "
                "FROM task_runs WHERE ended_at >= ? AND outcome IS NOT NULL",
                (week_ago,),
            )
            total, completed = cur.fetchone()
            result["success_rate"] = round(100.0 * (completed or 0) / total, 1) if total else 0.0
    except Exception as e:
        logger.error(f"success_rate: {e}", exc_info=True)
        result["success_rate"] = 0.0

    # avg_latency_s
    try:
        with sqlite3.connect(f"file:{_kanban_db()}?mode=ro", uri=True, check_same_thread=False) as conn:
            cur = conn.execute(
                "SELECT AVG(ended_at - started_at) FROM task_runs "
                "WHERE ended_at >= ? AND ended_at IS NOT NULL AND started_at IS NOT NULL AND outcome='completed'",
                (week_ago,),
            )
            val = cur.fetchone()[0]
            result["avg_latency_s"] = round(float(val), 1) if val is not None else 0.0
    except Exception as e:
        logger.error(f"avg_latency_s: {e}", exc_info=True)
        result["avg_latency_s"] = 0.0

    # by_profile
    try:
        with sqlite3.connect(f"file:{_kanban_db()}?mode=ro", uri=True, check_same_thread=False) as conn:
            cur = conn.execute(
                """
                SELECT profile,
                    SUM(CASE WHEN outcome='completed' THEN 1 ELSE 0 END),
                    SUM(CASE WHEN outcome IN ('completed','crashed','blocked','reclaimed') THEN 1 ELSE 0 END)
                FROM task_runs
                GROUP BY profile
                """
            )
            runs_by_profile = {row[0]: {"completed": row[1] or 0, "terminal": row[2] or 0} for row in cur.fetchall()}

            cur = conn.execute(
                "SELECT assignee, COUNT(*) FROM tasks WHERE status='running' GROUP BY assignee"
            )
            running_by_assignee = {row[0]: row[1] for row in cur.fetchall()}

            by_profile = []
            for profile, data in runs_by_profile.items():
                completed = data["completed"]
                terminal = data["terminal"]
                running = running_by_assignee.get(profile, 0)
                sr = round(100.0 * completed / terminal, 1) if terminal > 0 else 0.0
                by_profile.append(
                    {"profile": profile, "completed": completed, "running": running, "success_rate": sr}
                )

            by_profile.sort(key=lambda x: x["completed"], reverse=True)
            result["by_profile"] = by_profile[:15]
    except Exception as e:
        logger.error(f"by_profile: {e}", exc_info=True)
        result["by_profile"] = []

    # sessions_today
    try:
        with sqlite3.connect(f"file:{_state_db()}?mode=ro", uri=True, check_same_thread=False) as conn:
            cur = conn.execute(
                "SELECT COUNT(*) FROM sessions WHERE started_at >= ?", (today_midnight,)
            )
            result["sessions_today"] = cur.fetchone()[0]
    except Exception as e:
        logger.error(f"sessions_today: {e}", exc_info=True)
        result["sessions_today"] = 0

    # messages_today
    try:
        with sqlite3.connect(f"file:{_state_db()}?mode=ro", uri=True, check_same_thread=False) as conn:
            cur = conn.execute(
                "SELECT COUNT(*) FROM messages WHERE timestamp >= ?", (today_midnight,)
            )
            result["messages_today"] = cur.fetchone()[0]
    except Exception as e:
        logger.error(f"messages_today: {e}", exc_info=True)
        result["messages_today"] = 0

    # kanban_throughput (last 7 days, oldest first)
    try:
        with sqlite3.connect(f"file:{_kanban_db()}?mode=ro", uri=True, check_same_thread=False) as conn:
            throughput = []
            now = datetime.datetime.now()
            for i in range(6, -1, -1):
                day = now - datetime.timedelta(days=i)
                day_start = int(day.replace(hour=0, minute=0, second=0, microsecond=0).timestamp())
                day_end = int(day.replace(hour=23, minute=59, second=59, microsecond=999999).timestamp())
                cur = conn.execute(
                    "SELECT COUNT(*) FROM task_runs WHERE outcome='completed' AND ended_at >= ? AND ended_at <= ?",
                    (day_start, day_end),
                )
                throughput.append({"date": day.strftime("%a"), "completed": cur.fetchone()[0]})
            result["kanban_throughput"] = throughput
    except Exception as e:
        logger.error(f"kanban_throughput: {e}", exc_info=True)
        result["kanban_throughput"] = [{"date": "Mon", "completed": 0}] * 7

    # top_skills
    try:
        skill_counts: dict = {}
        # Primary source: state.db messages where tool_name='skill_view'
        with sqlite3.connect(f"file:{_state_db()}?mode=ro", uri=True, check_same_thread=False) as conn:
            cur = conn.execute(
                "SELECT content FROM messages WHERE tool_name = 'skill_view' AND content LIKE '%\"success\": true%'"
            )
            for (content_json,) in cur.fetchall():
                try:
                    data = json.loads(content_json)
                    if data.get("success") and data.get("name"):
                        name = data["name"]
                        skill_counts[name] = skill_counts.get(name, 0) + 1
                except Exception:
                    pass

        # Fallback: tasks.skills from kanban.db (only if primary source yields nothing)
        if not skill_counts:
            with sqlite3.connect(f"file:{_kanban_db()}?mode=ro", uri=True, check_same_thread=False) as conn:
                cur = conn.execute(
                    "SELECT skills FROM tasks WHERE skills IS NOT NULL AND skills != '' AND skills != '[]'"
                )
                for (skills_json,) in cur.fetchall():
                    try:
                        skills = json.loads(skills_json)
                        if isinstance(skills, list):
                            for skill in skills:
                                if isinstance(skill, str) and skill:
                                    skill_counts[skill] = skill_counts.get(skill, 0) + 1
                    except Exception:
                        pass

        sorted_skills = sorted(skill_counts.items(), key=lambda x: x[1], reverse=True)
        result["top_skills"] = [{"skill": s, "count": c} for s, c in sorted_skills[:20]]
    except Exception as e:
        logger.error(f"top_skills: {e}", exc_info=True)
        result["top_skills"] = []

    # tokens from sessions table (messages.token_count is never populated)
    try:
        with sqlite3.connect(f"file:{_state_db()}?mode=ro", uri=True, check_same_thread=False) as conn:
            row = conn.execute(
                "SELECT SUM(input_tokens), SUM(output_tokens) FROM sessions WHERE started_at >= ?",
                (today_midnight,),
            ).fetchone()
            result["tokens_input"] = int(row[0] or 0)
            result["tokens_output"] = int(row[1] or 0)
    except Exception as e:
        logger.error(f"tokens: {e}", exc_info=True)
        result["tokens_input"] = 0
        result["tokens_output"] = 0

    return result
