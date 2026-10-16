"""POST /api/hooks/knowledge works with NEO4J_* unset (Neo4j mirror removed 2026-10-15)."""
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

os.environ.setdefault("WEBHOOK_SECRET", "test-secret-not-real")

import routes.hooks as hooks  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


class KnowledgeHookNoNeo4jTest(unittest.TestCase):
    def setUp(self):
        env = {k: v for k, v in os.environ.items() if not k.startswith("NEO4J_")}
        self._env = mock.patch.dict(os.environ, env, clear=True)
        self._secret = mock.patch.object(hooks, "WEBHOOK_SECRET", "s3cret")
        self._env.start()
        self._secret.start()
        app = FastAPI()
        app.include_router(hooks.router, prefix="/api")
        self.client = TestClient(app)

    def tearDown(self):
        self._secret.stop()
        self._env.stop()

    def _post(self, payload):
        return self.client.post("/api/hooks/knowledge", json=payload,
                                headers={"Authorization": "Bearer s3cret"})

    def test_row_is_processed(self):
        r = self._post({"id": 42, "text": "a fact", "tags": ["x"]})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {"status": "processed", "row_id": 42})
        self.assertNotIn("neo4j", sys.modules)

    def test_empty_text_is_skipped(self):
        r = self._post({"id": 7, "text": ""})
        self.assertEqual(r.json(), {"status": "skipped", "reason": "empty_text"})

    def test_bad_token_rejected(self):
        r = self.client.post("/api/hooks/knowledge", json={"text": "x"},
                             headers={"Authorization": "Bearer wrong"})
        self.assertEqual(r.status_code, 401)


if __name__ == "__main__":
    unittest.main()
