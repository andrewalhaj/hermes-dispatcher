---
name: wall-dash
description: "Edit Andrew's Wall Dashboard: devices, rooms, subtabs."
category: home-automation
---

# Wall Dashboard

Andrew's wall-mounted dashboard is a custom single-page HTML app served by nginx:alpine on the backup server (178.156.246.115). It connects to Home Assistant via WebSocket for live state.

## Locations

| What | Where |
|---|---|
| Host | 178.156.246.115 (backup server) |
| Container | `wall-dash` (nginx:alpine) |
| Files on host | `/root/wall-dash/` |
| Mapped into container | `/root/wall-dash/` → `/usr/share/nginx/html/` |
| URL | `http://100.119.118.54:5051/` (Tailscale) |
| HA it connects to | `http://178.156.246.115:8123` (WebSocket) |

## Structure

The dashboard is `index.html` (~40KB as of 2026-06-07) plus a SEPARATE `dashboard.css` (~21KB). The CSS is NOT inline — it lives in `/root/wall-dash/dashboard.css` and is `<link>`ed from the HTML. No React, no frameworks — vanilla JS. The HA WebSocket populates an `entities` object at runtime.

⚠️ **ALWAYS read the live files before editing or quoting structure.** This dashboard has been refactored more than once and the layout model has CHANGED between versions. Do NOT trust this skill's markup snippets or your own memory as the current shape — `read_file`/`search_files` the live `index.html` and `dashboard.css` first, then match what is actually there. The live file is the source of truth; this skill documents patterns, not the guaranteed-current DOM.

### Views (top nav)
```
Home | Rooms | Cameras | Media
```

Each view is a `<div class="view" data-view="..." hidden>` section. `.view[hidden] { display: none !important; }` does the show/hide.

### Rooms view — TWO layout models have existed

The Rooms view layout has drifted between versions. Confirm which one is live before editing:

**Model A — block/row layout (LIVE as of 2026-06-07):** No subtabs. The Rooms view is a vertical stack of sections:
```html
<div id="rooms-view" class="view" data-view="rooms" hidden>
  <section class="room-block">                <!-- e.g. Living Room -->
    <div class="rooms-grid two"> ... room-tiles ... </div>
  </section>
  <div class="room-row">                       <!-- bottom row, 3 rooms side by side -->
    <section class="room-col"><h2 class="sec-title">Master Bedroom</h2><div class="tile room-tile">…</div></section>
    <section class="room-col"> … </section>
    <section class="room-col"> … </section>
  </div>
</div>
```
CSS lives in `dashboard.css`: `.room-block`, `.room-block-head`, `.rooms-grid` (auto-fill minmax 210px), `.rooms-grid.two` (auto-fit minmax 260px, wide tiles), `.room-row` (auto-fit minmax 240px), `.room-col`. Full extracted CSS block in `references/rooms-tab-css.md`.

**Model B — subtab/grid switching (OLDER, may reappear):** Subtab buttons (`.room-subtab` with `data-room="X"`) toggle `id="grid-X"` divs; generic JS hides all `grid-*` and shows the match. If you see `.room-subtab` buttons in the live file, you're on Model B and the subtab steps below apply. If you see `.room-block`/`.room-row`, you're on Model A and there are no subtabs to edit.

## Adding a new room + subtab

### Step 1: Add subtab button
After the last `<button class="room-subtab" ...>` entry:
```bash
sed -i "/<button class=\"room-subtab\".*Basement/a\          <button class=\"room-subtab\" data-room=\"kitchen\">Kitchen</button>" /root/wall-dash/index.html
```

### Step 2: Add grid
Insert the grid before the closing of the rooms-view. Use a unique marker:
```bash
sed -i "/<div class=\"empty-note\"><svg.*Media<\/span>/i\        <div class=\"rooms-unified-grid single\" id=\"grid-kitchen\" style=\"display:none;\">\n  ...tiles...\n        </div>\n" /root/wall-dash/index.html
```

### Step 3: Add tile(s) inside the grid
Use the `room-tile` pattern:
```html
<div class="tile room-tile">
  <div class="rt-room-label">Room Name</div>
  <div class="rt-icon on"><!-- SVG icon --></div>
  <div class="rt-name">Device Name</div>
  <div class="rt-state">On/Off/State text</div>
  <div class="rt-actions">
    <button class="rt-btn" onclick="..."><svg>...</svg><span>Action</span></button>
  </div>
  <!-- optional slider -->
  <div class="rt-slider">...</div>
  <!-- optional metadata row -->
  <div class="rt-meta">...</div>
</div>
```

## Tile patterns

