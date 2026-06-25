# Editing Workflow — How to Safely Make Changes

---

## Setup (one-time)

```bash
# Verify the service is running
systemctl status hermes-webui --no-pager | head -5

# Confirm the served file
grep "WorkingDirectory" /etc/systemd/system/hermes-webui.service
# → /root/projects/hermes-webui-new

# Get the auth password
grep HERMES_WEBUI_PASSWORD /root/projects/hermes-webui-new/.env
```

---

## Before any edit

```bash
# ALWAYS backup first
cp /root/projects/hermes-webui-new/standalone.html \
   /root/projects/hermes-webui-new/standalone.html.bak-$(date +%s)
```

---

## Type 1: Template HTML edits (colors, spacing, typography, layout)

These are edits to the HTML inside `scripts[3]` — the template JSON string.

### Read the current value first

```python
import re, json

html = open('/root/projects/hermes-webui-new/standalone.html').read()
scripts = re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL)
template = json.loads(scripts[3])

# Search for the element you want to change
idx = template.find('YOUR_SEARCH_TERM')
print(template[max(0,idx-200):idx+500])
```

### Make the edit (via server.py patch OR direct template edit)

**Option A — via server.py `_patch_standalone`** (recommended for anything non-trivial):

Add a new `str.replace` call inside `_patch_standalone()`:
```python
# server.py, inside _patch_standalone(html):
# Change the hero background color
html = html.replace(
    'background: #0a0c10; position: relative;',
    'background: #080b14; position: relative;'
)
```

**Option B — direct edit to standalone.html** (for simple one-off color changes):

Use the `patch` tool (not sed/awk — use the patch MCP tool which handles encoding):
```
patch(
  path="/root/projects/hermes-webui-new/standalone.html",
  old_string='background:#0a0c10',
  new_string='background:#080b14'
)
```

⚠️ Be careful with JSON escaping — the template is inside a JSON string, so `"` must be `\"` and backslashes must be doubled.

---

## Type 2: JS behavior edits (animations, dynamic colors, canvas rendering)

These go through `_patch_standalone()` in `server.py`. The component JS is gzip+base64 encoded and cannot be edited directly.

### Step 1: Extract and inspect the current JS

```python
import re, json, base64, gzip

html = open('/root/projects/hermes-webui-new/standalone.html').read()
# Apply patches to get the PATCHED JS (same as what server.py serves)
import sys; sys.path.insert(0, '/root/projects/hermes-webui-new')
import server
raw = open('/root/projects/hermes-webui-new/standalone.html').read()
patched = server._patch_standalone(raw)

# Extract the component JS
scripts_patched = re.findall(r'<script[^>]*>(.*?)</script>', patched, re.DOTALL)
manifest = json.loads(scripts_patched[1])
for k, v in manifest.items():
    if 'javascript' in v.get('mime', '') and v.get('compressed'):
        js = gzip.decompress(base64.b64decode(v['data'] + '==')).decode('utf-8', errors='replace')
        # Save for inspection
        open('/tmp/component.js', 'w').write(js)
        print(f"Extracted {len(js)} chars to /tmp/component.js")
        break
```

### Step 2: Find your target in the extracted JS

```bash
grep -n "YOUR_SEARCH_TERM" /tmp/component.js | head -20
# or
grep -n "drawGalaxy\|ensureSwarm\|renderVals" /tmp/component.js | head -30
```

### Step 3: Write the patch in `_patch_standalone()`

```python
# Inside server.py _patch_standalone(html: str) -> str:
# Find the start/end markers (unique strings around what you want to change)
js = js.replace(
    "EXACT_OLD_STRING_FROM_COMPONENT_JS",
    "NEW_STRING"
)
# OR for multi-line:
js = _replace_block(js,
    "UNIQUE_START_MARKER",
    "UNIQUE_END_MARKER",   # this stays; don't repeat it in replacement
    "YOUR_NEW_CODE\n"
)
```

### Step 4: Verify JS syntax BEFORE restart

```bash
# From the hermes-webui-new dir, run the check script
cd /root/projects/hermes-webui-new
HERMES_HOME=/root/.hermes /usr/local/lib/hermes-agent/venv/bin/python \
  scripts/check_patched_js.py
# → exit 0 = safe to restart
# → any error = fix the patch first
```

If `check_patched_js.py` doesn't exist or fails, do it manually:

