# Built-in-card dashboard rebuild + default-panel fix (session: Andrew, June 2026)

## Symptom chain (what the user actually experienced)
1. User reported "no changes in design am I opening it wrong?" — screenshots showed HA's stock **Overview** ("Welcome Hermes", default Areas grid). The custom dashboard was at url_path `andrew-home`; they kept opening the reserved-path Overview.
2. After setting `andrew-home` as the default panel, header changed to "Home" but the page was **empty** ("New section", blank) — in the companion app AND in a plain browser.
3. Plain-browser empty = NOT cache. It was a real client-side render failure: the dashboard was built entirely on `custom:bubble-card` + `custom:mushroom-*`, and the JS modules weren't registering in the frontend, so every card drew nothing.

## Why every server-side check lied
All of these PASSED while the user saw an empty page — they do NOT prove the dashboard renders:
- `lovelace.andrew-home` config valid, 9/4/8 cards across 3 views, all pointing at live entities.
- `/local/bubble-card.js` (813KB), `/local/mushroom.js` (712KB), `/local/slider-button-card.js` (128KB) all served HTTP 200, valid JS headers.
- `.storage/lovelace_resources` registered all three as `res_type: module`.

Lesson: with custom cards, "server is fine" is meaningless for the user-visible result. The only thing that matters is whether the module registers client-side, which headless checks can't confirm.

## ⚠️ CORRECTION — the REAL root cause was a storage-key mismatch, not the custom cards
The custom-card theory above was a red herring that cost extra rounds. After rebuilding on bulletproof **built-in** `tile` cards, the dashboard was STILL empty. Built-in cards cannot fail to load — so the only remaining explanation was that HA wasn't reading the config file at all. Confirmed it by self-driving a headless browser (SSH tunnel + token injection, see below) and asking HA's frontend websocket for the config:

```js
ws = new WebSocket('ws://localhost:8123/api/websocket');
// on auth_required -> {type:'auth',access_token}
// on auth_ok      -> {id:1,type:'lovelace/config',url_path:'andrew-home'}
// RESULT: {success:false, error:{code:'config_not_found', message:'No config found.'}}
```

`config_not_found` = HA could not locate the config file for this dashboard. Inspecting `.storage/lovelace_dashboards`:
```json
{"id":"andrewhome","title":"Home","url_path":"andrew-home","mode":"storage","show_in_sidebar":true}
```
The registration `id` is **`andrewhome`** (no dash). HA keys the storage file off the **`id`**, so it looks for `lovelace.andrewhome` — but every rebuild had written to `lovelace.andrew-home` (matching the *url_path*, with a dash). HA found nothing and fell back to the empty auto-generated "New section" view.

**Fix that ended it:**
```bash
docker exec homeassistant python3 -c "import json; d=json.load(open('/config/.storage/lovelace.andrew-home')); d['key']='lovelace.andrewhome'; json.dump(d, open('/config/.storage/lovelace.andrewhome','w'), indent=2)"
docker restart homeassistant
```
After restart, the websocket returned the real 3-view config and the browser rendered the dark dashboard with colorful tiles, sliders, and the live Sensi thermostat (68°F cooling → 70°F, humidity 37%).

**Takeaway for next time:** when a storage-mode dashboard is empty, FIRST check `.storage/lovelace_dashboards` → `data.items[].id` and confirm a `lovelace.<id>` file exists with that exact key. Derive the config filename from the `id`, NOT the `url_path`. This check takes 5 seconds and would have skipped the entire custom-card chase.

## Self-verifying the render (stop trusting user screenshots)
After multiple "still empty" screenshots, drive a real browser to see it directly:
1. SSH-tunnel HA to localhost: `ssh -o ExitOnForwardFailure=yes -N -L 8123:localhost:8123 root@VPS` (run as a tracked background process; verify `curl -o /dev/null -w '%{http_code}' http://localhost:8123/` → 200).
2. Bypass the login wall by injecting the long-lived token into `localStorage`. Build a tokens object and serve it from a tiny local HTTP server (CORS `*`):
   `{"http://localhost:8123/": {"access_token": <tok>, "token_type":"Bearer", "expires_in":315360000, "hassUrl":"http://localhost:8123", "clientId":"http://localhost:8123/", "expires":9999999999000, "ha_auth_provider":"homeassistant"}}`
