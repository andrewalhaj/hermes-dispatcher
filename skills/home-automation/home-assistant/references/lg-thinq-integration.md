# LG ThinQ Integration — PAT auth, region detection, config-flow via REST

Connecting LG smart appliances (washer/dryer combo, AC, fridge, robot vac — 30
device types) to Home Assistant via the official `lg_thinq` integration. It is
cloud-dependent and authenticates with a **Personal Access Token (PAT)**.

## The auth chain
1. User generates a PAT at `https://connect-pat.lgthinq.com` (only the user can —
   it's behind their LG account SSO). Enable ALL scopes (view devices, view
   statuses, control, event subscription, push, energy).
2. HA config flow takes exactly two fields: `access_token` (the PAT) + `country`
   (ISO-2). The flow's `data_schema` confirms this; default country `US`.
3. **PAT region MUST match the country submitted**, or LG rejects with an opaque
   error and HA surfaces only `not_allowed_api_again` on the form.

## THE KEY TECHNIQUE — probe the PAT directly against LG's regional gateways
When HA's config flow returns an opaque `not_allowed_api_again`, do NOT guess
countries one-by-one through the flow (each attempt can leave a stuck in-progress
flow — see pitfall below). Instead hit LG's ThinQ Connect API directly, read-only,
to determine the account's true region AND confirm the PAT is valid + scoped.
A 200 from one gateway names the region; the device list comes back in the same call.

```python
#!/usr/bin/env python3
import urllib.request, json, uuid
PAT = "thinqpat_..."  # the user's token
GATEWAYS = {  # ThinQ Connect regional gateways
    "US": "https://api-aic.lgthinq.com",   # Americas (AIC)
    "EU": "https://api-eic.lgthinq.com",   # Europe (EIC)
    "KIC": "https://api-kic.lgthinq.com",  # Korea/intl (KIC)
}
for name, base in GATEWAYS.items():
    h = {
        "Authorization": "Bearer " + PAT,
        "x-message-id": uuid.uuid4().hex[:22],
        "x-country": {"US": "US", "EU": "SE", "KIC": "KR"}[name],
        "x-client-id": "probe-" + uuid.uuid4().hex[:8],
        "x-api-key": "v6GFvkweNo7DK7yD3ylIZ9w52aKBU0eJ7wLXkSR3",  # public ThinQ Connect key
        "Content-Type": "application/json",
    }
    req = urllib.request.Request(base + "/devices", headers=h, method="GET")
    try:
        r = urllib.request.urlopen(req, timeout=20)
        print(f"[{name}] {r.status}\n   {r.read().decode()[:400]}")
    except urllib.error.HTTPError as e:
        print(f"[{name}] {e.code}\n   {e.read().decode()[:400]}")
```

**Interpreting results:**
- `200` with a `response` array of devices → THAT is the account's region. The
  payload includes `deviceType` (e.g. `DEVICE_WASHER`), `modelName`, and `alias`.
- `401` + `{"code":"1309","message":"Not allowed api call"}` → wrong region for
  this token (same root cause as HA's `not_allowed_api_again`).
- This proves PAT validity + scopes + region in ONE pass, decoupled from HA's
  flow quirks. Run it BEFORE fighting the HA config flow.

Observed mapping this session: a US account → `api-aic` 200, `api-eic`/`api-kic` 401.
So a Swedish-looking UI ≠ Swedish account; verify region empirically, don't infer
from locale.

## Driving the HA config flow over REST (no websocket needed)
- System refresh token (`HA_REFRESH_TOKEN`) is **read-only-ish**: it 401s on
  `POST /api/config/config_entries/flow`. Use the **admin login_flow** path to get
  an access token that can write (see SKILL.md §2 "Admin Login Flow").
- Start flow: `POST /api/config/config_entries/flow {"handler":"lg_thinq"}` → returns
  `flow_id` + `data_schema`.
- Submit: `POST /api/config/config_entries/flow/<flow_id> {"access_token":PAT,"country":"US"}`.
- Response `type`: `create_entry` = success; `form` with `errors` = LG rejected
  (real API response); `abort` with `reason` = HA-side (e.g. `already_in_progress`).

## PITFALL — stuck in-progress flows block retries with `already_in_progress`
Submitting the flow with a wrong country (or abandoning a started flow) leaves an
in-progress flow registered. HA then dedups EVERY new `lg_thinq` flow against it and
aborts new attempts with `abort reason=already_in_progress` BEFORE they reach LG —
so you can't even retry with the correct country.
- `GET /api/config/config_entries/flow` to LIST in-progress flows is **405** over
  REST — HA only exposes flow listing/abort via the **websocket API**
  (`config_entries/flow/progress`). Per-flow `DELETE /…/flow/<id>` works but you need
  the id, and ids from a crashed script may be lost.
- If no websocket client lib is available and `pip install` is undesirable, the clean
  reset is **`docker restart homeassistant`** — it flushes all in-progress flows.
  Gate it (it's a container restart): ~30–60s HA downtime, non-destructive, existing
  integrations reload. After restart, re-run the flow ONCE with the correct country.

## Regional bug to flag to the user
EU (EIC) accounts have a documented unresolved bug: token may generate but HA rejects
with `token_unauthorized` (EIC/KIC token differences, HA core issue #130041). US (AIC)
works cleanly. If the probe shows the account is EU, set expectations before proceeding.

## PAT portal login failures (all methods fail: QR + email + phone)
Most common root cause: the LG account was created via **Google/Apple SSO**, so no
email/password ever existed — and the PAT portal has NO SSO button. Fix in the phone
app: ThinQ → Menu → My Page → Edit Profile → create an email+password for the account,
then log in at the portal manually (autofill/Bitwarden causes 406; type by hand).
Secondary fixes: register as LG developer first (`developer.lge.com/main/Intro.dev`,
accept TOS, keep tab open), and select the correct country (defaults to Korea).
