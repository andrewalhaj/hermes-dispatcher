---
name: home-assistant
description: "Home Assistant: deploy, configure, operate smart home."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [home-assistant, smart-home, docker, tailscale, android-tv]
    created_by: agent
load_when:
  - "user asks about Home Assistant setup, deployment, or configuration"
  - "user wants to control smart home devices through Hermes"
  - "user asks about Android TV, Nvidia Shield, or media device integration"
  - "user mentions HA, HASS, or home-assistant in context of automation"
  - "user asks about connecting Hermes to a smart home platform"
---

# Home Assistant Integration

Home Assistant (HA) as a smart home backend for Hermes — deployed on a cloud VPS, bridged to LAN devices via Tailscale, controlled through the REST API.

## 1. Deployment

### Docker on Cloud VPS

HA needs to reach LAN devices (Shield, TV, lights). For cloud VPS deployments, use Tailscale to bridge networks. HA MUST use `--network host` — bridge networking blocks LAN discovery and Tailscale device access.

```bash
# On the VPS (178.156.246.115):
docker run -d \
  --name homeassistant \
  --restart unless-stopped \
  --network host \
  -v /root/homeassistant/config:/config \
  -e TZ=UTC \
  homeassistant/home-assistant:stable
```

Config lives at `/root/homeassistant/config/`. Key files:
- `configuration.yaml` — integrations config
- `.storage/core.config_entries` — UI-added integrations (JSON)
- `.storage/auth` — user credentials and refresh tokens
- `home-assistant.log` — live log

### Tailscale for LAN Access

Install Tailscale on both the VPS and the target device (e.g., Nvidia Shield via Play Store):

```bash
# VPS:
curl -fsSL https://tailscale.com/install.sh | sh
tailscale up   # prints auth URL — open in browser

# Verify both devices appear:
tailscale status
# Expected: 100.x.x.x  shield  alhajandrew91@  android
#          100.x.x.x  hostname  user@  linux
```

**Pitfall:** Devices showing in `tailscale status` does NOT guarantee connectivity. Verify with `ping -c 3 <tailscale-ip>` from the VPS. 100% packet loss means the device's Tailscale client isn't routing traffic — reopen the Tailscale app on the device, verify it shows "Connected."

## 2. Auth & Token Management

### Onboarding Flow (API-first, no browser needed)

HA exposes an onboarding API at `/api/onboarding` with four steps: user, core_config, analytics, integration.

**Create admin user (user step):**
```bash
curl -s -X POST http://localhost:8123/api/onboarding/users \
  -H "Content-Type: application/json" \
  -d '{"name":"Admin","username":"admin","password":"...","language":"en","client_id":"http://localhost:8123/"}'
# Returns: {"auth_code":"..."}
```

**Exchange auth_code for token:**
```bash
curl -s -X POST http://localhost:8123/auth/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=authorization_code&code=AUTH_CODE&client_id=http://localhost:8123/"
# Returns: {"access_token":"...","refresh_token":"...","expires_in":1800}
```

**Complete remaining onboarding:**
```bash
TOKEN=***
curl -s -X POST http://localhost:8123/api/onboarding/core_config \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"country":"US","currency":"USD","timezone":"UTC","unit_system":"metric","location_name":"Home","language":"en","elevation":0,"latitude":0,"longitude":0}'
```

**Pitfall:** `login_flow` returns `create_entry` with a `result` field that is NOT a usable bearer token — it's a transient authorization code that expires quickly and can't be exchanged at `/auth/token`. The `/api/onboarding/users` endpoint gives a proper `auth_code` that CAN be exchanged. Always use the onboarding flow for initial auth, not `login_flow`.

### System Refresh Token (preferred for Hermes)

After onboarding, HA creates a system refresh token (`token_type: "system"`) that never expires. This is the best token for Hermes — it survives reboots and has no expiry.

**Location:** `/root/homeassistant/config/.storage/auth` → `data.refresh_tokens[]` → find the token with `token_type: "system"`.

**Using it:**
```python
import urllib.request, urllib.parse, json

BASE = "http://HOME_ASSISTANT_IP:8123"
SYS_RT = "d6423063e4..."  # 128-char system refresh token

# Exchange for access token (valid 30 min)
form = urllib.parse.urlencode({"grant_type": "refresh_token", "refresh_token": SYS_RT}).encode()
req = urllib.request.Request(BASE + "/auth/token", data=form,
    headers={"Content-Type": "application/x-www-form-urlencoded"})
access = json.loads(urllib.request.urlopen(req).read())["access_token"]

# Use access token for API calls
h = {"Authorization": "Bearer " + access, "Content-Type": "application/json"}
```

**Save in Hermes config:**
```bash
# In ~/.hermes/.env:
HA_REFRESH_TOKEN=***
HA_BASE_URL=http://178.156.246.115:8123
```

### Admin Login Flow (for config management and API tokens)

The admin login flow IS exchangeable at `/auth/token` — the `result` code works with `grant_type=authorization_code`. The earlier "transient code" pitfall was based on a failed attempt caused by wrong password hash format, NOT an API limitation. This flow is the primary way to obtain access tokens programmatically:

```python
import requests
BASE = "http://HOME_ASSISTANT_IP:8123"

# Step 1: get login flow
r = requests.post(f"{BASE}/auth/login_flow", json={
    "client_id": f"{BASE}/",
    "redirect_uri": f"{BASE}/",
    "handler": ["homeassistant", None]
})
flow_id = r.json()["flow_id"]

# Step 2: submit credentials (one step for username+password, not two separate)
r = requests.post(f"{BASE}/auth/login_flow/{flow_id}", json={
    "client_id": f"{BASE}/",
    "username": "hermes_admin",
    "password": "@May161998"
})
code = r.json()["result"]  # THIS is exchangeable

# Step 3: exchange for access token (works fine)
r = requests.post(f"{BASE}/auth/token", data={
    "grant_type": "authorization_code",
    "code": code,
    "client_id": f"{BASE}/"
})
access_token = r.json()["access_token"]  # 183-char JWT, 30-min expiry
```

## 3. Config Entry Management (Direct Storage Write)

When the REST API config flow is unavailable (system tokens lack permission, admin login flow results are transient), write config entries directly to `.storage/core.config_entries`.

### Required Fields for Every Config Entry

