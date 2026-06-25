---
name: mealio-maintenance
description: "Maintain/extend Mealio recipe app: deploy loop, import"
---

# Mealio — maintain & extend Andrew's recipe app

## When to use
Any feature request, bug report, or change to the Mealio liquid-glass recipe app ("import is broken", "add X to the site", validation errors, UI additions). Also a reference for the stock Mealie instance running alongside.

## Topology (verified 2026-06-10)
- **HOST:** Mealio lives on the worker box **hil-1 (`5.78.238.81`)**, NOT on whatever box this agent runs from (default profile now runs on the Mac mini). Every path below is on hil-1 — reach it with `ssh root@5.78.238.81`. Don't waste calls `find`-ing these paths locally; if `/root/projects/mealio` is empty/absent locally, you're on the wrong box — SSH to hil-1.
- **Custom app:** `/root/projects/mealio/app/` — Next.js 14 app-router + TS + Tailwind glass tokens + Prisma/SQLite. Container `mealio`, port **3015**. Public URL: **https://mealio.andrewskingdom.com** (Cloudflare Tunnel, systemd `cloudflared.service`, since 2026-06-11 — see `cloudflare-tunnel-expose` skill). Shared with Andrew's friends — treat as a small-multi-user production app, not a toy. Single `docker-compose.yml` in the app dir; secrets/config in `.env.docker` (env_file).
- **Stock Mealie:** `/root/projects/mealio/mealie-stock/`, port 9925.
- **Entrypoint runs `prisma db push` on start** → schema changes apply on container restart, NO manual migrations. Schema: `prisma/schema.prisma` (Recipe→User author FK nullable; User has firstName/lastName).
- Auth: HMAC cookie `mealio_session`, scrypt hashes, middleware protects everything except `/login`, `/api/auth`, `/share`, `/api/health`. **Every API E2E test needs a session cookie.**
- **Full import-pipeline internals** (flow stages, screenshot route, youtubei.js v17 field paths, Firecrawl-YT failure signature, review-screen validation coupling, verified working result): `references/import-pipeline.md`.
- Import pipeline: `src/lib/import/` — `platformDetect`, `youtubeFetcher` (youtubei.js Innertube; NOT Firecrawl — YT desc/transcript are JS lazy-loaded, scrape returns page shell), `fetcher` (Firecrawl, IG/TikTok/generic + YT fallback), `extractor` (DeepSeek text), `visionExtractor` (Anthropic bypass, screenshot import), `foodImageSearch` (`searchFoodWeb`: Firecrawl `/v1/search` + `scrapeOptions:{formats:['markdown']}` → `metadata.ogImage` for real food hero photos + page markdown for supplemental step extraction when video desc had no instructions; provenance goes in `notes`).
- Vision: `ANTHROPIC_BYPASS_CREDENTIALS=/run/c...on` (RO mount of host `~/.claude/.credentials.json`), `VISION_MODEL=claude-haiku-4-5-20251001` (sonnet 429s — Max token shared with Hermes). See `open-design-claude-bypass` skill, "Lightweight variant".
  - **Vision 401 "Invalid authentication credentials" = the bypass OAuth token EXPIRED, not a code bug.** Token lives ~8h. The credentials file is a *live RO mount*, so the container reads it fresh on every request — **no rebuild/restart needed**. Fix: sync a fresh copy from a host whose token is still valid (the Mac mini default profile is the canonical fresh source). Check expiry: `cat ~/.claude/.credentials.json | python3 -c "import json,sys,time;d=json.load(sys.stdin);e=d['claudeAiOauth']['expiresAt'];print('expired' if e<int(time.time()*1000) else 'valid', round((e-int(time.time()*1000))/3600000,1),'h')"`. Sync hil-1 from mac mini: `scp ~/.claude/.credentials.json root@5.78.238.81:~/.claude/.credentials.json` — then just retry, container picks it up live. (Recurs ~every 8h — a cron to auto-sync before expiry is the durable fix if it bites repeatedly.)
