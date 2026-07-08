"""Tests for the Kanban → Sentry auto-resolve feature.

Mirrors tests/test_linear_autoclose.py. Covers:
  1. Reference extraction (idempotency_key, Sentry Issue ID marker, URL) — pure logic.
  2. resolve_sentry_issue() against a fully-mocked Sentry REST surface:
     - happy path (issue → resolved)
     - HTTP error (bad token / no permission) → structured error, never raises
     - no API key configured → skipped
  3. autoclose_sentry_for_card() DB resolver: reads a real (temp) Kanban DB,
     extracts the ref, drives the resolve — verifies the require_done gate and
     the no-ref short-circuit.

Runner-agnostic plain unittest.TestCase. The Sentry network layer
(sentry_autoclose._patch_issue) is monkeypatched, so no test touches the real
Sentry API.
"""
import os
import sqlite3
import sys
import tempfile
import unittest
import urllib.error
import io
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_TMP_HOME = tempfile.mkdtemp(prefix="hermes_sentry_autoclose_test_")
os.environ["HERMES_HOME"] = _TMP_HOME
_TMP_DB = str(Path(_TMP_HOME) / "kanban.db")
os.environ["KANBAN_DB"] = _TMP_DB
os.environ["SENTRY_API_KEY"] = "sntryu_test_key"

from routes import sentry_autoclose as sa  # noqa: E402


class FakeSentry:
    """Records PATCH calls and returns a canned body (or raises HTTPError)."""

    def __init__(self, *, raise_http=None, body=None):
        self.raise_http = raise_http
        self.body = body if body is not None else {"id": "1", "status": "resolved"}
        self.calls = []

    def __call__(self, issue_id, key, timeout=15):
        self.calls.append((issue_id, key))
        if self.raise_http is not None:
            raise urllib.error.HTTPError(
                url="https://sentry.io", code=self.raise_http, msg="err",
                hdrs=None, fp=io.BytesIO(b'{"detail":"nope"}'))
        return self.body


class TestExtraction(unittest.TestCase):
    def test_idempotency_key(self):
        self.assertEqual(sa.extract_sentry_ref(idempotency_key="sentry-1234567"), "1234567")

    def test_marker(self):
        self.assertEqual(
            sa.extract_sentry_ref(body="**Sentry Alert**\nSentry Issue ID: 6543210987"),
            "6543210987")

    def test_url(self):
        self.assertEqual(
            sa.extract_sentry_ref(
                body="see https://sentry.io/organizations/andrew-ol/issues/4455667788/events/"),
            "4455667788")

    def test_no_match_ignores_linear_identifier(self):
        self.assertIsNone(sa.extract_sentry_ref(body="just a linear HER-42 ref"))

    def test_none_when_empty(self):
        self.assertIsNone(sa.extract_sentry_ref())


class TestResolve(unittest.TestCase):
    def test_happy_path(self):
        fake = FakeSentry()
        orig = sa._patch_issue
        sa._patch_issue = fake
        try:
            res = sa.resolve_sentry_issue("999", task_id="t_x", key="k")
        finally:
            sa._patch_issue = orig
        self.assertEqual(res["status"], "ok")
        self.assertEqual(res["ref"], "999")
        self.assertEqual(fake.calls, [("999", "k")])

    def test_http_error_does_not_raise(self):
        fake = FakeSentry(raise_http=403)
        orig = sa._patch_issue
        sa._patch_issue = fake
        try:
            res = sa.resolve_sentry_issue("999", task_id="t_x", key="k")
        finally:
            sa._patch_issue = orig
        self.assertEqual(res["status"], "error")
        self.assertEqual(res["reason"], "HTTP 403")

    def test_no_key_skips(self):
        orig = sa.sentry_api_key
        sa.sentry_api_key = lambda: ""
        try:
            res = sa.resolve_sentry_issue("999", task_id="t_x", key=None)
        finally:
            sa.sentry_api_key = orig
        self.assertEqual(res["status"], "skipped")
        self.assertEqual(res["reason"], "no_api_key")


class TestAutocloseForCard(unittest.TestCase):
    def setUp(self):
        if os.path.exists(_TMP_DB):
            os.remove(_TMP_DB)
        c = sqlite3.connect(_TMP_DB)
        c.execute("CREATE TABLE tasks (id TEXT PRIMARY KEY, title TEXT, body TEXT, "
                  "status TEXT, idempotency_key TEXT)")
        c.execute("INSERT INTO tasks VALUES (?,?,?,?,?)",
                  ("t_done", "x", "Sentry Issue ID: 6543210987", "done", None))
        c.execute("INSERT INTO tasks VALUES (?,?,?,?,?)",
                  ("t_running", "x", "Sentry Issue ID: 6543210987", "running", None))
        c.execute("INSERT INTO tasks VALUES (?,?,?,?,?)",
                  ("t_noref", "x", "no sentry ref here", "done", None))
        c.commit()
        c.close()

    def test_done_card_resolves(self):
        fake = FakeSentry()
        orig = sa._patch_issue
        sa._patch_issue = fake
        try:
            res = sa.autoclose_sentry_for_card("t_done")
        finally:
            sa._patch_issue = orig
        self.assertEqual(res["status"], "ok")
        self.assertEqual(fake.calls[0][0], "6543210987")

    def test_running_card_skipped(self):
        res = sa.autoclose_sentry_for_card("t_running")
        self.assertEqual(res["status"], "skipped")
        self.assertEqual(res["reason"], "card_not_done")

    def test_no_ref_skipped(self):
        res = sa.autoclose_sentry_for_card("t_noref")
        self.assertEqual(res["status"], "skipped")
        self.assertEqual(res["reason"], "no_sentry_ref")

    def test_missing_card(self):
        res = sa.autoclose_sentry_for_card("t_nope")
        self.assertEqual(res["status"], "not_found")


if __name__ == "__main__":
    unittest.main()
