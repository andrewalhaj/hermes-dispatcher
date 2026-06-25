# Porting a full multi-panel redesign into the DC standalone (panel-by-panel `<sc-if>` swap)

When the user hands a NEW `.dc.html` design prototype and says "update everything
except the Memory tab" (or any "redesign all the panels with this" handoff that is
a fresh design, NOT a data-wiring task), the job is to swap each panel's template
HTML for the new design's version while keeping the `{{ }}` data bindings intact.
Proven 2026-06-19 porting "Hermes Task Dispatcher.dc.html" into
`hermes-webui-new/standalone.html`.

## The key insight: panel structure is IDENTICAL between design and live

Both the design prototype and our live standalone wrap each panel in
`<sc-if value="{{ showX }}">…</sc-if>`. The design's panel and our panel use the
SAME `showOverview` / `showChat` / `showPlugins` / etc. flags. So the port is a
clean per-panel string replacement: find the current `<sc-if value="{{ showX }}">…
</sc-if>` block, replace it with the design's version of the same block. The
`{{ bindings }}` carry over because the DC `renderVals()` already computes them.

**Panel-flag map (design → our standalone, this host):**
`showOverview, showChat, showKanban, showAgents, showSessions, showPlugins`
(Skills uses `showPlugins`), `showMemory` (SKIP if user excludes it), `showLogs`,
`showLogFilters`, `showInsights`, `showProfiles`, `showSettings`, `showLogin`.

## Extraction recipe (get exact OLD/NEW strings)

1. **Decode the live template** (the replacement target):
   ```python
   import re, json
   raw = open('/root/projects/hermes-webui-new/standalone.html','rb').read().decode('utf-8','replace')
   scripts = re.findall(r'<script[^>]*>(.*?)</script>', raw, re.DOTALL)
   template = json.loads(scripts[3])   # decoded HTML, == new_inner pre-patch
   ```
2. **Extract each panel block from the DESIGN prototype** by depth-counting
   `<sc-if>`/`</sc-if>` (panels nest sc-if internally, so a naive `.find('</sc-if>')`
   stops too early):
   ```python
   design = open('design.dc.html').read()
   tmpl = design[design.find('<x-dc>'):]
   def extract_panel(tmpl, flag):
       start = tmpl.find(f'<sc-if value="{{{{ {flag} }}}}"')
       depth, pos = 0, start
       while pos < len(tmpl):
           if tmpl[pos:].startswith('<sc-if'): depth += 1; pos += 6
           elif tmpl[pos:].startswith('</sc-if>'):
               depth -= 1
               if depth == 0: return tmpl[start:pos+8]
               pos += 8
           else: pos += 1
   ```
3. The corresponding OLD block in the live template is found the same way (or it's
   the verbatim current panel). Verify each OLD string with `old in template` BEFORE
   building any patch — a missing OLD = silent no-op.

## Apply via an importable module, NOT inline strings

The panel HTML is huge (the Chat panel was 31KB, the whole batch ~145KB). DO NOT
inline 145KB of patch strings into `server.py`. Instead:

1. Write a sibling module `hermes-webui-new/_redesign_patches.py` holding a
   `_REDESIGN_PAIRS = [(old, new), …]` list (use `repr()` to encode the strings
   safely) and an `apply_redesign_patches(template, logger)` function that does
   `template = template.replace(old, new)` for each pair and logs `N/M applied`.
2. Wire ONE call into `_patch_standalone`:
   ```python
   try:
       from _redesign_patches import apply_redesign_patches
       new_inner = apply_redesign_patches(new_inner, logger)
   except Exception as e:
       logger.warning("redesign patches import failed: %s", e)
   ```
   This keeps `server.py` clean, the patch data update-isolated, and is one
   `patch` call instead of authoring 145KB inline (which is the $100 output-token
   trap from AGENTS.md).

## THE ORDERING TRAP (cost a full restart cycle, 2026-06-19)

`_patch_standalone` runs MANY in-place HTML patches on `new_inner` AFTER the
JS-splice line `new_inner = template_str[:sm.start(1)] + js + template_str[sm.end(1):]`
— e.g. `plan-E` (`_PLAN_DOTS_OLD → _PLAN_DOTS_NEW`), the swarm-legend header swap,
the memory-search header. Those patches' OLD markers are substrings of the ORIGINAL
panel HTML. If you run `apply_redesign_patches` and it replaces, say, the whole Chat
panel, then a LATER patch whose OLD marker lived inside the old Chat HTML silently
no-ops (logged as "marker not found") — OR, the reverse: if your redesign's OLD_CHAT
marker was captured from the pre-plan-E template but plan-E already transformed
new_inner, YOUR replace no-ops and the panel stays old (logs say "13/13 applied" only
because that count is over pairs that DID match — a same-length no-op replace still
"succeeds").

