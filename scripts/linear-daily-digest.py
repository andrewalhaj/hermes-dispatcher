#!/usr/bin/env python3
"""Daily Linear digest — queries non-completed issues and prints a formatted digest.

The stdout of this script is the digest message. When run as a cron job with
no_agent=true, the output is saved to ~/.hermes/cron/output/<job_id>/<ts>.md
and picked up by the Dashboard Chat via /api/cron/output.
"""
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone

LINEAR_API_KEY = os.environ.get("LINEAR_API_KEY", "")
LINEAR_API_URL = "https://api.linear.app/graphql"

GRAPHQL_QUERY = """
query IssuesDigest {
  issues(
    first: 100
    filter: {
      state: { type: { neq: "completed" } }
      canceledAt: { null: true }
    }
    orderBy: updatedAt
  ) {
    nodes {
      identifier
      title
      priority
      updatedAt
      assignee { name }
      state { name }
    }
  }
}
"""


def query_linear() -> list[dict]:
    """Return list of non-completed issues from Linear."""
    if not LINEAR_API_KEY:
        print("ERROR: LINEAR_API_KEY not set", file=sys.stderr)
        sys.exit(1)

    req = urllib.request.Request(
        LINEAR_API_URL,
        data=json.dumps({"query": GRAPHQL_QUERY}).encode(),
        headers={
            "Authorization": LINEAR_API_KEY,
            "Content-Type": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read())
    except Exception as e:
        print(f"ERROR: Linear API call failed: {e}", file=sys.stderr)
        sys.exit(1)

    if "errors" in body:
        print(f"ERROR: Linear GraphQL errors: {body['errors']}", file=sys.stderr)
        sys.exit(1)

    return body.get("data", {}).get("issues", {}).get("nodes", [])


def days_ago(iso_str: str) -> int:
    """Return days since the given ISO timestamp, rounded down."""
    if not iso_str:
        return 0
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        return (now - dt).days
    except (ValueError, TypeError):
        return 0


def format_digest(issues: list[dict]) -> str:
    """Format issues into the morning digest."""
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%A, %B %-d")

    urgent = []
    stale = []
    normal = []

    for issue in issues:
        prio = issue.get("priority", 99)
        upd = issue.get("updatedAt", "")
        age = days_ago(upd)

        entry = {
            "id": issue.get("identifier", "???"),
            "title": issue.get("title", "Untitled"),
            "assignee": (issue.get("assignee") or {}).get("name") or "unassigned",
            "age": age,
            "state": (issue.get("state") or {}).get("name", "Unknown"),
        }

        if prio is not None and prio <= 1:
            entry["label"] = "urgent"
            urgent.append(entry)
        elif age > 7:
            entry["label"] = "stale"
            stale.append(entry)
        else:
            entry["label"] = "normal"
            normal.append(entry)

    total = len(issues)
    lines = []

    # Header
    lines.append(f"☀️ **Good morning** — {total} open issues  _{date_str}_")
    lines.append(f"🔴 {len(urgent)} urgent · ⚠️ {len(stale)} stale · 📋 {len(normal)} normal")
    lines.append("")

    # Urgent
    if urgent:
        lines.append("**🔴 Urgent**")
        for i in urgent:
            age_str = "today" if i["age"] == 0 else f"{i['age']}d" if i["age"] < 30 else f"{i['age'] // 30}mo"
            lines.append(f"🔴 {i['id']} {i['title']} _({age_str}, {i['assignee']})_")
        lines.append("")

    # Stale
    if stale:
        lines.append("**⚠️ Stale**")
        for s in stale[:5]:  # cap at 5 to keep digest compact
            lines.append(f"⚠️ {s['id']} {s['title']} _({s['age']}d, {s['assignee']})_")
        if len(stale) > 5:
            lines.append(f"  _...and {len(stale) - 5} more_")
        lines.append("")

    # Normal
    if normal:
        lines.append("**📋 Open**")
        for n in normal[:7]:
            lines.append(f"📋 {n['id']} {n['title']} _({n['assignee']})_")
        if len(normal) > 7:
            lines.append(f"  _...and {len(normal) - 7} more_")
        lines.append("")

    # Footer
    lines.append("---")
    lines.append(f"_{now.strftime('%H:%M UTC')} · Linear Digest_")

    return "\n".join(lines)


def main():
    issues = query_linear()
    if not issues:
        print("☀️ **Good morning** — no open issues today. 🎉")
        return

    digest = format_digest(issues)
    print(digest)


if __name__ == "__main__":
    main()
