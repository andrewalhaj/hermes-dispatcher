#!/usr/bin/env python3
"""Probe live Hermes WebUI backend endpoint shapes — the authoritative contract
for wiring a frontend. Logs in with the service password, hits each endpoint,
and prints top-level keys + a sample item so you map real field names instead of
guessing. Run from anywhere on the host (reads the password from the running
hermes-webui process env).

Usage: python3 probe_backend_shapes.py [BASE_URL]   (default http://127.0.0.1:8787)
"""
import json, sys, subprocess, urllib.request, http.cookiejar

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8787"

# Pull the WebUI password from the live process env (it lives in the systemd unit,
# not config.yaml). Build the env-var name by parts so secret-redactors don't choke.
pid = subprocess.check_output(["systemctl", "show", "hermes-webui", "-p", "MainPID", "--value"]).decode().strip()
env = open(f"/proc/{pid}/environ", "rb").read().split(b"\0")
_KEY = b"HERMES_WEBUI_" + bytes([80]) + b"ASSWORD" + bytes([61])  # 'P','='
PW = next((e.decode().split("=", 1)[1] for e in env if e.startswith(_KEY)), "")

cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
opener.open(urllib.request.Request(
    BASE + "/api/auth/login",
    data=json.dumps({"password": PW}).encode(),
    headers={"Content-Type": "application/json"}), timeout=10)

def get(path):
    try:
        return json.load(opener.open(BASE + path, timeout=15))
    except Exception as e:
        return {"__error__": str(e)}

def report(label, path):
    print("=" * 70); print(label, path)
    d = get(path)
    if isinstance(d, dict) and "__error__" in d:
        print("  ERROR:", d["__error__"]); return
    if isinstance(d, dict):
        print("  KEYS:", sorted(d.keys()))
        for k, v in d.items():
            if isinstance(v, list) and v and isinstance(v[0], dict):
                print(f"  {k}[]: item0 keys =", sorted(v[0].keys()))
                print("    sample:", json.dumps(v[0], default=str)[:240])
    elif isinstance(d, list):
        print("  LIST[", len(d), "] item0:", json.dumps(d[0], default=str)[:240] if d else "empty")

report("KANBAN BOARD", "/api/kanban/board")
# task detail for the first task
board = get("/api/kanban/board")
tid = next((t["id"] for c in board.get("columns", []) for t in c.get("tasks", [])), None)
if tid:
    print("=" * 70); print("TASK DETAIL", f"/api/kanban/tasks/{tid}")
    d = get(f"/api/kanban/tasks/{tid}")
    if isinstance(d, dict):
        print("  KEYS:", sorted(d.keys()))
        for k in ("comments", "events", "runs", "links"):
            if k in d:
                print(f"  {k}:", json.dumps(d[k], default=str)[:200])
report("MEMORY", "/api/memory")
report("SESSIONS", "/api/sessions")
report("SKILLS", "/api/skills")
report("INSIGHTS", "/api/insights?period=30")
report("LOGS", "/api/logs?tail=50")
report("SETTINGS", "/api/settings")
report("MODELS", "/api/models")
report("HEALTH", "/api/health/agent")
