# Camofox self-host on x86_64 — two sequential bugs, both fixed

Building `github.com/jo-inc/camofox-browser` from source on x86_64
(`make build/up ARCH=x86_64`, Camoufox 135.0.1) hits TWO independent defects.
**Bug #1 masks Bug #2:** the browser can't launch at all until #1 is fixed, so #2
stays invisible. After fixing #1, the browser launches but `POST /tabs` still 500s
until #2 is also fixed. Fix BOTH in one rebuild to avoid a confusing "I fixed it but
it's still broken" cycle.

Both fixes were verified end-to-end in-session: `Browser_navigate` to a Cloudflare
JS-challenged page (Reddit) returned the full DOM with `?solution=...&js_challenge=1`
in the resolved URL — i.e. Camofox + residential IP passed the challenge.

The fixes live in the **host clone** (`/root/web-stack/camofox-browser/`), which the
Dockerfile `COPY`s from — so a rebuild bakes them in durably (survives `make reset`).
These are upstream bugs; consider a PR to `jo-inc/camofox-browser`. Do NOT record them
as "Camofox is broken" — they are specific, fixed defects.

---

## Diagnosis order (don't skip /health's lie)

`curl http://localhost:9377/health` returns `{"ok":true,"browserConnected":...}` and is
a FALSE POSITIVE — it can say `browserConnected:true` (after #1 fix) while `/tabs` still
500s (#2). The only trustworthy probe is an actual navigation:

```bash
Browser_navigate https://example.com      # or:
curl -s -X POST http://localhost:9377/tabs -H 'Content-Type: application/json' \
  -d '{"userId":"t","sessionKey":"t","url":"https://example.com"}'
docker logs camofox-browser --tail 30     # read the REAL error here
```

---

## Bug #1 — unawaited Xvfb display Promise

**Symptom.** Every launch fails; logs show an empty display then a stringified Promise:
```
{"msg":"xvfb virtual display started","display":{},"attempt":1}          <-- display = {} (a pending Promise)
{"msg":"camoufox launch attempt failed",
 "error":"...Error: cannot open display: [object Promise]..."}            <-- DISPLAY = "[object Promise]"
```

**Root cause.** `node_modules/camoufox-js/dist/virtdisplay.js` declares `async get()`
(it spawns Xvfb with `-displayfd 3` and awaits the display number). The wrapper calls
it WITHOUT `await` in `server.js` → `launchBrowserInstance()` (~line 955):

```js
localVirtualDisplay = pluginCtx.createVirtualDisplay();
vdDisplay = localVirtualDisplay.get();    // BUG: Promise, not ":N"
```
`vdDisplay` (a Promise) is passed to `launchOptions({ virtual_display: vdDisplay })`,
stringifies to `[object Promise]`, and Firefox tries to open a display by that literal
name. `Xvfb`/`xvfb-run` ARE installed — the X tooling is fine; only the `await` is missing.

**Fix** (enclosing `launchBrowserInstance` is already `async`):
```diff
-        vdDisplay = localVirtualDisplay.get();
+        vdDisplay = await localVirtualDisplay.get();
```
After fix, the log shows a real display: `"display":":0"`.

---

## Bug #2 — playwright-core / Camoufox version skew (lockfile bypass)

**Symptom (only visible after #1 is fixed).** Browser launches, `browserConnected:true`,
but `POST /tabs` 500s:
```
browser.newContext: Protocol error (Browser.setDefaultViewport): ... parameters
  { "viewport": { ..., "isMobile": false } }
Found property "<root>.viewport.isMobile" - false which is not described in this scheme
```

**Root cause.** `Dockerfile` line ~62 is `RUN npm install --production`. `npm install`
does NOT respect the committed `package-lock.json` — it re-resolves `^1.58.0` to the
LATEST `playwright-core` (observed 1.61.0, targeting Firefox ~143). That Playwright sends
a viewport object with an `isMobile` field the **Camoufox 135** binary's older Juggler
protocol doesn't recognize, so `newContext` is rejected. The lockfile pins the tested
**1.59.1**.

Version skew check:
```bash
docker exec camofox-browser sh -c 'cat /app/node_modules/playwright-core/package.json | grep version'   # was 1.61.0
python3 -c "import json;d=json.load(open('package-lock.json'));[print(k,v.get('version')) for k,v in d['packages'].items() if k.endswith('playwright-core')]"  # pins 1.59.1
docker exec camofox-browser sh -c 'cat /root/.cache/camoufox/version.json'                                # 135.0.1 beta.24
```

**Fix** — make the build honor the lockfile (also COPY it in):
```diff
-COPY package.json ./
+COPY package.json package-lock.json ./
 COPY scripts/ ./scripts/
-RUN npm install --production
+RUN npm ci --omit=dev
```
`npm ci` requires `package-lock.json` present and installs EXACTLY its pins. After
rebuild, `playwright-core` is 1.59.1 and `/tabs` succeeds.

**General lesson:** when a Dockerized Node app breaks right after a `--no-cache` rebuild
but no source changed, suspect `npm install`-vs-`npm ci` lockfile drift first. Prefer
`npm ci` in any reproducible image build.

---

## Rebuild + verify loop

```bash
cd /root/web-stack/camofox-browser
# (apply both diffs to server.js and Dockerfile first)
make build ARCH=x86_64            # --no-cache; ~2-3 min. Watch for "added N packages" from npm ci.
make down && make up ARCH=x86_64  # recreate container from fixed image
docker exec camofox-browser sh -c 'cat /app/node_modules/playwright-core/package.json | grep version'  # expect 1.59.1
sleep 12
curl -s http://localhost:9377/health        # browserConnected:true (necessary, NOT sufficient)
Browser_navigate https://example.com         # REAL test: expect success + DOM snapshot
# Stretch test (the whole point): navigate a Cloudflare/JS-challenge site; expect full page,
# resolved URL containing ?solution=...&js_challenge=1
```

`make up` runs `docker run -d --restart unless-stopped --name camofox-browser -p 9377:9377 <IMAGE>`
— so restart-policy persistence is already handled by `make up`.
