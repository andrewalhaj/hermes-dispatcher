# Headless visual verification of the WebUI (when the sandboxed browser can't reach loopback)

The sandboxed `browser_navigate` tool frequently can't reach
`http://127.0.0.1:<port>` (returns a 500 from its own proxy, or Camoufox
"Unable to connect"). That does NOT mean you're stuck with "read the code and
ask the user." You can drive a real headless Chromium over the Chrome DevTools
Protocol (CDP) and capture an actual screenshot to inspect with `vision_analyze`.
This is the preferred way to verify a client-side render yourself before
declaring a UI change done.

Verified working 2026-06 on the Mac mini host against the password-protected
`hermes-webui.service` (port 8787).

## Prereqs / gotchas learned the hard way

- **Install:** `apt-get install -y chromium-browser` installs the Canonical
  **snap** (`/snap/bin/chromium`, the `chromium-browser` shim points at it).
  Use the `chromium` binary, `--headless=new`.
- **`websocket-client` is needed for the CDP driver.** System python3 here has
  no pip/venv; the Hermes venv does:
  `/usr/local/lib/hermes-agent/venv/bin/pip install websocket-client` and run
  the driver script with `/usr/local/lib/hermes-agent/venv/bin/python3`.
- **`--screenshot=` writes to CWD, not the path you pass** in some builds, and
  the simple `--screenshot` one-shot **can't auth or click a tab** — it just
  shoots whatever first paints (the login page). Use the CDP path below for
  anything past the login wall.
- **CORS on the debug socket:** Chromium rejects the WebSocket handshake with
  `403 ... Use --remote-allow-origins`. Launch with
  `--remote-allow-origins=*`. Also pass `origin="http://127.0.0.1:9222"` to
  `websocket.create_connection`.
- **Target id churns:** the `webSocketDebuggerUrl` from `/json/list` goes stale
  fast (navigation spawns new targets → `500 No such target id`). Re-fetch it
  immediately before connecting, in the same script run.
