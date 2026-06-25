# Full-shell redesign: offline staging clone + skin overlay + gated cutover

Use this when the change is **bigger than a CSS tweak** — a full restyle, a
sidebar/nav rebuild, multi-panel redesign, or anything that edits the app
**shell** (`index.html` structure, nav, boot). Editing the live `static/`
directly for a shell-wide change is dangerous: the live server renders the
current chat session, so a half-applied `index.html` (broken nav, unclosed
script) white-screens the very UI you're talking to the user through. Build in
a staging clone, verify with the CDP screenshot harness, cut over only on a
greenlight.

## Why a STATIC staging server, not a second backend
Two full backends pointed at one `HERMES_HOME` contend on the SQLite session
DB and can corrupt live state. Serve the staging `static/` with a plain
`python3 -m http.server` instead — no backend. API calls 404 gracefully; the
chrome, CSS, markup, JS, fonts, starfield all still render and are fully
verifiable. Data panels show their empty/"unavailable" state, which is exactly
what you want for visual sign-off.

## Setup
```bash
TS=$(date +%Y%m%d-%H%M%S)
mkdir -p ~/.hermes/backups
tar -czf ~/.hermes/backups/webui-static-pre-redesign-$TS.tar.gz -C /root/projects/hermes-webui static   # golden copy FIRST
rsync -a --delete --exclude '.git' --exclude 'node_modules' --exclude 'tests' --exclude 'static/*.bak' \
  /root/projects/hermes-webui/ /root/projects/hermes-webui-staging/
```

### Placeholder pre-substitution (REQUIRED — app won't boot offline otherwise)
`server.py` substitutes template tokens at request time. A static server serves
them raw, so `window.__HERMES_CONFIG__={maxUploadBytes:__MAX_UPLOAD_BYTES__,...}`
is a JS syntax error that halts boot → white page. Replace them in the staging
`index.html` before serving:
- `__WEBUI_VERSION__` → `staging`
- `__MAX_UPLOAD_BYTES__` → `26214400`
- `__CSRF_TOKEN_JSON__` → `"staging-csrf"`
(Note: `__HERMES_CONFIG__` is a real JS global, NOT a placeholder — leave it.)

### URL-layout mirror (assets 404 otherwise)
Live serves `index.html` at `/` and assets under `/static/`. A server rooted at
`static/` makes `static/style.css` 404 (double prefix). Mirror the real layout:
```bash
mkdir -p staging/_serve && cp staging/static/index.html staging/_serve/index.html
ln -sfn ../static staging/_serve/static          # /static/* now resolves
cd staging/_serve && python3 -m http.server 8788 --bind 127.0.0.1
```
Verify: `curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8788/static/style.css` → 200.

## Verify with the CDP harness (cache-disabled!)
Reuse `~/.hermes/scripts/webui_shot.py` and the CDP driver in
`references/headless-visual-verify.md`. Two staging-specific musts:
- **`Network.setCacheDisabled {cacheDisabled:true}`** — the `?v=staging` token
  never changes, so Chrome serves stale CSS/JS on every reload (the frozen
  cache-key trap, in miniature). Without this you'll "see no change" after every
  edit. This single flag is the difference between verifying your edit and
  chasing a ghost.
- **Force the skin before nav:** `localStorage.setItem('hermes-skin','mission-control')`
  then re-navigate so the boot script applies `data-skin`.
- **Prove the edit is on the wire** before trusting a screenshot:
  `curl -s http://127.0.0.1:8788/static/style.css | grep -c '<new rule>'`.
- **Measure, don't just eyeball:** `Runtime.evaluate` computed styles
  (`getComputedStyle(document.body).backgroundColor`, `--accent` via
  `getComputedStyle(document.documentElement).getPropertyValue('--accent')`,
  injected-node counts) gives objective pass/fail that a vision model can't
  flake on.
- **No-backend board render:** to screenshot Kanban cards offline, inject a mock
  and call the column renderer directly into the board element:
  `document.getElementById('kanbanBoard').innerHTML = mockCols.map(_kanbanRenderColumn).join('')`.
  Calling `_kanbanRenderBoard()` alone won't work — it re-filters from internal
  state your mock didn't populate.

## Prefer the SKIN-OVERLAY pattern over overwriting the default theme
The WebUI has a `data-skin` system: each theme is a
`:root.dark[data-skin="NAME"]{ --var:value; }` block in `style.css`, plus
skin-scoped structural overrides. Build a redesign as a **new skin** (e.g.
`mission-control`), not by editing the default theme. Wins:
- **Append-only** to `style.css` — zero existing rules touched (verify:
  every original line still present → `python3` set-diff = 0 missing).
- **Reversible & opt-in** — switching skin away restores the original byte-for-
  byte. This is least-astonishment made mechanical; verify it (load default
  skin → assert injected nodes == 0, rail width back to original).
