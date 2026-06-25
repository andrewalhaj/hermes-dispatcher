# Cron → Linear → Kanban Intake

Cron jobs create Linear issues to trigger autonomous Kanban dispatch.
The webhook handler routes every new issue to the coder fleet with priority mapping.

## Quick Start

```bash
curl -s -X POST https://api.linear.app/graphql \
  -H "Authorization: $LINEAR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "mutation($input: IssueCreateInput!) { issueCreate(input: $input) { success issue { id identifier title url } } }",
    "variables": {
      "input": {
        "teamId": "38a0c106-e9a8-4f65-84d2-ec8bdc61855d",
        "title": "YOUR TITLE HERE",
        "description": "Optional markdown description",
        "priority": 2
      }
    }
  }'
```

## Priority Mapping

| Linear Priority | Value | Kanban Priority | Meaning |
|---|---|---|---|
| Urgent | 0 | 50 | Dispatched first |
| High | 1 | 30 | |
| Medium | 2 | 10 | Default for cron |
| Low | 3 | 5 | |
| None | 4 | 1 | Skip unless urgent |

## Pipeline

```
cron detects anomaly
  → POST /graphql (create Linear issue)
    → Linear webhook fires
      → handler stores to knowledge store
      → handler dispatches Kanban card (random coder, round-robin)
      → handler notifies Telegram (LINEAR_TELEGRAM_CHAT)
```

## Team

- **Name:** Hermesjarvis
- **Key:** HER
- **UUID:** `38a0c106-e9a8-4f65-84d2-ec8bdc61855d`

## Required Env

- `LINEAR_API_KEY` — personal API key (already set)
- `LINEAR_WEBHOOK_SECRET` — webhook secret (already set)
- `LINEAR_TELEGRAM_CHAT` — Telegram chat ID for routing reports (already set)

## Rate Limits

- 5,000 requests/hour per API key
- 3,000,000 complexity points/hour
- Issue create mutation: ~10 complexity points — basically free

## Example: Cron Job Using This

```python
import os, subprocess

def report_to_linear(title, description="", priority=2):
    """Fire-and-forget issue creation. Returns identifier on success."""
    result = subprocess.run([
        "curl", "-s", "-X", "POST",
        "https://api.linear.app/graphql",
        "-H", f"Authorization: {os.environ['LINEAR_API_KEY']}",
        "-H", "Content-Type: application/json",
        "-d", json.dumps({
            "query": "mutation($input: IssueCreateInput!) { issueCreate(input: $input) { success issue { identifier url } } }",
            "variables": {
                "input": {
                    "teamId": "38a0c106-e9a8-4f65-84d2-ec8bdc61855d",
                    "title": title,
                    "description": description,
                    "priority": priority
                }
            }
        })
    ], capture_output=True, text=True, timeout=10)
    # Webhook handles the rest — Kanban dispatch + Telegram notify
    return result.stdout
```
