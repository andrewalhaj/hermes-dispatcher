# Wall-dash — Custom Dashboard Architecture

Andrew's primary dashboard is the custom Wall-dash at `http://100.119.118.54:5051/` (Tailscale IP). It is NOT a Home Assistant Lovelace dashboard — it's a standalone nginx-served SPA with an inline WebSocket bridge to HA.

## Infrastructure

- **Docker container:** `wall-dash` running `nginx:alpine`
- **Host files:** `/root/wall-dash/` on the backup server (178.156.246.115)
- **Mounts:**
  - `/root/wall-dash` → `/usr/share/nginx/html` (static files)
  - `/root/wall-dash/default.conf` → `/etc/nginx/conf.d/default.conf` (listen 5051)
- **Key files:**
  - `index.html` — self-contained SPA (HTML + inline CSS refs + inline JS)
  - `dashboard.css` — stylesheet
  - `govee_config.json` — Govee device configuration
  - `scene_art/` + `scene_art_map.json` — scene artwork assets

## Architecture

### Navigation
Top nav bar with buttons: Home, Rooms, Cameras, Media. Each `data-view` maps to a `<section>` with matching `data-view` attribute. Switching hides/shows sections.

### Rooms Sub-tabs
The Rooms view uses a sub-tab pattern:
```html
<div class="room-subtabs">
  <button class="room-subtab selected" data-room="living-room">Living Room</button>
  <button class="room-subtab" data-room="kitchen">Kitchen</button>
  ...
</div>
```

Each sub-tab has a matching grid:
```html
<div class="rooms-unified-grid" id="grid-living-room">...</div>
<div class="rooms-unified-grid single" id="grid-kitchen" style="display:none;">...</div>
```

Sub-tab switching is handled by generic JS that hides all `rooms-unified-grid[id^="grid-"]` elements and shows `grid-{data-room}`. Adding a new room requires only: (a) the subtab button with `data-room`, (b) the grid with matching `id="grid-{room}"`.

### Room Tile Pattern
Each room has one or more tiles with this structure:
```html
<div class="tile room-tile <optional-cell-class>">
  <div class="rt-room-label">Room Name</div>
  <div class="rt-icon on|off"><svg>...</svg></div>
  <div class="rt-name">Device Name</div>
  <div class="rt-state">On/Off/Playing</div>
  <div class="rt-actions"><button>...</button></div>
  <div class="rt-slider"><input type="range"><span class="rt-val"></span></div>
  <div class="rt-meta"><span>extra info</span></div>
</div>
```

### HA WebSocket Bridge
The dashboard connects to HA via WebSocket at `178.156.246.115:8123`. On `auth_ok` it subscribes to `state_changed` events and fetches all states. Each state change triggers `refreshAll()` which updates every tile synchronously.

Token is stored in `localStorage` (`ha_token`). If missing, the dashboard prompts.

### Refresh Pattern
`refreshAll()` is the central refresh function called on every state change. It:
1. Refreshes Sensi thermostat
2. Syncs Shield tiles (media player state + TV bias light)
3. Iterates ALL `.room-tile` elements, looks up `roomEntityMap[name]`, updates icon/state/slider
4. Runs Sonos sync
5. Runs bathroom group sync
6. Runs any dedicated per-device refresh calls (basement, purifiers)

**Adding a new device type:** A dedicated `refreshXxx()` function is called directly from `refreshAll()`, bypassing the generic room-tile loop. The function reads entity state from the global `entities` object and updates specific DOM elements by ID.

### Tile CSS Classes
- `.room-tile` — base room tile
- `.shield-cell` — Shield tiles (special sync logic)
- `.purifier-cell` — air purifier tiles (fan + PM2.5 + air quality)
- `.bath-group-cell` — bathroom group tile
- `.basement-cell` — basement washer tile

### Adding a Purifier Tile

Template for a purifier room tile:
```html
<div class="tile room-tile purifier-cell">
  <div class="rt-room-label">Room</div>
  <div class="rt-icon on" id="XX-purifier-icon"><svg>fan-icon</svg></div>
  <div class="rt-name" id="XX-purifier-name">Device Name</div>
  <div class="rt-state" id="XX-purifier-state">Off</div>
  <div class="rt-actions">
    <button onclick="togglePurifier('fan.entity_id')"><span>Power</span></button>
    <button onclick="cyclePurifierSpeed('fan.entity_id')"><span>Speed</span></button>
  </div>
  <div class="rt-meta">
    <span id="XX-pm25">PM2.5: --</span>
    <span id="XX-air-quality">Air: --</span>
  </div>
</div>
```

