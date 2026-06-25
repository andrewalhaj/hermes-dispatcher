# ha-fusion Dashboard (headless deployment)

A modern Svelte HA dashboard (matt8707/ha-fusion, MIT, pre-beta, last commit Oct 2024).
Runs as its own Docker container, talks to HA over websocket with a long-lived token.

## Deployment (backup VPS, 178.156.246.115)

Tailscale IP of VPS: `100.119.118.54`. **Bind the port to the Tailscale IP only** —
never `0.0.0.0` — so the dashboard is reachable over Tailnet but NOT the public internet.

```bash
docker run -d --name ha-fusion --restart unless-stopped \
  -p 100.119.118.54:5050:5050 \
  -v /root/ha-fusion/data:/app/data \
  -e TZ=UTC -e HASS_URL=http://178.156.246.115:8123 \
  ghcr.io/matt8707/ha-fusion:latest
```

Access from phone/laptop on the tailnet: `http://100.119.118.54:5050`

## Config files (in /root/ha-fusion/data, mounted to /app/data)

Two YAML files. ha-fusion writes these itself when edited via UI, but for headless
setup author them directly:

- **configuration.yaml** — app settings + auth token:
  ```yaml
  hassUrl: http://178.156.246.115:8123
  locale: en
  token: <183-char HA long-lived access token>
  ```
  The `token:` here is what authenticates the dashboard to HA headlessly (no browser
  login needed). Mint a DEDICATED long-lived token (not the admin token) so it's
  independently revocable.

- **dashboard.yaml** — the views/sections/cards. Schema:
  ```yaml
  theme: godis           # bundled themes: godis, muted, contrast
  hide_views: false
  hide_sidebar: false
  sidebarWidth: 391
  views:
    - name: Home
      icon: material-symbols:home-rounded
      id: <int>          # IDs are arbitrary unique ints (app uses ~13-digit)
      sections:
        - type: horizontal-stack   # groups columns side by side
          id: <int>
          sections:
            - name: Living Room
              id: <int>
              items:
                - type: button     # the workhorse card — works for switch/light/climate/sensor/media_player
                  entity_id: switch.living_room_lamp
                  id: <int>
                  name: Living Room Lamp   # optional override
                  icon: mdi:lamp           # optional
                  color: '#1cd760'         # optional active color
                  marquee: true            # optional scrolling long names
  sidebar:
    - type: time
      id: <int>
      hour12: true
    - type: date
      id: <int>
    - type: sensor
      entity_id: sensor.x
      prefix: 'Indoor: '
      suffix: '°F'
      id: <int>
    - type: divider
      id: <int>
  ```

## Card types (from src/lib/Types.ts)
- `button` — universal toggle/state card. Use for switch, light, climate, media_player, sensor.
- `media` — rich media_player card. This is the "TV / now-playing feed" card — it shows
  cover art / show thumbnail of what's playing (e.g. an Nvidia Shield `media_player`),
  idle state otherwise. It is a MAIN-GRID card (put it in a view section, not the sidebar).
  Syntax uses a `conditional:` LIST of entity_ids, NOT a flat `entity_id:`:
  ```yaml
  - type: media
    id: <int>
    conditional:
      - entity_id: media_player.unnamed_device
  ```
- Sidebar-only types: time, date, sensor, weather, weather-forecast, divider, graph, bar,
  radial, template, navigate, timer, camera, iframe, image.

## Weather card (met.no, free, no API key)
ha-fusion has native `weather` (current) and `weather-forecast` (multi-day) SIDEBAR cards.
To feed them:
1. **Set HA home location FIRST.** A fresh HA sits at lat/long `0.0/0.0` (null island) and
   any weather integration returns garbage (Atlantic Ocean). Patch `.storage/core.config`
   -> `data.{latitude,longitude,elevation,time_zone,location_name}`, restart HA.
2. Add the `met` config entry (Met.no, free, no key) directly to `.storage/core.config_entries`
   with `source: "onboarding"`, `data:{latitude,longitude,elevation,name}`. Restart.
   It creates `weather.forecast_*` (entity id often `weather.forecast_forecast`).
