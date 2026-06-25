#!/usr/bin/env python3
"""Read-only scan: which Honcho sessions contain dummy-data / confabulation keywords.

Run this to QUANTIFY contamination before proposing session deletion. Its job is to
PROVE whether targeted deletion is viable. In practice (June 2026) it showed 79% of
sessions contained keyword hits AND that the highest-scoring sessions were the
correction conversations themselves — i.e. keyword-based deletion would destroy the
fixes along with the real history. There is no delete-message in the API, so you
cannot carve out individual bad turns. Treat a high hit-spread as a STOP sign for
deletion; fall back to scoped honcho_conclude negations + card-only injection.

Makes only POST .../sessions/list and POST .../messages/list (read-only queries).
Performs NO mutations. Reads HONCHO_API_KEY from ~/.hermes/.env.

Edit WORKSPACE and KEYWORDS for the specific case before running.
"""
import json, os, urllib.request, urllib.error

WORKSPACE = "hermes"
KEYWORDS = [
    # Replace/extend with the actual confabulations you're chasing.
    "3ds max", "rtx 5080", "sprint review", "team standup",
    "sanja", "ellie", "elliana", "jasper", "matte",
    "swedish", "dearborn", "sterling heights", "railway", "lancedb",
]

ENV = os.path.expanduser("~/.hermes/.env")
key = None
with open(ENV) as f:
    for line in f:
        if line.startswith("HONCHO_API_KEY"):
            key = line.strip().split("=", 1)[1]
            break
if not key:
    raise SystemExit("HONCHO_API_KEY not found in ~/.hermes/.env")

BASE = f"https://api.honcho.dev/v3/workspaces/{WORKSPACE}"

def call(path, method="GET", payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header("Authorization", "Bearer " + key)
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        r = urllib.request.urlopen(req, timeout=30)
        return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()
    except Exception as e:
        return "ERR", str(e)

code, body = call("/sessions/list", "POST", {})
if code != 200:
    raise SystemExit(f"sessions/list failed: {code} {body[:200]}")
sessions = json.loads(body).get("items", [])

hits = {}
for s in sessions:
    sid = s.get("id")
    msgs, page = [], 1
    while True:
        c, b = call(f"/sessions/{sid}/messages/list?page={page}&size=100", "POST", {})
        if c != 200:
            break
        items = json.loads(b).get("items", [])
        msgs.extend(items)
        if len(items) < 100 or page > 20:
            break
        page += 1
    for m in msgs:
        content = (m.get("content") or "").lower()
        for kw in KEYWORDS:
            if kw in content:
                hits.setdefault(sid, {}).setdefault(kw, 0)
                hits[sid][kw] += 1

print("=== Sessions containing keywords (sorted by total hits) ===\n")
for sid, kws in sorted(hits.items(), key=lambda x: -sum(x[1].values())):
    total = sum(kws.values())
    klist = ", ".join(f"{k}:{v}" for k, v in sorted(kws.items(), key=lambda x: -x[1]))
    print(f"[{total:>4} hits] {sid}\n          {klist}\n")

print(f"Scanned {len(sessions)} sessions; {len(hits)} contain hits "
      f"({100*len(hits)//max(len(sessions),1)}%).")
print("\nIf hit-spread is high OR top sessions are correction conversations,")
print("session deletion is the WRONG tool — use scoped conclusions + card-only injection.")
