"""MS01 metrics probe: a rejected host key must be loud, not look like "MS01 is down"."""

import os
import subprocess
import sys
import unittest
from unittest import mock

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from routes import system  # noqa: E402


class StudioHostKeyTest(unittest.TestCase):
    def _run(self, stderr):
        done = subprocess.CompletedProcess([], 255, stdout="", stderr=stderr)
        with mock.patch.object(system.subprocess, "run", return_value=done):
            return system._fetch_studio_metrics()

    def test_changed_host_key_is_logged(self):
        with self.assertLogs(system.__name__, "ERROR") as logs:
            snap = self._run("@@@ WARNING: REMOTE HOST IDENTIFICATION HAS CHANGED! @@@\nHost key verification failed.\n")
        self.assertEqual(snap["error"], "unreachable")
        self.assertIn("Host key verification failed", logs.output[0])

    def test_plain_unreachable_stays_quiet(self):
        # polled every ~3s; ordinary downtime must not flood the journal
        with self.assertNoLogs(system.__name__, "ERROR"):
            self._run("ssh: connect to host ms01 port 22: Connection timed out\n")


if __name__ == "__main__":
    unittest.main()
