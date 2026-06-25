# Honcho Webhook Auth: HMAC-SHA256 Signature Verification

**Source:** Read from `plastic-labs/honcho` `src/webhooks/webhook_delivery.py` (2026-06-24).

## Honcho signs webhook payloads like this:

```python
# Honcho's server-side signing (src/webhooks/webhook_delivery.py)
event_payload = {"type": "...", "data": {...}, "timestamp": "..."}
event_json = json.dumps(event_payload, separators=(",", ":"), sort_keys=True)
signature = hmac.new(
    WEBHOOK_SECRET.encode("utf-8"),
    event_json.encode("utf-8"),
    hashlib.sha256
).hexdigest()

# Sent as: X-Honcho-Signature: <hex-digest>
```

## Key details:

- **Header:** `X-Honcho-Signature` (NOT `Authorization: Bearer`)
- **Algorithm:** HMAC-SHA256
- **Input:** The full JSON body bytes, NOT a concatenation of headers or a canonical form
- **JSON format:** `sort_keys=True`, compact separators `(",", ":")` — but verification just hashes the raw body bytes, so the receiver doesn't need to care about the format
- **Secret:** The "Signing Secret" from the Honcho dashboard webhook page

## Our verification (routes/hooks.py):

```python
async def _verify_honcho(request: Request) -> bytes:
    signature = request.headers.get("X-Honcho-Signature", "")
    if not signature:
        raise HTTPException(401, "Missing X-Honcho-Signature header")
    body = await request.body()
    expected = hmac.new(
        HONCHO_WEBHOOK_SECRET.encode("utf-8"),
        body,
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise HTTPException(401, "Invalid signature")
    return body  # raw bytes for json.loads()
```

## Pitfall: assuming Bearer token

The naive approach (Bearer token comparison) will always fail because Honcho never sends `Authorization: Bearer <secret>`. It sends `X-Honcho-Signature: <hmac-hex>`. The Honcho dashboard shows a "Signing Secret" field, not a "Bearer token" field — that's the signal.

## Testing

Honcho dashboard has a "Send Test" button, but it requires the **deriver** process to be running on Honcho's side (the docs say "webhooks require the deriver process to be running"). The button may silently do nothing if the deriver is down. To test locally, reconstruct Honcho's signing and curl the endpoint:

```python
import hmac, hashlib, json, requests
secret = "<signing-secret>"
payload = {"type": "conclusion", "data": {"content": "test"}, "timestamp": "..."}
body = json.dumps(payload, separators=(",", ":"), sort_keys=True)
sig = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()
requests.post("https://hermes.andrewskingdom.com/api/hooks/honcho",
              data=body, headers={"X-Honcho-Signature": sig, "Content-Type": "application/json"})
```