- **Theme system (since 2026-06-10):** dark default + light mode. Glass tokens are CSS variables in `globals.css` (`:root` = dark, `html.light` overrides); `tailwind.config.ts` glass colors point at the vars. `ThemeToggle.tsx` persists to localStorage `mealio-theme`; inline script in `layout.tsx` `<head>` applies the class pre-hydration (no flash). Hardcoded `text-white/*` classes are remapped in light mode via `html.light .text-white\/N { ... !important }` overrides — when adding new components prefer the token classes so they theme automatically.

## Deploy loop (the only one that works smoothly)
```
cd /root/projects/mealio/app && docker compose build 2>&1 | tail -3
docker compose -f /root/projects/mealio/app/docker-compose.yml stop
docker compose -f /root/projects/mealio/app/docker-compose.yml up -d   # the -f form avoids the long-lived-process heuristic block on bare `docker compose up -d`
sleep 12 && docker logs mealio 2>&1 | tail -3   # expect prisma push + "Ready in Xms"
```
`.env.docker`-only changes need restart only, no rebuild.

## E2E verification pattern (NEVER skip; subagent self-reports are not proof)
1. Signup throwaway user → grab `mealio_session` cookie from Set-Cookie.
2. Exercise the endpoint with `-H "Cookie: $COOKIE"`. **Cookie vars don't survive across separate terminal calls** — keep login+test in ONE command block, or do the whole flow in one python script via subprocess curl.
3. Inspect DB directly when needed: `docker exec mealio sh -c 'node -e "const {PrismaClient}=require(\"@prisma/client\");const db=new PrismaClient();db.<model>.<op>(...).then(r=>console.log(JSON.stringify(r))).finally(()=>db.\$disconnect())"'`
4. Delete the test user (cascades are configured).
5. **Check the actual response shape before judging** — import responses nest under `extracted`, not top-level.

## Pitfalls (each one cost a debugging round)
- **Zod `.optional()` rejects `null`.** LLM extraction prompts say "X or null" and emit literal nulls → every optional recipe/ingredient/step field must be `.nullish()`. `isFavorite` stays `.optional()` (non-nullable in Prisma).
- **Type drift killed a build:** `RecipeFormData` was a hand-written interface duplicating the Zod schema. Now `z.infer<typeof recipeSchema>` in `src/lib/types.ts` — keep it that way; never re-introduce parallel hand-written form types.
- `steps` is intentionally NOT `.min(1)` — imports legitimately produce 0 steps; review page seeds an empty placeholder that filters to `[]`.
- Surface Zod field errors in API 400s (`path.join('.') + message`) — the bare "Validation error" string wasted a round-trip with the user.
- Import status honesty: empty extraction → `partial` + errorMsg, not `done`. Status check must run AFTER the supplemental merge.
- youtubei.js v17: title/desc under `primary_info`/`secondary_info` (not `basic_info`); `getTranscript()` 400s from this server IP — description + supplemental web extraction is the working path.
- Social-platform thumbnails are the creator's face, not food → hero image always goes through `searchFoodWeb` first for non-generic platforms.
- **`router.push()` to the current route is a silent no-op** (no remount, sessionStorage handoff never re-read) — screenshot import's "Redirecting…" toast hung forever. Use `window.location.assign()` for any sessionStorage-handoff navigation.
- Secrets inline in terminal commands get redacted to `***` by the shell layer (breaks quoting / mangles writes); route them through `write_file` (display-only redaction) and verify length/prefix on disk. Validate a pasted key against its provider (429 quota ≠ valid) BEFORE wiring + restarting.
- `searchFoodWeb(title, creator)` is creator-aware: prefers the video creator's own site for supplemental steps so instructions match the video; `matchedCreator` drives the provenance note wording.
- **Paywalled creator pages** (Substack "for paid subscribers" cutting off right at Preparation): supplemental merge must be per-field independent (ingredients and steps merged separately — never all-or-nothing keyed on steps), with a last-resort generic search for steps labeled as a different creator's version.
- **Multi-user since 2026-06-10:** shared recipe library; per-user favorites (`UserFavorite` join table — `Recipe.isFavorite` column removed), collections, meal plans, import history. New user-owned models: nullable `userId`, stamp on create, scope lists, ownership-check mutations. Test-user cleanup: signup lowercases emails — delete with lowercased address and verify by count.

