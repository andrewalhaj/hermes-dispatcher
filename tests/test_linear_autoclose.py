"""Tests for the Kanban → Linear auto-close feature.

Covers:
  1. Reference extraction (idempotency_key, identifier, URL) — pure logic.
  2. close_linear_issue() against a fully-mocked Linear GraphQL surface:
     - happy path (open issue → completed + comment)
     - already-completed issue (no state update, no comment)
     - issue not found
     - no API key configured
  3. autoclose_for_card() DB resolver: reads a real (temp) Kanban DB,
     extracts the ref, and drives the close — verifies the require_done gate.
  4. The /api/hooks/kanban webhook end-to-end through a FastAPI TestClient
     (auth gate + done-event filtering + delegation to the orchestrator).

Runner-agnostic: plain unittest.TestCase so it runs under pytest and the
stdlib runner. The Linear network layer (linear_autoclose._graphql) is
monkeypatched, so no test ever touches the real Linear API.
"""
import importlib
import json
import os
import sqlite3
import sys
import tempfile
import time
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Point HERMES_HOME / KANBAN_DB at scratch space before importing the module
# (it reads KANBAN_DB at import time).
_TMP_HOME = tempfile.mkdtemp(prefix="hermes_autoclose_test_")
os.environ["HERMES_HOME"] = _TMP_HOME
_TMP_DB = str(Path(_TMP_HOME) / "kanban.db")
os.environ["KANBAN_DB"] = _TMP_DB
os.environ["LINEAR_API_KEY"] = "lin_test_key"
os.environ["DASHBOARD_PUBLIC_URL"] = "https://dash.example.com"

from routes import linear_autoclose as la  # noqa: E402


# ---------------------------------------------------------------------------
# Fake Linear GraphQL backend
# ---------------------------------------------------------------------------
class FakeLinear:
    """Routes GraphQL queries by signature to canned responses + records calls."""

    def __init__(self, *, issue_state_type="unstarted", issue_found=True):
        self.issue_state_type = issue_state_type
        self.issue_found = issue_found
        self.calls = []  # list of (kind, variables)

    def __call__(self, query, variables, key, timeout=15):
        self.calls.append((self._kind(query), variables))
        if "query IssueState" in query:
            if not self.issue_found:
                return {"data": {"issue": None}}
            return {"data": {"issue": {
                "id": "uuid-issue-1",
                "identifier": "HER-42",
                "url": "https://linear.app/acme/issue/HER-42/x",
                "state": {"id": "st-cur", "name": "In Progress", "type": self.issue_state_type},
                "team": {"id": "team-1"},
            }}}
        if "query TeamStates" in query:
            return {"data": {"team": {"states": {"nodes": [
                {"id": "st-todo", "name": "Todo", "type": "unstarted"},
                {"id": "st-done", "name": "Done", "type": "completed"},
                {"id": "st-cancel", "name": "Canceled", "type": "canceled"},
            ]}}}}
        if "mutation CloseIssue" in query:
            return {"data": {"issueUpdate": {"success": True, "issue": {
                "id": "uuid-issue-1", "identifier": "HER-42",
                "state": {"id": variables["stateId"], "name": "Done", "type": "completed"},
            }}}}
        if "mutation Comment" in query:
            return {"data": {"commentCreate": {"success": True, "comment": {"id": "cmt-1"}}}}
        raise AssertionError(f"unexpected query: {query[:60]}")

    @staticmethod
    def _kind(query):
        for k in ("IssueState", "TeamStates", "CloseIssue", "Comment"):
            if k in query:
                return k
        return "?"


# ---------------------------------------------------------------------------
# 1. Reference extraction
# ---------------------------------------------------------------------------
class ExtractRefTest(unittest.TestCase):
    def test_idempotency_key_uuid(self):
        ref = la.extract_linear_ref(idempotency_key="linear-1a2b3c4d-5e6f-7081-9aaa-bbbbccccdddd")
        self.assertEqual(ref, "1a2b3c4d-5e6f-7081-9aaa-bbbbccccdddd")

    def test_identifier_in_body(self):
        ref = la.extract_linear_ref(body="See HER-42 for context.")
        self.assertEqual(ref, "HER-42")

    def test_url_in_body_preferred_over_loose_identifier(self):
        body = "Tracking https://linear.app/acme/issue/HER-99/title here, mentions HER-1 too"
        self.assertEqual(la.extract_linear_ref(body=body), "HER-99")

    def test_title_fallback(self):
        self.assertEqual(la.extract_linear_ref(title="[ABC-7] fix bug"), "ABC-7")

    def test_none_when_no_ref(self):
        self.assertIsNone(la.extract_linear_ref(body="nothing here", title="plain"))

    def test_idempotency_non_linear_ignored(self):
        self.assertIsNone(la.extract_linear_ref(idempotency_key="github-123", body="x"))


