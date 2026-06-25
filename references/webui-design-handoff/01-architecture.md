# Architecture — How the Standalone File Works

## The DC Bundle Format

`standalone.html` is NOT a normal HTML file. It is a **DC/bundler standalone** — a self-contained app where:

```
standalone.html
├── <head>          — Google Fonts imports (Space Grotesk, Inter, IBM Plex Mono)
├── <script>[0]     — 6.4KB init script (DOMContentLoaded, window globals setup)
├── <script>[1]     — 529KB bundler manifest JSON
│                     { "uuid": { "mime": "...", "compressed": true, "data": "<b64gzip>" } }
│                     Contains: component JS (77KB decoded), runtime CSS, fonts
├── <script>[2]     — [] (empty array)
└── <script>[3]     — 221KB template JSON string
                      The full HTML markup as a JSON-encoded string.
                      This is what the DC runtime renders into the DOM.
                      Contains: all panel HTML, nav rail, sidebar, CSS styles.
```

## What lives where

### CSS / Styling
All CSS lives **inside the template JSON** (`scripts[3]`), as `<style>` blocks within the encoded HTML string. There are two style blocks:

**Style block 0 (13KB)** — Google Font face declarations only (Space Grotesk, Inter, IBM Plex Mono weights).

**Style block 1 (2KB)** — Core resets and animations:
```css
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.09); border-radius: 6px; }
::-webkit-scrollbar-thumb:hover { background: rgba(255,255,255,0.18); }
@keyframes hpulse { 0%,100% { transform: scale(1); opacity: 1; } 50% { transform: scale(0.5); opacity: 0.4; } }
input::placeholder, textarea::placeholder { color: #565d72; }
select option { background: #11151f; color: #cdd2e0; }
```

**Inline styles on elements** — Almost all design is via inline `style="..."` attributes directly on elements in the template. This is the primary place to edit colors, spacing, typography, layout.

**Component JS renderVals** — Dynamic colors/styles that depend on state (e.g. active tab highlight, hover states, tier colors in Galaxy) are computed in the component class's `renderVals()` method in the decoded JS asset.

### The Component JS
Decoded from the manifest's largest JS asset (77KB compressed → ~200KB decoded). Contains:
- `renderVals()` — computes all dynamic state values the template binds to via `{{ key }}`
- `drawGalaxy()` — Canvas 2D 3D scatter renderer for the Memory Galaxy panel
- `ensureSwarm()` + `drawSwarm()` — Canvas 2D particle renderer for Agent Swarm
- Event handlers, API fetch calls, SSE polling

### Template `{{ }}` bindings
In the template HTML, `{{ keyName }}` binds a value from `renderVals()`. These are NOT editable as static text — they're dynamic. Example:
```html
<span style="color: {{ accentColor }}">{{ taskCount }} tasks</span>
```

## How server.py patches the standalone at startup

`server.py` calls `_patch_standalone(html)` once at startup (line 1110). This function applies **54 string-replace patches** to the decoded component JS, injecting real data bindings in place of mock defaults. For example:

```python
# Replace mock galaxy data with real window.__RD_GALAXY__ binding
js = _replace_block(js, "initGalaxyData() {\n    const T = [", "\n  galaxyDecor(", NEW_GALAXY_INIT)
```

**Do NOT edit the template or component JS by modifying `standalone.html` directly in a text editor** — the JS is gzip+base64 encoded. All edits to JS behavior go through new `_replace_block()` / `js.replace()` calls in `server.py`'s `_patch_standalone()` function.

**DO edit the template HTML** (the JSON string in `scripts[3]`) carefully, or add new CSS rules. This is safe because the template is plain HTML-as-JSON.

## How to decode the template for inspection

```python
import re, json

html = open('/root/projects/hermes-webui-new/standalone.html').read()
scripts = re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL)
template_html = json.loads(scripts[3])
# Now template_html is the full HTML string — search/edit it
```

## How `server.py` serves the page

```python
# server.py startup:
raw_html = Path("standalone.html").read_text()
patched = _patch_standalone(raw_html)  # 54 JS patches applied once

# Per request at GET /:
data = _inject_globals(patched)  # Injects __RD_* globals with fresh data
# Returns data as the HTTP response
```

The `_inject_globals()` call inserts a `<script>` block into `<head>` containing:
```js
window.__RD_KANBAN__ = {...};     // live board data
window.__RD_MEMORY__ = {...};     // memory content  
window.__RD_GALAXY__ = {...};     // 3D memory nodes
window.__RD_SWARM__  = {...};     // agent topology
window.__RD_INS__    = {...};     // insights stats
// etc.
```

## Safe edit surface for design work

| What to change | Where to edit | Risk |
|---|---|---|
| Background colors | Inline `style=` in template JSON (`scripts[3]`) | Low |
| Font sizes, weights | Inline `style=` in template JSON | Low |
| Spacing, padding, gaps | Inline `style=` in template JSON | Low |
| CSS animations | Style block 1 in template JSON | Low |
| Hover states / transitions | New `<style>` block in template JSON | Low |
| Dynamic accent colors (heatmap, chart) | `renderVals()` in component JS via `_patch_standalone` | Medium |
| Canvas rendering (Galaxy appearance) | `drawGalaxy()` in component JS via `_patch_standalone` | Medium |
| Panel layout/structure | Template HTML in `scripts[3]` | Medium |
| Nav rail structure | Template HTML in `scripts[3]` | Medium — test switchPanel() still works |
| Adding new CSS vars | New `<style>` block + replace inline hex with `var(--name)` | Low-Medium |

## The `_replace_block` helper

For safe multi-line JS replacements in `server.py`:

```python
def _replace_block(js: str, start_marker: str, end_marker: str, replacement: str) -> str:
    si = js.find(start_marker)
    ei = js.find(end_marker, si)
    if si < 0 or ei < 0:
        logger.warning("_replace_block: marker not found")
        return js
    # CRITICAL: replacement must NOT repeat the end_marker
    # js[ei:] already provides it
    return js[:si] + replacement + js[ei:]
```

**Pitfall:** If your `replacement` string accidentally contains the `end_marker` text, the resulting JS will have it doubled → `Unexpected token ';'` → blank main panel. Always end your replacement one token *before* the `end_marker`.
