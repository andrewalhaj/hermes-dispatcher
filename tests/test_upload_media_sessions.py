"""Audit #13 (upload cap, media served as download) and #14 (session soft-delete)."""

import io
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)
os.environ.pop("SENTRY_DSN", None)

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from routes import media, upload  # noqa: E402


def _app(*routers):
    app = FastAPI()
    for r in routers:
        app.include_router(r, prefix="/api")
    return TestClient(app)


class UploadCapTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        upload.IMAGE_CACHE = Path(self.tmp) / "img"
        upload.DOC_CACHE = Path(self.tmp) / "doc"
        upload.MAX_UPLOAD_BYTES = 3 * 1024 * 1024
        self.c = _app(upload.router)

    def test_under_cap_saved(self):
        r = self.c.post("/api/chat/upload", files={"file": ("a.txt", io.BytesIO(b"x" * 1024), "text/plain")})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(Path(r.json()["path"]).exists())

    def test_over_cap_413_and_no_partial_file(self):
        big = io.BytesIO(b"x" * (4 * 1024 * 1024))
        r = self.c.post("/api/chat/upload", files={"file": ("big.bin", big, "application/octet-stream")})
        self.assertEqual(r.status_code, 413)
        self.assertEqual(list(upload.DOC_CACHE.glob("*")), [], "partial upload must be removed")


class MediaHeadersTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(os.path.expanduser("~/.hermes")) / "cache" / "scratch" / "media-test"
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "evil.html").write_text("<script>alert(document.cookie)</script>")
        (self.root / "evil.svg").write_text("<svg onload='alert(1)'/>")
        (self.root / "pic.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\0" * 16)
        self.c = _app(media.router)

    def tearDown(self):
        for p in self.root.glob("*"):
            p.unlink()

    def _get(self, name):
        return self.c.get("/api/media", params={"path": str(self.root / name)})

    def test_html_is_download_not_inline(self):
        r = self._get("evil.html")
        self.assertEqual(r.status_code, 200)
        self.assertIn("attachment", r.headers["content-disposition"])
        self.assertEqual(r.headers["x-content-type-options"], "nosniff")
        self.assertNotIn("text/html", r.headers["content-type"])

    def test_svg_is_download(self):
        r = self._get("evil.svg")
        self.assertIn("attachment", r.headers["content-disposition"])
        self.assertNotIn("svg", r.headers["content-type"])

    def test_png_inline(self):
        r = self._get("pic.png")
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("content-disposition", r.headers)
        self.assertEqual(r.headers["content-type"], "image/png")
        self.assertEqual(r.headers["x-content-type-options"], "nosniff")


class SessionSoftDeleteTest(unittest.TestCase):
    def setUp(self):
        from routes import sessions
        self.sessions = sessions
        self.db = Path(tempfile.mkdtemp()) / "state.db"
        con = sqlite3.connect(self.db)
        con.executescript("""
            CREATE TABLE sessions(id TEXT PRIMARY KEY, title TEXT, source TEXT, started_at REAL,
                                  ended_at REAL, message_count INT, archived INT DEFAULT 0, model TEXT);
            CREATE TABLE messages(id INTEGER PRIMARY KEY, session_id TEXT, role TEXT, content TEXT, timestamp REAL);
            INSERT INTO sessions VALUES('s1','t','cli',1,2,2,0,'m');
            INSERT INTO messages(session_id,role,content,timestamp) VALUES('s1','user','hello',1),('s1','assistant','hi',2);
        """)
        con.commit(); con.close()
        self._orig = sessions._connect
        sessions._connect = lambda: sqlite3.connect(self.db)
        self.c = _app(sessions.router)

    def tearDown(self):
        self.sessions._connect = self._orig

    def test_delete_archives_and_keeps_rows(self):
        r = self.c.delete("/api/sessions/s1")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(r.json()["archived"])
        con = sqlite3.connect(self.db)
        self.assertEqual(con.execute("SELECT archived FROM sessions WHERE id='s1'").fetchone()[0], 1)
        self.assertEqual(con.execute("SELECT count(*) FROM messages WHERE session_id='s1'").fetchone()[0], 2,
                         "messages must survive a UI delete")

    def test_unknown_session_404(self):
        self.assertEqual(self.c.delete("/api/sessions/nope").status_code, 404)


if __name__ == "__main__":
    unittest.main()
