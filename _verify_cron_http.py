import os
os.environ.setdefault("HERMES_HOME", "/root/.hermes")
from fastapi.testclient import TestClient
from server import app
from routes.auth import SESSION_TOKEN

c = TestClient(app)
cookies = {"hd_session": SESSION_TOKEN}

r = c.get("/api/cron", cookies=cookies)
print("GET /api/cron ->", r.status_code, "| jobs:", len(r.json()))
print("  sample:", r.json()[0] if r.json() else None)

jid = r.json()[0]["id"]
r2 = c.get(f"/api/cron/{jid}/output", cookies=cookies)
print(f"GET /api/cron/{jid}/output ->", r2.status_code, "| rows:", len(r2.json()))

# a job with known output
r3 = c.get("/api/cron/6537cacf1cd6/output", cookies=cookies)
print("GET /api/cron/6537cacf1cd6/output ->", r3.status_code, "| rows:", len(r3.json()))
if r3.json():
    print("  content head:", repr(r3.json()[0]["content"][:80]))
