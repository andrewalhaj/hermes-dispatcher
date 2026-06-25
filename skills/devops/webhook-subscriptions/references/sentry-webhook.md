# Sentry Webhook

## Source
Sentry Internal Integrations → Webhooks. HMAC-SHA256 signing using the integration's Client Secret. Header: `Sentry-Hook-Signature`.

## Auth Model
- **No webhook secret field in Sentry UI.** The integration's "Client Secret" IS the HMAC key.
- Header: `Sentry-Hook-Signature: <hmac-sha256-hex>`
- Verify with `hmac.compare_digest(expected, request.headers["Sentry-Hook-Signature"])`
- Sentry does NOT let you customize the secret — you get one per integration.

## End-to-End Pipeline

### 1. Sentry Projects + SDK Instrumentation
Create one Sentry project per app via API or UI. Instrument each stack:

| Stack | SDK | Init Pattern |
|---|---|---|
| Python/FastAPI | `pip install sentry-sdk` | `sentry_sdk.init(dsn=..., environment="production")` at TOP of server.py; `SentryAsgiMiddleware(app)` at END (after all routes) |
| React/TypeScript | `npm install @sentry/react` | `Sentry.init({dsn, integrations:[browserTracingIntegration()]})` BEFORE `createRoot()`; wrap with `<Sentry.ErrorBoundary>` |
| Node.js/Docker | Check for built-in support first | If app has sentry.ts: set `SENTRY_DSN` env var. Else: `npm install @sentry/node` + `Sentry.init()` |

DSNs are **public keys** — safe to hardcode. See `references/sentry-sdk-instrumentation.md` for full init patterns.

### 2. Webhook Handler (`routes/hooks.py`)
- HMAC-SHA256 verification via `Sentry-Hook-Signature` header
- Parse `action`, `data.event.title`, `data.event.web_url`, `data.event.project.name`, `data.event.level`
- Store to knowledge store via `knowledge.py store --text "..." --tags sentry,alert --source sentry-webhook --priority high`
- Append to `data/sentry_messages.json` for dashboard Sentry channel
- **On `action == "created"`: POST to `http://127.0.0.1:8787/api/kanban/tasks`** to auto-create a Kanban card (title: `"Sentry: <issue_title>"`, desc: project/level/URL, tenant: `"internal"`)
- Fire Telegram notification via `/api/hooks/notify` (auth-exempt endpoint)

### 3. Notify Endpoint (`routes/notify.py`)
Auth-exempt POST endpoint at `/api/hooks/notify`. Uses Telegram Bot API directly:
```python
url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
async with aiohttp.ClientSession() as session:
    await session.post(url, json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"})
```
Must be added to `_AUTH_EXEMPT` in `server.py`.

### 4. Dashboard Sentry Channel
Frontend (`Chat.tsx`): Add "Sentry" channel row in sidebar under "Channels" group. Bell icon, red accent (`#f87171`), reads from `/api/sentry/messages` endpoint. Backend (`routes/sentry.py`): serves `data/sentry_messages.json`.

### 5. Linear Intake Pipeline (Pattern B)

When a new Sentry issue fires (`action == "created"`), the webhook handler **creates a Linear issue** instead of a direct Kanban card. The Linear webhook then handles Kanban dispatch with clean formatting:

```
Sentry alert → POST https://api.linear.app/graphql (create issue)
  → Linear webhook fires → /api/hooks/linear
    → Kanban card dispatched to random coder (Pattern B auto-route)
    → Telegram notification (LINEAR_TELEGRAM_CHAT)
```

Linear issue format:
- Title: `[Sentry] <project>: <title>`
- Priority: 1 (High) — Sentry alerts are urgent
- Team: Hermesjarvis (`38a0c106-e9a8-4f65-84d2-ec8bdc61855d`)

The handler requires `LINEAR_API_KEY` from env. Cards land as dispatched (ready/running) via the Linear webhook's Pattern B routing.

### 6. Knowledge Store (fire-and-forget)

Both Sentry and Linear webhook handlers wrap `knowledge.py store` in try/except with `timeout=5`. This prevents a slow Supabase backend from blocking the event loop for 10+ seconds. If the knowledge store is down, the alert still routes through Linear → Kanban.

### 6. Telegram Group
Set `SENTRY_TELEGRAM_CHAT` in `.env` to a dedicated Telegram group ID. Create the group, add the bot, get the chat ID (negative number format).

## HMAC Verification (Reference Implementation)

```python
import hmac, hashlib, json
expected = hmac.new(SECRET.encode(), request_body, hashlib.sha256).hexdigest()
if not hmac.compare_digest(expected, request.headers.get("Sentry-Hook-Signature", "")):
    raise HTTPException(status_code=401)
```

## Testing

```python
# From the host
import hmac, hashlib, json, requests
payload = json.dumps({"action": "created", "installation": {"uuid": "test"}, "data": {"event": {"title": "Test", "web_url": "https://..."}}})
sig = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
r = requests.post("https://hermes.andrewskingdom.com/api/hooks/sentry",
    data=payload,
    headers={"Content-Type": "application/json", "Sentry-Hook-Signature": sig})
```

## Secret Safety

The Client Secret is shown in the Sentry UI and is the HMAC key. If it leaks into chat, revoke it in Sentry's integration settings and update `.env`.
