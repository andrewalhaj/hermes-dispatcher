# Lightweight variant: direct Messages API from any container (no CLI install)

Verified 2026-06-10 wiring Mealio's screenshot-import vision extractor. When a containerized app
just needs to CALL the Anthropic API on the Max plan (not run the `claude` CLI), skip the whole
CLI-install/exec-volume dance — three pieces suffice:

## 1. RO-mount the host credentials
```yaml
# docker-compose.yml, service volumes:
- /root/.claude/.credentials.json:/run/claude_credentials.json:ro
```
Single-writer holds: Hermes refreshes the canonical file lazily (`agent/anthropic_adapter.py`,
60s buffer); the container only reads. **Read the token at REQUEST time, never cache it** —
file contents rotate under you (~50 min token life).

## 2. Read token + call the API (Node example, no SDK needed)
```typescript
const creds = JSON.parse(readFileSync(process.env.ANTHROPIC_BYPASS_CREDENTIALS!, 'utf8'))
const token = creds?.claudeAiOauth?.accessToken   // key path: claudeAiOauth.accessToken

const res = await fetch('https://api.anthropic.com/v1/messages', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${token}`,          // Bearer, NOT x-api-key
    'anthropic-version': '2023-06-01',
  },
  body: JSON.stringify({ model, max_tokens, system, messages }),
})
```
Vision: content part `{ type: 'image', source: { type: 'base64', media_type, data } }`.

## 3. Model choice on the shared Max token (verified empirically)
- **Sonnet (`claude-sonnet-4-*`) 429s near-instantly** — the Max account's rate limit is shared
  with live Hermes sessions; vision-sized requests on big models lose that contention every time.
- **`claude-haiku-4-5-20251001` works reliably** — high limit headroom, fully vision-capable,
  right-sized for OCR/extraction jobs.
- Dated model IDs from memory may 404. Enumerate live:
  `GET https://api.anthropic.com/v1/models` with the same Bearer + anthropic-version headers.
  (2026-06-10 list included: claude-fable-5, claude-opus-4-8, claude-sonnet-4-6,
  claude-haiku-4-5-20251001, …)

## Gotchas
- **No `response_format: json_object` on the Messages API** (unlike OpenAI). Prompt for
  JSON-only output AND strip markdown fences before parsing:
  `content.replace(/^```json\s*/m,'').replace(/^```\s*$/m,'').trim()`.
- Response shape: `data.content` is an array of blocks — find `type === 'text'`.
- Token in creds file ≠ valid forever: if the host Hermes process has been down longer than the
  token life, the mounted file holds an expired token (no refresher ran). Check `expiresAt`
  (ms epoch) when debugging 401s.
- This variant needs NO keep-warm cron *as long as the host Hermes is actively running* —
  Hermes' own lazy refresh keeps the file current. The OD keep-warm cron exists because OD's
  sidecar copy (`/root/.claude-od`) is a separate file nobody else refreshes.
