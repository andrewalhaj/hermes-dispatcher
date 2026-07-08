"""Tests for the Hermes Dispatcher startup port pre-flight check (server.py).

Why these tests exist
---------------------
Production launches the dispatcher via ``uvicorn server:app`` (see the systemd
unit ``hermes-dashboard.service`` and ``start-server.sh``). That imports
``server.py`` as a module and lets *uvicorn* bind the socket — so the
``if __name__ == "__main__"`` block (which historically held all the
port-conflict handling) never runs in the real deployment. A port collision
therefore surfaced as an unhandled ``OSError(Errno 98)`` from deep inside
uvicorn and was reported to Sentry (HERMES-DISPATCHER-8).

The fix is an import-time pre-flight (``_preflight_port_check`` →
``_assert_port_free``) that probes the bind port BEFORE uvicorn does and exits
early with an actionable message on conflict. These tests verify:

1. ``_assert_port_free`` returns quietly when the port is free.
2. ``_assert_port_free`` raises ``SystemExit(1)`` with a helpful message when
   the port is already bound (the core HERMES-DISPATCHER-8 scenario).
3. Importing ``server`` under a test runner does NOT abort the process even
   when the default port (8787) is occupied — the opt-out guards hold, so the
   test suite itself can run on a host where the dispatcher is live.

Runner-agnostic by design
--------------------------
Written as ``unittest.TestCase`` classes so they run under both ``pytest`` and
the stdlib runner (``python -m unittest``), matching tests/test_upload.py.
"""

import contextlib
import io
import os
import socket
import sys
import unittest
from pathlib import Path

# ---------------------------------------------------------------------------
# Make the repo root importable, and point HERMES_HOME at a scratch dir before
# importing ``server`` (server.py reads env at import time for its data paths).
# Importing server triggers _preflight_port_check(), but that self-disables
# under a test runner (it sees ``pytest`` in sys.modules or, failing that, we
# set the explicit skip flag below), so importing here is always safe.
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Belt-and-suspenders: guarantee the import-time pre-flight no-ops even when
# this file is run via ``python -m unittest`` (no ``pytest`` module loaded).
os.environ.setdefault("HERMES_DISPATCHER_SKIP_PREFLIGHT", "1")

import server  # noqa: E402  (import after sys.path / env setup)


def _free_port() -> int:
    """Grab an ephemeral port number that is free at this instant."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]
    finally:
        s.close()


class AssertPortFreeTest(unittest.TestCase):
    def test_free_port_returns_quietly(self):
        """A bindable port must not raise — uvicorn would be allowed to start."""
        port = _free_port()
        # Should simply return None without raising.
        self.assertIsNone(server._assert_port_free("127.0.0.1", port))

    def test_busy_port_raises_systemexit_with_guidance(self):
        """An occupied port must raise SystemExit(1) with an actionable message.

        This is the exact HERMES-DISPATCHER-8 condition: something already
        listening on the dispatcher's bind address.
        """
        holder = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # No SO_REUSEADDR — mirror a real conflicting listener.
        holder.bind(("127.0.0.1", 0))
        holder.listen(1)
        busy_port = holder.getsockname()[1]
        try:
            stderr = io.StringIO()
            # The check logs via the logging module; capture the record too so
            # we can assert the message is genuinely actionable. assertLogs is
            # the OUTER context so ``logs`` is always bound even though the
            # inner call raises SystemExit.
            with self.assertLogs("hermes.dispatcher", level="ERROR") as logs:
                with self.assertRaises(SystemExit) as ctx:
                    with contextlib.redirect_stderr(stderr):
                        server._assert_port_free("127.0.0.1", busy_port)
            # Non-zero exit so uvicorn never attempts its own bind.
            self.assertEqual(ctx.exception.code, 1)
            joined = "\n".join(logs.output)
            self.assertIn("already in", joined)
            self.assertIn(str(busy_port), joined)
            # Mentions both remediations (kill the holder / change the port).
            self.assertIn("ss -tlnp", joined)
            self.assertIn("HERMES_DISPATCHER_PORT", joined)
        finally:
            holder.close()


class PreflightGuardsTest(unittest.TestCase):
    def test_skip_env_disables_check(self):
        """HERMES_DISPATCHER_SKIP_PREFLIGHT short-circuits before probing."""
        holder = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        holder.bind(("127.0.0.1", 0))
        holder.listen(1)
        busy_port = holder.getsockname()[1]
        prev_skip = os.environ.get("HERMES_DISPATCHER_SKIP_PREFLIGHT")
        prev_host = os.environ.get("HERMES_DISPATCHER_HOST")
        prev_port = os.environ.get("HERMES_DISPATCHER_PORT")
        try:
            os.environ["HERMES_DISPATCHER_SKIP_PREFLIGHT"] = "1"
            os.environ["HERMES_DISPATCHER_HOST"] = "127.0.0.1"
            os.environ["HERMES_DISPATCHER_PORT"] = str(busy_port)
            # Must NOT raise even though the port is busy — guard wins.
            self.assertIsNone(server._preflight_port_check())
        finally:
            holder.close()
            for key, val in (
                ("HERMES_DISPATCHER_SKIP_PREFLIGHT", prev_skip),
                ("HERMES_DISPATCHER_HOST", prev_host),
                ("HERMES_DISPATCHER_PORT", prev_port),
            ):
                if val is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = val

    def test_pytest_guard_disables_check(self):
        """Under a test runner the check no-ops even without the skip flag.

        ``_preflight_port_check`` returns early when ``pytest`` is imported or
        ``PYTEST_CURRENT_TEST`` is set. We simulate the latter and clear the
        explicit skip flag to prove the runner-detection guard alone holds.
        """
        holder = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        holder.bind(("127.0.0.1", 0))
        holder.listen(1)
        busy_port = holder.getsockname()[1]
        prev_skip = os.environ.get("HERMES_DISPATCHER_SKIP_PREFLIGHT")
        prev_marker = os.environ.get("PYTEST_CURRENT_TEST")
        prev_host = os.environ.get("HERMES_DISPATCHER_HOST")
        prev_port = os.environ.get("HERMES_DISPATCHER_PORT")
        try:
            os.environ.pop("HERMES_DISPATCHER_SKIP_PREFLIGHT", None)
            os.environ["PYTEST_CURRENT_TEST"] = "test_preflight_port::guard"
            os.environ["HERMES_DISPATCHER_HOST"] = "127.0.0.1"
            os.environ["HERMES_DISPATCHER_PORT"] = str(busy_port)
            self.assertIsNone(server._preflight_port_check())
        finally:
            holder.close()
            for key, val in (
                ("HERMES_DISPATCHER_SKIP_PREFLIGHT", prev_skip),
                ("PYTEST_CURRENT_TEST", prev_marker),
                ("HERMES_DISPATCHER_HOST", prev_host),
                ("HERMES_DISPATCHER_PORT", prev_port),
            ):
                if val is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = val


if __name__ == "__main__":
    unittest.main(verbosity=2)
