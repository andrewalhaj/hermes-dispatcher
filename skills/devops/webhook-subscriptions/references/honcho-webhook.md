# Honcho Webhook Integration

Honcho's webhook delivery uses HMAC-SHA256 signing, not Bearer tokens.

## Signature Format

**Header:** `X-Honcho-Signature: <hex digest>`

**How Honcho signs** (from `plastic-labs/honcho/src/webhooks/webhook_delivery.py`):
```python
event_json = json.dumps(event_payload, separators=(",", ":"), sort_keys=True)
signature = hmac.new(
    secret.encode("utf-8"),
    event_json.encode("utf-8"),
    hashlib.sha256
).hexdigest()
```

## Verification (FastAPI handler)

```python
async def _verify_honcho(request: Request) -> bytes:
    signature = request.headers.get("X-Honcho-Signature", "")
    if not signature:
        raise HTTPException(401, "Missing X-Honcho-Signature header")

    body = await request.body()
    expected = hmac.new(
        SECRET.encode("utf-8"),
        body,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected, signature):
        raise HTTPException(401, "Invalid signature")

    return body  # raw body bytes for json.loads()
```

## Pitfalls

- **Don't use Bearer auth.** Honcho never sends an `Authorization` header.
- **Read body once.** Call `await request.body()` in the verifier, pass bytes to `json.loads()`. Don't call `request.json()` separately — the body is already consumed.
- **Dashboard "Send Test" may not deliver.** The test emit requires Honcho's deriver process to be running. Real events from active sessions flow fine.

## Registration

Register via the Honcho dashboard at `app.honcho.dev` → Webhooks → Create:
- URL: `https://<your-server>/api/hooks/honcho`
- The "Signing Secret" shown after creation is what goes in `HONCHO_WEBHOOK_SECRET` env var
