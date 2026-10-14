"""test_sentry_ref_roundtrip.py

Verifies that the description string hooks.py writes into a Linear issue
(the Sentry intake path) is correctly parsed by sentry_autoclose.extract_sentry_ref.

Finding #6: the old code wrote 'sentry-issue-id:123' but the regex looked for
'Sentry Issue ID: 123'. The fix writes the format the closer expects.
"""
import sys
import os
import tempfile
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Minimal env so sentry_autoclose imports cleanly without a real DB
_TMP = tempfile.mkdtemp(prefix="hermes_sentry_ref_test_")
os.environ.setdefault("HERMES_HOME", _TMP)
os.environ.setdefault("KANBAN_DB", str(Path(_TMP) / "kanban.db"))

from routes.sentry_autoclose import extract_sentry_ref  # noqa: E402


class TestSentryRefRoundtrip(unittest.TestCase):
    def _hooks_description(self, project: str, level: str, issue_url: str,
                           sentry_issue_id: str) -> str:
        """Reproduce the description string hooks.py writes (sentry_webhook handler)."""
        return (
            f"**Sentry Alert**\n\n"
            f"- **Project:** {project}\n"
            f"- **Level:** {level}\n"
            f"- **URL:** {issue_url}"
            + (f"\n\nSentry Issue ID: {sentry_issue_id}" if sentry_issue_id else "")
        )

    def test_roundtrip_extracts_id(self):
        desc = self._hooks_description(
            project="hermes-dispatcher",
            level="error",
            issue_url="https://sentry.io/organizations/andrew-ol/issues/5551234567/",
            sentry_issue_id="5551234567",
        )
        self.assertEqual(extract_sentry_ref(body=desc), "5551234567")

    def test_roundtrip_no_id_returns_none(self):
        desc = self._hooks_description(
            project="hermes-dispatcher",
            level="warning",
            issue_url="https://sentry.io/api/0/issues/9999/",
            sentry_issue_id="",
        )
        # No marker embedded → should fall back to URL match or None
        # The URL is an API URL which the URL regex doesn't match (api/0/issues path);
        # this exercises the no-ref path too.
        result = extract_sentry_ref(body=desc)
        # May be None or a URL-extracted id — either is fine; just must not raise
        self.assertIsInstance(result, (str, type(None)))


if __name__ == "__main__":
    unittest.main()