### Light tile (with brightness slider + scene popover)
```html
<div class="tile room-tile">
  <div class="rt-room-label">Room</div>
  <div class="rt-icon on"><svg class="ic" viewBox="0 0 24 24"><path d="M8.5 3h7l2.2 6.5H6.3L8.5 3z"/><path d="M12 9.5V18"/><path d="M8.5 18h7"/></svg></div>
  <div class="rt-name">Device Name</div>
  <div class="rt-state">On</div>
  <div class="rt-actions">
    <button class="rt-btn" onclick="openGoveePanel('light.entity_id')">...</button>
    <button class="rt-btn" onclick="openScenePopover('input_select.scene_entity')">...</button>
  </div>
  <div class="rt-slider"><svg class="si">...</svg><input type="range" min="0" max="100"><span class="rt-val"></span></div>
</div>
```

### Fan tile (purifier, office fan)
```html
<div class="tile room-tile purifier-cell">
  <div class="rt-room-label">Room</div>
  <div class="rt-icon on" id="X-icon"><svg class="ic">...fan SVG...</svg></div>
  <div class="rt-name" id="X-name">Device Name</div>
  <div class="rt-state" id="X-state">Off</div>
  <div class="rt-actions">
    <button class="rt-btn" id="X-power" onclick="togglePurifier('fan.entity_id')">Power</button>
    <button class="rt-btn" id="X-speed" onclick="cyclePurifierSpeed('fan.entity_id')">Speed</button>
  </div>
  <div class="rt-meta" style="display:flex;gap:1rem;justify-content:center;font-size:0.78rem;margin-top:0.2rem;">
    <span id="X-pm25">PM2.5: --</span>
    <span id="X-air-quality">Air: --</span>
  </div>
</div>
```

### Shield tile (Nvidia Shield with TV bias light)
```html
<div class="tile room-tile shield-cell">
  <div class="rt-room-label">Room</div>
  <div class="rt-icon on"><svg class="ic">...shield/TV SVG...</svg></div>
  <div class="rt-name">Nvidia Shield</div>
  <div class="rt-state">On</div>
  <div class="rt-actions">...</div>
  <div class="rt-slider">...</div>
</div>
```

## JS patterns

### Refresh functions
Each device type needs a refresh function called from `refreshAll()`:

```javascript
function refreshPurifier(fanEntity, iconId, stateId, pm25Id, aqId) {
  const fan = entities[fanEntity];
  if (!fan) return;
  const isOn = fan.state === "on";
  document.getElementById(iconId).className = "rt-icon " + (isOn ? "on" : "");
  document.getElementById(stateId).textContent = isOn ? "On" : "Off";
  // Sensor data
  const pm25Ent = entities[fanEntity.replace("fan.", "sensor.") + "_pm2_5"];
  if (pm25Ent) document.getElementById(pm25Id).textContent = "PM2.5: " + pm25Ent.state + " µg/m³";
}
```

Call from `refreshAll()` after the Sonos sync block:
```bash
sed -i "/sonosStateEl.textContent/a\  refreshPurifier(\"fan.living_room\", ...);" /root/wall-dash/index.html
```

### Service calls
Toggle on/off:
```javascript
function togglePurifier(entityId) {
  const fan = entities[entityId];
  const service = fan.state === "on" ? "turn_off" : "turn_on";
  ws.send(JSON.stringify({id: ++msgId, type: "call_service", domain: "fan", service: service, target: {entity_id: entityId}}));
}
```

Cycle speed:
```javascript
function cyclePurifierSpeed(entityId) {
  const fan = entities[entityId];
  const current = (fan.attributes && fan.attributes.percentage) || 33;
  let pct = current <= 33 ? 66 : current <= 66 ? 100 : 33;
  ws.send(JSON.stringify({id: ++msgId, type: "call_service", domain: "fan", service: "set_percentage", target: {entity_id: entityId}, service_data: {percentage: pct}}));
}
```

## Projects Tab — Named Boards + Dropdown (added 2026-06-10)

The Projects tab renders `kanban-state.json` (pushed by `~/.hermes/scripts/kanban_export.py` every 5 min). As of 2026-06-10 it supports **multiple named boards** with a dropdown selector.

### How boards work

Tasks are routed to boards in `kanban_export.py` by **title prefix** (case-insensitive). The board list is defined in `BOARD_DEFS`:

```python
BOARD_DEFS = [
    {"slug": "dm-voice-board", "name": "DM Voice Board", "prefix": "dm voice board"},
    {"slug": "mealio",         "name": "Mealio",          "prefix": "mealio"},
    {"slug": "default",        "name": "Other",           "prefix": None},  # catch-all
]
```

