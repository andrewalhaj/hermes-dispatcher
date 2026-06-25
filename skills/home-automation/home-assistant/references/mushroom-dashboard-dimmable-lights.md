# Mushroom Dashboard + Dimmable Govee Lights (HA 2026.6)

Building a native Lovelace dashboard in the dark-tile "Mushroom" aesthetic, with
Govee lights converted from on/off switches to full brightness+RGB `light.*` entities.

## Part 1 — Dimmable Govee lights (switch.* → light.*)

All individual Govee devices support `brightness` + `colorRgb` (verify with
`govee.py list` — look for those instances in capabilities). Only group entities
(BaseGroup/SameModeGroup) are power-only.

### govee.py commands used
- `govee.py brightness <pct> "<device>"` — set 1-100
- `govee.py color <r> <g> <b> "<device>"`
- `govee.py state "<device>"` — JSON: `{"online":bool,"power":0/1,"brightness":int,"rgb":[r,g,b]}`
  (the `state` command was added specifically to feed HA template lights — returns full state, not just on/off)

### Three-file architecture (all in /config, baked govee.py at /usr/local/bin/govee.py)
1. **command_line sensors** (appended into the existing `command_line: !include govee_switches.yaml`):
   one `- sensor:` per light, `command: govee.py state "<dev>"`, `value_template: "{{ value_json.power }}"`,
   `json_attributes: [online, brightness, rgb]`. This polls real device state every 60s.
2. **shell_command: !include shell_commands.yaml** — 4 commands per light (on/off/bri/rgb),
   e.g. `govee_lrl_bri: 'govee.py brightness {{ pct }} "Living Room Lamp"'`
3. **template: !include govee_template.yaml** — modern template light per device that reads
   the sensor for state/level/rgb/availability and calls the shell_commands for control.

### CRITICAL: HA 2026.6 template light syntax
The LEGACY `light: - platform: template / lights:` syntax is **REJECTED** in 2026.6
("Configuring the template integration under the light platform key is not supported").
Use the MODERN `template:` integration instead:
```yaml
# govee_template.yaml  (included via: template: !include govee_template.yaml)
- light:
    - name: "Living Room Lamp"
      unique_id: govee_lrl_dim
      state: "{{ states('sensor.govee_lrl') == '1' }}"
      level: "{{ (state_attr('sensor.govee_lrl','brightness') | float(0) / 100 * 255) | round(0) | int }}"
      rgb: >
        {% set c = state_attr('sensor.govee_lrl','rgb') %}
        {{ (c[0], c[1], c[2]) if c else (255,255,255) }}
      availability: "{{ state_attr('sensor.govee_lrl','online') | default(true) }}"
      turn_on:  { action: shell_command.govee_lrl_on }
      turn_off: { action: shell_command.govee_lrl_off }
      set_level:
        action: shell_command.govee_lrl_bri
        data: { pct: "{{ (brightness / 255 * 100) | round(0) | int }}" }
      set_rgb:
        action: shell_command.govee_lrl_rgb
        data: { r: "{{ r }}", g: "{{ g }}", b: "{{ b }}" }
```
Note: brightness scale is HA 0-255 ⇄ Govee 1-100 — convert in both directions.

### Apostrophe gotcha (again)
Device "Andrew's Office Fan" — in single-quoted YAML the apostrophe must be DOUBLED (`Andrew''s`),
AND the double-quotes for the shell arg escaped (`\"`). Generator must apply BOTH:
`gv.replace('"','\\"').replace("'","''")`. A raw apostrophe → `yaml.parser.ParserError`.

### Verify dimming end-to-end
```bash
curl -s -X POST --oauth2-bearer "$TOK" -H "Content-Type: application/json" \
  -d '{"entity_id":"light.living_room_lamp","brightness_pct":45}' \
  http://localhost:8123/api/services/light/turn_on
sleep 5; govee.py state "Living Room Lamp"   # brightness should read 45
```

## Part 2 — Mushroom dashboard (NO HACS needed)

Mushroom ships as a single JS bundle — skip HACS entirely (avoids its auto-update
nag surface, aligns with minimal-footprint). Same for slider-button-card.

### Install
```bash
docker exec homeassistant sh -c "mkdir -p /config/www && cd /config/www && \
  curl -sL -o mushroom.js https://github.com/piitaya/lovelace-mushroom/releases/download/v5.1.1/mushroom.js && \
  curl -sL -o slider-button-card.js https://github.com/mattieha/slider-button-card/releases/download/v1.10.3/slider-button-card.js"
```

