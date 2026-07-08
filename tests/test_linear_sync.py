"""Tests for routes/linear_sync.py — bidirectional Linear↔Kanban comment sync.

Exercises the pure logic and DB paths with a temp SQLite kanban DB and a
monkeypatched Linear API call (no network). Run:

    cd <repo-root> && .venv/bin/python -m pytest tests/test_linear_sync.py -v
"""
import asyncio
import importlib
import json
import sqlite3
import time

import pytest


def _make_db(path):
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE tasks (
            id TEXT PRIMARY KEY, title TEXT, body TEXT, status TEXT,
            created_at INTEGER, idempotency_key TEXT
        );
        CREATE TABLE task_comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT, author TEXT, body TEXT, created_at INTEGER
        );
        CREATE TABLE task_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT, run_id INTEGER, kind TEXT, payload TEXT, created_at INTEGER
        );
        """
    )
    now = int(time.time())
    # A task linked to Linear issue ISSUE-123, plus an unlinked task.
    conn.execute(
        "INSERT INTO tasks (id,title,body,status,created_at,idempotency_key) "
        "VALUES ('t_linked','Linked','b','running',?,?)",
        (now, "linear-ISSUE-123"),
    )
    conn.execute(
        "INSERT INTO tasks (id,title,body,status,created_at,idempotency_key) "
        "VALUES ('t_plain','Plain','b','running',?,NULL)",
        (now,),
    )
    conn.commit()
    conn.close()


@pytest.fixture()
def mod(tmp_path, monkeypatch):
    db = tmp_path / "kanban.db"
    _make_db(str(db))
    state = tmp_path / "sync_state.json"
    monkeypatch.setenv("KANBAN_DB", str(db))
    monkeypatch.setenv("LINEAR_API_KEY", "lin_test_key")
    import routes.linear_sync as ls
    importlib.reload(ls)
    # Redirect state file + DB path that were bound at import time.
    ls.DB_PATH = str(db)
    ls._SYNC_STATE_FILE = state
    ls.LINEAR_API_KEY = "lin_test_key"
    return ls


# --- mapping -------------------------------------------------------------

def test_mapping_both_directions(mod):
    assert mod.linear_issue_for_task("t_linked") == "ISSUE-123"
    assert mod.linear_issue_for_task("t_plain") is None
    assert mod.task_for_linear_issue("ISSUE-123") == "t_linked"
    assert mod.task_for_linear_issue("NOPE") is None


# --- inbound: Linear → Kanban -------------------------------------------

def test_inbound_writes_kanban_comment(mod):
    res = mod.handle_inbound_linear_comment(
        {"issueId": "ISSUE-123", "body": "Hello from Linear"}, actor_name="Andrew"
    )
    assert res["status"] == "synced"
    assert res["task_id"] == "t_linked"
    conn = sqlite3.connect(mod.DB_PATH)
    row = conn.execute(
        "SELECT author, body FROM task_comments WHERE task_id='t_linked'"
    ).fetchone()
    conn.close()
    assert row is not None
    assert row[0].startswith("linear:")           # inbound author tag
    assert mod.SYNC_MARKER_LINEAR in row[1]        # 'via Linear' footer
    assert "Hello from Linear" in row[1]


def test_inbound_skips_echo_of_our_outbound(mod):
    # A Linear comment that is actually our own pushed comment coming back.
    res = mod.handle_inbound_linear_comment(
        {"issueId": "ISSUE-123", "body": f"echo\n\n{mod.SYNC_MARKER_KANBAN}"},
        actor_name="bot",
    )
    assert res["status"] == "skipped"
    assert res["reason"] == "echo_of_outbound"


def test_inbound_skips_unlinked_issue(mod):
    res = mod.handle_inbound_linear_comment(
        {"issueId": "UNKNOWN", "body": "x"}, actor_name="a"
    )
    assert res["status"] == "skipped"
    assert res["reason"] == "no_linked_task"


# --- outbound: Kanban → Linear ------------------------------------------

def _insert_comment(mod, task_id, author, body):
    conn = sqlite3.connect(mod.DB_PATH)
    cur = conn.execute(
        "INSERT INTO task_comments (task_id,author,body,created_at) VALUES (?,?,?,?)",
        (task_id, author, body, int(time.time())),
    )
    conn.commit()
    cid = cur.lastrowid
    row = conn.execute("SELECT id,task_id,author,body FROM task_comments WHERE id=?", (cid,)).fetchone()
    conn.close()
    # emulate sqlite3.Row access by name via a tiny shim
    class R(dict):
        def __getitem__(self, k):
            return super().__getitem__(k)
    return R(id=row[0], task_id=row[1], author=row[2], body=row[3])


def test_outbound_pushes_native_comment(mod, monkeypatch):
    calls = []

    async def fake_create(issue_id, body):
        calls.append((issue_id, body))
        return {"id": "lc_1", "url": "https://linear.app/c/lc_1"}

    monkeypatch.setattr(mod, "_linear_comment_create", fake_create)
    row = _insert_comment(mod, "t_linked", "coder", "native work note")
    status = asyncio.run(mod._sync_one_outbound(row))
    assert status == "synced"
    assert len(calls) == 1
    assert calls[0][0] == "ISSUE-123"
    assert mod.SYNC_MARKER_KANBAN in calls[0][1]   # outbound 'via Kanban' footer


def test_outbound_skips_inbound_echo(mod, monkeypatch):
    called = []
    async def fake_create(issue_id, body):
        called.append(1); return {"id": "x"}
    monkeypatch.setattr(mod, "_linear_comment_create", fake_create)

    # Comment that came FROM Linear (carries the via-Linear marker + author tag)
    row = _insert_comment(mod, "t_linked", "linear:Andrew", f"x\n\n{mod.SYNC_MARKER_LINEAR}")
    status = asyncio.run(mod._sync_one_outbound(row))
    assert status == "skipped"
    assert called == []                            # never hit the API


def test_outbound_no_link_for_plain_task(mod, monkeypatch):
    async def fake_create(issue_id, body):
        return {"id": "x"}
    monkeypatch.setattr(mod, "_linear_comment_create", fake_create)
    row = _insert_comment(mod, "t_plain", "coder", "note")
    status = asyncio.run(mod._sync_one_outbound(row))
    assert status == "no_link"


# --- state persistence ---------------------------------------------------

def test_state_roundtrip(mod):
    mod._save_last_synced_id(42)
    assert mod._load_last_synced_id() == 42
