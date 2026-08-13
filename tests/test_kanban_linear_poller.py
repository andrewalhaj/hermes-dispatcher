"""Tests for the Kanban → Linear REVERSE-SYNC POLLER (routes/kanban_linear_poller).

This covers the poller that closes linked Linear issues when a Kanban card
reaches ``done`` via the worker ``kanban_complete`` path (which writes straight
into kanban.db and fires no webhook — the gap this feature fills).

The close logic itself (routes/linear_autoclose) has its own suite
(test_linear_autoclose.py); here we test the POLLER's responsibilities:

  1. Candidate selection: only done + linear-mapped cards, archived excluded.
  2. Idempotency: a done-mapped issue is closed exactly ONCE across repeat ticks.
  3. Archive ≠ resolved: an archived card is never closed.
  4. Linear API error → NOT marked synced → retried on the next tick.
  5. already_completed / not_found → terminal (marked synced, not retried).

The Linear network layer (linear_autoclose._graphql) is monkeypatched via the
same FakeLinear backend the autoclose suite uses, so no test touches the real
Linear API. State DBs live in scratch temp space.
"""
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

# Scratch home/DBs BEFORE importing the modules (they read env at import time).
_TMP_HOME = tempfile.mkdtemp(prefix="hermes_revsync_test_")
os.environ["HERMES_HOME"] = _TMP_HOME
_TMP_KANBAN_DB = str(Path(_TMP_HOME) / "kanban.db")
_TMP_SYNC_DB = str(Path(_TMP_HOME) / "linear_reverse_sync.db")
os.environ["KANBAN_DB"] = _TMP_KANBAN_DB
os.environ["LINEAR_REVERSE_SYNC_DB"] = _TMP_SYNC_DB
os.environ["LINEAR_API_KEY"] = "lin_test_key"
os.environ["DASHBOARD_PUBLIC_URL"] = "https://dash.example.com"

from routes import linear_autoclose as la  # noqa: E402
from routes import kanban_linear_poller as poller  # noqa: E402


# ---------------------------------------------------------------------------
# Fake Linear GraphQL backend (mirrors test_linear_autoclose.FakeLinear)
# ---------------------------------------------------------------------------
class FakeLinear:
    def __init__(self, *, issue_state_type="unstarted", issue_found=True, raise_on_update=False):
        self.issue_state_type = issue_state_type
        self.issue_found = issue_found
        self.raise_on_update = raise_on_update
        self.calls = []

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
            ]}}}}
        if "mutation CloseIssue" in query:
            if self.raise_on_update:
                raise RuntimeError("simulated Linear API outage")
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


def _make_kanban_db(path):
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE tasks (id TEXT PRIMARY KEY, title TEXT, body TEXT, "
        "status TEXT, idempotency_key TEXT, completed_at INTEGER)"
    )
    conn.commit()
    return conn


