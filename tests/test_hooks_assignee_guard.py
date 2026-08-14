"""Tests for routes/hooks.py Linear-intake assignee validation guard.

Root-fixes the failure mode where a Kanban card could be created with an
assignee pointing at a profile that no longer exists (the deleted `ha-bot`,
removed 2026-06-25). Such a card is undispatchable and silently rots on the
board. The guard `routes.hooks._valid_assignee` coerces any assignee outside
the live worker set (`KNOWN_ASSIGNEES`) to `ASSIGNEE_FALLBACK` ("coder") and
logs a warning, so no card is ever written with a nonexistent profile.

Runner-agnostic: plain unittest.TestCase (runs under pytest and stdlib).
No network, no DB — the guard is a pure function.
"""
import logging
import os
import sys
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# hooks.py reads WEBHOOK_SECRET at import; a value keeps import side effects quiet.
os.environ.setdefault("WEBHOOK_SECRET", "test-secret-not-real")

import routes.hooks as hooks  # noqa: E402


class TestValidAssignee(unittest.TestCase):
    def test_known_assignees_pass_through_unchanged(self):
        for name in hooks.KNOWN_ASSIGNEES:
            self.assertEqual(hooks._valid_assignee(name), name)

    def test_coder_fleet_and_default_are_known(self):
        # The webhook's round-robin pool + orchestration profile must all be valid.
        for name in ("coder", "coder-b", "coder-c", "coder-d", "default"):
            self.assertIn(name, hooks.KNOWN_ASSIGNEES)

    def test_deleted_ha_bot_falls_back_to_coder(self):
        # The regression this task exists to kill: ha-bot must never survive.
        self.assertEqual(hooks._valid_assignee("ha-bot"), "coder")
        self.assertEqual(hooks._valid_assignee("ha-bot"), hooks.ASSIGNEE_FALLBACK)
        self.assertNotIn("ha-bot", hooks.KNOWN_ASSIGNEES)

    def test_unknown_profile_falls_back(self):
        for junk in ("rvc-runner", "atlas-etl", "npc-builder", "totally-made-up"):
            self.assertEqual(hooks._valid_assignee(junk), hooks.ASSIGNEE_FALLBACK)

    def test_empty_and_none_fall_back(self):
        self.assertEqual(hooks._valid_assignee(None), hooks.ASSIGNEE_FALLBACK)
        self.assertEqual(hooks._valid_assignee(""), hooks.ASSIGNEE_FALLBACK)
        self.assertEqual(hooks._valid_assignee("   "), hooks.ASSIGNEE_FALLBACK)

    def test_non_string_input_falls_back(self):
        bad_inputs: list[object] = [123, [], {}, object()]
        for bad in bad_inputs:
            self.assertEqual(hooks._valid_assignee(bad), hooks.ASSIGNEE_FALLBACK)  # type: ignore[arg-type]

    def test_fallback_is_itself_a_known_assignee(self):
        # A fallback that isn't dispatchable would just move the bug.
        self.assertIn(hooks.ASSIGNEE_FALLBACK, hooks.KNOWN_ASSIGNEES)

    def test_unknown_assignee_logs_warning(self):
        with self.assertLogs(hooks.logger, level="WARNING") as cm:
            hooks._valid_assignee("ha-bot")
        self.assertTrue(any("ha-bot" in line for line in cm.output))

    def test_valid_assignee_does_not_log(self):
        # A valid assignee must be silent (no spurious warnings on the happy path).
        logging.disable(logging.NOTSET)
        with self.assertNoLogs(hooks.logger, level="WARNING"):
            hooks._valid_assignee("coder")


if __name__ == "__main__":
    unittest.main()
