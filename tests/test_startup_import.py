"""Startup-import regression test for the Hermes Dispatcher.

Why this test exists
--------------------
On 2026-10-15 a dead-code trim deleted ``routes/workspace.py``; ``routes/media.py``
still imported ``_jail`` from it. All 85 tests passed, because none of them
imported ``server`` — the break only surfaced when the systemd unit restarted.
This test imports ``server`` exactly as uvicorn does (``server:app``), so a
broken router import fails the suite instead of the service.

It also pins the Sentry opt-in contract: with ``SENTRY_DSN`` unset (the test
default), ``server.app`` must be the bare FastAPI object and no Sentry client
may be initialised — otherwise every test run reports to production Sentry
and feeds the Sentry→Linear→kanban self-healing loop (the 2026-10-15 swarm).

Runner-agnostic: unittest.TestCase, runs under pytest and ``python -m unittest``.
"""

import importlib
import os
import sys
import unittest

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)


class StartupImportTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.pop("SENTRY_DSN", None)
        sys.modules.pop("server", None)
        cls.server = importlib.import_module("server")

    def test_server_imports_and_exposes_fastapi_app(self):
        from fastapi import FastAPI

        self.assertIsInstance(self.server.fastapi_app, FastAPI)
        self.assertIs(self.server.app, self.server.fastapi_app,
                      "SENTRY_DSN unset → app must not be wrapped in SentryAsgiMiddleware")

    def test_sentry_disabled_without_dsn(self):
        import sentry_sdk

        self.assertFalse(self.server.SENTRY_ENABLED)
        client = sentry_sdk.get_client() if hasattr(sentry_sdk, "get_client") else None
        if client is not None:
            self.assertFalse(client.is_active(), "Sentry client active with no DSN")

    def test_every_router_module_mounted(self):
        """Every routes/*.py that defines a ``router`` must be mounted under /api."""
        import pkgutil

        import routes

        # Public OpenAPI paths, not FastAPI's private router internals (which
        # changed shape in 0.138 and dropped the /api prefix).
        paths = set(self.server.fastapi_app.openapi()["paths"])
        self.assertGreater(len(paths), 20, f"only {len(paths)} routes mounted")
        self.assertIn("/api/health", paths)

        # Every module with a `router` must be mounted under /api — a dropped
        # include_router() line would otherwise ship green and 404 in prod.
        for m in pkgutil.iter_modules(routes.__path__):
            mod = importlib.import_module(f"routes.{m.name}")
            if getattr(mod, "router", None) is None:
                continue
            own = {"/api" + r.path for r in mod.router.routes if getattr(r, "include_in_schema", False)}
            self.assertTrue(own, f"routes.{m.name} defines a router with no routes")
            self.assertTrue(own & paths, f"routes.{m.name} router is not mounted in server.py")

    def test_sentry_enabled_wraps_app(self):
        """The production branch: a DSN set → init called, app wrapped in the ASGI middleware."""
        from unittest import mock

        import sentry_sdk

        # Mock init: a real client with a fake DSN would try to send events.
        with mock.patch.dict(os.environ, {"SENTRY_DSN": "https://k@sentry.invalid/1"}), \
                mock.patch.object(sentry_sdk, "init") as init:
            sys.modules.pop("server", None)
            try:
                srv = importlib.import_module("server")
            finally:
                sys.modules["server"] = self.server
        init.assert_called_once()
        self.assertEqual(init.call_args.kwargs["dsn"], "https://k@sentry.invalid/1")
        self.assertTrue(srv.SENTRY_ENABLED)
        self.assertIsNot(srv.app, srv.fastapi_app)
        self.assertIs(srv.app.app, srv.fastapi_app)


if __name__ == "__main__":
    unittest.main()
