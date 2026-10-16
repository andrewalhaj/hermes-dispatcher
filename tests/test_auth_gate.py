"""Auth gate + login rate-limiter tests (audit finding #18: no tests for the auth gate).

The limiter key must be the *real* client behind the Cloudflare tunnel. Before the
fix, ``request.client.host`` was always 127.0.0.1 (cloudflared), so five failed
guesses from anyone on the internet locked the owner out too.
"""

import os
import socket
import sys
import threading
import time
import unittest
import urllib.error
import urllib.request

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)
os.environ.pop("SENTRY_DSN", None)

import uvicorn  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import server  # noqa: E402
from routes import auth  # noqa: E402


class _UvicornServer:
    """The real app under real uvicorn on loopback, configured like production
    (CLI defaults: proxy_headers on, forwarded_allow_ips=127.0.0.1), so the test
    exercises the same X-Forwarded-For handling the tunnel traffic gets."""

    def __enter__(self):
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        self.url = "http://127.0.0.1:%d" % sock.getsockname()[1]
        self.srv = uvicorn.Server(uvicorn.Config(server.app, lifespan="off", log_level="warning"))
        self.thread = threading.Thread(target=self.srv.run, kwargs={"sockets": [sock]}, daemon=True)
        self.thread.start()
        deadline = time.time() + 10
        while not self.srv.started:
            if time.time() > deadline or not self.thread.is_alive():
                raise RuntimeError("uvicorn did not start")
            time.sleep(0.01)
        return self

    def __exit__(self, *exc):
        self.srv.should_exit = True
        self.thread.join(5)


class LoginRateLimitTest(unittest.TestCase):
    # Captured from a real tunnel request (2026-10-16): peer 127.0.0.1, and cloudflared
    # sends CF-Connecting-IP plus a one-entry X-Forwarded-For with the same address.
    def setUp(self):
        auth._FAIL_LOG.clear()

    def _bad_login(self, url, headers):
        req = urllib.request.Request(url + "/api/auth/login", data=b'{"password": "definitely-wrong"}',
                                     headers={"content-type": "application/json", **headers})
        try:
            return urllib.request.urlopen(req).status
        except urllib.error.HTTPError as e:
            return e.code

    def _tunnel(self, ip, xff=None):
        return {"cf-connecting-ip": ip, "x-forwarded-for": xff or ip, "x-forwarded-proto": "https"}

    def test_attacker_lockout_does_not_lock_other_ips(self):
        with _UvicornServer() as s:
            for _ in range(auth._FAIL_LIMIT):
                self.assertEqual(self._bad_login(s.url, self._tunnel("203.0.113.9")), 401)
            self.assertEqual(self._bad_login(s.url, self._tunnel("203.0.113.9")), 429, "attacker should be limited")
            self.assertEqual(self._bad_login(s.url, self._tunnel("198.51.100.4")), 401, "other client must not be limited")

    def test_client_supplied_xff_prefix_does_not_open_new_buckets(self):
        # Cloudflare appends the real address to whatever XFF the client sent; only
        # the rightmost entry is trustworthy, so rotating the prefix must not help.
        with _UvicornServer() as s:
            codes = [self._bad_login(s.url, self._tunnel("203.0.113.9", xff="10.9.9.%d, 203.0.113.9" % i))
                     for i in range(auth._FAIL_LIMIT + 1)]
        self.assertEqual(codes[-1], 429, codes)

    def test_forged_cf_header_without_proxy_does_not_open_new_buckets(self):
        # A local caller that skips the tunnel can set CF-Connecting-IP to anything;
        # it must stay in the loopback bucket.
        with _UvicornServer() as s:
            codes = [self._bad_login(s.url, {"cf-connecting-ip": "192.0.2.%d" % i})
                     for i in range(auth._FAIL_LIMIT + 1)]
        self.assertEqual(codes[-1], 429, codes)


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
