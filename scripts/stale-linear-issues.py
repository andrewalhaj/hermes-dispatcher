#!/usr/bin/env python3
"""Check Linear for stale issues (untouched 14+ days, not done/canceled).

Reads LINEAR_API_KEY from env. Outputs a Dashboard Chat message to stdout.
Returns exit code 0 with no output when nothing is stale.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone, timedelta

API_URL = "https://api.linear.app/graphql"
TEAM_ID = "38a0c106-e9a8-4f65-84d2-ec8bdc61855d"
STALE_DAYS = 14


def _get_key() -> str:
    key = os.environ.get("LINEAR_API_KEY", "").strip()
    if not key:
        sys.stderr.write("LINEAR_API_KEY not set\n")
        sys.exit(2)
    return key


def gql(query: str, variables: dict | None = None) -> dict:
    key = _get_key()
    payload = {"query": query}
    if variables:
        payload["variables"] = variables
    req = urllib.request.Request(
        API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": key,
            "User-Agent": "hermes-stale-linear-check/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        sys.stderr.write(f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')}\n")
        sys.exit(1)
    except urllib.error.URLError as e:
        sys.stderr.write(f"Network error: {e}\n")
        sys.exit(1)

    result = json.loads(body)
    if "errors" in result and result["errors"]:
        sys.stderr.write(f"GraphQL errors: {json.dumps(result['errors'])}\n")
        if not result.get("data"):
            sys.exit(1)
    return result.get("data", {}) or {}


def main() -> None:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=STALE_DAYS)).strftime(
        "%Y-%m-%dT%H:%M:%S.000Z"
    )

    query = """
    query($filter: IssueFilter, $first: Int!) {
      issues(filter: $filter, first: $first, orderBy: updatedAt) {
        nodes {
          id
          identifier
          title
          updatedAt
          url
          state { name type }
          assignee { name }
        }
      }
    }
    """

    # Exclude completed/canceled; filter to team; filter by updatedAt
    variables = {
        "filter": {
            "team": {"id": {"eq": TEAM_ID}},
            "updatedAt": {"lt": cutoff},
            "state": {"type": {"nin": ["completed", "canceled"]}},
        },
        "first": 100,
    }

    data = gql(query, variables)
    issues = data.get("issues", {}).get("nodes", [])

    if not issues:
        # Silent exit — nothing stale
        return

    # Sort by staleness (oldest first)
    issues.sort(key=lambda i: i.get("updatedAt", ""))

    # Build message lines
    lines = [f"\u26a0\ufe0f {len(issues)} stale issue{'s' if len(issues) != 1 else ''}:"]
    for issue in issues:
        ident = issue["identifier"]
        title = issue["title"]
        url = issue["url"]
        try:
            updated = datetime.fromisoformat(
                issue["updatedAt"].replace("Z", "+00:00")
            )
            days = (datetime.now(timezone.utc) - updated).days
        except (ValueError, KeyError):
            days = "?"
        assignee = issue.get("assignee")
        who = f" ({assignee['name']})" if assignee else ""
        lines.append(f"  {ident} ({days}d){who} — {title}")
        lines.append(f"  {url}")

    # Also emit a compact summary line for the notifier
    summary_ids = ", ".join(i["identifier"] for i in issues)
    lines.append(f"\n\u2014 Stale issue check: {summary_ids}")

    print("\n".join(lines))


if __name__ == "__main__":
    main()
