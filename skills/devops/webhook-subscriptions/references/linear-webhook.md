# Linear Webhook Integration

## Registration
Linear webhooks are registered via GraphQL API or UI at Settings → API → Webhooks.

### Via API
```graphql
mutation {
  webhookCreate(input: {
    url: "https://hermes.andrewskingdom.com/api/hooks/linear"
    teamId: "<team-uuid>"
    resourceTypes: ["Issue", "Comment", "Project"]
  }) {
    success
    webhook { id enabled secret }
  }
}
```

Linear returns a secret (`lin_wh_...`) — use THIS, not a self-generated one.

## Authentication
- Header: `Linear-Signature` (hex-encoded HMAC-SHA256 of raw body)
- Delivery tracking: `Linear-Delivery` header (UUID v4)
- Event type: `Linear-Event` header (e.g. "Issue", "Comment")

### Verification Code
```python
body = await request.body()
expected = hmac.new(
    LINEAR_WEBHOOK_SECRET.encode(), body, hashlib.sha256
).hexdigest()
if not hmac.compare_digest(expected.encode(), signature.encode()):
    raise HTTPException(status_code=401)
```

### Timestamp Check
Linear includes `webhookTimestamp` (UNIX ms) in payload. Verify within 120s to prevent replay:
```python
ts = payload.get("webhookTimestamp", 0)
now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
if abs(now_ms - ts) > 120_000:
    raise HTTPException(status_code=401, detail="Stale timestamp")
```

## Payload Structure
```json
{
  "action": "create|update|remove",
  "type": "Issue|Comment|Project|...",
  "data": { "id": "...", "title": "...", ... },
  "actor": { "id": "...", "type": "user", "name": "...", "email": "..." },
  "url": "https://linear.app/issue/...",
  "createdAt": "2024-01-01T00:00:00.000Z",
  "organizationId": "...",
  "webhookTimestamp": 1704067200000,
  "webhookId": "..."
}
```

## Handler Pattern
Follows the standard webhook pipeline:
1. HMAC verification (hex-encoded, unlike Sentry)
2. Timestamp replay check
3. Extract action/type/title/url
4. Store to knowledge store via `knowledge.py store`
5. Create Kanban card for `Issue create` events (POST `/api/kanban/tasks`)
6. Telegram notify via `/api/hooks/notify` (if `LINEAR_TELEGRAM_CHAT` set)

## Environment Variables
- `LINEAR_WEBHOOK_SECRET`: From Linear's webhook create response (`lin_wh_...`)
- `LINEAR_TELEGRAM_CHAT`: Telegram chat ID for notifications (optional)
- `LINEAR_API_KEY`: Personal API key for webhook registration
## Auth Exempt

Add to `server.py` `_AUTH_EXEMPT`:
```python
"/api/hooks/linear",
```

## Handler Pitfalls

### Synchronous subprocess blocks the event loop

The handler at `/api/hooks/linear` calls `knowledge.py store` via `subprocess.run(..., timeout=10)`. This is a synchronous blocking call inside an async FastAPI handler. If Supabase is slow or unreachable, the entire uvicorn worker hangs for 10+ seconds — every webhook delivery times out.

**Fix:** wrap in try/except with reduced timeout:
```python
# Store to knowledge store (fire-and-forget, don't block the pipeline)
try:
    subprocess.run(
        [...],
        capture_output=True, text=True, timeout=5,
        env={**os.environ, "HERMES_HOME": str(HERMES_HOME)},
    )
except Exception:
    pass  # Don't let knowledge store failures block routing
```

### Pattern B: autonomous routing (no manual gate)

As of 2026-06-24, the handler routes ALL new Issues to Kanban without a label gate. Previous behaviour checked for `manual`/`manual-triage` labels and skipped routing when present — this gate has been removed. Every new Linear issue becomes a Kanban card with round-robin coder assignment.

Priority mapping: Linear 0→Kanban 50, 1→30, 2→10, 3→5, 4→1.

### Required environment variables for full pipeline

- `LINEAR_WEBHOOK_SECRET` — from Linear webhook create response (`lin_wh_...`)
- `LINEAR_API_KEY` — personal API key for registration/reverse calls
- `LINEAR_TELEGRAM_CHAT` — Telegram chat ID for routing reports (e.g. Home channel)

### Self-POST deadlock in uvicorn (critical)

**Symptom:** The Linear webhook handler returns 200 but no Kanban card is created. No error in the response body.

**Root cause:** The handler POSTs to `http://127.0.0.1:8787/api/kanban/tasks` to create Kanban cards — but uvicorn runs single-worker (`uvicorn server:app`, no `--workers` flag). The handler occupies the only worker slot, so the self-POST queues indefinitely, hits the 5-second timeout, and the exception is caught silently with `logger.warning("linear webhook: kanban dispatch failed: %s", exc)`.

**Fix (applied 2026-06-24):** Replace the `aiohttp.ClientSession().post()` with a direct SQLite INSERT matching the pattern in `routes/kanban.py`:

```python
import sqlite3 as _sqlite3
_task_id = "t_" + uuid.uuid4().hex[:8]
_now = int(datetime.now(timezone.utc).timestamp())
_db_path = os.environ.get("KANBAN_DB", "/root/.hermes/kanban.db")
_conn = _sqlite3.connect(_db_path)
try:
    _conn.execute(
        "INSERT INTO tasks (id, title, body, status, priority, created_by, created_at, tenant, assignee) "
        "VALUES (?, ?, ?, 'triage', 4, 'dashboard', ?, ?, NULL)",
        (_task_id, entity_title, kanban_body, _now, "internal"),
    )
    _conn.commit()
finally:
    _conn.close()
```

**Same pitfall affects:** The `/api/hooks/notify` self-POST at the Telegram notification step. Both the Sentry and Linear handlers POST to `http://127.0.0.1:8787/api/hooks/notify` — same deadlock. If Telegram notifications from webhooks are silent, this is the cause.

**Detection:** To verify, test with a simulated webhook (signed payload) → check if `kanban_list` includes the expected card within 2 seconds. If the kanban POST directly works (`curl -X POST http://127.0.0.1:8787/api/kanban/tasks ...`) but the webhook handler creates none, the deadlock is confirmed.

### LINEAR_API_KEY in dispatcher environment

The dispatcher's uvicorn process needs `LINEAR_API_KEY` in its environment. It's typically set in `~/.hermes/.env` but the dispatcher's own `.env` at `/root/hermes-dispatcher/.env` may not carry it. The Sentry webhook handler reads `os.environ.get("LINEAR_API_KEY")` to create Linear issues — if empty, the Sentry→Linear hop fails silently.

Verify: `cat /proc/$(pgrep -f "uvicorn server:app")/environ | tr '\0' '\n' | grep LINEAR_API_KEY`