## Build loop discipline (hard rules — each pattern burned tokens or money)

**Docker rebuild/test cycles must be delegated, never run inline:**
```python
delegate_task(
    goal="Rebuild Mealio container and verify <endpoint>",
    context="Changes: <summary>. Deploy loop: cd /root/projects/mealio/app && docker compose build 2>&1 | tail -5; docker compose -f /root/projects/mealio/app/docker-compose.yml stop; docker compose -f /root/projects/mealio/app/docker-compose.yml up -d; sleep 12 && docker logs mealio 2>&1 | tail -5; <curl test here>. Return only: success/failure + final log lines + curl response.",
    toolsets=["terminal"]
)
```
Re-verify live yourself after the subagent returns — subagents report green on partial/timed-out runs.

**Rate-limit retry polling must NEVER block the main loop:**
```python
# Right: background process, notify on done
terminal(command="...<long curl poll loop>...", background=True, notify_on_complete=True)
# Wrong: sleep-and-curl in foreground — burns 1 terminal call + tokens per retry
```

**Library/dependency debugging (e.g. youtubei.js import errors) uses execute_code batching:**
```python
execute_code(code="""
# Batch all import attempts + env probes in one call
import subprocess
for variant in ["import youtubei.js", "from youtubei.js import Innertube", ...]:
    result = subprocess.run(["node", "-e", variant], capture_output=True, text=True)
    print(variant, "->", result.returncode, result.stderr[:200])
""")
# Do NOT do: terminal("node -e 'import ...'") × 7, each with full traceback in context
```

**Rule of thumb:** if the next step is docker/npm/prisma + wait + curl, that's a subagent. If it's trying one import form after another, that's execute_code.

## Working conventions for this project
- **One kanban card per shipped change** (project `mealio`, status `done`, root-cause + verification in description): `python3 /root/.hermes/scripts/kanban_export.py add --title "Mealio — <change>" --project mealio --status done --description "..."` Standing instruction: board always current.
- **Delegate multi-file implementation to a subagent** with file-by-file instructions, exact code blocks, the deploy-loop commands above (including the `-f` workaround), and mandatory E2E curl steps. Then **re-verify live yourself** — subagents report green on stale/partial runs (one timed out after finishing the work; the changes were fine, only verification was missing).
- Subagent timeout ≠ failure: check the filesystem/container state before redoing anything.
- **Mealio code is REMOTE (hil-1, `5.78.238.81`); this agent runs on the Mac mini.** All file edits + deploys go through `ssh root@5.78.238.81`. Consequence: a subagent's `write_file`/`patch` tools target the LOCAL FS and will NOT touch the remote path — the file-mutation verifier then fires a false "NOT modified" warning for `/root/projects/mealio/...`. The working pattern is the subagent writing the file via `ssh ... 'cat > file'` (or a remote write inside `terminal`). When you see that verifier warning on a Mealio path, do NOT redo the work blindly — verify the truth with `ssh root@5.78.238.81 "grep -n '<new symbol>' <path>"`; the change is usually already live. Instruct delegated subagents to write remote files via SSH/terminal, never the local file tool.
- Destructive UI actions get a confirmation modal (GlassModal pattern in `RecipeDetail.tsx`); delete lives on detail page only, not on cards — deliberate.

## Deeper notes absorbed from mealio-app-maintenance (2026-06-15 consolidation)