class ReverseSyncPollerTest(unittest.TestCase):
    def setUp(self):
        self._orig_graphql = la._graphql
        # Pin module globals to our scratch DBs. These are frozen at import
        # time from env; when another test module imports `la`/`poller` first
        # with a different KANBAN_DB, the import-time value is stale — so we
        # (re)assign here to stay order-independent under the full suite.
        self._orig_la_db = la.KANBAN_DB
        self._orig_poller_db = poller.KANBAN_DB
        self._orig_sync_db = poller.REVERSE_SYNC_DB
        la.KANBAN_DB = _TMP_KANBAN_DB
        poller.KANBAN_DB = _TMP_KANBAN_DB
        poller.REVERSE_SYNC_DB = _TMP_SYNC_DB
        # Fresh kanban DB + wiped sync DB every test.
        for p in (_TMP_KANBAN_DB, _TMP_SYNC_DB):
            if os.path.exists(p):
                os.remove(p)
        self.kb = _make_kanban_db(_TMP_KANBAN_DB)
        poller._ensure_schema()

    def tearDown(self):
        la._graphql = self._orig_graphql
        la.KANBAN_DB = self._orig_la_db
        poller.KANBAN_DB = self._orig_poller_db
        poller.REVERSE_SYNC_DB = self._orig_sync_db
        self.kb.close()
        for p in (_TMP_KANBAN_DB, _TMP_SYNC_DB):
            if os.path.exists(p):
                os.remove(p)

    def _insert(self, task_id, status, idem=None, body="", completed_at=None):
        self.kb.execute(
            "INSERT INTO tasks (id, title, body, status, idempotency_key, completed_at) "
            "VALUES (?,?,?,?,?,?)",
            (task_id, "", body, status, idem, completed_at or int(time.time())),
        )
        self.kb.commit()

    # -- candidate selection -------------------------------------------------
    def test_candidate_query_only_done_and_linear_mapped(self):
        self._insert("t_done_linear", "done", idem="linear-uuid-a")
        self._insert("t_done_nolinear", "done", idem=None)
        self._insert("t_running_linear", "running", idem="linear-uuid-b")
        self._insert("t_archived_linear", "archived", idem="linear-uuid-c")
        ids = poller._done_linear_task_ids()
        self.assertEqual(ids, ["t_done_linear"])

    def test_archived_card_never_closed(self):
        fake = FakeLinear(issue_state_type="started")
        la._graphql = fake
        self._insert("t_arch", "archived", idem="linear-uuid-arch")
        counts = poller._tick()
        self.assertEqual(counts["scanned"], 0)
        self.assertEqual(fake.calls, [])  # Linear never touched

    # -- happy path + idempotency -------------------------------------------
    def test_done_card_closed_once_idempotent(self):
        fake = FakeLinear(issue_state_type="started")
        la._graphql = fake
        self._insert("t_1", "done", idem="linear-1a2b3c4d-5e6f-7081-9aaa-bbbbccccdddd")

        # First tick: closes the issue.
        counts1 = poller._tick()
        self.assertEqual(counts1["scanned"], 1)
        self.assertEqual(counts1["closed"], 1)
        close_calls_after_1 = sum(1 for c in fake.calls if c[0] == "CloseIssue")
        self.assertEqual(close_calls_after_1, 1)

        # Second tick: card drops out of the candidate set — NO further close.
        counts2 = poller._tick()
        self.assertEqual(counts2["scanned"], 0)
        close_calls_after_2 = sum(1 for c in fake.calls if c[0] == "CloseIssue")
        self.assertEqual(close_calls_after_2, 1, "issue must be closed exactly once")

        # Sync state recorded.
        with sqlite3.connect(_TMP_SYNC_DB) as sc:
            sc.row_factory = sqlite3.Row
            row = sc.execute(
                "SELECT * FROM reverse_sync WHERE task_id='t_1'"
            ).fetchone()
        self.assertIsNotNone(row)
        self.assertIsNotNone(row["synced_at"])
        self.assertEqual(row["linear_state"], "completed")

    def test_already_completed_marked_synced_not_retried(self):
        fake = FakeLinear(issue_state_type="completed")
        la._graphql = fake
        self._insert("t_2", "done", idem="linear-2b2b3c4d-5e6f-7081-9aaa-bbbbccccdddd")
        counts = poller._tick()
        self.assertEqual(counts["already"], 1)
        # No CloseIssue mutation for an already-completed issue.
        self.assertEqual([c[0] for c in fake.calls], ["IssueState"])
        # Second tick: nothing to scan.
        self.assertEqual(poller._tick()["scanned"], 0)

    def test_not_found_marked_synced(self):
        fake = FakeLinear(issue_found=False)
        la._graphql = fake
        self._insert("t_3", "done", idem="linear-3c2b3c4d-5e6f-7081-9aaa-bbbbccccdddd")
        counts = poller._tick()
        self.assertEqual(counts["not_found"], 1)
        self.assertEqual(poller._tick()["scanned"], 0)

    # -- error → retry -------------------------------------------------------
    def test_linear_error_is_retried_next_tick(self):
        fake = FakeLinear(issue_state_type="started", raise_on_update=True)
        la._graphql = fake
        self._insert("t_4", "done", idem="linear-4d2b3c4d-5e6f-7081-9aaa-bbbbccccdddd")

        counts1 = poller._tick()
        self.assertEqual(counts1["retry"], 1)
        self.assertEqual(counts1["closed"], 0)
        # Still a candidate — NOT marked synced.
        self.assertIn("t_4", poller._pending_task_ids())

        # attempts incremented, synced_at still NULL.
        with sqlite3.connect(_TMP_SYNC_DB) as sc:
            sc.row_factory = sqlite3.Row
            row = sc.execute("SELECT * FROM reverse_sync WHERE task_id='t_4'").fetchone()
        self.assertIsNone(row["synced_at"])
        self.assertGreaterEqual(row["attempts"], 1)

        # Recovery: Linear healthy on the next tick → closes, drops out.
        fake.raise_on_update = False
        counts2 = poller._tick()
        self.assertEqual(counts2["closed"], 1)
        self.assertEqual(poller._tick()["scanned"], 0)

    def test_multiple_cards_mixed_outcomes(self):
        fake = FakeLinear(issue_state_type="started")
        la._graphql = fake
        self._insert("t_a", "done", idem="linear-aa2b3c4d-5e6f-7081-9aaa-bbbbccccdddd")
        self._insert("t_b", "done", idem="linear-bb2b3c4d-5e6f-7081-9aaa-bbbbccccdddd")
        counts = poller._tick()
        self.assertEqual(counts["scanned"], 2)
        self.assertEqual(counts["closed"], 2)
        self.assertEqual(poller._pending_task_ids(), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