### Register as Lovelace resources — `.storage/lovelace_resources`
```json
{"version":1,"minor_version":1,"key":"lovelace_resources","data":{"items":[
  {"id":"mushroom0001","res_type":"module","url":"/local/mushroom.js"},
  {"id":"sliderbtn0001","res_type":"module","url":"/local/slider-button-card.js"}]}}
```
(`/config/www/x.js` serves at `/local/x.js`.)

### Dashboard storage — `.storage/lovelace.<url_path>`
The storage file key MUST be `lovelace.<url_path>` and match the dashboards registry.
```json
{"version":1,"minor_version":1,"key":"lovelace.andrew-home","data":{"config":{
  "title":"Home","views":[ {"title":"Home","path":"home","type":"sections",
  "max_columns":3,"sections":[{"type":"grid","cards":[ ... ]}]} ]}}}
```

### Register dashboard — `.storage/lovelace_dashboards`
```json
{"id":"andrewhome","icon":"mdi:home-assistant","title":"Home",
 "url_path":"andrew-home","require_admin":false,"show_in_sidebar":true,"mode":"storage"}
```

### CRITICAL: url_path "home" collides with a reserved panel
Using `url_path: "home"` throws `ValueError: Overwriting panel home`, which cascades
and **breaks the entire `frontend` component** (logbook/my/default_config all fail).
Use a NON-reserved path like `andrew-home`. The storage file key must follow:
`lovelace.andrew-home`. Reserved names to avoid: home, lovelace, config, developer-tools, profile, map, energy, history, logbook.

### Card types that work for this stack
- `custom:slider-button-card` — the horizontal brightness-slider light tile (the star of the look)
- `custom:mushroom-title` — section headers (title + subtitle)
- `custom:mushroom-chips-card` — compact status row (temp/humidity/battery at top)
- `custom:mushroom-template-card` — custom toggle tile with jinja primary/secondary/icon_color
- `custom:mushroom-media-player-card` — Shield / Sonos media
- `custom:mushroom-fan-card` — fan with animation (Office Fan has fanSpeedMode capability)
- `custom:mushroom-entity-card` — generic sensor tile
- `thermostat` (built-in) — best for the climate round dial
- `grid` with `columns: 2` — 2-up tile layout