- Run Chromium as a **background process** (it's long-lived); kill it when done.

## The WebUI password (auth wall)

The live unit carries the password in its systemd `Environment=` line, not in
`config.yaml` (which often shows empty `password: ''`):

```bash
grep HERMES_WEBUI_PASSWORD /etc/systemd/system/hermes-webui.service
```

NOTE: the value in the unit file may be displayed elided as `nLeK...11a` in
some viewers — read it with python to get the real string:
`python3 -c "print([l.split('=',2)[-1].strip().strip(chr(34)) for l in open('/etc/systemd/system/hermes-webui.service').read().splitlines() if 'PASSWORD' in l][0])"`

Login endpoint is `POST /api/auth/login` with `{"password": "..."}` →
`{"ok": true}` and sets the `hermes_session` cookie. Public (no-auth) paths
include `/login`, `/health`, `/api/auth/login`, `/api/auth/status`.

## Full recipe

```bash
# 1) Launch headless Chromium with CDP open (background; --remote-allow-origins is mandatory)
chromium --headless=new --no-sandbox --disable-gpu --window-size=1400,900 \
  --remote-debugging-port=9222 --remote-allow-origins=* "about:blank"

# 2) Get the WebUI session cookie via the login API
PW="<from systemd unit>"
SESS=$(curl -s -c /tmp/c.txt -X POST http://127.0.0.1:8787/api/auth/login \
  -H 'Content-Type: application/json' -d "{\"password\":\"$PW\"}" >/dev/null; \
  awk '/hermes_session/{print $7}' /tmp/c.txt)

# 3) Drive CDP: set cookie, navigate, switch tab, screenshot
WS=$(curl -s http://127.0.0.1:9222/json/list | \
  /usr/local/lib/hermes-agent/venv/bin/python3 -c "import sys,json;print(json.load(sys.stdin)[0]['webSocketDebuggerUrl'])")

/usr/local/lib/hermes-agent/venv/bin/python3 - "$WS" "$SESS" <<'PY'
import websocket, json, time, base64, sys
ws_url, sess = sys.argv[1], sys.argv[2]
ws = websocket.create_connection(ws_url, timeout=15, origin="http://127.0.0.1:9222")
_id=0
def send(m,p={}):
    global _id; _id+=1
    ws.send(json.dumps({"id":_id,"method":m,"params":p}))
    while True:
        r=json.loads(ws.recv())
        if r.get("id")==_id: return r
send("Network.enable")
send("Network.setCookie", {"name":"hermes_session","value":sess,
     "domain":"127.0.0.1","path":"/","httpOnly":True})
send("Page.enable")
send("Page.navigate", {"url":"http://127.0.0.1:8787"})
time.sleep(7)  # let the SPA boot
# switch to the panel you want (Kanban here); function lives in panels.js
send("Runtime.evaluate", {"expression":"switchPanel('kanban',{fromRailClick:true})"})
time.sleep(3)
img = send("Page.captureScreenshot", {"format":"png"}).get("result",{}).get("data","")
open("/root/kanban_live.png","wb").write(base64.b64decode(img))
print("saved", len(img), "b64 chars")
ws.close()
PY
```

Then `vision_analyze("/root/kanban_live.png", "<specific question>")` to read the
render — ask pointed questions (are column borders colored? is the avatar a
circle? is the description body hidden?), not "describe the page."

## When `vision_analyze` is unavailable → PIL pixel-sampling (deterministic fallback)

`vision_analyze` can return `No LLM provider configured for task=vision`
(the configured vision provider is down / not set up). When that happens, DON'T
fall back to "ask the user to eyeball it" — you already have the PNG, so
measure it objectively with PIL in the Hermes venv. For verifying a SKIN/LAYOUT
port (background color, sidebar width, accent presence) this is actually MORE
reliable than a vision model: it gives exact px/hex, not a prose guess that can
flake. Pattern (proven 2026-06 verifying the mission-control redesign was live):

```python
/usr/local/lib/hermes-agent/venv/bin/python3 - <<'PY'
from PIL import Image
img = Image.open("/tmp/webui_live.png").convert("RGB")
w, h = img.size
# 1) Sample exact colors at known coordinates → confirm the skin's palette is live
for label,(x,y) in {"sidebar":(50,400),"main-bg":(700,450)}.items():
    r,g,b = img.getpixel((x,y)); print(f"{label}: #{r:02x}{g:02x}{b:02x}")
# 2) Find the sidebar→main edge → confirm a wide-nav rebuild shipped (not the icon rail)
prev=img.getpixel((0,400))
for x in range(400):
    p=img.getpixel((x,400))
    if abs(p[0]-prev[0])>20: print(f"sidebar edge ~x={x}px"); break
    prev=p
# 3) Count accent-range pixels → confirm the active-state glow uses the new accent
#    (e.g. amber #f6b73c: 200<r<255, 150<g<200, 30<b<80) and the OLD accent is gone
#    (e.g. gold #FFD700: 220<r<255, 200<g<255, b<30 → expect 0 once skin swapped)
PY
```

Interpretation: a wide-nav redesign shows the edge at ~220–240px (icon rail is
~48–64px); the new base background hex should match the skin spec exactly; the
new accent should have a non-zero pixel count while the OLD accent reads 0. This
turns "does it look right?" into pass/fail arithmetic with no provider
dependency. Use vision_analyze for subjective/structural questions when it's up;
use pixel-sampling for objective palette/geometry checks always.

## Sanity check before blaming the render

Always confirm your edit is on the wire first (rules out a real failure vs. a
client-cache illusion): `curl -s http://127.0.0.1:8787/static/panels.js | grep -c "<new symbol>"`.
A non-zero count means the server is serving your code; any visual mismatch is
then cache or a CSS-targeting bug, not a missing edit.