```json
{
  "entry_id": "<uuid>",
  "version": 1,
  "minor_version": 1,
  "domain": "androidtv",
  "title": "Nvidia Shield",
  "data": { ... },
  "options": {},
  "pref_disable_new_entities": false,
  "pref_disable_polling": false,
  "source": "user",
  "unique_id": "<unique-string>",
  "disabled_by": null,
  "discovery_keys": {},
  "created_at": "<ISO-8601>",
  "modified_at": "<ISO-8601>",
  "subentries": []
}
```

### Android TV / Shield Config Entry

**Critical networking nuance:** The VPS HOST can reach `10.0.0.45` when Tailscale subnet routing is active. But HA runs inside a Docker container (`--network host`), and Docker's network stack does NOT propagate Tailscale subnet routes into containers. From inside the container, `100.69.145.58` (Tailscale IP) is reachable but `10.0.0.45` (local IP) is NOT.

→ **Use the Tailscale IP in the HA config entry** (`100.69.145.58`), not the local IP. The VPS host can use either; the container can only use the Tailscale IP.

**Verify container connectivity before adding the entry:**
```bash
docker exec homeassistant bash -c 'timeout 3 bash -c "echo >/dev/tcp/100.69.145.58/5555" 2>&1 && echo PORT_OPEN || echo PORT_CLOSED'
```

```json
{
  "domain": "androidtv",
  "title": "Nvidia Shield",
  "data": {
    "host": "100.69.145.58",
    "port": 5555,
    "adbkey": "/config/.storage/adbkey",
    "device_class": "androidtv",
    "get_sources": true,
    "apps": {},
    "state_detection_rules": {}
  }
}
```

### Schema Discovery

When a field is missing, HA crashes with a `KeyError` naming the exact missing key. Add it and restart. Common missing keys (in order of discovery):
1. `created_at` / `modified_at` — ISO-8601 timestamps
2. `discovery_keys` — empty object `{}`
3. `subentries` — empty array `[]`
4. Domain-specific fields in `data` (e.g., `device_class` for androidtv)

### VeSync (Levoit Air Purifiers)

VeSync does NOT support YAML setup — config entry must be injected directly into `.storage/core.config_entries`. After restart, HA authenticates to VeSync, discovers all devices (air purifiers, smart plugs, fans), and creates entities automatically. Per-device entities: `fan.<name>`, `sensor.<name>_pm2_5`, `sensor.<name>_air_quality`, `sensor.<name>_filter_lifetime`, `switch.<name>_display`, `switch.<name>_child_lock`, `update.<name>_firmware`. Full schema and dashboard card patterns: `references/vesync-integration.md`.

### Verifying

After writing, restart HA and check logs:
```bash
docker logs homeassistant --tail 30 | grep -i "error\|android\|setup"
```

No errors = entry loaded. Verify entities:
```python
r = urllib.request.Request(BASE + "/api/states", headers=h)
states = json.loads(urllib.request.urlopen(r).read())
media = [s for s in states if s["entity_id"].startswith("media_player")]
```

## 4. Network Verification

Before adding integrations, verify the VPS can reach the target device:

```bash
# General connectivity
ping -c 3 -W 2 <device-tailscale-ip>

# Port-specific check
timeout 5 bash -c "echo > /dev/tcp/<ip>/5555" 2>&1 && echo "open" || echo "closed"
```

**Android TV caveat:** `ping`/`nc` to the Tailscale IP (`100.x.x.x`) will likely fail even when Tailscale shows `active; direct` — ADB binds to the local interface only. After enabling Tailscale subnet routing (Section 5), test the **local** IP:
```bash
ping -c 3 -W 2 10.0.0.45     # Should work with subnet routing
adb connect 10.0.0.45:5555   # Connect via local IP
```

## 5. Tailscale Subnet Routing (for ADB on Android TV)

**Sonos / other non-Tailscale LAN devices:** Sealed appliances (Sonos speakers) cannot run Tailscale, so cloud HA must ROUTE into the home LAN via an always-on subnet router. Android (Shield/phone) CANNOT advertise routes — use a Linux/Win/Mac box. Full procedure (Windows subnet router, route approval, container-side bridge verification, explicit-IP Sonos config — SSDP multicast does not cross Tailscale) in `references/sonos-cloud-ha-subnet-router.md`.

**The problem:** On Android TV / Nvidia Shield, ADB network debugging binds to the device's **local** IP (e.g., `10.0.0.45`) — NOT the Tailscale interface (`100.x.x.x`). The VPS cannot reach `10.0.0.45` directly even with both devices on the same Tailnet. ADB connect to `100.x.x.x:5555` times out despite Tailscale showing `active; direct`.

**Symptoms:** `tailscale status` shows device active, but `ping` and `nc` to the Tailscale IP fail. `adb connect 100.x.x.x:5555` times out. The Shield's Developer Options shows `10.0.0.45:5555` (local IP only).

**Solution: Tailscale subnet routing.** Make the Shield advertise its local subnet so the VPS can route to `10.0.0.45` through Tailscale.

**On the Shield:**
1. Open Tailscale app → tap avatar → **Settings** or **Exit Node**
2. Find **"Subnet routes"** or **"Run exit node"** — toggle ON
3. It should advertise `10.0.0.0/24` (or whatever the local subnet is)

**On the Tailscale admin console (login.tailscale.com):**
1. Find the Shield device → **Edit route settings**
2. **Approve** the `10.0.0.0/24` route

**Then from VPS:**
```bash
ping 10.0.0.45                        # Should work now
adb connect 10.0.0.45:5555           # Connect via local IP
```

The HA config entry should use the **local** IP (`10.0.0.45`), not the Tailscale IP, when subnet routing is active.

## 5b. Subnet Router for Non-Tailscale Appliances (Sonos, Hue, most IoT)

**When the target device CANNOT run Tailscale** (sealed appliances: Sonos speakers, Philips Hue bridges, smart plugs, printers, most IoT), the Android-TV approach in Section 5 does NOT apply. Cloud-hosted HA reaches these ONLY through a **subnet router** — an always-on device on the home LAN running Tailscale and advertising the home subnet.

**Hard limitation — Android Tailscale clients CANNOT advertise subnet routes.** The Android client (Shield, phone) has no `--advertise-routes` capability; it can connect and use an exit node but cannot relay traffic to *other* LAN devices. In `tailscale status --json`, Android peers always show `PrimaryRoutes: None` even when active. **Do not propose the Shield/phone as the subnet router** — it physically cannot do it. Only Linux/macOS/Windows clients can advertise routes.