3. In the page console: `fetch('http://127.0.0.1:8799/hass_tokens.json').then(r=>r.json()).then(d=>localStorage.setItem('hassTokens', JSON.stringify(d['http://localhost:8123/'])))`, then reload.
4. **Watch the URL path**: `/lovelace/home` is the stock Overview (renders fine, NOT your work); `/andrew-home` is the custom dashboard. Mixing these up wasted a round — Overview rendering perfectly proved the frontend was healthy and isolated the fault to the custom dashboard's config loading.
5. Token clears on HA restart — re-inject after each `docker restart`.

## The built-in-card rebuild (the robust card shapes — still correct)
Replaced the whole config with `tile` / `thermostat` / `heading` only. Card-type audit after: `['heading','thermostat','tile']`, custom: NONE. Native `tile` supports a per-card `"color"` (e.g. `purple`, `pink`, `teal`, `indigo`, `light-blue`) which recreates the colorful pill look without Bubble Card.

Key card shapes (storage-mode sections layout):
- Dimmable light w/ drag slider — `tile` + `light-brightness` feature:
  `{"type":"tile","entity":"light.x","name":"X","color":"purple","features_position":"bottom","features":[{"type":"light-brightness"}]}`
- Thermostat dial — `{"type":"thermostat","entity":"climate.sensi_thermostat"}`
- Header — `{"type":"heading","heading":"Lights","heading_style":"title","icon":"mdi:lightbulb-group"}`
- Switch/fan/group — `{"type":"tile","entity":"switch.office_fan","icon":"mdi:fan","color":"cyan"}`

View structure: `view.type="sections"`, `view.theme="andrew_dark"`, `view.max_columns=3`, each section `{"type":"grid","cards":[...]}`. Cards live under `section.cards`.

Generator used: `scripts/ha_dashboard_builtin.py` — edit the `lights`/`switches` lists, scp into container, `docker exec homeassistant python3 ...`, then `docker restart homeassistant`. It backs up the existing `lovelace.<url_path>` to `.bak.<ts>` first. NOTE: the generator writes to a path you pass — make sure that path matches the registration `id` (see correction above), not the url_path.

## Live entities (Andrew's setup, for reference)
Lights (all dimmable, brightness+RGB via Govee template): living_room_lamp, lantern_lamp, tv_bias_light, office_light, bathroom_1, bathroom_2, bathroom_3.
Switches/groups: office_fan, bathroom_group, office_group, lantern_floor_lamp (+ command_line bathroom_light_1/2/3).
Climate: climate.sensi_thermostat, sensor.sensi_thermostat_temperature, sensor.sensi_thermostat_humidity, binary_sensor.sensi_thermostat_online.
Observed this session: bathroom_1 and bathroom_2 showed "Unavailable" (the Govee command_line lights not responding — separate from the dashboard issue).

## Navigation / default-panel fix
- HA reserves `home`/`lovelace` url_path for auto Overview. Custom dashboard registered in `.storage/lovelace_dashboards` as url_path `andrew-home`, id `andrewhome`, `show_in_sidebar: true`.
- User id (the human) from `.storage/auth` → `data.users[].id` where active and name != "Home Assistant Content". Here: `96df88d8b06547a2b4b4e9e86508111c` (name "Hermes").
- No `frontend.user_data_<id>` existed → created cleanly:
  ```json
  {"version":1,"minor_version":1,"key":"frontend.user_data_<id>","data":{"core.default_panel":"andrew-home"}}
  ```
- Restart HA (reads `.storage` at boot). User now lands directly on the custom dashboard.
- Companion app caches dashboards hard — for "empty/unchanged" diagnosis, test a plain browser first to separate cache from render bug.

## Reversibility
Old config backed up to `lovelace.andrew-home.bak.<timestamp>` before every rewrite. Theme picker is per-browser/per-app one-time: H avatar → Themes → `andrew_dark`.