**Rule: call `apply_redesign_patches(new_inner, …)` IMMEDIATELY after the JS-splice
line, BEFORE plan-E and every other `new_inner.replace(...)`/in-place HTML patch.**
Then the redesign sees the raw spliced template (matching the OLD markers you
captured), and the later in-place patches operate on your NEW design HTML (which —
if it kept the same structural anchors — they still match; if not, they log a warn
you then fix or drop).

## Verification (do ALL — "N/N applied" is NOT proof)

1. **Build-time:** `import server; server._patch_standalone(raw)` — must not raise,
   and the patched template must still contain every panel flag including the
   EXCLUDED one (`showMemory` present = you didn't clobber it).
2. **Live wire after gated restart:** the injected `__RD_*` globals push the script
   index — the template is now `scripts[4]`, NOT `scripts[3]` (an extra `<script>`
   tag is prepended). Re-find it by content, don't hardcode the index.
3. **Marker check uses the DESIGN's REAL bindings, not guesses.** The first
   verification pass FAILED because the markers checked (`planMainOpen`, `cmpProfile`)
   weren't what the new design uses — extract the actual `{{ }}` bindings from the
   NEW panel string (`re.findall(r'\{\{\s*(\w+)\s*\}\}', new_chat)`) and grep THOSE.
   The design's chat used `chatActiveAvBg`, `folderMenuDisplay`, `modelMenuDisplay`,
   etc. — checking for invented names produces false "✗ missing" on a panel that
   landed fine.
4. **CDP screenshot + `vision_analyze` per panel** — the only real proof the design
   rendered. Click the rail tab via the real flow, screenshot, describe.

## KNOWN FOLLOW-UP: template-HTML port ≠ JS-render wiring

Swapping the panel TEMPLATE is only half. The new design's panel may bind keys the
current `renderVals()` doesn't compute (e.g. the new Skills panel binds
`plugin.category` / a richer skill-drawer shape the old `renderVals` never produced),
so the panel renders BLANK even though its HTML is on the wire. That's a SEPARATE
JS-side task (patch `renderVals()` + the component data arrays), not a template
patch. Scope it explicitly and tell the user: "template HTML is done; the Skills
panel renders blank because its bindings need the JS `renderVals()` updated — that's
the next pass." Don't claim the redesign is fully done when a panel is blank.

## PHASE 2: adding whole MISSING FEATURES, not just swapping panels (2026-06-19)

A redesign handoff is often more than panel swaps — it ships entirely new CROSS-PANEL
features the live standalone never had: a Universal Tile Info drawer (`tileInfo`,
`position:fixed`, shared across every panel), a Chat planning timeline (`m.isPlan`
block + step state), animated Composer dropdown menus (4 pills with `<sc-for>` option
lists), and the CSS `@keyframes` those animations need (`hdrawerin`, `hscrimin`,
`hmenuup`, `hdropswap`, `hcmdrow`). Each feature = a TEMPLATE-HTML injection AND a
`renderVals()` JS-wiring pass. Proven this session against "Hermes Task Dispatcher.dc.html".

### Inventory the feature delta by MARKER-COUNT diff (design vs live)

Before touching anything, count each feature's signature marker in the design's decoded
template vs the live decoded template. A `>0` vs `0` split IS the gap list:
```python
for key in ['tileInfo','planMainOpen','m.isPlan','composerMenu','profileOptions',
            'skillDetail','@keyframes hdrawerin','@keyframes hmenuup']:
    print(key, design.count(key), 'vs', live.count(key))
```
Markers present in design but absent (`0`) in live are the Phase-2 work. This is the
WHOLE-OBJECTIVE inventory for a redesign — do it before routing workers.

### THE #1 TRAP: build OLD/NEW patch strings against the DECODED template (`new_inner`), NOT the raw standalone or the design file

