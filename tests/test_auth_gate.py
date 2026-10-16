"""Auth gate + login rate-limiter tests (audit finding #18: no tests for the auth gate).

The limiter key must be the *real* client behind the Cloudflare tunnel. Before the
fix, ``request.client.host`` was always 127.0.0.1 (cloudflared), so five failed
guesses from anyone on the internet locked the owner out too.
"""

import os
import sys
import unittest

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)
os.environ.pop("SENTRY_DSN", None)

from fastapi.testclient import TestClient  # noqa: E402

import server  # noqa: E402
from routes import auth  # noqa: E402


class _Req:
    def __init__(self, peer, headers=None):
        self.client = type("C", (), {"host": peer})() if peer else None
        self.headers = headers or {}


class ClientIpTest(unittest.TestCase):
    def test_loopback_peer_uses_cloudflare_header(self):
        self.assertEqual(auth.client_ip(_Req("127.0.0.1", {"cf-connecting-ip": "203.0.113.9"})), "203.0.113.9")

    def test_loopback_peer_falls_back_to_first_xff(self):
        self.assertEqual(auth.client_ip(_Req("::1", {"x-forwarded-for": "198.51.100.4, 10.0.0.1"})), "198.51.100.4")

    def test_direct_peer_ignores_spoofed_headers(self):
        self.assertEqual(auth.client_ip(_Req("192.0.2.77", {"cf-connecting-ip": "1.2.3.4"})), "192.0.2.77")

    def test_no_client(self):
        self.assertEqual(auth.client_ip(_Req(None)), "unknown")


class LoginRateLimitTest(unittest.TestCase):
    def setUp(self):
        auth._FAIL_LOG.clear()
        # peer = loopback, exactly like cloudflared delivering a tunnel request
        self.c = TestClient(server.fastapi_app, client=("127.0.0.1", 50000))

    def _bad_login(self, ip):
        return self.c.post("/api/auth/login", json={"password": "definitely-wrong"},
                           headers={"cf-connecting-ip": ip})

    def test_attacker_lockout_does_not_lock_other_ips(self):
        for _ in range(auth._FAIL_LIMIT):
            self.assertEqual(self._bad_login("203.0.113.9").status_code, 401)
        self.assertEqual(self._bad_login("203.0.113.9").status_code, 429, "attacker should be limited")
        self.assertEqual(self._bad_login("198.51.100.4").status_code, 401, "a different client must not be limited")


class AuthGateTest(unittest.TestCase):
    def setUp(self):
        self.c = TestClient(server.fastapi_app)

    def test_api_without_cookie_is_401(self):
        for p in ("/api/kanban/tasks", "/api/cron", "/api/settings", "/api/memory/galaxy"):
            self.assertEqual(self.c.get(p).status_code, 401, p)

    def test_exempt_paths_open(self):
        self.assertEqual(self.c.get("/api/health").status_code, 200)

    def test_assets_traversal_is_not_exempt(self):
        r = self.c.get("/assets/../.env", follow_redirects=False)
        self.assertIn(r.status_code, (302, 401, 404))
        self.assertNotIn("SUPABASE", r.text)


if __name__ == "__main__":
    unittest.main()
