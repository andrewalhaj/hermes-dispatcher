# Sensi Thermostat Integration (iprak/sensi)

## Model
- **Emerson Sensi Wi-Fi ST55** — no HomeKit support
- Cloud API only (not local)
- Manager: `manager.sensicomfort.com` (free for basic remote control; paid tier = geofencing + energy reports, neither needed for HA)

## Custom Integration
- **Repository:** `iprak/sensi` (GitHub)
- **Install:** Download into `/config/custom_components/sensi/`
- **Domain:** `sensi`
- **Storage key:** `sensi` (`.storage/sensi`)

## Auth Architecture

The integration uses `storage.Store` — config lives in `.storage/sensi`, NOT in `core.config_entries` data. The config entry only holds the `refresh_token` from the config flow; actual tokens are stored separately.

### OAuth Exchange

```
Endpoint:  POST https://oauth.sensiapi.io/token
Grant:     refresh_token
Client:    fleet
Params:
  client_id     = fleet
  client_secret = JLFjJmketRhj>M9uoDhusYKyi?zUyNqhGB)H2XiwLEF#KcGKrRD2JZsDQ7ufNven
  grant_type    = refresh_token
  refresh_token = <user-provided-jwt>

Response:
  access_token  = <371-char JWT>
  refresh_token = <new-337-char JWT>
  expires_in    = 14400  (4 hours)
  user_id       = 001Ps00001QBZuNIAX  (Salesforce ID — used as unique_id)
```

### Websocket
- **URL:** `https://rt.sensiapi.io` (socket.io, path `/thermostat`, transport `websocket`)
- **Auth header:** `Authorization: bearer <access_token>` (lowercase 'b' intentional)

## Getting the Initial Refresh Token

Not available from the Sensi mobile app. Must use the web manager:

1. Open `manager.sensicomfort.com` in **Chrome on desktop** (not mobile)
2. F12 → Network tab → check "Preserve log"
3. Filter for `token`
4. Log in — the `token?device=FL33T-...` request flashes during login handshake, BEFORE the plan selection page
5. Click it → Response tab → copy `refresh_token`

The token is a JWT with 10-year expiry containing:
```json
{
  "client_id": "fleet",
  "user_id": "alhajandrew91@gmail.com",
  "device": "FL33T-alhajandrew91-9297125439",
  "salesforce_id": "001Ps00001QBZuNIAX",
  "fleet_enabled": false
}
```

## Database Setup (Bypassing Config Flow)

When the HA REST API config flow is unusable (401 on token, 404 on endpoint), write directly to both stores:

### 1. Config entry in `.storage/core.config_entries`

```json
{
  "domain": "sensi",
  "title": "Sensi Thermostat",
  "unique_id": "001Ps00001QBZuNIAX",
  "data": {"refresh_token": "<337-char-jwt>"},
  "source": "user",
  "version": 1,
  "minor_version": 1
}
```

### 2. Token store in `.storage/sensi`

```json
{
  "version": 1,
  "minor_version": 1,
  "key": "sensi",
  "data": {
    "access_token": "<371-char-jwt>",
    "refresh_token": "<337-char-jwt>",
    "expires_at": 1790000000.0,
    "user_id": "001Ps00001QBZuNIAX"
  }
}
```

### Python Script for Token Exchange + Store Write

```python
import json, urllib.request, urllib.parse, time

refresh_token = "<user-jwt>"

data = urllib.parse.urlencode({
    "client_id": "fleet",
    "client_secret": "JLFjJmketRhj>M9uoDhusYKyi?zUyNqhGB)H2XiwLEF#KcGKrRD2JZsDQ7ufNven",
    "grant_type": "refresh_token",
    "refresh_token": refresh_token,
}).encode()

req = urllib.request.Request("https://oauth.sensiapi.io/token", data=data)
req.add_header("Content-Type", "application/x-www-form-urlencoded; charset=utf-8")

with urllib.request.urlopen(req, timeout=15) as resp:
    result = json.loads(resp.read())

store = {
    "version": 1, "minor_version": 1, "key": "sensi",
    "data": {
        "access_token": result["access_token"],
        "refresh_token": result["refresh_token"],
        "expires_at": time.time() + result.get("expires_in", 3600),
        "user_id": result["user_id"],
    }
}

with open("/config/.storage/sensi", "w") as f:
    json.dump(store, f)
```

## Fleet vs Consumer Auth

The integration uses the fleet (`client_id: "fleet"`) OAuth path. The integration has a commented-out consumer path (`client_id: "android"`, `grant_type: "password"`) but it's unused in the current code.

**Potential issue:** If the account has `fleet_enabled: false`, the fleet websocket at `rt.sensiapi.io` may not serve thermostat state events. The socket may connect (authentication succeeds) but never emit `state` events, causing the integration to time out in `wait_for_devices()`.

## Debug Notes

- The integration retries device discovery once, then raises `ConfigEntryNotReady`. HA auto-retries the config entry setup periodically.
- If the socket connects but never receives device data, check: is `fleet_enabled` true on the account? Does the fleet API serve consumer thermostats?
- The access token expires in 4 hours. The integration's `refresh_access_token()` in `auth.py` handles automatic renewal when the websocket reports token expiry.