# ---------------------------------------------------------------------------
# 2. close_linear_issue against the fake backend
# ---------------------------------------------------------------------------
class CloseIssueTest(unittest.TestCase):
    def setUp(self):
        self._orig = la._graphql

    def tearDown(self):
        la._graphql = self._orig

    def test_happy_path_closes_and_comments(self):
        fake = FakeLinear(issue_state_type="started")
        la._graphql = fake
        res = la.close_linear_issue("HER-42", task_id="t_abc123", key="k")
        self.assertEqual(res["status"], "ok")
        self.assertEqual(res["state"], "completed")
        self.assertEqual(res["comment"], "commented")
        kinds = [c[0] for c in fake.calls]
        self.assertEqual(kinds, ["IssueState", "TeamStates", "CloseIssue", "Comment"])
        # Comment body carries the card link.
        comment_vars = fake.calls[-1][1]
        self.assertIn("Completed via Kanban", comment_vars["body"])
        self.assertIn("t_abc123", comment_vars["body"])
        self.assertIn("dash.example.com", comment_vars["body"])
        # Chosen state is the completed-type "Done" state.
        self.assertEqual(fake.calls[2][1]["stateId"], "st-done")

    def test_already_completed_skips_update_and_comment(self):
        fake = FakeLinear(issue_state_type="completed")
        la._graphql = fake
        res = la.close_linear_issue("HER-42", task_id="t_abc123", key="k")
        self.assertEqual(res["status"], "ok")
        self.assertEqual(res["state"], "already_completed")
        self.assertEqual(res["comment"], "skipped")
        # Only the lookup happened — no mutation, no comment.
        self.assertEqual([c[0] for c in fake.calls], ["IssueState"])

    def test_issue_not_found(self):
        fake = FakeLinear(issue_found=False)
        la._graphql = fake
        res = la.close_linear_issue("HER-404", task_id="t_x", key="k")
        self.assertEqual(res["status"], "not_found")

    def test_no_api_key(self):
        res = la.close_linear_issue("HER-42", task_id="t_x", key="")
        # key="" forces a re-resolve; clear env to be sure none is found.
        old = os.environ.pop("LINEAR_API_KEY", None)
        try:
            res = la.close_linear_issue("HER-42", task_id="t_x", key=None)
        finally:
            if old is not None:
                os.environ["LINEAR_API_KEY"] = old
        self.assertEqual(res["status"], "skipped")
        self.assertEqual(res["reason"], "no_api_key")


# ---------------------------------------------------------------------------
# 3. autoclose_for_card DB resolver
# ---------------------------------------------------------------------------
def _make_db(path):
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE tasks (id TEXT PRIMARY KEY, title TEXT, body TEXT, "
        "status TEXT, idempotency_key TEXT)"
    )
    conn.commit()
    return conn