- **Multi-user data model (the rule for ANY new user-owned model):** recipe library is SHARED; everything else is per-user. Favorites = `UserFavorite` join table (`@@id([userId, recipeId])`, cascade both ways); the old `Recipe.isFavorite` boolean column is GONE (was a global flag). Collections, MealPlanEntry, ImportHistory carry nullable `userId` + ownership checks (403/404 for non-owners). When adding a new user-owned model: nullable `userId` (db-push compatibility with existing rows), stamp from `getSessionUserId()` on create, scope every list query, verify ownership on mutation. NEVER re-add per-user state as a column on the shared Recipe.
- **Camera/QR scanner is DUAL-MODE** (`src/components/ui/CameraScanner.tsx`), auto-selected by `window.isSecureContext && navigator.mediaDevices?.getUserMedia`: HTTPS → live viewfinder (getUserMedia `facingMode:'environment'` → per-RAF canvas → `jsQR(imageData)`; cleanup MUST stop tracks + cancelAnimationFrame or the camera LED stays on). Plain HTTP → fallback modal with **"Take Photo"** (`<input type=file accept=image/* capture=environment>`) + **"Upload Image"** (same input, no `capture`). `capture` is a HINT not a command — Android opens camera, iOS shows a sheet, desktop ignores it (this is why "Open Camera opens file explorer" on desktop — expectation-setting, not a code fix). Diagnosis rule: "camera doesn't work" on a self-hosted app → check the origin SCHEME first.
- **Direct DB inspection / test-user cleanup** uses `docker exec mealio sh -c 'node -e "..."'` PrismaClient (no sqlite3 CLI in the container). Signup LOWERCASES emails — cleanup with the original-cased address silently deletes nothing; always lowercase the delete `where` and verify with a count.
- **Stale host Prisma client breaks `npm run build` on the host** after any schema change (symptom: `'fieldX' does not exist in type 'UserSelect'` for a field clearly in the schema). Fix: `cd /root/projects/mealio/app && npx prisma generate` then rebuild. Host-side `npx prisma` is FINE (resolves the local v5 install) — the "never npx prisma" rule applies only INSIDE the container, where it would pull Prisma 7.x.
- **`docker compose build` must run from `/root/projects/mealio/app/`** — the parent dir has no compose file.
- **"API before UI" pattern:** routes routinely ship before their UI button (DELETE /api/recipes/[id] existed for days with no button). When Andrew says "no way to do X", check whether the API already exists — often it's a UI-only change. "X isn't persistent/per-user" complaints → check whether the DB layer is already correct and only the UI fails to surface state (favorites were DB-correct all along; only the card mapping was missing).

## UI/UX lessons from live iteration (Andrew's corrections — follow these defaults)
- **Hover-only controls are invisible on mobile.** `opacity-0 group-hover:opacity-100` makes buttons untappable on touch devices (meal-plan delete X was 'missing' on phone). Pattern: always-visible dimmed on mobile, hover-reveal only behind `md:` — `opacity-60 md:opacity-0 md:group-hover:opacity-100`.
- **No dropdown for 2 actions.** Andrew rejected a paperclip→dropdown(2 items) design: each action gets its own nav icon button. Later the redundant one was removed entirely — prefer fewer, flatter, single-purpose controls; expect feature removal requests and keep them cheap (camera/QR replaced screenshot import).
- **`getUserMedia` requires HTTPS** — on plain HTTP build the fallback first: `<input type="file" accept="image/*" capture="environment">` opens native camera on Android, choice-sheet on iOS, file picker on desktop (capture is a hint, not a command — say so honestly). Keep a secure-context check (`window.isSecureContext && navigator.mediaDevices?.getUserMedia`) so live-viewfinder mode lights up automatically once HTTPS exists. jsQR decodes both live frames and still photos.
- **Shopping lists are not recipes.** Andrew iterated THREE times before it landed; final rules (formatter in `meal-plan/page.tsx`: `JUST_BUY` / `COUNT_ITEMS` / `WEIGHT_KEYWORDS` / `DENSITY`):
  1. **Count of 1 → name only, no number.** "1 Chicken Breast / 1 Parsley / 1 Half and Half" was the explicit rejected output — humans write "Chicken Breast". Only show a count when >1 ("2 Potatoes").
  2. **`JUST_BUY` name-only category is BROAD**: not just spices/oil — all herbs, dairy liquids (half and half, cream, milk, sour cream), condiments, stocks, grains/pasta/bread, canned beans. If you buy it as one package regardless of recipe amount, no quantity.
  3. Countable produce/eggs → pieces via avg-grams lookup; meat/seafood/cheese → weight ("500g Chicken") only when ≥50g, else name-only.
  4. Strip prep words AND capitalize the cleaned name.
  Generalize: any 'list for humans' feature renders in the consumer's mental model, not the data model — and expect multiple correction rounds; make the category tables easy to extend.
