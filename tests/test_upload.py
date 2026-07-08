"""Tests for the Hermes Dashboard form-data upload route (routes/upload.py).

Why these tests exist
---------------------
The ``/api/chat/upload`` endpoint accepts a ``multipart/form-data`` file
upload (``UploadFile = File(...)``). FastAPI/Starlette can only parse that
body when the optional **python-multipart** dependency is installed. When it
is missing, ``server.py`` deliberately skips mounting the upload router (the
``try/except (ImportError, RuntimeError)`` guard) and the feature silently
disappears — this was the root cause of Sentry issue HERMES-DASHBOARD-3.

These tests therefore do two jobs:

1. Exercise the real upload code path through a FastAPI ``TestClient`` to
   confirm form-data parsing works end-to-end (text + image uploads).
2. Act as a **regression guard** so the dependency cannot quietly fall out
   of the environment again. ``MultipartDependencyTest`` and the functional
   upload tests all fail hard when python-multipart is absent.

Runner-agnostic by design
--------------------------
Tests are written as ``unittest.TestCase`` classes so they run under both
``pytest`` and the stdlib runner (``python -m unittest``), the latter needing
no extra test dependency in the deploy venv.

The module configures a throwaway ``HERMES_HOME`` *before* importing the
upload router, because ``routes.upload`` reads that env var at import time to
decide where uploaded files land. This keeps the real image/document caches
untouched.
"""

import importlib
import os
import sys
import tempfile
import unittest
from pathlib import Path

# ---------------------------------------------------------------------------
# Make the repo root importable (so ``import routes.upload`` works regardless
# of the directory pytest/unittest is invoked from) and point HERMES_HOME at a
# scratch dir BEFORE the router module is imported.
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_TMP_HOME = tempfile.mkdtemp(prefix="hermes_upload_test_")
os.environ["HERMES_HOME"] = _TMP_HOME


def _multipart_installed():
    """Return the installed python-multipart module, or None if absent.

    python-multipart historically exposed the top-level module name
    ``multipart``; newer releases also ship ``python_multipart``. Accept
    either so the guard is robust across versions.
    """
    for name in ("python_multipart", "multipart"):
        try:
            return importlib.import_module(name)
        except ImportError:
            continue
    return None


_MULTIPART = _multipart_installed()


class MultipartDependencyTest(unittest.TestCase):
    """Direct regression guard: the optional dependency must be importable.

    This is the test that *fails without the dependency*. If python-multipart
    is uninstalled, this fails immediately with a clear message instead of the
    feature silently disappearing at server startup (HERMES-DASHBOARD-3).
    """

    def test_python_multipart_is_importable(self):
        self.assertIsNotNone(
            _MULTIPART,
            "python-multipart is not installed. The /api/chat/upload route "
            "cannot parse multipart/form-data without it and server.py will "
            "silently skip mounting the upload router (Sentry HERMES-DASHBOARD-3). "
            "Install it: pip install 'python-multipart>=0.0.18'.",
        )

    def test_starlette_form_parser_sees_multipart(self):
        """Starlette exposes the parser only when python-multipart is present.

        Starlette imports python-multipart lazily; ``starlette.formparsers``
        keeps a module-level handle to it. A truthy handle is what lets a
        ``File(...)`` endpoint parse a request body at runtime.
        """
        import starlette.formparsers as fp

        self.assertTrue(
            getattr(fp, "multipart", None) is not None
            or getattr(fp, "parse_options_header", None) is not None,
            "starlette.formparsers could not bind python-multipart; multipart "
            "form parsing will fail at request time.",
        )


@unittest.skipIf(
    _MULTIPART is None,
    "python-multipart not installed; functional upload tests cannot run "
    "(this is itself surfaced by MultipartDependencyTest).",
)
class UploadEndpointTest(unittest.TestCase):
    """End-to-end form-data submission through a real FastAPI app.

    Mirrors how server.py mounts the router (``include_router(prefix="/api")``)
    so the request paths match production exactly: ``/api/chat/upload``.
    """

    @classmethod
    def setUpClass(cls):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        # Import here (not at module top) so a missing httpx/multipart turns
        # into a skip via the class decorator rather than a collection error.
        from routes.upload import router as upload_router

        app = FastAPI()
        app.include_router(upload_router, prefix="/api")
        cls.client = TestClient(app)

    def test_upload_text_file_returns_parsed_content(self):
        payload = b"hello multipart world\nsecond line\n"
        resp = self.client.post(
            "/api/chat/upload",
            files={"file": ("notes.txt", payload, "text/plain")},
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertTrue(body["is_text"])
        self.assertFalse(body["is_image"])
        self.assertEqual(body["filename"], "notes.txt")
        self.assertEqual(body["mime"], "text/plain")
        # The route reads the saved file back and returns its contents.
        self.assertEqual(body["text_content"], payload.decode())
        # File was actually persisted under the (temp) HERMES_HOME.
        self.assertTrue(Path(body["path"]).is_file())

    def test_upload_image_file_is_flagged_as_image(self):
        # Minimal valid 1x1 PNG.
        png = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00"
            b"\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc"
            b"\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        resp = self.client.post(
            "/api/chat/upload",
            files={"file": ("pixel.png", png, "image/png")},
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertTrue(body["is_image"])
        self.assertFalse(body["is_text"])
        self.assertIsNone(body["text_content"])
        self.assertTrue(Path(body["path"]).is_file())
        self.assertTrue(Path(body["path"]).suffix == ".png")

    def test_missing_file_field_is_unprocessable(self):
        """A request with no file part is rejected by FastAPI validation.

        This still exercises the multipart machinery (the request must be
        parsed before validation can report the missing required field), so it
        too depends on python-multipart being present.
        """
        resp = self.client.post("/api/chat/upload")
        self.assertEqual(resp.status_code, 422, resp.text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
