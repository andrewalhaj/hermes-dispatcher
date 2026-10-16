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
        """Every routes/*.py that defines a ``router`` must contribute at least one path."""
        import pkgutil
        from starlette.routing import Mount, Route

        import routes

        def leaves(rs):
            for r in rs:
                # FastAPI ≥0.138 keeps include_router() lazy: _IncludedRouter
                sub = getattr(r, "routes", None)
                inner = getattr(r, "original_router", None)
                if inner is not None:
                    yield from leaves(inner.routes)
                elif sub is not None and not isinstance(r, Route):
                    yield from leaves(sub)
                elif getattr(r, "path", None):
                    yield r.path

        paths = set(leaves(self.server.fastapi_app.routes))
        self.assertGreater(len(paths), 20, f"only {len(paths)} routes mounted")
        self.assertIn("/api/health", paths)

        # Optional routers (e.g. upload needs python-multipart) may be skipped
        # deliberately; everything else with a `router` must import cleanly.
        for m in pkgutil.iter_modules(routes.__path__):
            mod = importlib.import_module(f"routes.{m.name}")
            if getattr(mod, "router", None) is None:
                continue
            self.assertTrue(
                any(getattr(r, "path", None) for r in mod.router.routes),
                f"routes.{m.name} defines a router with no routes",
            )


if __name__ == "__main__":
    unittest.main()