JS functions needed (append before `</script>`):
```javascript
function refreshPurifier(fanEntity, iconId, stateId, pm25Id, aqId) {
  const fan = entities[fanEntity];
  if (!fan) return;
  const isOn = fan.state === "on";
  document.getElementById(iconId).className = "rt-icon " + (isOn ? "on" : "");
  document.getElementById(stateId).textContent = isOn ? "On" : "Off";
  const pm25Ent = entities[fanEntity.replace("fan.", "sensor.") + "_pm2_5"];
  if (pm25Ent) document.getElementById(pm25Id).textContent = "PM2.5: " + pm25Ent.state + " µg/m³";
  const aqEnt = entities[fanEntity.replace("fan.", "sensor.") + "_air_quality"];
  if (aqEnt) document.getElementById(aqId).textContent = "Air: " + aqEnt.state;
}

function togglePurifier(entityId) { /* call_service turn_on/turn_off */ }
function cyclePurifierSpeed(entityId) { /* set_percentage low/medium/high */ }
```

Then add refresh calls at the end of `refreshAll()`:
```javascript
refreshPurifier("fan.living_room", "lr-purifier-icon", "lr-purifier-state", "lr-pm25", "lr-air-quality");
refreshPurifier("fan.dining_room", "kt-purifier-icon", "kt-purifier-state", "kt-pm25", "kt-air-quality");
```

## Tile Placement Rules (Critical)

Every room tile MUST be nested inside its corresponding `grid-{room}` div — between the opening `<div class="rooms-unified-grid ..." id="grid-{room}">` and its closing `</div>`. A tile placed OUTSIDE any grid div (loose in the parent `rooms-view` container) is a sibling of all grids and cannot be hidden by the subtab JS, which only toggles `display` on `[id^="grid-"]` elements. Result: the tile appears in EVERY room subtab.

**After inserting a new tile, verify nesting:**
```bash
grep -n 'grid-<room>\|id="grid-' index.html | head -20
# The tile's line number must fall between the grid's open and close lines
```

## Pitfalls
- **File size:** `index.html` is ~160KB. `patch()` struggles with large files — use `sed` with line numbers or a Python script for edits.
- **`sed r` inserts AFTER the addressed line, not before.** When inserting a new tile before a grid's closing `</div>`, address the line BEFORE the close, not the close itself. If you insert after the `</div>`, the tile becomes a loose sibling of all grids — visible in every subtab. Always verify placement by checking line numbers against the grid boundaries.
- **Never use regex to insert new elements into large HTML files.** Regex substitutions with greedy `.*?` quantifiers can silently produce duplicate DOM elements. When two elements share the same `id`, `document.getElementById` returns the FIRST (often empty/stale) one and the second one with your actual content is invisible. Always use precise line-number insertion or a DOM-aware tool. **Corollary: if a subtab shows content from the wrong room or appears empty, grep for duplicate `id=` values first.** Also grep for loose tiles outside grid boundaries — a tile at the wrong nesting level is invisible to the subtab toggle.
- **Always backup first:** `cp index.html index.html.bak-$(date +%s)` before any edit. The file has pre-existing `.bak` files from prior edits.
- **Container restart required:** Nginx caches nothing (static files), but the Docker container must be restarted to pick up changes if using volume mounts that don't hot-reload. A `docker restart wall-dash` is sufficient (no rebuild needed).
- **Token lifecycle:** If the HA token expires or is revoked, the dashboard prompts for a new one on load. Generate via HA UI → Profile → Security → Long-Lived Access Tokens.
- **Entity naming convention:** VeSync creates entities with underscores: `fan.living_room`, `sensor.living_room_pm2_5`. The JS entity lookup uses exact entity_id strings.

- **Stale browser cache after dashboard fix:** After patching a render bug (empty subtab, wrong device), the corrected HTML may not appear until the browser does a hard refresh. `Ctrl+Shift+R` (or Cmd+Shift+R). The nginx container was restarted but the browser may have cached the broken version.
