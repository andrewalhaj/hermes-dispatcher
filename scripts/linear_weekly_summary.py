#!/usr/bin/env python3
"""Linear Weekly Cycle Summary — run weekly (no_agent cron).

Queries Linear for issues created/completed in the past 7 days,
computes avg time-to-close, and prints a formatted report to stdout.

Stdout is delivered verbatim to Dashboard Chat by the no_agent cron runner.
Silent when zero activity.
"""
import json, os, subprocess, sys
from datetime import datetime, timezone, timedelta

TEAM_ID = "38a0c106-e9a8-4f65-84d2-ec8bdc61855d"
API_KEY = os.getenv("LINEAR_API_KEY", "")
now = datetime.now(timezone.utc)
week_start = (now - timedelta(days=7)).strftime("%Y-%m-%dT00:00:00Z")

def linear_query(query):
    """Run a Linear GraphQL query, return parsed JSON."""
    r = subprocess.run([
        "curl", "-s", "-X", "POST", "https://api.linear.app/graphql",
        "-H", f"Authorization: {API_KEY}",
        "-H", "Content-Type: application/json",
        "-d", json.dumps({"query": query})
    ], capture_output=True, text=True, timeout=20)
    return json.loads(r.stdout)

# ── 1. Closed issues ────────────────────────────────────────────────────
d = linear_query(f"""
{{
  issues(filter: {{
    team: {{ id: {{ eq: "{TEAM_ID}" }} }},
    state: {{ type: {{ in: ["completed", "canceled"] }} }},
    updatedAt: {{ gte: "{week_start}" }}
  }}, first: 50) {{
    nodes {{
      identifier title
      state {{ type }}
      createdAt completedAt canceledAt
      url
    }}
  }}
}}
""")
closed = d.get("data", {}).get("issues", {}).get("nodes", []) if not d.get("errors") else []

# ── 2. Opened issues ────────────────────────────────────────────────────
d = linear_query(f"""
{{
  issues(filter: {{
    team: {{ id: {{ eq: "{TEAM_ID}" }} }},
    createdAt: {{ gte: "{week_start}" }}
  }}, first: 50) {{
    nodes {{ identifier title createdAt url }}
  }}
}}
""")
opened = d.get("data", {}).get("issues", {}).get("nodes", []) if not d.get("errors") else []

# ── 3. Avg time-to-close ────────────────────────────────────────────────
deltas = []
for i in closed:
    created = i.get("createdAt")
    closed_at = i.get("completedAt") or i.get("canceledAt")
    if created and closed_at:
        try:
            dc = datetime.fromisoformat(created.replace("Z", "+00:00"))
            da = datetime.fromisoformat(closed_at.replace("Z", "+00:00"))
            deltas.append((da - dc).total_seconds() / 86400.0)
        except (ValueError, TypeError):
            pass
avg = sum(deltas) / len(deltas) if deltas else None

# ── 4. Silent exit if nothing happened ──────────────────────────────────
if not closed and not opened:
    sys.exit(0)

# ── 5. Format ───────────────────────────────────────────────────────────
nf = now.strftime("%b %d")
wf = (now - timedelta(days=7)).strftime("%b %d")

lines = [f"\U0001f4ca **Week in Review** \u2014 {wf}\u2013{nf}"]
parts = []
if closed:
    parts.append(f"\u2705 {len(closed)} closed")
if opened:
    parts.append(f"\U0001f4e5 {len(opened)} opened")
if avg is not None:
    parts.append(f"\u23f1\ufe0f Avg close: {avg:.1f} days")
lines.append(" \u00b7 ".join(parts))

if closed:
    shipped = ", ".join(f"{i['identifier']} {i['title']}" for i in closed)
    lines.append(f"\n**Shipped:** {shipped}")
if opened:
    ops = ", ".join(f"{i['identifier']} {i['title']}" for i in opened)
    lines.append(f"**Opened:** {ops}")

print("\n".join(lines))