class AutocloseForCardTest(unittest.TestCase):
    def setUp(self):
        self._orig = la._graphql
        # Fresh DB per test.
        if os.path.exists(_TMP_DB):
            os.remove(_TMP_DB)
        self.conn = _make_db(_TMP_DB)

    def tearDown(self):
        la._graphql = self._orig
        self.conn.close()
        if os.path.exists(_TMP_DB):
            os.remove(_TMP_DB)

    def _insert(self, task_id, status, body="", idem=None, title=""):
        self.conn.execute(
            "INSERT INTO tasks (id, title, body, status, idempotency_key) VALUES (?,?,?,?,?)",
            (task_id, title, body, status, idem),
        )
        self.conn.commit()

    def test_done_card_with_idempotency_key(self):
        fake = FakeLinear(issue_state_type="started")
        la._graphql = fake
        self._insert("t_1", "done", idem="linear-1a2b3c4d-5e6f-7081-9aaa-bbbbccccdddd")
        res = la.autoclose_for_card("t_1")
        self.assertEqual(res["status"], "ok")
        self.assertEqual(res["state"], "completed")
        self.assertEqual(res["task_id"], "t_1")

    def test_done_card_with_identifier_in_body(self):
        fake = FakeLinear(issue_state_type="started")
        la._graphql = fake
        self._insert("t_2", "done", body="Linked to HER-42 via intake.")
        res = la.autoclose_for_card("t_2")
        self.assertEqual(res["status"], "ok")

    def test_not_done_card_is_gated(self):
        fake = FakeLinear()
        la._graphql = fake
        self._insert("t_3", "running", idem="linear-uuid-issue-1")
        res = la.autoclose_for_card("t_3")
        self.assertEqual(res["status"], "skipped")
        self.assertEqual(res["reason"], "card_not_done")
        self.assertEqual(fake.calls, [])  # never hit Linear

    def test_card_without_ref(self):
        fake = FakeLinear()
        la._graphql = fake
        self._insert("t_4", "done", body="no linear here")
        res = la.autoclose_for_card("t_4")
        self.assertEqual(res["status"], "skipped")
        self.assertEqual(res["reason"], "no_linear_ref")

    def test_missing_card(self):
        res = la.autoclose_for_card("t_nope")
        self.assertEqual(res["status"], "not_found")


# ---------------------------------------------------------------------------
# 4. /api/hooks/kanban webhook end-to-end
# ---------------------------------------------------------------------------
def _testclient_available():
    try:
        from fastapi.testclient import TestClient  # noqa: F401
        return True
    except Exception:
        return False


@unittest.skipIf(
    not _testclient_available(),
    "fastapi TestClient unavailable (httpx not installed); webhook E2E skipped. "
    "The orchestrator is still covered directly by AutocloseForCardTest.",
)
class KanbanWebhookTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["WEBHOOK_SECRET"] = "test_secret"
        # Import hooks AFTER setting WEBHOOK_SECRET (read at import time).
        import routes.hooks as hooks
        importlib.reload(hooks)
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        app = FastAPI()
        app.include_router(hooks.router, prefix="/api")
        cls.client = TestClient(app)
        cls.hooks = hooks

    def setUp(self):
        self._orig = la._graphql
        if os.path.exists(_TMP_DB):
            os.remove(_TMP_DB)
        self.conn = _make_db(_TMP_DB)

    def tearDown(self):
        la._graphql = self._orig
        self.conn.close()
        if os.path.exists(_TMP_DB):
            os.remove(_TMP_DB)

    def _insert(self, task_id, status, body="", idem=None):
        self.conn.execute(
            "INSERT INTO tasks (id, title, body, status, idempotency_key) VALUES (?,?,?,?,?)",
            (task_id, "", body, status, idem),
        )
        self.conn.commit()

    def _post(self, payload, token: object = "test_secret"):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.client.post("/api/hooks/kanban", json=payload, headers=headers)

    def test_missing_auth_rejected(self):
        resp = self._post({"task_id": "t_1", "status": "done"}, token=None)
        self.assertEqual(resp.status_code, 401)

    def test_bad_token_rejected(self):
        resp = self._post({"task_id": "t_1", "status": "done"}, token="wrong")
        self.assertEqual(resp.status_code, 401)

    def test_done_event_triggers_close(self):
        fake = FakeLinear(issue_state_type="started")
        la._graphql = fake
        self._insert("t_1", "done", idem="linear-1a2b3c4d-5e6f-7081-9aaa-bbbbccccdddd")
        resp = self._post({"task_id": "t_1", "status": "done"})
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["state"], "completed")

    def test_event_alias_completed(self):
        fake = FakeLinear(issue_state_type="started")
        la._graphql = fake
        self._insert("t_2", "done", body="HER-42")
        resp = self._post({"task_id": "t_2", "event": "completed"})
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(resp.json()["status"], "ok")

    def test_non_done_event_ignored(self):
        fake = FakeLinear()
        la._graphql = fake
        resp = self._post({"task_id": "t_3", "status": "running"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "ignored")
        self.assertEqual(fake.calls, [])

    def test_missing_task_id(self):
        resp = self._post({"status": "done"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "skipped")


if __name__ == "__main__":
    unittest.main(verbosity=2)