### Diagnosis (read-only, from VPS)
```bash
# Is ANY peer advertising the home subnet?
tailscale status --json | python3 -c "import sys,json; d=json.load(sys.stdin); [print(p.get('HostName'),'Routes:',p.get('PrimaryRoutes'),'AllowedIPs:',p.get('AllowedIPs')) for p in d.get('Peer',{}).values()]"
# Routes: None on every peer = NO subnet router exists yet. This is the gate.

# Can the VPS reach the home LAN at all?
ping -c3 -W2 10.0.0.45   # 100% loss = no route into the LAN
```
`PrimaryRoutes: None` everywhere + 100% ping loss to a LAN IP = **the bridge does not exist**. Nothing in HA can be configured until a desktop-OS subnet router is up and its route approved.

### Setup: subnet router on an always-on home machine

**Linux/macOS (preferred — SSH-able afterward over the tailnet):**
```bash
curl -fsSL https://tailscale.com/install.sh | sh   # Linux
sudo sysctl -w net.ipv4.ip_forward=1               # Linux: enable forwarding
sudo tailscale up --advertise-routes=10.0.0.0/24
```

**Windows (PowerShell as Administrator — needs a registry change to route):**
```powershell
Set-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Services\Tcpip\Parameters" -Name "IPEnableRouter" -Value 1
& "C:\Program Files\Tailscale\tailscale.exe" up --advertise-routes=10.0.0.0/24 --unattended
```
`--unattended` keeps it routing when no user is logged in. **Windows is the hard case**: no clean SSH path in, so the agent cannot drive it — hand the user copy-paste commands and verify from the VPS side. Connecting to the tailnet ≠ advertising a route; the route is a separate `tailscale up --advertise-routes` step.

### Approve the route, then verify
1. login.tailscale.com → the router device → **Edit route settings** → approve `10.0.0.0/24`.
2. From VPS: `ping -c3 10.0.0.<sonos-ip>` should now succeed.
3. **From inside the container** (Docker does NOT inherit Tailscale routes — see Section 7): subnet routing into the container works differently than Android-TV direct IPs. Verify: `docker exec homeassistant sh -c 'timeout 3 sh -c "echo > /dev/tcp/10.0.0.<ip>/1400" && echo OPEN || echo CLOSED'`. Use `sh`, not `bash` (the HA container image has no bash; `/dev/tcp` works under its `sh`).

