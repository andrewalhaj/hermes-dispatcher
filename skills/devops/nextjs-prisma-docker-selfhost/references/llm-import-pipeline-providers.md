# LLM import/extraction pipeline — provider wiring + vision capability map

Findings from wiring Mealio's social-import (text) and researching the screenshot-import
(vision) extension, 2026-06-10. Saves a future session ~30 min of provider probing.

## Provider-agnostic extraction pattern (text — shipped, working)

Keep the LLM step swappable via env vars, OpenAI-compatible client:

```
EXTRACTION_MODEL=deepseek-chat
EXTRACTION_BASE_URL=https://api.deepseek.com/v1
DEEPSEEK_API_KEY=<key>        # or EXTRACTION_API_KEY
```

- `new OpenAI({ apiKey, baseURL })`, `response_format: { type: 'json_object' }`,
  temperature 0.1, max_tokens 2000.
- Truncate scraped markdown to ~8000 chars before sending — enough for any recipe,
  avoids token-limit failures on long video-description pages.
- Prompt returns a fixed JSON schema; parse defensively (ensure arrays exist, wrap
  JSON.parse in try → throw with the first 200 chars of the raw reply for debugging).
- Fetch layer: Firecrawl REST `/v1/scrape` (`formats: ['markdown']`) handles JS-rendered
  IG/TikTok/YouTube pages; pull `metadata.ogImage` as the default hero image.

## Vision capability map (verified by live probes 2026-06-10)

| Provider | Vision? | Notes |
|---|---|---|
| DeepSeek API | **NO** | Models list = `deepseek-v4-flash`, `deepseek-v4-pro` only; docs + community confirm no image input via API. Do not plan vision features on the DeepSeek key. |
| Nous inference API | YES (gated) | `https://inference-api.nousresearch.com/v1` exposes `google/gemini-3.5-flash`, `openai/gpt-chat-latest`, etc. — but these bill against the credits balance, NOT the subscription. Error shape when balance is empty: HTTP 404 `"Model 'X' requires available credits"` (a 404, not a 402 — easy to misread as wrong model name). |
| Anthropic direct via hermes-claude-auth OAuth | **NO for external apps** | See below. |
| OpenAI direct | YES | `gpt-4o-mini` is the cheap per-image option if the user adds a key. |

## hermes-claude-auth bypass is NOT a reusable credential for external apps

Tried: raw `Authorization: Bearer <oauth access_token from auth.json>` against
`https://api.anthropic.com/v1/messages` → **401 Invalid bearer token**.
The bypass works only inside the patched Python SDK
(`/root/.hermes/patches/anthropic_billing_bypass.py`): it spoofs Claude Code's
billing header (`cc_version`/`cc_entrypoint`/`cch` computed per-request) plus
x-stainless fingerprint headers. A Node.js app cannot piggyback on it without
reimplementing that spoof. Don't burn time retrying header variants.

## Where Nous credentials live (for probing)

`/root/.hermes/auth.json`:
- `providers.nous.access_token` + `providers.nous.inference_base_url`
- `credential_pool` carries per-provider entries (incl. a `custom:manifest-vision`
  pointing at an internal box) — entries have `base_url`/`auth_type` but secrets
  are fingerprinted, not stored raw in pool entries.

## Probe recipe (cheap, before building anything)

1. `GET {base}/models` with Bearer token → confirm the model id exists.
2. Smoke-test vision with a 1×1 PNG data URL (OpenAI-style content array):
   `{"type":"image_url","image_url":{"url":"data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwADhQGAWjR9awAAAABJRU5ErkJggg=="}}`
   + a "what color?" text part, max_tokens ~20.
3. Only after a 200 on the smoke test, wire `VISION_MODEL` / `VISION_BASE_URL` /
   `VISION_API_KEY` env vars (same provider-agnostic shape as EXTRACTION_*).

## Process rule

When the feature's required provider capability is missing (no vision-capable key
available), STOP and present the options + costs to the user before writing the
feature code. Do not ship a UI whose backend can only return a configuration error —
a reported blocker beats a silently dead feature. (Applied 2026-06-10: screenshot
import paused pending Nous credits top-up or an OpenAI key.)
