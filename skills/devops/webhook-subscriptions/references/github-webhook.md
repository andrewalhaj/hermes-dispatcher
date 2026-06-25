# GitHub Webhook Integration

GitHub uses **X-Hub-Signature-256** (HMAC-SHA256 of the raw request body) for webhook auth.

## Auth

```python
GITHUB_WEBHOOK_SECRET = os.environ.get("GITHUB_WEBHOOK_SECRET", "")

signature = request.headers.get("X-Hub-Signature-256", "")
body = await request.body()
expected = "sha256=" + hmac.new(
    GITHUB_WEBHOOK_SECRET.encode(), body, hashlib.sha256
).hexdigest()

if not hmac.compare_digest(expected, signature):
    raise HTTPException(401, "Invalid signature")
```

## Event Routing

| Event header | Handler | Stored as |
|---|---|---|
| `issues` | `_handle_issues` | knowledge store (tags: github,issue) |
| `pull_request` | `_handle_pull_request` | knowledge store (tags: github,pr) |
| `push` | `_handle_push` | knowledge store (tags: github,push) |
| `ping` | inline | ack only |

## Registration

POST to `https://api.github.com/repos/{owner}/{repo}/hooks`:
```json
{
  "name": "web",
  "config": {
    "url": "https://your-domain/api/hooks/github",
    "content_type": "json",
    "secret": "<GITHUB_WEBHOOK_SECRET>"
  },
  "events": ["issues", "pull_request", "push"],
  "active": true
}
```

Requires a GitHub PAT with `admin:repo_hook` scope.

## Knowledge Store Facts

Each event produces a fact stored via `knowledge.py store`:
- **Issue opened:** `Issue #N opened in owner/repo: title`
- **PR merged:** `PR #N merged in owner/repo: title` (priority=high)
- **Push:** `Push to owner/repo/branch: N commit(s) by user — latest message`
- Context prefix = HTML URL for issues/PRs, `repo/ref` for pushes

## Pitfalls

- **`X-Hub-Signature-256` header, not `X-Hub-Signature`.** The `-256` variant is SHA-256; the older `X-Hub-Signature` is SHA-1. Both exist — GitHub sends both but we verify the 256 variant.
- **Raw body, not parsed JSON.** HMAC is computed over the exact bytes GitHub sent. Read `await request.body()` before any JSON parsing.
- **Ping on creation.** GitHub sends a `ping` event immediately after webhook registration. Handler must return 2xx.
- **No subprocess blocking.** Knowledge store writes use `subprocess.run` with a 10s timeout so the webhook returns 200 quickly (GitHub retries on timeout/5xx).