### Add Sonos by explicit IP (NOT auto-discovery)
SSDP/multicast discovery does NOT cross Tailscale — only unicast. Configure each speaker by IP:
```yaml
# configuration.yaml
sonos:
  media_player:
    hosts:
      - 10.0.0.x
      - 10.0.0.y
```
Get IPs from the Sonos app → **Settings → System → About My System** (lists each speaker's LAN IP). Restart HA, confirm `media_player.*` entities appear. Sonos control port is **1400**.

### THE REAL GATE: Sonos needs a BIDIRECTIONAL route (return path), not just outbound
**Reaching the speakers (HA→Sonos:1400 OPEN) is necessary but NOT sufficient.** Sonos uses UPnP eventing: HA sends a SUBSCRIBE telling the speaker "push state updates back to me at my IP," and the speaker must then **call back into HA**. On a one-way subnet route (VPS→LAN works, LAN→tailnet does not), the callback dies and the speaker rejects the subscription. The integration then **fails to set up entirely** — zero entities created. Symptom in `docker logs`:
```
Error setting up entry Sonos for sonos
  ... async_subscribe_to_zone_updates
  aiohttp ... ClientResponseError: 412, message='Precondition Failed',
  url='http://10.0.0.40:1400/ZoneGroupTopology/Event'
```
A **412 on /ZoneGroupTopology/Event** = the return path is missing. The Sonos speaker's default gateway is the home router, which has **no route to the tailnet (`100.64.0.0/10`)**, so its callback to cloud HA never arrives.

**This applies to any LAN device that PUSHES state to HA** (Sonos, anything UPnP/event-driven, webhook-style integrations) — not just command-only devices like ADB/Shield. Command-only devices work on a one-way route; event-driven devices do not.

**Fix — make the route bidirectional (Tailscale site-to-site):** add a **static route on the home router**: `100.64.0.0/10 → <subnet-router's LAN IP>`. This teaches the LAN "to reach the tailnet, go through the subnet-router machine." Combined with IP forwarding already enabled on that machine (`net.ipv4.ip_forward=1` / Windows `IPEnableRouter`), the speaker's callbacks reach cloud HA.
- *Needs:* admin access to the home router + ability to add a static route, and the subnet-router machine's **LAN IP**.
- *Catch:* many consumer routers don't expose static routes. If so, the clean fix is **running HA on the home LAN itself** (no asymmetry — discovery and eventing just work). Surface this as the architecturally-correct option early when the device is event-driven.

**Always check `docker logs homeassistant --since 3m | grep -i sonos` after the restart** — a clean port-1400 probe will lull you into thinking it worked. Only the log + presence of `media_player.*` entities confirm setup.

### Port-binding mismatch: advertise_addr vs. HA's UPnP listen interface

Even with a bidirectional route, Sonos can 412 if the `advertise_addr` in `configuration.yaml` doesn't match the network interface HA's UPnP subsystem binds to. On cloud deployments where HA runs with `--network host` and Tailscale, the UPnP callback port (1400) is typically bound to the **Tailscale IP** only (e.g., `100.119.118.54:1400`), NOT the public IP. If `advertise_addr` is set to the public IP (`178.156.246.115`), the speaker receives a callback URL it can route to but HA isn't listening there — the SUBSCRIBE still gets 412.

**Verify with:**
```bash
ss -tlnp | grep 1400
# Expected: 100.119.118.54:1400 (Tailscale IP only — NOT 0.0.0.0, NOT the public IP)
```

**Fix:** set `advertise_addr` to the Tailscale IP (what `ss` shows), then the speaker must be able to reach that IP. Combined with a static route on the home router (`100.64.0.0/10 → subnet-router-LAN-IP`), the speaker can route to the Tailscale IP through the subnet router. Without the static route, the speaker can route to a public IP but not the Tailscale IP — and the public IP isn't listening on 1400. Both the route AND the correct `advertise_addr` must be in place; either alone still 412s.

### Caveats
- **A laptop works to validate but is a poor permanent router** — if it sleeps, closes the lid, or leaves the home network, the bridge dies and every appliance behind it drops out of HA. For permanence, recommend a Pi / mini-PC / NAS / Tailscale-capable router (GL.iNet, OPNsense, some Ubiquiti/OpenWrt).
- **Confirm the actual home subnet before advertising.** Don't assume `10.0.0.0/24` — derive it from a known LAN IP (e.g. Shield at `10.0.0.45`) or ask. Wrong CIDR = no route.
- **Rollback is clean and non-destructive:** `tailscale down` on the router (or un-approve the route) removes the bridge; delete the `sonos:` block + restart HA removes the integration. No data touched.

Full Sonos / subnet-router session detail: `references/sonos-subnet-router.md`.

## 5c. LG ThinQ Appliances (PAT auth + region detection)

LG smart appliances (washer/dryer combo, AC, fridge, robot vac — 30 device types)
connect via the official `lg_thinq` integration using a **Personal Access Token**.
The #1 setup trap is **region mismatch**: the PAT's home region must match the
`country` submitted, or HA fails with an opaque `not_allowed_api_again` and you're
left guessing countries. **Don't guess through the HA flow** — probe LG's regional
gateways directly (read-only) to determine the account's region AND validate the PAT
in one call: a 200 names the region and returns the device list (`deviceType`,
`modelName`, `alias`); a 401 `code:1309` = wrong region for that token. A
Swedish/non-English UI does NOT imply a non-US account — verify empirically.
Drive the config flow over REST with an **admin** token (system refresh token 401s on
config-entry writes). Full probe script, gateway URLs, REST flow recipe, the
`already_in_progress` stuck-flow trap, the EU `token_unauthorized` bug, and PAT-portal
login fixes (SSO accounts, autofill 406): `references/lg-thinq-integration.md`.

## 6. Custom Integration Storage Patterns

Some custom integrations do NOT read config from `entry.data` — they use `storage.Store` with a domain-specific key and a separate `.storage/<domain>` file. This is common for integrations that handle OAuth tokens (Sensi, Nest, etc.).

### Identifying Storage Store Integrations

Look at the integration's `__init__.py` → `async_setup_entry`. If it calls something like `get_stored_config(hass)` instead of reading `entry.data`, it uses a separate store.

Check `const.py` for `STORAGE_KEY` and `STORAGE_VERSION` to find the store file path: `.storage/{STORAGE_KEY}`.

### Storage.Store File Format

HA's `storage.Store` expects a wrapper format, NOT a flat JSON object:

```json
{
  "version": 1,
  "minor_version": 1,
  "key": "sensi",
  "data": {
    "access_token": "...",
    "refresh_token": "...",
    "expires_at": 1790000000.0,
    "user_id": "001Ps00001QBZuNIAX"
  }
}
```

**Critical:** Writing flat JSON directly to `.storage/<domain>` causes `KeyError: 'version'` on load. Always wrap in the storage envelope.

### Token Exchange for Cloud API Integrations

When bypassing a config flow (direct `.storage` write), you may need to exchange tokens via the external API BEFORE writing to the store. The integration's `auth.py` or `config_flow.py` reveals the auth flow:

1. Read the integration's `auth.py` for OAuth endpoints, client secrets, grant types
2. Call the external OAuth endpoint to exchange `refresh_token` → `access_token`
3. Write both tokens (plus `expires_at` and `user_id`) into the store's `data` field

For the Sensi (`iprak/sensi`) integration, a pre-built token exchange script is available at `scripts/sensi_token_exchange.py`. Full setup details in `references/sensi-integration.md`.

### Config Entry unique_id Must Match Integration

The `unique_id` in `core.config_entries` must match what the integration uses internally. For OAuth-based integrations, this is typically the API's `user_id` from the token response (e.g., `001Ps00001QBZuNIAX`), NOT the user's email address (`alhajandrew91@gmail.com`). Check `config_flow.py` → `async_set_unique_id(result.config.user_id)` to see what value it expects.

### Store Format Debug Workflow

If the integration crashes with `KeyError: 'version'` or `missing refresh_token`:
1. Check `const.py` for `STORAGE_KEY` and `STORAGE_VERSION`
2. Read the integration's `auth.py` → `get_stored_config()` to see what keys it reads
3. Write the store file with the HA storage envelope `{version, minor_version, key, data}`
4. Verify token exchange works by calling the OAuth endpoint from inside the container first

## 6b. Dashboards (Lovelace) — prefer built-in cards

**Default to HA's built-in cards (`tile`, `thermostat`, `heading`, `entities`). Use custom cards (Mushroom, Bubble Card, slider-button) ONLY when the user explicitly asks for that look AND accepts the fragility.** Custom cards are JS modules loaded as Lovelace resources — when a module fails to register in the frontend, every card built on it renders as NOTHING. A storage-mode view full of `custom:bubble-card` / `custom:mushroom-*` then shows up as an EMPTY dashboard ("New section", blank), with no error. The server-side config is perfectly valid; the failure is purely client-side module registration. This burns multiple debugging rounds because every server-side check (config valid, bundles serve HTTP 200, resources registered) passes while the user still sees nothing.

**The robust rebuild — built-in cards, zero custom JS:**
- Dimmable light with a drag-to-dim slider: `tile` card + `light-brightness` feature (NO custom card needed):
  ```json
  {"type":"tile","entity":"light.living_room_lamp","name":"Living Room Lamp",
   "features_position":"bottom","features":[{"type":"light-brightness"}]}
  ```
- Thermostat: built-in `{"type":"thermostat","entity":"climate.sensi_thermostat"}`
- Section headers: `{"type":"heading","heading":"Lights","heading_style":"title","icon":"mdi:lightbulb-group"}`
- Switches/fans/groups: plain `{"type":"tile","entity":"switch.office_fan","icon":"mdi:fan"}`

Storage-mode dashboards use the **sections layout**: `view.type="sections"`, each section `{"type":"grid","cards":[...]}`. Cards live under `section.cards`, not `view.cards`. A quick audit for hidden custom-card dependency:
```bash
docker exec homeassistant python3 -c "
import json; d=json.load(open('/config/.storage/lovelace.<url_path>'))
t=set(c.get('type') for v in d['data']['config']['views'] for s in v.get('sections',[]) for c in s.get('cards',[]))
print('custom:', [x for x in t if str(x).startswith('custom:')] or 'NONE')"
```
A `scripts/ha_dashboard_builtin.py` generator (lights→tile+slider, thermostat, headings) is at this skill's scripts dir — copy and adapt the entity lists, scp into the container, run, restart HA.

### Navigation: custom dashboards get a non-default url_path
HA reserves the `home`/`lovelace` url_path for its auto-generated **Overview**. A custom storage-mode dashboard MUST use a different `url_path` (e.g. `andrew-home`, storage key `lovelace.andrew-home`, registered in `.storage/lovelace_dashboards`). Consequence: the user keeps landing on the stock **Overview** and thinks "nothing changed" — they're opening the wrong sidebar entry. **Fix it at the root: set the custom dashboard as the default landing panel** so HA opens straight into it, instead of telling the user to click the right entry (taps on the sidebar entry often don't stick / bounce back). Write a per-user data file (no existing file → create cleanly):
```bash
# user id from .storage/auth -> data.users[].id (the human, not "Home Assistant Content")
cat > /config/.storage/frontend.user_data_<USER_ID> <<'EOF'
{"version":1,"minor_version":1,"key":"frontend.user_data_<USER_ID>",
 "data":{"core.default_panel":"andrew-home"}}
EOF
```
Restart HA (it reads `.storage` at boot). Then the user just reopens — lands on the custom dashboard. **Companion app caches dashboards hard**: when diagnosing "empty/unchanged," test in a plain browser first to rule cache out before chasing a render bug — but note an empty result in a fresh browser means a real render failure (the custom-card problem above), not cache.