3. Sidebar cards:
   ```yaml
   - type: weather
     entity_id: weather.forecast_forecast
     icon_pack: meteocons
     show_apparent: true
     id: <int>
   - type: weather-forecast
     entity_id: weather.forecast_forecast
     icon_pack: meteocons
     days_to_show: 5
     id: <int>
   ```

## Calendar agenda (ha-fusion has NO native calendar card)
ha-fusion exposes no calendar widget — and a `calendar.*` entity only surfaces the NEXT
event in its attributes, not a list. The working pattern for an upcoming-events agenda:
1. Add a `local_calendar` config entry (`data:{calendar_name:"Family"}`) -> `calendar.family`.
   Seed events via `calendar.create_event` service (needs a USER token — see 401 note below).
2. Add a **trigger-based template sensor** that calls `calendar.get_events` on HA-start and
   every 15 min, storing the full list in an attribute. Append to an existing `template:`
   include file (don't add a second `template:` key in configuration.yaml):
   ```yaml
   - trigger:
       - platform: homeassistant
         event: start
       - platform: time_pattern
         minutes: "/15"
     action:
       - service: calendar.get_events
         target: {entity_id: calendar.family}
         data: {duration: {hours: 336}}
         response_variable: agenda
     sensor:
       - name: "Family Agenda"
         unique_id: family_agenda
         state: "{{ agenda['calendar.family']['events'] | count }}"
         attributes:
           events: "{{ agenda['calendar.family']['events'] }}"
   ```
3. Render in a sidebar `template` card. Event `start` is `YYYY-MM-DDTHH:MM:SS±TZ` for timed
   events and bare `YYYY-MM-DD` for all-day — branch on `'T' in s` and `strptime` accordingly.
4. Swapping in real calendars later just changes the entity_id — no dashboard rebuild.
- Pitfall: the HA-start trigger can fire before the calendar platform finishes loading, so
  the sensor reads `unknown` for ~20s after a restart, then the time_pattern repopulates it.
  Don't conclude it's broken — wait one cycle and recheck.

## Minting the dedicated token (headless)
HA host has no pip. Do it INSIDE the HA container (has aiohttp):
1. login_flow with hermes_admin creds -> access_token
2. websocket `auth/long_lived_access_token` with `lifespan: 3650`
3. Write result to /config/ha-fusion-token.txt, copy to ha-fusion data dir.
See scripts/ha_setup2.py pattern (aiohttp-based, no extra deps).

## Verification gates
- `curl -o /dev/null -w "%{http_code}" http://100.119.118.54:5050/` -> 200
- `curl http://.../` HTML should contain your view/section NAMES (proves dashboard.yaml loaded, not default)
- `docker logs ha-fusion | grep -i auth` -> no errors
- token valid: `curl -H "Authorization: Bearer <tok>" http://localhost:8123/api/` -> 200

## Pitfalls
- **System refresh token gets 401 on `/api/services/*` and `/api/template`.** The
  `token_type:"system"` refresh token works fine for READ endpoints (`/api/states`,
  `/api/states/<id>`) but is REJECTED (HTTP 401) for service calls (e.g.
  `calendar.create_event`) and template rendering. For those, mint a USER token via the
  admin login flow (`/auth/login_flow` -> submit hermes_admin creds in ONE step ->
  exchange `result` at `/auth/token` with `grant_type=authorization_code`). The 183-char
  user JWT works for services and templates. Don't burn time re-trying the system token.
- **Pre-beta + stale (Oct 2024).** Works, but no upstream fixes if a future HA core
  release breaks its websocket calls. Pin image tag if stability matters. HA's own
  Lovelace stays untouched as fallback.
- **Bind to Tailscale IP, not 0.0.0.0.** Dashboard holds a long-lived HA token; never
  expose 5050 publicly.
- **Empty /app/data on first run is normal** — ha-fusion generates config on first
  authenticated UI load. For headless, pre-author both YAMLs.
- **Command substitution `$(cat token)` gets mangled by Hermes redaction layer** when
  the token looks secret-like. Write verification as a .sh file, scp it, run remotely.

## Camera / TV-snapshot item: overlay chrome + sizing
- The main-grid `camera` item (`{type: camera, entity_id: camera.tv_screen, stream: false}`)
  ALWAYS renders a name+state label overlay ("TV Screen / Idle") on top of the image, and
  you can't turn it off via item fields. `camera` is one of the fork's `large` item types
  (`["conditional_media","picture_elements","camera"]`) — they render bigger than buttons.
- **Clean fix for "no overlay + control the size": render the snapshot as a plain `<img>`
  in a `template` item instead of a `camera` item.** HA serves files in `/config/www/` at
  `http://<ha>:8123/local/<file>` with NO auth required (verified HTTP 200 on
  `/local/tv_snapshot.png`). So:
  ```yaml
  - type: template
    id: <int>
    template: >-
      <img src="http://178.156.246.115:8123/local/tv_snapshot.png?{{ now().timestamp()|int }}"
           style="width:100%;border-radius:0.5rem"/>
  ```
  The `?{{ now().timestamp() }}` cache-buster forces the browser to refetch the new snapshot.
  No name/state chrome, full size control.

## Custom Panel (amedello fork) — CANONICAL SCHEMA (verified rendering)
The fork's `custom_panel` item type collapses a light + its scene picker (+ sensor/camera
rows) into ONE tile. After an initial hand-authored failure, the working schema was recovered
by building ONE panel in the UI editor, saving, and reading back what the editor produced.
**The canonical schema — VERIFIED to render a working slider + scene button:**
```yaml
- type: custom_panel
  id: <int>
  rows:
    - type: slider          # brightness slider bound to a light
      id: <int>
      entity_id: light.lantern_lamp
    - type: buttons         # NOTE: row holds `items:`, NOT `buttons:`
      id: <int>
      columns: <int>        # how many buttons per row
      items:
        - id: <int>
          entity_id: input_select.govee_scene_lantern   # opens scene picker modal
```
Row types: `slider`, `buttons`, `sensor`, `camera`. The panel must be nested as an ITEM
inside a section (`view → sections → section → items → custom_panel`), NOT as the view itself.