- Register the skin in the `skins={...}` allowlist in `index.html`'s boot
  script, else the boot script silently falls back to `default`.

### Structural changes that can't be pure CSS → skin-gated enhancement script
A 48px icon rail can't become a 236px text nav by overwriting DOM (the buttons
carry `data-panel` + `switchPanel()` wiring and a tab-reorder/hide script keyed
on `.rail .rail-btn.nav-tab[data-panel]`; rebuilding breaks nav). Instead inject
extra nodes (labels, group headers, brand badge, agents list) with a script that:
- early-returns unless `document.documentElement.dataset.skin === '<skin>'`;
- is idempotent (guard via a `dataset.*Built` flag);
- tags every injected node with a marker class (e.g. `.rail-mc`) so teardown is
  one `querySelectorAll(...).forEach(remove)`;
- runs on DOMContentLoaded AND on a `hermes-skin-change` event (enhance on skin,
  teardown otherwise).
Same reversible pattern as the starfield layer. Collision note: rail buttons
already carry `.has-tooltip::after{content:attr(data-tooltip)}`, so you CANNOT
use `::after`+attr for inline labels — inject real `<span>` text instead.

## Cutover (gated — get explicit greenlight; it blips the live session)
THE TRAP: never rsync the staging `index.html` straight to live — its
placeholders were replaced with static values. Shipping it hardcodes
`?v=staging` (breaks cache-busting forever) and a fake CSRF token. Build a
cutover artifact that RESTORES the placeholders first:
```
?v=staging                → ?v=__WEBUI_VERSION__   (every asset tag)
{maxUploadBytes:26214400,csrfToken:"staging-csrf"} → {maxUploadBytes:__MAX_UPLOAD_BYTES__,csrfToken:__CSRF_TOKEN_JSON__}
```
Then `diff` the restored index against LIVE — it must show ONLY your intended
edits (fonts link, skin-allowlist entry, injected scripts). Confirm
`grep -c '?v=staging'` == 0 and `__WEBUI_VERSION__` count > 0 before shipping.

Cutover steps: (1) second golden tar of live `static/`; (2) rsync staging
`style.css`/`panels.js` + the restored `index.cutover.html`→live `index.html`;
(3) `systemctl restart hermes-webui` — **blips the current chat ~5s, regenerates
the cache token**, get OK first; (4) hard-refresh / `hardRefreshWebUIClient()`.

Decision to surface at the gate: should the new skin be the **default** or stay
**opt-in** (user flips it in Settings)? Opt-in is the least-astonishing default
for a redesign; let the user choose.
```
Plan/scratch for a multi-phase redesign lives well in
~/.hermes/references/webui-redesign-plan.md (durable across context compaction).

## Resuming after a restart / context compaction — STOP re-executing done work
The #1 way a multi-phase cutover goes wrong is not a bad edit — it's **re-doing
completed steps after a restart**. Context compaction drops the working memory of
what already shipped; the in-progress todo and any stale plan then read as "not
done yet," so you re-read files and re-run edits that are already live. The user
experiences this as you looping ("you keep repeating the same thing").

Guard against it at the START of every resumed turn on a long task:
1. **Verify done-state against the LIVE system, never against the plan or todo.**
   The world is the source of truth. Before redoing anything, grep the live
   target: `grep -c '<new-rule-or-token>' /root/projects/hermes-webui/static/style.css`,
   `grep -c '<symbol>' .../boot.js`, `systemctl is-active hermes-webui`. If the
   change is already present, it is DONE — do not re-apply it.
2. **A non-zero match means SKIP, not "verify harder."** Re-reading the file to
   "make sure" is how the loop perpetuates. One grep is the check; act on it.
3. **Record completion where a cold context will see it.** The durable plan file
   and an explicit todo status are necessary but the todo's `content` should state
   the *evidence of completion* ("style.css 40 refs, service active"), and a
   compact memory entry should say "PHASE N LIVE — do not redo" so the next turn
   starts knowing. Memory captures done-state; the plan file captures how.
   **CAVEAT — the memory-offload cron can eat your progress entry.** The hourly
   "Memory Offload (default)" cron (`jobs.json`, `0 * * * *`) compacts MEMORY.md
   when it crosses ~85% of cap by offloading "stable reference facts" to the cold
   store and replacing them with a one-line `knowledge.py search` pointer stub. A
   plainly-worded "PHASE N LIVE" entry looks exactly like an offloadable reference
   fact, so it gets stubbed out — and the stub reads as "not done" on the next
   restart, re-arming the very loop you were guarding against. Mitigations:
   (a) the LIVE-system grep in step 1 is the real defense — it doesn't depend on
   the memory entry surviving, so always reconcile against the host, not memory;
   (b) phrase the entry as a hard constraint, not a reference fact — lead with
   "DO NOT REDO" / "MUST NOT re-run", which the cron's rules explicitly protect
   from offload; (c) keep the authoritative state in the plan file
   (`~/.hermes/references/webui-redesign-plan.md`) and the todo, which the cron
   never touches. If you find a progress entry replaced by a search pointer after
   a restart, that's the cron working as designed — don't treat the stub as proof
   the work is unfinished; grep the live system.
4. **Idempotent patches help but aren't enough** — a `patch` whose `old_string`
   was already replaced will simply fail to match, which looks like an error and
   tempts a re-read. Prefer the grep-first check so you never issue the redundant
   patch in the first place.
The throughline: on resume, **reconcile against the live system, trust the
reconciliation, and refuse to re-execute applied steps** — even when the todo
or your own narrative implies there's work left.
```

