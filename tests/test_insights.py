"""routes/insights.py: range clamp, per-metric window filtering, multi-profile aggregation."""

import asyncio
import importlib
import json
import sqlite3
import sys
import time
from pathlib import Path

import pytest
from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

NOW = int(time.time())
H = 3600
D = 86400


def _db(path, ddl, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(path)
    for stmt in ddl:
        c.execute(stmt)
    for sql, args in rows:
        c.execute(sql, args)
    c.commit()
    c.close()


STATE_DDL = [
    "CREATE TABLE sessions (started_at INT, input_tokens INT, output_tokens INT)",
    "CREATE TABLE messages (timestamp INT, tool_name TEXT, content TEXT)",
]


def _skill(name):
    return json.dumps({"success": True, "name": name})


@pytest.fixture
def ins(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    import routes.insights as m
    importlib.reload(m)
    _db(tmp_path / "kanban.db",
        ["CREATE TABLE tasks (started_at INT, status TEXT, assignee TEXT, skills TEXT)",
         "CREATE TABLE task_runs (profile TEXT, outcome TEXT, started_at INT, ended_at INT)"],
        [("INSERT INTO tasks VALUES (?,?,?,?)", (NOW - 2 * H, "running", "coder", None)),
         ("INSERT INTO tasks VALUES (?,?,?,?)", (NOW - 2 * D, "done", "coder", None)),
         ("INSERT INTO tasks VALUES (?,?,?,?)", (NOW - 5 * D, "done", "coder", None)),
         ("INSERT INTO task_runs VALUES (?,?,?,?)", ("coder", "completed", NOW - 2 * H - 100, NOW - 2 * H)),
         ("INSERT INTO task_runs VALUES (?,?,?,?)", ("coder", "crashed", NOW - 3 * H - 50, NOW - 3 * H)),
         ("INSERT INTO task_runs VALUES (?,?,?,?)", ("coder", "completed", NOW - 2 * D - 300, NOW - 2 * D)),
         ("INSERT INTO task_runs VALUES (?,?,?,?)", ("coder", "completed", NOW - 5 * D - 10, NOW - 5 * D))])
    # default profile
    _db(tmp_path / "state.db", STATE_DDL,
        [("INSERT INTO sessions VALUES (?,?,?)", (NOW - H, 10, 5)),
         ("INSERT INTO sessions VALUES (?,?,?)", (NOW - 2 * D, 100, 50)),
         ("INSERT INTO messages VALUES (?,?,?)", (NOW - H, "skill_view", _skill("a"))),
         ("INSERT INTO messages VALUES (?,?,?)", (NOW - 2 * D, "skill_view", _skill("a"))),
         ("INSERT INTO messages VALUES (?,?,?)", (NOW - 2 * D, None, "hi"))])
    # a profile, and a dot-dir that must be ignored
    _db(tmp_path / "profiles" / "coder" / "state.db", STATE_DDL,
        [("INSERT INTO sessions VALUES (?,?,?)", (NOW - H, 1, 2)),
         ("INSERT INTO messages VALUES (?,?,?)", (NOW - H, "skill_view", _skill("b"))),
         ("INSERT INTO messages VALUES (?,?,?)", (NOW - 6 * D, "skill_view", _skill("b")))])
    _db(tmp_path / "profiles" / ".hidden" / "state.db", STATE_DDL,
        [("INSERT INTO sessions VALUES (?,?,?)", (NOW - H, 999, 999))])
    (tmp_path / "profiles" / "broken").mkdir()
    (tmp_path / "profiles" / "broken" / "state.db").write_text("not a db")
    return lambda days=7: asyncio.run(m.get_insights(days))


@pytest.mark.parametrize("bad", [0, 2, 30, -1])
def test_days_outside_set_is_400(ins, bad):
    with pytest.raises(HTTPException) as e:
        ins(bad)
    assert e.value.status_code == 400


def test_one_day_window(ins):
    r = ins(1)
    assert r["tasks_started"] == 1
    assert r["sessions"] == 2  # default + coder profile; dot-dir and broken DB ignored
    assert r["messages"] == 2
    assert r["success_rate"] == 50.0  # 1 completed of 2 terminal runs
    assert r["avg_latency_s"] == 100.0
    assert r["tokens_input"] == 11 and r["tokens_output"] == 7
    assert {s["skill"]: s["count"] for s in r["top_skills"]} == {"a": 1, "b": 1}
    assert len(r["kanban_throughput"]) == 24
    assert sum(b["completed"] for b in r["kanban_throughput"]) == 1


def test_three_day_window_includes_older_rows(ins):
    r = ins(3)
    assert r["tasks_started"] == 2
    assert r["sessions"] == 3 and r["messages"] == 4
    assert round(r["success_rate"], 1) == 66.7
    assert r["tokens_input"] == 111
    assert {s["skill"]: s["count"] for s in r["top_skills"]} == {"a": 2, "b": 1}
    assert len(r["kanban_throughput"]) == 3
    assert sum(b["completed"] for b in r["kanban_throughput"]) == 2
    assert r["by_profile"] == [{"profile": "coder", "completed": 2, "running": 1, "success_rate": 66.7}]


def test_seven_day_window_and_default(ins):
    r = ins()
    assert r["days"] == 7
    assert r["tasks_started"] == 3
    assert r["messages"] == 5
    assert {s["skill"]: s["count"] for s in r["top_skills"]} == {"a": 2, "b": 2}
    assert len(r["kanban_throughput"]) == 7
    assert sum(b["completed"] for b in r["kanban_throughput"]) == 3