### The two things that broke the first attempt (BOTH must be avoided)
1. **`primary_row_id` is a FABRICATED field — do not invent it.** The editor's real output has
   NO `primary_row_id`. Adding it (a guess at "pin one row to the tile face") was a primary
   cause of the silent-empty render. The `buttons` row uses `items:` with `{id, entity_id}`
   entries plus a `columns:` field — NOT a `buttons:` key.
2. **Placing the panel as a VIEW instead of an ITEM blanks the whole dashboard.** Writing
   `views: - type: custom_panel` (panel AS the view) produces a view with no `sections`, which
   ha-fusion renders as the empty "Welcome Home / Open dashboard menu" fallback — wiping the
   entire main grid. The panel must live under `section.items`.

### Failure mode is a silent client-side empty render (server checks all FALSE-POSITIVE)
A bad `custom_panel` does NOT fail gracefully — it can blank the entire dashboard while EVERY
server-side check passes: YAML parses, `curl` serves the config intact, HTTP 200, `docker logs`
clean (only an unrelated node DeprecationWarning). The failure is purely client-side render,
visible ONLY in a screenshot — and these dashboards are Tailscale-only (agent can't screenshot).
So you cannot catch it from the VPS.

### Safe rollout procedure (proven this session)
- Always keep a `dashboard.yaml.prepanel` backup so revert is one `cp` + restart.
- Build exactly ONE panel on the simplest room using the canonical schema above, deploy, and
  have the USER screenshot-confirm it renders (slider + scene button present AND the rest of
  the dashboard still intact) BEFORE rolling out to other rooms. Never roll out unseen.
- If the user/agent can't get a confirmation, fall back to PLAN A: place the `light` button and
  its scene `input_select` button side-by-side in the same section (visual pairing). Both keep
  working, zero fragility, fully verifiable.
- (This session: first attempt with `primary_row_id` + panel-as-view broke everything; reverted
  from backup; rebuilt ONE panel via UI editor, read back the canonical schema, nested it as a
  section item — confirmed working by user screenshot.)

## Verification gap: Tailscale-only dashboards can't be screenshotted by the agent
The dashboard binds to a Tailscale IP (`100.119.118.54:5050`), unreachable from the cloud
browser tool — so the agent CANNOT visually self-verify CSS/layout/render. Verify everything
reachable: served HTML contains expected names/classes, `/api/template` renders widget HTML
correctly, `/api/camera_proxy/<cam>` returns valid image bytes (check PNG/JPEG magic),
sensors have live state. Then STATE PLAINLY that pixel-level look is unverified and ask the
user to screenshot if anything looks off. Don't claim a visual result you couldn't see.
This user prefers: surface consolidation/layout tradeoffs WITH a recommendation before
blind-building anything fragile; default to the verifiable approach over the slick-but-unseeable one.

## Climate dial + bigger fonts: build with `template` items + custom_style.css, NOT fragile cards
When the user wants a DAKboard-style **circular thermostat dial** (big target temp in the
center, `HVAC_ACTION • time` status line, room label at the bottom of the ring, humidity/
cooling icons around it), DO NOT reach for a custom thermostat card or chase a special widget
type. Build it as a sidebar/section **`template` item** rendering a CSS circular dial — the
SAME proven mechanism the weather, calendar, and server-metric tiles already use. Bind to the
standardized HA climate attributes (no integration-specific guessing needed):
- target temp: `{{ state_attr('climate.sensi_thermostat','temperature') }}`
- current temp: `{{ state_attr('climate.sensi_thermostat','current_temperature') }}`
- status: `{{ state_attr('climate.sensi_thermostat','hvac_action') }}` (idle/cooling/heating)
- humidity: a separate `sensor.*_humidity` (climate entities don't always expose humidity)
Define the `.dial`/ring CSS in `custom_style.css`. This avoids the custom-card silent-empty
trap entirely (template items render raw HTML, can't fail to register a JS module).

**"Increase calendar font" = a two-value CSS edit, no YAML/restart.** The agenda is already a
`template` item using `.cal-item .ev` (title) and `.cal-item .wh` (date/time) classes. Bump
`.cal-item .ev` font-size (e.g. 0.95rem→1.15rem) and `.cal-item .wh` (0.8rem→0.95rem) in
`custom_style.css`. ha-fusion hot-reloads its data files (`dashboard.yaml`, `custom_style.css`)
— CSS/template-only edits need NO container restart; the user just reopens. Rollback = restore
the `.prev` of the CSS file. Keep a `.prev` backup before every edit.

## Probing a climate entity's live attributes when `.ha_token` is expired
`/root/homeassistant/config/.ha_token` is a SHORT-LIVED session token — it returns **HTTP 401**
shortly after minting, so don't rely on it for read-back. To learn an entity's real
attributes/state without a fresh token:
1. Try `.storage/core.restore_state` (last-known states with full attributes) — but note a
   given entity **may be absent** if it wasn't captured at the last save; an empty result there
   does NOT mean the entity doesn't exist.
2. Confirm the entity actually exists via `.storage/core.entity_registry`
   (`grep -o "<entity_slug>[a-z_]*"`). A full entity set (e.g. `sensi_thermostat`,
   `sensi_thermostat_humidity`, `sensi_thermostat_fan_speed`…) present in the registry =
   the integration IS set up; the dashboard reading the entity confirms it's live.
3. For the actual values, either mint a fresh user token (admin login_flow path) or rely on
   HA's **standardized** climate attribute schema (current_temperature, temperature,
   hvac_action, hvac_mode, fan_mode) — these are stable across all climate integrations, so a
   template dial can bind confidently without a live read.

## Terminal redaction mangles command substitution AND inline `Bearer <token>`
Beyond the `$(cat token)` case: Hermes's secret-redaction layer rewrites secret-looking
strings to `***` INSIDE the shell command, which breaks `TOKEN=$(...)` command substitution
(the `$(...)` becomes `***`) and inline `-H "Authorization: Bearer <jwt>"` mid-command,
producing bash syntax errors (`syntax error near unexpected token ')'`). **Fix:** never inline
tokens or `$(...)` cmd-subst in a remote SSH one-liner. Write a self-contained Python script
that reads the token from its file on the remote box (`open('/config/.ha_token').read().strip()`),
`scp` it over, and run it with `python3 /tmp/script.py`. Python file content is not subject to
the same inline-command mangling.

## Rollback
```bash
docker rm -f ha-fusion && rm -rf /root/ha-fusion
# revoke the long-lived token in HA: Profile -> Long-lived access tokens -> Delete "ha-fusion"
```
HA core entirely unaffected.
