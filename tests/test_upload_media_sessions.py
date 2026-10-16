"""Audit #13 (upload cap, media served as download) and #14 (session soft-delete)."""

import io
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)
os.environ.pop("SENTRY_DSN", None)

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from routes import chat, media, sessions, upload  # noqa: E402


def _app(*routers):
    app = FastAPI()
    for r in routers:
        app.include_router(r, prefix="/api")
    return TestClient(app)


class UploadCapTest(unittest.TestCase):
    def setUp(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        for name, value in (("IMAGE_CACHE", tmp / "img"), ("DOC_CACHE", tmp / "doc"),
                            ("MAX_UPLOAD_BYTES", 3 * 1024 * 1024)):
            p = mock.patch.object(upload, name, value)
            p.start()
            self.addCleanup(p.stop)
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

    def test_content_length_over_cap_413_before_parse(self):
        # Not valid multipart: if the body were parsed we'd get 400/422, not 413.
        junk = b"x" * (upload.MAX_UPLOAD_BYTES + upload._MULTIPART_SLACK + 1)
        r = self.c.post("/api/chat/upload", content=junk,
                        headers={"content-type": "multipart/form-data; boundary=zz"})
        self.assertEqual(r.status_code, 413, r.text)


class MediaHeadersTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(os.path.realpath(tempfile.mkdtemp()))
        self.addCleanup(shutil.rmtree, self.root)
        p = mock.patch.object(media, "_ALLOWED_ROOTS", [str(self.root)])
        p.start()
        self.addCleanup(p.stop)
        (self.root / "evil.html").write_text("<script>alert(document.cookie)</script>")
        (self.root / "evil.svg").write_text("<svg onload='alert(1)'/>")
        (self.root / "pic.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\0" * 16)
        self.c = _app(media.router)

    def _get(self, name):
        return self.c.get("/api/media", params={"path": str(self.root / name)})

    def test_html_is_download_not_inline(self):
        r = self._get("evil.html")
        self.assertEqual(r.status_code, 200)
        self.assertIn("attachment", r.headers["content-disposition"])
        self.assertEqual(r.headers["x-content-type-options"], "nosniff")

    def test_svg_is_download(self):
        r = self._get("evil.svg")
        self.assertIn("attachment", r.headers["content-disposition"])
        self.assertEqual(r.headers["x-content-type-options"], "nosniff")

    def test_non_latin1_and_quote_names_download(self):
        # The extension comes from the client; a hand-built header 500'd on these.
        for name in ('webui_a.日本', 'webui_b."x'):
            (self.root / name).write_text("data")
            r = self._get(name)
            self.assertEqual(r.status_code, 200, name)
            self.assertTrue(r.headers["content-disposition"].startswith("attachment; filename*=utf-8''"), name)

    def test_png_inline(self):
        r = self._get("pic.png")
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("content-disposition", r.headers)
        self.assertEqual(r.headers["content-type"], "image/png")
        self.assertEqual(r.headers["x-content-type-options"], "nosniff")


class SessionSoftDeleteTest(unittest.TestCase):
    def setUp(self):
        self.db = Path(tempfile.mkdtemp()) / "state.db"
        con = sqlite3.connect(self.db)
        con.executescript("""
            CREATE TABLE sessions(id TEXT PRIMARY KEY, title TEXT, source TEXT, started_at REAL,
                                  ended_at REAL, message_count INT, archived INT DEFAULT 0, model TEXT);
            CREATE TABLE messages(id INTEGER PRIMARY KEY, session_id TEXT, role TEXT, content TEXT, timestamp REAL,
                                   active INT DEFAULT 1);
            INSERT INTO sessions VALUES('s1','t','cli',1,2,2,0,'m');
            INSERT INTO messages(session_id,role,content,timestamp) VALUES('s1','user','hello',1),('s1','assistant','hi',2);
        """)
        con.commit(); con.close()
        p = mock.patch.object(sessions, "_db_path", lambda: self.db)
        p.start()
        self.addCleanup(p.stop)
        self.c = _app(sessions.router)

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

    def test_archived_messages_not_readable_by_id(self):
        self.assertEqual(len(self.c.get("/api/sessions/s1/messages").json()), 2)
        self.c.delete("/api/sessions/s1")
        self.assertEqual(self.c.get("/api/sessions/s1/messages").json(), [])


class ChatArchivedSessionTest(unittest.TestCase):
    """The chat panel injects into the gateway's current telegram session; if the
    user archived it, the gateway would keep appending to a "deleted" session."""

    def setUp(self):
        home = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, home)
        con = sqlite3.connect(home / "state.db")
        con.executescript("""
            CREATE TABLE sessions(id TEXT PRIMARY KEY, title TEXT, source TEXT, started_at REAL, archived INT DEFAULT 0);
            CREATE TABLE messages(id INTEGER PRIMARY KEY, session_id TEXT, role TEXT, content TEXT,
                                  timestamp REAL, active INT DEFAULT 1);
            INSERT INTO sessions VALUES('old','t','telegram',1,0),('cur','t','telegram',2,1);
            INSERT INTO messages(session_id,role,content,timestamp) VALUES('cur','user','secret',2);
        """)
        con.commit(); con.close()
        p = mock.patch.dict(os.environ, {"HERMES_HOME": str(home)})
        p.start()
        self.addCleanup(p.stop)
        self.c = _app(chat.router)

    def test_send_rejected_when_current_session_archived(self):
        # Short poll so a regression fails in seconds instead of hanging 120 s.
        with mock.patch("aiohttp.ClientSession") as http, mock.patch.object(chat, "_POLL_TIMEOUT", 2):
            r = self.c.post("/api/chat/send", json={"session_id": "x", "message": "hi"})
        self.assertIn('"type": "error"', r.text)
        self.assertIn("/new", r.text)
        http.assert_not_called()

    def test_archived_messages_not_readable_by_id(self):
        self.assertEqual(self.c.get("/api/chat/sessions/cur/messages").json(), [])


if __name__ == "__main__":
    unittest.main()