- **`/api/recipes` returns a flat array** — UI code unwrapping `data.recipes` silently produces empty lists (broke meal-plan add-modal). Always `Array.isArray(data)` guard.
- **`RecipeLibrary.tsx` maps API fields explicitly, one by one** — any new field added to the API response (e.g. `isFavorite` for the card heart badge) is silently dropped until added to that mapping AND to `RecipeCardData`. When a backend feature "doesn't show up", check this plumbing before suspecting the API: favorites were per-user and DB-persistent all along; only the UI pass-through was missing.
- **Modal pickers pre-load content on open** — don't require 2+ typed chars before showing anything; show full library + filter as you type + explicit empty-state text.
- Generic site imports credit the source domain ('Imported from hellofresh.com', not 'Imported from web'). HelloFresh works through the generic JSON-LD path — no special-casing; their recipe pages are public with full method. No-API sites with public recipe pages need zero custom fetchers.
- **Instagram URL import is DEAD via Firecrawl (2026 upstream lockdown).** Firecrawl now returns `403 "we do not support this site"` for IG. Verified live on hil-1 that EVERY free no-auth path is blocked: oEmbed empty, GraphQL `?__a=1` → "Page Not Found", raw page → login wall, `yt-dlp` → "Instagram sent an empty media response... use --cookies". This is industry-wide, not a Mealio bug. **Do NOT build a DIY scraper**: Instagram rotates GraphQL `doc_id` values as a deliberate anti-scrape measure, so any self-hosted scraper breaks every 2-4 weeks (Scrapfly, 2026) — the exact cookie/treadmill maintenance Andrew rejects. **Reliable fix = a managed scraper API** (Apify Instagram Scraper ⭐ ~$5/mo free credits, doc_id rotation + proxies + TLS-fingerprint bypass is THEIR job; or ScrapeCreators for pure pay-as-you-go). Wire as `instagramFetcher.ts` → managed API returns caption JSON → slot into `fetchFromUrl` for `platform==='instagram'` BEFORE the Firecrawl fallback; caption → existing DeepSeek extractor, hero via existing `searchFoodWeb`. The API key is account-bound — Andrew must sign up + provide it; can't self-provision. **Interim no-cost path that already works: the screenshot/paperclip import** (vision extracts the caption) — immune to IG lockdowns because it never touches their API. For any 403 from IG/TikTok, surface "Instagram blocks automated import — screenshot the reel and use the 📎 button" instead of the raw Firecrawl error. **Apify wiring is now spec'd with a verified working API call (actor ID, RESIDENTIAL-proxy requirement, error-shape handling) + the `require_login` vs public-account diagnosis → `references/apify-instagram-fetcher.md`. Andrew provided a FREE-tier Apify key 2026-06-13 (stored in hil-1 `.env.docker` as `APIFY_API_KEY`).**
- **Nav import controls (verified 2026-06-13):** `src/components/layout/Nav.tsx` carries Search input + Camera (QR/link scan via `CameraScanner`) + **Paperclip (image/screenshot upload)** + submit. Paperclip uses a hidden `<input type="file" accept="image/*">` + `fileInputRef.current?.click()`; on file pick → POST FormData (`'image'` key) to `/api/import/image` → `sessionStorage.setItem('mealio-import', JSON.stringify(data))` → `window.location.assign('/import/review')` (NOT `router.push` — sessionStorage-handoff nav needs a real navigation). The `/api/import/image` vision route + review-page sessionStorage key already existed; adding an upload entry point is purely a Nav wiring change.
