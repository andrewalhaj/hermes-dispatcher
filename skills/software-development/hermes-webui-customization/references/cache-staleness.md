# WebUI static-asset edits "do nothing" — the frozen cache-key trap

The single most common dead-end when editing the vanilla-JS WebUI
(`/root/projects/hermes-webui/static/*`): you patch `style.css` / `panels.js`,
the user reloads, and **the page looks identical**. The edit did NOT fail — the
browser is serving a cached copy. Root-caused 2026-06.

## The mechanism

`static/index.html` loads assets with a version query:

```html
<link rel="stylesheet" href="static/style.css?v=__WEBUI_VERSION__">
<script src="static/panels.js?v=__WEBUI_VERSION__" defer></script>
```

The server substitutes `__WEBUI_VERSION__` at request time with `WEBUI_VERSION`
(see `api/updates.py`). `WEBUI_VERSION` is a **module-level constant computed
ONCE at process startup**:

```python
WEBUI_VERSION = _detect_webui_version()   # git describe --tags --always --dirty
# dirty suffix = "-dirty-" + sha1(git diff HEAD)[:8]   (see _dirty_suffix)
```

So the token = git tag + a hash of the working-tree diff **as it was when the
server started**. An edit you make *after* startup does not change the token the
running server hands out. The browser therefore keeps requesting the exact same
`style.css?v=<old-token>` URL it already has — and both the HTTP cache and the
service worker's CacheStorage (`static/sw.js`, `CACHE_NAME =
hermes-shell-<token>`) return the stale bytes.

Key insight: **the file on disk is correct AND the server serves the new bytes
when asked for them — the browser just never asks for the new URL.** This is why
"grep the disk" and even "grep the served file" both look fine while the page
stays stale.

## Diagnose in order (don't re-edit blindly)

1. **Prove the new code is on the wire** (rules out a real edit failure):
   ```bash
   PW=$(grep -oE 'HERMES_WEBUI_PASSWORD=[^"]+' /etc/systemd/system/hermes-webui.service | cut -d= -f2)
   curl -s "http://127.0.0.1:8787/static/style.css?v=anything" \
     -H "X-Hermes-WebUI-Password: $PW" | grep -c "<a string from your new rule>"
   ```
   `1` → your change IS served; the issue is purely client-side cache. `0` →
   you edited the wrong file / wrong dir (re-check the live served directory via
   `systemctl status hermes-webui`).

2. **Confirm the token is frozen**: compare server start time to your edit time.
   ```bash
   systemctl show hermes-webui -p ActiveEnterTimestamp --value
   stat -c '%y' /root/projects/hermes-webui/static/style.css
   ```
   Edit newer than start time + token unchanged = frozen-cache-key confirmed.

## Fix — ranked

1. **`hardRefreshWebUIClient()` in the browser console** (zero-risk, no
   restart). It's a built-in function in `panels.js`: unregisters all service
   workers, deletes all CacheStorage keys, reloads. Because the current SW is
   network-first for shell assets, after this the browser fetches fresh on every
   future reload — the trap won't recur on that browser. Manual equivalent:
   ```js
   navigator.serviceWorker.getRegistrations().then(r=>r.forEach(x=>x.unregister()));
   caches.keys().then(k=>k.forEach(x=>caches.delete(x)));
   location.reload();
   ```

   **Telling the user how to run it (they're often on Windows, not a Mac/Linux
   shell).** Give platform-correct keystrokes — don't just say "open the
   console":
   - Open DevTools on the focused WebUI tab: **`F12`**, or Console directly with
     **`Ctrl+Shift+J`** (Chrome/Edge) / **`Ctrl+Shift+K`** (Firefox). macOS:
     `Cmd+Option+J` / `Cmd+Option+K`.
   - Click into the Console prompt, type `hardRefreshWebUIClient()`, press Enter.
   - If the console blocks pasting ("Allow pasting" self-XSS warning), have them
     type the confirmation phrase first, or just type the short command by hand.
   - **`hardRefreshWebUIClient is not defined` is EXPECTED here**, not an error:
     the browser is still running the OLD cached `panels.js` that predates the
     function (or predates your edit). Give them the inline one-liner fallback —
     it needs no app code and does the same thing:
     ```js
     navigator.serviceWorker?.getRegistrations().then(rs=>Promise.all(rs.map(r=>r.unregister()))).then(()=>caches.keys()).then(ks=>Promise.all(ks.map(k=>caches.delete(k)))).then(()=>location.reload(true))
     ```
   - **Plain `Ctrl+Shift+R` / `Cmd+Shift+R` alone usually does NOT fix it** — the
     registered service worker re-serves the cached shell. Say so explicitly so
     the user doesn't "try a hard refresh," see no change, and conclude the edit
     failed.

2. **`systemctl restart hermes-webui`** — regenerates `WEBUI_VERSION` (its diff
   hash now includes your edits), so every open browser cache-misses and pulls
   fresh with no console needed. CAVEAT: this server renders the live WebUI
   chat. A restart drops the current session's connection for ~5s and
   interrupts the in-flight turn (history survives in the session DB; the socket
   blips). It's an infra action — get explicit user OK, never do it unprompted.

## Why a plain reload sometimes "should" work but doesn't

The shipped `sw.js` IS network-first for shell assets (it fetches with
`cache: 'no-store'` and only falls back to cache on network failure). But an
*older* SW version may still be the registered controller in the user's browser
until it's replaced — and the HTTP disk cache can still satisfy the identical
`?v=` URL before the SW even runs. That's why the deterministic fix is to clear
the SW + CacheStorage (option 1), not to trust a soft reload.