## Corrupted source from a prior botched edit — literal `\n` in the file (proven 2026-06-18)
A prior session's edit (often an `execute_code`/`write_file` that built a string
with the wrong escaping) can leave **literal two-character `\n` sequences inside
`index.html`/`panels.js`** where real newlines belong — e.g. a single physical
line reading `..._buildSkinPicker(skinVal);\n    const accentVal = ...;\n    ...`.
Symptoms this session:
- `node --check panels.js` fails with `SyntaxError: Invalid or unexpected token`
  pointing at the offending `\n`.
- A whole HTML panel renders as one giant line; `sed -n '...' | cat -A` shows
  `\n` between `$`-terminated real lines.
- The `patch` tool reports the surrounding block as already-present-but-wrong, or
  its lint step surfaces a *pre-existing* error your edit didn't introduce
  (the message literally says "Pre-existing lint errors — this edit didn't
  introduce new ones but the file is still broken").
Fix — do NOT keep fighting `patch`; rewrite the bad span cleanly in Python:
1. Detect it: `grep -n "skinVal);\\\\n" file.js` or scan the suspect block with
   `sed -n 'A,Bp' file | cat -A` (real newlines end in `$`; corruption shows `\n`).
2. Read the file with plain Python (`open().read()`), `str.replace()` the exact
   bad literal string (build the search target with `\\n` in a normal Python
   string so it matches the two literal chars) with the correctly-newlined block,
   write it back, then re-run `node --check`. One pass fixes it; the patch tool's
   fuzzy matcher can't reliably target a span that contains literal `\n`.
3. After fixing, re-verify the WHOLE file (`node --check`), not just the span —
   a botched session often left more than one such line.
Lesson: when `node --check` or `patch` lint flags a "pre-existing" break in a
staging file you're editing, STOP and scan for literal `\n` before layering new
edits on top of a file that won't parse.

## Delegation timed out → fall back to direct, targeted patches (proven 2026-06-18)
Delegating the Phase-3 authoring to a Studio subagent **timed out at 900s with 2
API calls** (the large multi-file prompt stalled ingestion). For WebUI feature
work that is a handful of *targeted, sequential* edits to known anchor points
(insert a swatch row, append a JS module, append a CSS block), direct execution
by the orchestrator is faster and more reliable than delegation — you already
know the exact `old_string` anchors from the read phase, so each `patch` is one
deterministic call. Reserve delegation for genuinely parallel or
context-heavy work; don't delegate a 3-file linear patch sequence. If a delegate
call times out mid-task, the correct recovery is to do the remaining edits
directly (grep the live anchors first), not to retry the same oversized delegation.

### The MORE dangerous delegation mode: subagent reports success while its edits silently DIDN'T land (proven 2026-06-18)
Worse than a clean timeout: a retried subagent **summarized as if it succeeded**
("Overview panel added", "CSS appended") while its `patch` calls had actually
FAILED — one on a non-unique `old_string` (`Found 4 matches`), one on a no-match
(`Could not find a match`). The truth was in the runtime's **file-mutation
verifier** line appended to the result: `⚠️ 2 file(s) were NOT modified this turn
despite any wording above that may suggest otherwise.` A subagent's prose summary
is a SELF-REPORT, not proof. Rules:
1. **Never trust a subagent's "done" for file edits — verify the artifact yourself.**
   After any delegated WebUI edit, run the same grep counts you'd use for your own
   work: `grep -c '<new-symbol>' …/panels.js`, `grep -c '<new-class>' …/style.css`,
   `grep -c '<new-id>' …/index.html`. Zero = it didn't land, regardless of the summary.
2. **The verifier's "NOT modified" line is ground truth; the summary is not.** If
   the runtime appends a file-mutation-verifier warning, believe it over any
   success wording in the same response.
3. **Why `patch` failed for the subagent and not for you:** you'd already read the
   file and have the EXACT unique anchors; a subagent working from a prose spec
   guesses anchors and hits non-unique/no-match. This is another reason targeted
   multi-anchor WebUI edits belong with the orchestrator that did the read phase —
   not delegated. When you must delegate, give EXACT, verified-unique `old_string`
   anchors in the task, and still verify the diff after.
```
