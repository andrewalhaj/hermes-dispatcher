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
        "teamId": "<TEAM_UUID>",
        "title": "YOUR TITLE HERE",
        "description": "Optional markdown description",
        "priority": 2
      }
    }
  }'
```

## Priority Mapping

| Linear Priority | Value | Kanban Priority |
|---|---|---|
| Urgent | 0 | 50 |
| High | 1 | 30 |
| Medium | 2 | 10 |
| Low | 3 | 5 |
| None | 4 | 1 |

## Pipeline

```
cron detects anomaly
  → POST /graphql (create Linear issue)
    → Linear webhook fires
      → handler stores to knowledge store (fire-and-forget)
      → handler dispatches Kanban card (random coder, round-robin)
      → handler notifies Telegram (LINEAR_TELEGRAM_CHAT)
```

## Required Env

- `LINEAR_API_KEY` — personal API key
- `LINEAR_WEBHOOK_SECRET` — webhook secret
- `LINEAR_TELEGRAM_CHAT` — Telegram chat ID for routing reports

## Rate Limits

- 5,000 requests/hour per API key
- 3,000,000 complexity points/hour
- Issue create mutation: ~10 complexity points