### Custom theme for the exact dark-blue/gray palette
`/config/themes/andrew_dark.yaml` — key vars: `lovelace-background` (gradient),
`card-background-color: "#16202f"`, `ha-card-border-radius: "18px"`,
`primary-color/accent-color: "#3b82f6"`, mush-rgb-* color tokens, `slider-color`.
Loaded via the existing `frontend: themes: !include_dir_merge_named themes`.
Set per-dashboard via the view/profile theme picker (themes don't auto-apply).

## Verification gates (API-level — reliable even when browser login is flaky)
- `curl --oauth2-bearer $TOK http://localhost:8123/api/` → 200 (frontend up)
- `/local/mushroom.js` and `/local/slider-button-card.js` → 200 each
- template `{{ states.light | map(attribute='entity_id') | list }}` lists all 7 lights
- `docker logs homeassistant | grep -i "overwriting panel\|frontend"` → empty
- Inspect stored dashboard JSON directly for view/card counts.

### Browser screenshot caveat
The cloud (Firecrawl) headless browser without residential proxy repeatedly bounces
HA login back to "Start over" (bot protection). Don't rely on it for visual confirm —
verify at the API/storage layer instead. Real login works fine from the user's phone/Tailscale.

## Color control (mushroom-light-card)
The `custom:mushroom-light-card` gives inline brightness + color + color-temp pickers:
```yaml
- type: custom:mushroom-light-card
  entity: light.living_room_lamp
  show_brightness_control: true
  show_color_control: true
  show_color_temp_control: true
  use_light_color: true
  collapsible_controls: false
```
Requires the template light to expose `set_rgb` (wired to `govee.py color r g b`) — already
built in Part 1. Verified end-to-end: HA `light.turn_on` with `rgb_color:[0,255,0]` →
device reports `rgb:[0,255,0]`. Brightness and color are independent service calls; sending
only `rgb_color` leaves brightness unchanged (correct Mushroom behavior).

## Part 3 — Bubble Card (colorful room "pill" layout, NO HACS)

Bubble Card gives the colorful gradient room-pill look (rounded cards with chip
sub-buttons). Same no-HACS install. **No release assets** — the built JS lives in the
repo at `dist/bubble-card.js`; pull it pinned to a tag:
```bash
docker exec homeassistant sh -c "cd /config/www && \
  curl -sL -o bubble-card.js https://raw.githubusercontent.com/Clooos/Bubble-Card/v3.2.2/dist/bubble-card.js"
```
Add `{"id":"bubblecard0001","res_type":"module","url":"/local/bubble-card.js"}` to
`.storage/lovelace_resources`. Restart HA (resource registry reload sometimes needs it).

### Colorful room pill (button card + sub-button chips + gradient via styles)
```yaml
- type: custom:bubble-card
  card_type: button
  button_type: name
  name: Living Room
  icon: mdi:sofa
  entity: light.living_room_lamp
  card_layout: large
  sub_button:
    - { entity: light.living_room_lamp, icon: mdi:lamp, show_background: true }
    - { entity: light.tv_bias_light, icon: mdi:television-ambient-light, show_background: true }
  styles: |
    .bubble-background { background: linear-gradient(135deg, #4338ca 0%, #6d28d9 100%) !important; opacity: 1 !important; }
    .bubble-main-icon, .bubble-name, .bubble-state, .bubble-sub-button { color: #ffffff !important; }
    .bubble-icon-container { background: rgba(255,255,255,0.18) !important; }
```
- `button_type`: `name` (room pill), `state` (shows value), `slider` (inline brightness drag)
- Per-card gradient comes from the `styles:` block targeting `.bubble-background` (the fill layer — see CRITICAL note below; do NOT use `.bubble-button-card-container`).
- `card_type: separator` makes the "My Dashboard" header.
- Merge into existing dashboard: read `.storage/lovelace.andrew-home`, replace the
  `path==home` view, keep Climate/Lights. (gen script does this via ssh+docker cat.)

### CRITICAL: Bubble Card v3 gradient selector (the README LIES)
The README example targets `.bubble-button-card-container` for `background:` — that class
EXISTS in the bundle but is the wrong layer. Bubble Card v3 renders an absolute-positioned
fill element `.bubble-background` (height/width 100%, on TOP of the container). A background
set on the container is HIDDEN behind that opaque fill, so the gradient never shows and the
pill falls back to the default dark theme (looks identical to a plain Mushroom dashboard —
this is the "it's the same as the last one?" trap). Correct styling:
```css
.bubble-background { background: <gradient> !important; opacity: 1 !important; }
.bubble-main-icon, .bubble-name, .bubble-state, .bubble-sub-button { color: #fff !important; }
.bubble-icon-container { background: rgba(255,255,255,0.18) !important; }
```
Verify the actual class names against the SHIPPED bundle, not the README:
`grep -o 'bubble-background' /config/www/bubble-card.js | wc -l`. Source CSS lives at
`src/components/base-card/styles.css` and `src/cards/button/styles.css` on the repo tag.
Text classes are `.bubble-main-icon` / `.bubble-name` / `.bubble-state` (NOT `.bubble-icon`).

## Sonos over Tailscale — KNOWN BLOCKER (not fixed)
container (port 1400 reachable, "Connection reestablished" logged) but entities never
materialize. Root cause: **UPnP eventing fails with `412 Precondition Failed`** on
`http://<speaker>:1400/ZoneGroupTopology/Event`. Sonos eventing requires the SPEAKER to
POST callbacks BACK to HA, and HA-in-Docker-on-VPS reached via Tailscale subnet route has
no return address the speakers accept. This is the classic Sonos-over-VPN limitation.
Workarounds (none trivial, deferred): run an HA instance on the LAN, or a Sonos↔MQTT
bridge on a LAN host, or sonos2mqtt. Don't rabbit-hole — report honestly.

## Rollback (full)
```bash
docker exec homeassistant sh -c "
  rm -f /config/govee_template.yaml /config/shell_commands.yaml /config/www/mushroom.js /config/www/slider-button-card.js
  rm -f /config/.storage/lovelace.andrew-home /config/.storage/lovelace_resources
  cp /config/govee_switches.yaml.bak /config/govee_switches.yaml
  cp /config/configuration.yaml.bak /config/configuration.yaml"
# restore lovelace_dashboards to just the map entry, restart HA
```
The original 9 command_line switches stay intact as fallback the whole time.