`new_inner` inside `_patch_standalone` is the JSON-**decoded** template — real `"` and
real `\n`. The raw `standalone.html` on disk stores that same template DOUBLY-escaped
(`\"` = literal backslash+quote, `\n` = literal backslash+n) inside a JS/JSON string.
So a worker who extracts an OLD string from the raw HTML, or from the design `.dc.html`
file, gets a string that **does not exist in `new_inner`** → `0/N` matches, silent
no-op. This session burned a full round on it: 4 delegated workers all returned OLD
strings sourced from the design/raw HTML; every one was `found 0x` against the live
decoded template.

**Correct procedure:** decode the live template ONCE (byte-walk the
`<script type="__bundler/template">` value or `json.loads(scripts[-1])`), save it to a
file (`/tmp/live_template.html`), and build EVERY OLD anchor by `.find()`-ing inside
THAT decoded string. Verify `live_template.count(OLD) == 1` (unique) for each before
assembling the patch. The NEW string = the same decoded-HTML dialect (the design's
panel/feature block is already in that dialect since it came from the design's own
`<x-dc>` template, not from raw bytes).

Anchor choices that worked:
- **Keyframes:** anchor on the last existing keyframe line (`@keyframes hstars {…} }\n`),
  append the missing keyframes after it.
- **tileInfo drawer:** anchor on `  <sc-if value="{{ toast }}">`, inject the tileInfo
  block immediately BEFORE it (both are top-level fixed overlays).
- **Plan timeline:** the `m.isPlan` block goes inside the `chatMsgs` `<sc-for>`; anchor
  on the loop's closing `{{ m.time }}</div>\n…\n</sc-for>` and insert before `</sc-for>`.
  A bare `</sc-for>` is NOT unique (5+ occurrences) — include the `{{ m.time }}` tail.
- **Composer dropdowns:** the live composer already had the 4 pill BUTTONS as flat
  `onclick="{{ onPickX }}"` toasts; the design replaces the whole composer outer
  `<div style="flex: none; padding: 14px 22px 18px;…">` (depth-count `<div>` to extract
  the exact bounds) with the version carrying `<sc-for>` dropdown menus.

### Wire the JS side as string-replaces on `js` BEFORE the splice line

The feature TEMPLATE patches live in `apply_phase2_patches(new_inner,…)` (a second
importable function alongside `apply_redesign_patches`, called right after it). The JS
state/`renderVals` wiring is a separate set of `js = js.replace(OLD, NEW, 1)` calls
placed BEFORE the `new_inner = template_str[:sm.start(1)] + js + …` splice line, so the
patched `js` is what gets spliced in. Each feature needs:
- **tileInfo:** `tileInfo: s.tileInfo` + `onCloseInfo: () => this.setState({tileInfo:null})`
  added to the renderVals return (anchor on `toast: s.toast,`).
- **plan:** add `isPlan: m.role==='plan'` / `isBubble:…` to the `chatMsgs` mapper, plus
  per-plan `headBg/mainRows/steps[]` fields, plus `planCollapsed:{}, planStepOpen:{}`
  initial state.
- **composer dropdowns:** `composerMenu`/`cmpProfile/Folder/Model/Reason` state +
  `profMenuDisplay`/`folderMenuDisplay`/… + `onToggleXMenu` handlers + the four
  `profileOptions`/`folderOptions`/`modelOptions`/`reasoningOptions` `.map()` lists in
  renderVals (each option: `{label, selected, color, bg, onClick:setState}`).

### Verify both layers separately

After the gated restart, decode the PATCHED standalone (`server._get_patched_standalone()`
→ byte-walk → `scripts[-1]`) and assert BOTH: template-HTML markers present
(`tileInfo`, `isPlan`, `hdrawerin`, `composerMenu`, `reasoningOptions` in `template_str`)
AND JS-wiring markers present (`tileInfo: s.tileInfo`, `isPlan: m.role`, `composerMenuOpen`,
`profMenuDisplay`, the four `*Options` lists in `js`). The log line `phase2 patches: 4/4
applied` only proves the TEMPLATE patches matched — it says nothing about the JS
`js.replace` calls (those are silent if their anchor drifted). Check the JS markers
explicitly.

## Fan-out shape (for the authoring, not the integration)

The panel-HTML authoring is N independent chunks (one per panel group) → fan out via
`delegate_task` (3 workers covering ~3-4 panels each is a good split), each producing
its `(OLD, NEW)` pairs verified against the live template. The orchestrator is the
INTEGRATOR: collect the pairs, dedup, run the full dry-run simulation against the
decoded template, assemble `_redesign_patches.py`, wire the single call, gated
restart, verify. Workers author; you splice and verify — never grind all the panel
HTML inline.