- First matching prefix wins. `prefix: None` = catch-all for unmatched tasks.
- All boards always appear in the JSON (even if empty), so the dropdown shows them regardless.
- To add a new board: add a `BOARD_DEFS` entry + title your kanban tasks with the matching prefix.

### Adding a new board

1. Edit `~/.hermes/scripts/kanban_export.py` — add entry to `BOARD_DEFS` and `BOARD_ORDER`.
2. No dashboard HTML change needed — the dropdown auto-populates from the JSON.
3. Verify: `python3 ~/.hermes/scripts/kanban_export.py --verbose` then check `/tmp/kanban-state.json`.

### HTML structure (current as of 2026-06-10)

```html
<div id="projects-view" class="view" data-view="projects" hidden>
  <div class="proj-head">
    <div class="proj-head-top">
      <h2 class="sec-title">Projects</h2>
      <select class="proj-board-select" id="proj-board-select">
        <option value="">Loading…</option>
      </select>
    </div>
    <span class="proj-updated" id="proj-updated"></span>
  </div>
  <div class="proj-board" id="proj-board">…</div>
</div>
```

The JS self-contained IIFE at the bottom of `index.html` handles: fetch → populate dropdown → render selected board. Board selection persists within the tab session; re-opening the tab always re-fetches.

### CSS additions (dashboard.css)

`.proj-head` now `flex-direction: column`. `.proj-head-top` is a new flex row holding the title + select. `.proj-board-select` is a styled `<select>` with a custom chevron SVG background.

## After editing

```bash
docker restart wall-dash
```

Verify:
```bash
# ⚠️ nginx binds to the Tailscale IP, NOT localhost — curl localhost:5051 returns nothing
curl -s http://100.119.118.54:5051/ | grep -o 'proj-board-select\|grid-kitchen' | sort | uniq -c
```

## Pitfalls

- **The live file is source of truth — this skill and your memory drift.** This dashboard has been refactored repeatedly (inline CSS → separate `dashboard.css`; subtab/grid model → block/row model). On 2026-06-07 the stored memory note AND this skill both described a `room-subtab`/`grid-<room>` model that no longer matched the live file (which used `.room-block`/`.room-row`). ALWAYS `read_file`/`search_files` the live `index.html` and `dashboard.css` before quoting structure or editing. Never answer "what does the CSS/markup look like" from memory — pull it live first.
- **CSS is in a separate file.** `dashboard.css` (not inline in HTML). Edits to room/tile styling go there, not in `index.html`.
- **NEVER use regex for insertion in this file.** The HTML has too many ambiguous matches — regex substitutions create duplicate elements (esp. duplicate IDs). `getElementById` returns the first match, so duplicates cause empty-looking subtabs. Always use sed with line numbers or unique anchor strings.
- **sed `a`/`r` inserts AFTER the matched line, not inside it.** When inserting a tile inside a grid div, you must insert BEFORE the grid's closing `</div>`, not after an interior line. Example: `sed -i "/<div class=.tile room-tile.*Purifier/a\\...new tile..."` puts the new tile AFTER the purifier tile but still inside the grid. But `sed -i "/<\\/div>.*end of grid/a\\...new tile..."` puts it OUTSIDE the grid — it becomes a loose child of the parent view and appears in EVERY subtab. Always verify nesting with: `grep -n "grid-living-room\|grid-kitchen\|purifier-cell" index.html | head -20` and check that purifier tiles appear between their grid's open and close lines.
- **Always verify no duplicate IDs after edits**: `grep -c "grid-kitchen"` should return 1.
- **Browser cache hides fixes.** After any edit + `docker restart wall-dash`, the user may still see the old broken version. Tell them to hard-refresh (Ctrl+Shift+R). The code can be correct and still appear broken due to cache.
- **Backup before every edit** — the file has many pre-edit snapshots (`.bak-*` files).
- **Container restart required** — nginx caches nothing, but the container needs restart to serve updated files (or touch the file and clear browser cache).
- **Subtab JS is generic** — it queries ALL `.room-subtab` buttons. No per-room JS registration needed. Just match `data-room="X"` with `id="grid-X"`.
- **HA entities must exist** before adding tiles — the WebSocket connection populates the `entities` object at runtime. Missing entities show "--" or "Off" forever.
- **Token prompt** — dashboard uses `localStorage.getItem("ha_token")`. If it prompts on load, generate a long-lived token in HA Profile → Security.
- **`curl localhost:5051` returns nothing.** nginx binds to `100.119.118.54:5051` (Tailscale IP), not `0.0.0.0`. Always curl the Tailscale IP: `curl -s http://100.119.118.54:5051/`. This trips verification after every edit from the host.
