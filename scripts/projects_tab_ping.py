#!/usr/bin/env python3
"""
projects_tab_ping.py — completion watcher for kanban task t_78a99c0f
(HAJarvis adding the Projects tab to wall-dash).

Watchdog pattern: SILENT (empty stdout) while still running. On the FIRST
terminal state it VERIFIES the tab against the LIVE nginx-served index.html
(not the self-report) + confirms the JSON endpoint, then prints a ping.
A state file latches it to ping exactly once. Exits 0 on transient errors.
"""
import os, sqlite3, subprocess, sys

TASK = "t_fc69472f"
STATE = "/tmp/projects_tab_ping_done"
HERMES = os.path.expanduser("~/.hermes")
DASH = "http://100.119.118.54:5051/"
JSON_URL = "http://100.119.118.54:5051/kanban-state.json"

if os.path.exists(STATE):
    sys.exit(0)

try:
    con = sqlite3.connect(f"{HERMES}/kanban.db", timeout=5)
    con.row_factory = sqlite3.Row
    row = con.execute(
        "select status, completed_at from tasks where id=?", (TASK,)
    ).fetchone()
    if not row:
        sys.exit(0)

    status = (row["status"] or "").lower()
    terminal = bool(row["completed_at"]) or status in (
        "done", "completed", "archived", "failed", "error", "cancelled"
    )
    if not terminal:
        sys.exit(0)  # still running — SILENT

    failed = status in ("failed", "error", "cancelled")

    def curl(url, want_body=False):
        try:
            if want_body:
                r = subprocess.run(["curl", "-s", "--max-time", "15", url],
                                   capture_output=True, text=True, timeout=20)
                return r.stdout
            r = subprocess.run(
                ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
                 "--max-time", "15", url],
                capture_output=True, text=True, timeout=20)
            return r.stdout.strip()
        except Exception:
            return ""

    # --- verify against LIVE served HTML (the real proof) ---
    html = curl(DASH, want_body=True)
    btn = 'data-view="projects"' in html
    view = html.count('data-view="projects"') >= 2  # button + view div
    dash_code = curl(DASH)
    json_code = curl(JSON_URL)

    # worker summary (context, not proof)
    summary = ""
    try:
        r = con.execute(
            "select summary from task_runs where task_id=? "
            "order by id desc limit 1", (TASK,)
        ).fetchone()
        if r and r["summary"]:
            summary = str(r["summary"]).strip().replace("\n", " ")[:400]
    except Exception:
        pass

    with open(STATE, "w") as f:
        f.write(status)

    out = []
    if failed:
        out.append(f"⚠️ HAJarvis Projects-tab task {TASK} ended status={status} (not clean).")
    else:
        out.append(f"✅ HAJarvis finished the Projects tab (task {TASK}, status={status}).")
    out.append(f"Live verify — dashboard HTTP {dash_code}, kanban-state.json HTTP {json_code}.")
    if view:
        out.append("VERIFIED in served HTML: projects nav button + view div both present.")
    elif btn:
        out.append("⚠️ Partial: found the nav button but not a matching view div — needs eyes.")
    else:
        out.append("⚠️ Could NOT find the projects tab in the served HTML — needs eyes.")
    if summary:
        out.append(f"His report: {summary}")
    out.append("Open the Projects tab on the wall-dash to eyeball it — pixels unconfirmed (Tailscale-only).")
    print("\n".join(out))
    sys.exit(0)

except Exception:
    sys.exit(0)