```bash
# Extract patched JS and node --check it
HERMES_HOME=/root/.hermes /usr/local/lib/hermes-agent/venv/bin/python << 'EOF'
import re, json, base64, gzip, sys
sys.path.insert(0, '/root/projects/hermes-webui-new')
import server
raw = open('/root/projects/hermes-webui-new/standalone.html').read()
patched = server._patch_standalone(raw)
scripts = re.findall(r'<script[^>]*>(.*?)</script>', patched, re.DOTALL)
manifest = json.loads(scripts[1])
for k, v in manifest.items():
    if 'javascript' in v.get('mime', '') and v.get('compressed'):
        js = gzip.decompress(base64.b64decode(v['data'] + '==')).decode('utf-8', errors='replace')
        open('/tmp/check_js.js', 'w').write(js)
        print(f"Written {len(js)} chars"); break
EOF
node --check /tmp/check_js.js && echo "✓ JS OK" || echo "✗ SYNTAX ERROR"
```

---

## Restarting the service

The restart is write-gated. Present what changed, then:

```bash
# Arm the gate (get epoch first)
date +%s  # e.g. 1781914000
# Write grant (valid 10min)
# write_file /root/.hermes/.write_gate_grant:
# {"armed_at": 1781914000, "expires": 1781914600, "note": "approved webui restart"}

# Then restart
systemctl restart hermes-webui
sleep 3
systemctl status hermes-webui --no-pager | head -5
```

---

## Visual verification via CDP screenshot

```bash
# Start headless Chromium (background)
# Then in a new terminal:
WS=$(curl -s http://127.0.0.1:9223/json/list | python3 -c "import sys,json; d=json.load(sys.stdin); print(d[0]['webSocketDebuggerUrl'])")

python3 - "$WS" << 'PYEOF'
import sys, json, base64, time, urllib.request, http.cookiejar
import websocket

WS = sys.argv[1]
PW = open('/root/projects/hermes-webui-new/.env').read()
PW = [l.split('=',1)[1].strip() for l in PW.splitlines() if 'PASSWORD' in l][0]

ws = websocket.create_connection(WS)
_id = [0]
def send(method, params=None):
    _id[0] += 1
    ws.send(json.dumps({"id": _id[0], "method": method, "params": params or {}}))
    while True:
        r = json.loads(ws.recv())
        if r.get("id") == _id[0]: return r

send("Network.enable")
req = urllib.request.Request("http://127.0.0.1:8787/api/auth/login",
    data=json.dumps({"password": PW}).encode(), headers={"Content-Type": "application/json"}, method="POST")
cj = http.cookiejar.CookieJar()
urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj)).open(req)
session_val = next((c.value for c in cj if c.name == "hermes_session"), "")
send("Network.setCookie", {"name": "hermes_session", "value": session_val, "domain": "127.0.0.1", "path": "/"})
send("Page.navigate", {"url": "http://127.0.0.1:8787/"})
time.sleep(4)
r = send("Page.captureScreenshot", {"format": "png"})
png = base64.b64decode(r["result"]["data"])
open("/tmp/verify.png", "wb").write(png)
print(f"Screenshot: /tmp/verify.png ({len(png)} bytes)")
ws.close()
PYEOF
```

Then use `vision_analyze(image_url="/tmp/verify.png", question="Did the change land correctly?")`.

---

## Common traps

### Trap 1: `_replace_block` end-marker doubled
```python
# WRONG — repeats the end marker inside the replacement
js = _replace_block(js, "START", "};", "NEW CODE\n};")
#                                          ^^^^ doubled!

# RIGHT — replacement ends one token before the end marker
js = _replace_block(js, "START", "};", "NEW CODE\n")
# js[ei:] provides the "};" automatically
```

### Trap 2: JSON escape in template string
The template is encoded as a JSON string. Inside it:
- `"` must be `\"` 
- `\n` must be `\\n`
- `\` must be `\\`

When using `str.replace` on the raw HTML (before `json.loads`), you're working in the JSON-encoded layer. Test by searching for your exact string with escapes:
```python
assert '\\\"YOUR_TERM\\\"' in html  # json-encoded layer
# vs:
template = json.loads(scripts[3])
assert '"YOUR_TERM"' in template    # decoded layer
```

### Trap 3: Editing the raw standalone vs the patched version
`server.py` patches the JS at startup. The raw `standalone.html` still has the mock data. Always inspect the **patched** version (run `server._patch_standalone(raw)`) to see what's actually served. Searching the raw file for `initGalaxyData` will show the old mock version, not the patched real-data version.

### Trap 4: Cache
After a server restart, the browser may serve cached assets. Hard-refresh (Ctrl+Shift+R) or use the CDP flow above (it bypasses cache).

### Trap 5: `</script>` inside template JSON
The template JSON contains HTML including `</script>` tags (inside `<template>` elements, etc). If you try to use regex to find `</script>` boundaries in the raw HTML, it will match these inner occurrences and truncate prematurely. Use the `json.loads(scripts[3])` approach to get the decoded template first.