### THE #1 EMPTY-DASHBOARD CAUSE: storage-key mismatch (config_not_found)
**HA keys a storage-mode dashboard's config file off its `id` field in `.storage/lovelace_dashboards`, NOT its `url_path`.** If the registration has `id: andrewhome` but you write the config to `lovelace.andrew-home` (matching the url_path, with a dash), HA looks for `lovelace.andrewhome`, finds nothing, and serves an EMPTY auto-generated view ("New section"). The symptom is **byte-identical to the custom-card failure** — but here even built-in `tile` cards render empty, which is the tell: built-in cards CANNOT fail to load, so if they're empty too, HA isn't reading your config file at all.

**Confirm authoritatively via the frontend websocket** (don't trust screenshots or that the file exists on disk). With a valid token in `localStorage.hassTokens`, ask HA directly:
```js
// in browser console, after auth:
ws = new WebSocket('ws://HOST:8123/api/websocket');
// auth_required -> send {type:'auth',access_token}; auth_ok -> send {id:1,type:'lovelace/config',url_path:'andrew-home'}
// result.success=false with error.code 'config_not_found' => HA is NOT reading your file. Storage-key mismatch.
```
A `config_not_found` reply = the file is at the wrong key. **Fix:** copy the config to the `id`-based filename and set its inner `key` field to match:
```bash
# id from .storage/lovelace_dashboards -> data.items[].id  (e.g. 'andrewhome', no dash)
docker exec homeassistant python3 -c "import json; d=json.load(open('/config/.storage/lovelace.andrew-home')); d['key']='lovelace.andrewhome'; json.dump(d, open('/config/.storage/lovelace.andrewhome','w'), indent=2)"
docker restart homeassistant
```
**Prevention:** when creating the dashboard config file, derive the filename from the registration `id`, not the `url_path`. Read `.storage/lovelace_dashboards` FIRST and match `data.items[].id`.

### Self-verify the render — don't rely on the user's screenshots
After several rounds of "still empty," stop trusting screenshots and SEE IT YOURSELF: SSH-tunnel HA to localhost (`ssh -fNL 8123:localhost:8123 root@VPS`), then drive a headless browser. Bypass the login wall by injecting the long-lived token into `localStorage`: serve a small `hass_tokens.json` (`{access_token, token_type:'Bearer', expires:9999999999000, hassUrl, clientId}`) from a local HTTP port and `fetch().then(d=>localStorage.setItem('hassTokens', JSON.stringify(d)))` in the page console, then reload. Screenshot to confirm cards actually render — and to catch the `/lovelace/home` (Overview) vs `/andrew-home` (custom) URL mix-up that wastes rounds.

Full session detail (the custom-card→empty failure, the built-in-card rebuild, the default-panel fix): `references/builtin-card-dashboard.md`.

## 6c. Govee Scenes via OpenAPI (dynamic_scene capability)

The custom `/usr/local/bin/govee.py` rig talks to the official Govee OpenAPI (`openapi.api.govee.com/router/api/v1`). Beyond on/off/brightness/RGB/temp, every individual light (not BaseGroups) exposes `dynamic_scene` capabilities: `lightScene` (built-in scenes — Sunrise, Aurora, Forest…) and `diyScene` (user's app DIY scenes).

**Scene value format:** the control endpoint takes the scene's value dict verbatim, e.g. `{"paramId":110,"id":128}`. Fetch per-device scene lists from `POST /device/scenes` (lightScene) and `POST /device/diy-scenes` (diyScene) — `payload.capabilities[].parameters.options[]` gives `{name, value}`. Resolve name→value, cache on disk (`/config/govee_scenes_cache.json`), then `POST /device/control` with `capability.type=devices.capabilities.dynamic_scene`, `instance=lightScene|diyScene`, `value=<the dict>`. Success = `code:200, state.status:success`.

**Dashboard wiring (ha-fusion):** one `input_select.govee_scene_<slug>` per light holding the full scene-name list, + an automation per light (trigger on input_select state change, condition excludes the placeholder option, action = `shell_command.govee_<slug>_scene` passing `{{ trigger.to_state.state }}`). ha-fusion `button` bound to the input_select opens a native modal option-picker.

**Pitfalls:**
- **The official Govee OpenAPI returns NO scene artwork — only {name, paramId, id}.** The colorful per-scene preview thumbnails seen in the Govee phone app come from Govee's separate undocumented APP API (app2.govee.com/appsku/v1/light-effect-libraries?sku=SKU). **Important correction:** that scene-library endpoint is **AUTH-FREE** (only AppVersion + User-Agent headers, no login/token) and the icon PNGs live on a **public CloudFront CDN** — so real Govee scene art IS reliably obtainable without the user's Govee credentials. Each scene returns iconUrls: [normal, pressed, dark]; prefer the _dark variant for dark UIs. See govee-control skill's references/scene-artwork-api.md + runnable scripts/fetch_scene_art.py (auth-free fetcher, ~96% scene coverage across SKUs). It's still undocumented/fragile (Govee can gate it; a 401/403 is the canary) and ToS-gray, so use it for the *visual* layer only, never as the control mechanism (control stays on the official paramId/id path). When a user asks for "scene art," you no longer need to talk them out of real thumbnails — pull them with the fetcher. Fallback if the endpoint ever gates: (A) color-tinted scene buttons via ha-fusion's per-button color: field, or (B) self-generated abstract tiles. "Andrew's Office Fan" must be escaped '' inside YAML single quotes, else check_config fails with "expected <block end>" at that line.
- **`!include`d input_select file must NOT repeat the `input_select:` top-level key** — configuration.yaml already nests it under `input_select: !include`. Include the bare mapping (dedented), or HA errors "required key 'options' not provided" and sets up 0 entities.
- **System refresh token gets 401 on service calls AND `/api/template`/`/api/onboarding` service POSTs.** Use the admin login_flow → authorization_code → `/auth/token` path for any service invocation; system token is read-only-ish (states/history fine).
- **Govee scene counts vary per SKU** (H6604 TV strip = 237, H6006 bathroom bulbs = 56). Generate lists live per device; don't assume a shared set.

## 6c-prime. ha-fusion Layout Patterns (Andrew's conventions)

**Lights + scene pickers MUST be consolidated into `custom_panel`s, not standalone buttons.** A section that contains separate button items for a light and its scene picker should be refactored into a single `custom_panel` with a slider row (brightness) and a buttons row (scene picker). Multiple device types can share one panel (e.g. TV bias light slider + Nvidia Shield media_player + Bias Scene picker). Full patterns, climate dial CSS tuning, and anti-patterns: `references/ha-fusion-layout-patterns.md`.

The climate dial (`display: dial` on `custom_panel`) renders CSS from `custom_style.css` on the HA host. This **hot-reloads — no Docker rebuild needed** for sizing adjustments. The CSS classes are `.dial-tile`, `.dial-ring`, `.dial-target`, `.dial-target .deg`, `.dial-room`, `.dial-status`, `.dial-meta`. When dial "looks wonky," bump ring and font sizes ~30% as a starting point.

For any dashboard YAML/CSS work beyond a one-line hot-edit, **delegate immediately** using the `home-assistant-dashboard` skill. Per AGENTS.md delegation triggers. Do not build or iterate on dashboards in the main loop.

## 6d. ha-fusion fork (amedello) vs upstream (matt8707)

`ghcr.io/amedello/ha-fusion` is an actively-maintained fork (42 commits ahead, pushed 2026, vs upstream's Jan 2025). Same architecture — `dashboard.yaml`/`configuration.yaml` carry over unchanged, so swapping is just `docker rm -f ha-fusion` + re-`docker run` with the new image, **keeping the same `-p 100.119.118.54:5050:5050` Tailscale-only bind and `-v /root/ha-fusion/data:/app/data` volume**. Pin a tag (e.g. `v2026.5.3`), not `latest`. Adds: Custom Panel item type (camera+slider+buttons+sensor rows in one tile), bilingual manual, lock-code support, inline toolbar. Rollback = recreate container on `ghcr.io/matt8707/ha-fusion:latest`, data dir untouched. Back up the data dir before swap (`cp -r /root/ha-fusion/data /root/backups/...`).

## 6e. ha-fusion: weather forecast broken + custom widgets/CSS (amedello fork)

**Weather forecast card renders nothing on modern HA** — HA removed the `forecast` attribute from weather entities (now a service). ha-fusion's `weather-forecast` sidebar card reads the dead attribute, so `days_to_show` never has data. **Fix:** trigger-template sensor calling `weather.get_forecasts` (type daily, response_variable) every 30 min, store `forecast[:7]` as an attribute, then render a custom row via a sidebar `template` item with inline HTML (flex row of day/icon/hi/lo). Same dead-attribute trap applies to any HA service-migrated attribute — verify with `/api/states/<entity>` that the attribute still exists before binding a card to it.

**Climate dial / DAKboard-style thermostat — CRITICAL: `template` items DO NOT work in the ha-fusion MAIN GRID.** The main-area item dispatcher (`Main/Content.svelte`) only handles `configure | button | conditional_media | picture_elements | camera | empty` (+ `custom_panel` on the amedello fork). A `template` item placed in a section's `items` falls through to the empty `Configure` fallback and renders SILENTLY BLANK — the same trap as custom cards. `template` items are SIDEBAR-ONLY (that's why weather/calendar/server-metrics widgets work — they live in the sidebar). So a circular climate dial in the main grid CANNOT be a template item; it must be a **source patch**. Proven approach: extend the fork's `CustomPanel.svelte` with a `display: 'dial'` mode (add `display`/`climate_entity`/`humidity_entity` fields to the `CustomPanelItem` type in `Types.ts`), render a CSS circular ring (big target temp center, `hvac_action • time` status line, room label, current-temp/humidity/fan/cooling rows), bind to standardized climate attributes (`temperature`, `current_temperature`, `hvac_action`, `fan_mode`), then rebuild the image (see source-patch flow below). Live clock for the status line = a local `setInterval` in the component (there is NO `$clock` store). Ring color driven by `hvac_action` (cooling=blue, heating=orange, idle=grey). **"Bigger calendar font" IS a pure CSS edit** (`.cal-item .ev` / `.cal-item .wh` in custom_style.css) — that hot-reloads with no rebuild, but the dial does not. When probing a climate entity's live attributes, note `.ha_token` is a short-lived session token that 401s quickly; fall back to `.storage/core.entity_registry` to confirm existence and rely on HA's standardized climate attribute schema. Terminal redaction mangles `$(...)` cmd-subst and inline `Bearer <token>` — write a Python script that reads the token from its file remotely and scp it. Full detail (climate dial source patch, scene-art picker patch, build-ship-swap flow, attribute-probe fallback, redaction workaround): `references/ha-fusion-dashboard.md` + `references/ha-fusion-source-patch-rebuild.md`.

**Custom CSS (font/look):** the amedello fork loads `data/custom_style.css` when `configuration.yaml` has `custom_css: /app/data/custom_style.css` (the manual says boolean `true`, but the path form works and is explicit). Injected as a `<style>` tag on every page. The godis theme's base font is `'Inter Variable'`; override globally with `* { font-family: ... !important }` and target the clock with the theme var `--theme-sizes-sidebar-time` or `[class*="time"]`. Custom HTML classes used in `template` widgets (e.g. `.wx-week`, `.srv .bar`) must be defined in this CSS file — ha-fusion template items render raw HTML so class-based styling works.

**Server metrics (CPU%/RAM%) without extra integrations:** HA runs `--network host`, so the container's `/proc/stat` + `/proc/meminfo` reflect the HOST it runs on (verified: container readings match `free`/`uptime` on the host). A `command_line` sensor running a tiny python script (read /proc twice 0.5s apart for CPU, MemTotal-MemAvailable for RAM) gives live local-host metrics with zero new integrations. For a REMOTE host, the same script SSHes (`ssh -i keyfile host 'python3 - <<EOF ...'`) — the HA container HAS an ssh client at /usr/bin/ssh, and a key generated into `/config/.ssh/` persists via the config volume. Remote needs the pubkey in the target's authorized_keys (user-gated if you lack access). Make the sensor degrade gracefully: emit `{"ok": false}` JSON on failure so the dashboard shows "offline" not a crash.

**ha-fusion renders arbitrary image URLs ONLY where the source supports it — investigate the SHIPPED Svelte source before promising a card feature.** The amedello/matt8707 image is a compiled SvelteKit build (`/app/build`), so config + custom_style.css alone cannot add a feature the source doesn't expose. Before telling the user "yes I can show X in the picker/tile," clone the matching tag (`git clone --depth 1 https://github.com/matt8707/ha-fusion.git`) and read the relevant component. Concrete finding: the scene/option **picker is text+iconify only** — `InputSelectModal.svelte` maps each option to `{id, label}` (no image field), and `Select.svelte` renders an optional per-option `icon` via iconify `<Icon icon={name}>` (named vector icons, **NOT arbitrary image/PNG URLs**); the list is virtualized with no per-row CSS hook, so there's no config-only or custom-CSS path to inject thumbnails. To show real image thumbnails you MUST patch the Svelte source (`InputSelectModal` to pass an `image` field, `Select` to render `<img>` when present), bake the images into the image, and rebuild. **Build location matters:** `npm run build` (SvelteKit) OOMs on a ~1-2 GB HA host — build the custom image on a beefier box (6 GB+ RAM, Node 22, Docker), `docker save` → ship → `docker load`, then recreate the container preserving the Tailscale bind. This mirrors the custom-card "renders silently empty" lesson: prove the capability exists in the shipped artifact before committing to a build/deploy. Do the whole local build + self-test first (zero prod impact), then pause for explicit greenlight before swapping the production container.

## 6f. TV snapshot feed (ADB screencap → local_file camera)To show "what's on the TV" on a dashboard (Shield/Android TV), poll a screencap into HA's www dir and surface it as a `local_file` camera. DRM apps (Netflix/Prime/Disney+) return BLACK frames (HDCP); screensaver/launcher/YouTube/games capture fine.

**Pipeline:**
1. Host-side bash script: `adb connect 10.0.0.45:5555; adb -s 10.0.0.45:5555 exec-out screencap -p > /tmp/tmp.png && mv /tmp/tmp.png /root/homeassistant/config/www/tv_snapshot.png`. Use `exec-out` (no sdcard round-trip). Atomic mv so the dashboard never reads a half-written file; leave prior snapshot on failure. **Capture takes ~15s** (Shield PNG encode+transfer) — fine for a periodic still, NOT live. `/root/homeassistant/config/www` is mounted to `/config/www` in the container.
2. systemd timer (`OnUnitActiveSec=30`, `OnBootSec=30`) runs it every 30s. Runs on the HOST (it has the adb client + key), not the container.
3. **`local_file` camera no longer supports YAML platform setup** in HA 2026.x — `ERROR: does not support platform setup, please remove it from your config`. Add it as a config entry in `.storage/core.config_entries` instead: domain `local_file`, `options:{file_path:/config/www/tv_snapshot.png, name:TV Screen}`, empty `data:{}`. Restart → `camera.tv_screen` appears.
4. **Verify the image actually serves** (don't trust state): `GET /api/camera_proxy/camera.tv_screen` should return PNG/JPEG bytes (check magic header), and `ls -la` the snapshot file to confirm the timer is refreshing it.

**ha-fusion main-grid camera item:** `{type: camera, entity_id: camera.tv_screen, stream: false}` — `stream:false` shows the still snapshot (no HLS attempt). Works in a section's `items`, not just sidebar.

## 6g. Per-metric graph sensors + custom CSS widgets recap

For "graph-like" metrics, split a combined JSON sensor into discrete numeric `command_line` sensors (one per metric, `unit_of_measurement: '%'`, `value_template` returning a float) so HA records history per metric. Then render either via ha-fusion sidebar `graph` items (sparklines, sidebar-only) or a custom `template` widget with CSS bars + `repeating-linear-gradient` gridlines to read like a graph. Numeric sensors degrade to `0` (not 'unavailable') so the bar collapses cleanly instead of erroring.

**View-nav tabs hard to read when unselected (godis theme):** unselected `#navigation button` are dimmed in JS. Force readability in custom_style.css: `#navigation button {opacity:0.55 !important; text-shadow:0 1px 3px rgba(0,0,0,.4)!important}` and a `.selected/[aria-selected=true]::after` underline accent for the active tab. The nav container id is `#navigation`, buttons are direct children.

**Custom date display:** hide the stock `[class*="date"]` sidebar item with `display:none` and render a styled one via a `template` item (`now().strftime('%A')` big, `now().strftime('%B %-d')` small/uppercase/letter-spaced) for a cleaner two-line look than the built-in "Thursday June 4".

## 6h. Wall-dash (Custom nginx Dashboard — NOT Lovelace)

Andrew's primary dashboard is a custom nginx-served SPA at port 5051 (Tailscale IP), NOT a HA Lovelace dashboard. It's served from the `wall-dash` Docker container (`nginx:alpine`), with all content in `/root/wall-dash/index.html` — a self-contained HTML+JS file with an inline WebSocket bridge to HA. Adding devices means editing the static HTML: room tiles, JS refresh functions, sub-tab navigation, and `refreshAll()` integration. Full architecture, tile patterns, and pitfalls: `references/wall-dash-architecture.md`. The Lovelace dashboard sections (6b–6g) do NOT apply to this dashboard.

## 6i. Voice Satellites → Hermes (Assist pipeline as transport)

To speak to the FULL Hermes agent by voice: **HA Voice Preview Edition** (still the latest voice hardware as of June 2026 — no successor announced; "Preview" = software maturity, not beta hardware). Pipeline: on-device wake word ("Hey Jarvis" is stock) → Whisper STT via Wyoming on hil-1 (ash-1 too small) → conversation-agent slot pointed at a shim → Hermes webhook (port 8644, needs enabling — gated) → TTS reply through the device (Piper/Edge/RVC-post-processed). HA is transport only; it never interprets the sentence. **Echo Dot is a dead end for this** (locked firmware, custom-skill path has ~8s response deadline + forced invocation prefix); Sonos mics are locked too (output-only). HA Green is a server, not a voice device. Full decision record, architecture, vendor notes: `references/voice-satellite-hermes.md`.

## 7. Pitfalls

- **`--network host` is required for Tailscale access, but Docker does NOT propagate Tailscale subnet routes into containers.** Always verify connectivity FROM INSIDE the container (`docker exec ... bash -c 'echo >/dev/tcp/<ip>/<port>'`), not just from the VPS host. Use the Tailscale IP in HA config entries when HA runs in Docker.
- **Android TV ADB binds to local interface only, not Tailscale.** Use Tailscale subnet routing (Section 5) for the VPS host, but the HA Docker container must use the Tailscale IP directly.
- **Android TV auto-disables ADB network debugging after a timeout.** If `adb connect` fails after working previously, check Developer Options — the toggle likely turned itself off. Re-enable and reconnect.
- **The entity name from androidtv integration cannot be renamed via API in HA 2026.6.** The entity will be `media_player.unnamed_device` with `friendly_name: None`. The entity is NOT in the entity registry. Rename it via the HA web UI (entity → ⚙️ → Rename to "TV") — it takes 5 seconds. Direct registry manipulation crashes HA (missing `aliases_v2` key in 2026.6.0).
- **customize.yaml `friendly_name` does NOT take effect in HA 2026.6.0 for androidtv entities.** Do not waste time on this approach.
- **Password hashing for `auth_provider.homeassistant`:** Passwords are stored as base64(bcrypt(plaintext)). To change a password, hash INSIDE the container (to get the same bcrypt library version), then base64-encode:
  ```python
  import bcrypt, base64
  hashed = bcrypt.hashpw(b"newpassword", bcrypt.gensalt(rounds=12))
  b64hash = base64.b64encode(hashed).decode()
  # Write b64hash to auth_provider.homeassistant -> data.users[0].password
  ```
- **Shell quoting destroys Python inside SSH heredocs/f-strings.** Write scripts to local files → scp → execute remotely. Alternatively, use `execute_code` (Hermes built-in) which avoids all quoting issues.
- **The admin login flow DOES work for token exchange** — the `result` code in `create_entry` responses is exchangeable at `/auth/token` with `grant_type=authorization_code`.
- **`docker logs` silently rolls over.** After restart, check timestamps to distinguish current-boot errors from historical.
- **Android TV ADB hangs HA core if device unreachable.** Verify network connectivity AND port accessibility FROM INSIDE THE CONTAINER before adding the config entry.
- **Non-Tailscale appliances (Sonos, Hue, IoT) need a desktop-OS subnet router — Android clients can't be one.** See Section 5b. The #1 gate is that no peer is advertising the home subnet (`PrimaryRoutes: None` everywhere). Don't propose the Shield/phone as the router; the Android Tailscale client has no `--advertise-routes`. Confirm the real home CIDR before advertising, and remember Sonos must be added by explicit IP (port 1400) because multicast discovery doesn't cross Tailscale.
- **Event-driven LAN devices (Sonos) need a BIDIRECTIONAL route, not just outbound reachability.** Port-1400 OPEN from the container is necessary but NOT sufficient — Sonos UPnP eventing requires the speaker to call BACK into HA. A one-way subnet route fails with `412 Precondition Failed` on `/ZoneGroupTopology/Event` and the integration loads ZERO entities. Fix: static route `100.64.0.0/10 → subnet-router-LAN-IP` on the home router, or run HA on the home LAN. See Section 5b. Always verify with `docker logs ... | grep -i sonos` + entity presence, never just a port probe. Full transcript: `references/sonos-cloud-ha-subnet-router.md`.
- **The agent cannot 'take control' of a machine that isn't yet on a reachable network.** When the task is to onboard the user's own laptop/PC, the first step (install Tailscale + advertise route) MUST be done by the user at the keyboard — there's no channel in until it's on the tailnet. After a Linux/macOS box joins, the agent can SSH over the tailnet; Windows stays copy-paste + VPS-side verification. State this plainly rather than implying remote control is possible.
- **Custom-card dashboards (Mushroom/Bubble/slider-button) render SILENTLY EMPTY when the JS module fails to register.** The user sees "New section"/blank while every server-side check passes (config valid, bundles HTTP 200, resources registered). Do NOT keep re-checking the server. Rebuild on built-in cards (`tile`+`light-brightness` feature, `thermostat`, `heading`) — zero external JS, can't fail this way. See Section 6b. Default to built-in cards; reach for custom cards only on explicit request. The `references/mushroom-dashboard-dimmable-lights.md` approach is the fragile one — prefer `references/builtin-card-dashboard.md`.
- **Custom dashboards land users on the wrong page.** HA reserves `home`/`lovelace` for auto-generated Overview, so custom dashboards live at a different url_path. The user keeps opening Overview and reports "nothing changed." Fix at the root by setting the custom dashboard as the default landing panel (`frontend.user_data_<USER_ID>` → `core.default_panel`), don't just tell them to click the right sidebar entry — those taps often bounce. Companion app caches dashboards hard; test in a plain browser when diagnosing empty/stale. Section 6b.
- **Empty dashboard with config_not_found = storage-key mismatch (HA keys the file off the dashboard `id`, NOT `url_path`).** Registration `id: andrewhome` but file at `lovelace.andrew-home` → HA serves a blank "New section" view. Symptom is identical to the custom-card failure, BUT here even built-in `tile` cards are empty — the tell that HA isn't reading your file at all. Confirm via frontend websocket (`lovelace/config` returns `config_not_found`), not screenshots. Fix: copy config to the `id`-based filename and set its inner `key` to match. Prevention: read `.storage/lovelace_dashboards` first, derive the filename from `data.items[].id`. Section 6b. This burned multiple rebuilds before diagnosis — check the storage key BEFORE rebuilding cards when a dashboard is empty.
- **LG ThinQ `not_allowed_api_again` on the config flow = PAT region mismatch, NOT a bad token.** Don't guess countries through the HA flow (each wrong submit can leave a stuck in-progress flow that then aborts all retries with `already_in_progress`). Probe LG's regional gateways directly first (`api-aic`=US, `api-eic`=EU, `api-kic`=KR) — a 200 names the region and returns the device list, proving PAT validity + scopes + region in one read-only call. Section 5c + `references/lg-thinq-integration.md`.
- **HA in-progress config flows can only be LISTED/ABORTED over the websocket API, not REST** (`GET /api/config/config_entries/flow` is 405). A stuck flow dedups new attempts with `abort reason=already_in_progress`. With no ws client lib available, the clean reset is `docker restart homeassistant` (gated; flushes all in-progress flows). Per-flow `DELETE /…/flow/<id>` works only if you still hold the id.
