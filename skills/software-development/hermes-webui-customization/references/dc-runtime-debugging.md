# Debugging the DC/bundler standalone at RUNTIME (panel switch broken, blank panels)

When a redesign/wiring patch lands cleanly (`N/N applied`, `node --check` passes,
markers present on the wire) but the LIVE UI misbehaves — nav clicks don't switch
panels, every panel except the initially-rendered one is blank, a feature renders
empty — you cannot diagnose it from `grep`/`curl`/static reads. You must inspect the
**running DC component** in the browser. This reference is the CDP-driven runtime
inspection playbook plus the specific root causes seen so far.

> **DO THIS FIRST — `scripts/audit_template_balance.py`.** For the specific symptom
> "every panel but the first is blank / nav clicks don't switch," the cause is almost
> always a structural `<div>`/`<sc-if>` imbalance in the patched template, and the
> static audit script finds it in ONE run — no CDP, no browser, no screenshots. Run it
> from the served project dir BEFORE reaching for any of the CDP probes below:
> `HERMES_HOME=/root/.hermes /usr/local/lib/hermes-agent/venv/bin/python scripts/audit_template_balance.py /root/projects/hermes-webui-new`
> It prints whole-template balance, per-panel depth, and per-patch net delta, and exits
> non-zero on any problem. A 2026-06-19 session burned ~20 tool calls hand-deriving
> exactly what this script already does because it treated the script as a footnote.
> The CDP playbook below is only needed when the imbalance audit comes back CLEAN and
> the bug is something subtler (a real handler/state problem).

## The framework you're actually debugging

The standalone's runtime is the DC framework (`support.js` in the design handoff
bundle is the readable source of the same runtime). Key facts that change how you debug:

- **It compiles the template to React** (React 18.3.1, concurrent mode via
  `createRoot`). `onclick="{{ x.onClick }}"` becomes a React **synthetic** `onClick`
  prop — NOT a native `element.onclick`. So `button.onclick` in the live DOM reads
  `function kd(){}` (an unrelated framer-motion internal) even when the handler works
  fine. **Do NOT conclude "the handler is empty" from `button.onclick` — check the
  React fiber's `pendingProps.onClick` instead.** This false lead cost a long detour.
- **State lives on the logic instance, not React.** `setState` →
  `__host.__setLogicState(update)` merges into `this.logic.state` and bumps an internal
  `__v` counter to force a re-render. The React fiber's `memoizedState` is just a tick
  number, so walking fibers for `state.panel` finds nothing.
- **Globals it exposes:** `window.__dcRegistry` (`{ Root: {html, tpl, Logic, ...}, 'Hermes Board v2': {...} }`),
  `getDC`, `DCLogic`, `__dcUpdate`, `__dcSetProps`, `__dcBoot`. `__dcRegistry.Root.tpl`
  is a FUNCTION `(vals, ctx) => builders.map(...)`, not an array. `Root.Logic` is the
  author's `Component` class; `new Root.Logic()` gives a fresh instance with `.state`,
  `.renderVals()`, and all the author methods.
- **Template HTML vs scripts:** `Root.html` is the template body WITHOUT the `<script>`
  blocks (the component JS is compiled into `Logic` separately). So `Root.html.length`
  (~197K) being smaller than the decoded `__bundler/template` (~299K) is expected, not a
  sign the patch didn't land. Check `'hdrawerin' in Root.html` etc. to confirm patches.

## CDP access gotcha: docker-proxy steals the debug port on IPv4

Launching `chromium --remote-debugging-port=9377` can bind only `[::1]:9377` (IPv6)
because a `docker-proxy` already holds `127.0.0.1:9377` (IPv4). Then
`curl http://127.0.0.1:9377/json/list` returns a stray container's 404 HTML and your
CDP driver fails with a confusing JSON parse error. Diagnose with `ss -tlnp | grep 9377`
(look for two listeners — `docker-proxy` on IPv4, `chrome` on `[::1]`). Fix: talk to
Chrome over IPv6 — `http://[::1]:9377/json/list`, and in the WS URL rewrite the host:
`re.sub(r'ws://[^/]+/', 'ws://[::1]:9377/', ws_url)`. (Or just pick a port docker isn't
proxying.) The MCP `browser_navigate` tool also routes through a fixed proxy port and
will 500 here — drive raw CDP via `websocket-client` instead (see headless-visual-verify.md).

## The runtime probes that actually find the bug

Run these via the CDP `Runtime.evaluate` driver. They isolate WHERE the pipeline breaks.

1. **Does the click reach setState?** Wrap the prototype before clicking:
   ```js
   const proto = window.__dcRegistry.Root.Logic.prototype;
   const orig = proto.setState; window._calls = [];
   proto.setState = function(u,cb){ window._calls.push(JSON.stringify(typeof u==='function'?u(this.state):u)); return orig.call(this,u,cb); };
   // then click the nav button, read window._calls
   ```
   If you see `{"panel":"kanban"}` → the click + synthetic event work; the bug is downstream.
2. **Does renderVals compute the right flags?** Wrap `proto.renderVals` to push
   `{panel:this.state.panel, showKanban:result.showKanban, showOverview:result.showOverview}`.
   If it logs `showKanban:true, showOverview:false` → the logic is correct; the bug is in
   how the result is COMMITTED to the DOM.
3. **A fresh instance renders fine but the live one doesn't?**
   `const inst=new window.__dcRegistry.Root.Logic(); inst.renderVals()` — if a fresh
   instance with `panel='kanban'` (define a getter to override `.state`) returns
   `showKanban:true`, the template/logic is sound. The fault is structural in the DOM tree.
4. **Where did the panel content actually go?** The `.sc-host` div is the React root
   output. Enumerate `document.querySelector('.sc-host').children` and each child's
   `data-dc-tpl` + `innerHTML.length`. **Expected: ONE child** (the app's outer div).
   **Bug signature: 4+ sibling children**, with extra big DIVs each containing a partial
   re-render of the app (one had `134K` of HTML starting "HERMES task dispatcher"). That
   means the template's panel `<sc-if>` blocks are being emitted as SEPARATE render
   subtrees instead of as children of `#hermes-shell` — so when the active panel's sc-if
   toggles, the fragment lands in the wrong tree and the shell shows only `<nav>` +
   `#hermes-chat-hist` (the starfield `position:fixed z-index:0` layer then shows through,
   looking "blank").

## Root cause class: unbalanced `<div>` from a redesign panel-swap patch

The above 4-children signature is caused by a structural HTML error introduced when a
redesign patch swapped a large panel block and left the div nesting unbalanced (an extra
or missing `</div>` somewhere in the ~59K panels region between `</nav>` and the closing
`</div>` of `#hermes-shell`). The browser's `template.innerHTML` parser silently
re-balances the broken tree, which pushes the trailing panel sc-ifs OUT of `hermes-shell`
into sibling position. Everything downstream (setState, renderVals) is correct, which is
exactly why it's so misleading.

**Find it — DO THE STATIC AUDIT FIRST, you usually don't need CDP at all.** The runtime
probes above prove it's structural; once you know that, skip CDP and audit the patched
template offline. Mechanical procedure (the session that wrote this fixed it end-to-end
without ever screenshotting):

1. **Apply all patches in-process and decode the patched template.** Don't read the raw
   `standalone.html` — it shows pre-patch mock/`false`. Do:
   `import server; patched = server._patch_standalone(server.STANDALONE_PATH.read_text(errors='replace'))`,
   then byte-walk the `<script type="__bundler/template">` JSON string (same boundary walk
   `_patch_standalone` uses) and `json.loads` it to get the decoded template HTML.
   (`_patch_standalone` takes a STRING, not bytes; the exported patch list is
   `_redesign_patches._REDESIGN_PAIRS`, a list of `(old, new)` tuples — not `PATCHES`.)
2. **Whole-template balance:** `template.count('<div') - template.count('</div>')` and the
   same for `<sc-if>`. Both must be 0. A non-zero here confirms the structural break.
3. **Per-panel depth trace — this pinpoints the culprit.** For each
   `<sc-if value="{{ showX }}">` (regex `<sc-if\s+value="\{\{\s*(show\w+)\s*\}\}"`), compute
   the div depth of the slice BEFORE it (`pre.count('<div')-pre.count('</div>')`). **Every
   main panel must report the SAME depth (e.g. `div_depth=2, sc-if_depth=0`).** The FIRST
   panel whose depth is wrong is downstream of the bad patch; the bad patch is the panel
   swap JUST BEFORE it. (In the session, `showChat` was fine at depth 2 but `showKanban`
   onward read depth −2 → the Chat swap was the culprit.)
4. **Per-patch NET delta:** for each `(old, new)` pair compute
   `(new.div_open-new.div_close) - (old.div_open-old.div_close)` and the same for sc-if.
   Sum across all patches = the whole-template imbalance from step 2. The patch(es) with a
   non-zero net delta are the offenders. A surgical partial-replace (swapping just one
   opening `<div ...>` tag) is *intentionally* unbalanced in isolation — judge by NET
   delta vs OLD, not by the NEW block's standalone balance.

**The #1 failure mode this session hit twice — the ORPHANED-TAIL panel swap.** A redesign
patch's OLD string covers only the FIRST N chars of the original panel's full `<sc-if>`
block (e.g. OLD = 4,778 chars but the real `showChat` block is 17,933 chars — OLD stops
mid-header-toolbar). The NEW string is a complete redesigned panel WITH its own closing
`</sc-if>`. Result: the original block's remaining tail (history dropdown → message area →
composer → the real `</sc-if>`) is left DANGLING as an orphan with negative div/sc-if
balance, poisoning every panel after it. **Fix: extend the patch's OLD to the FULL original
panel block** — find the panel's `<sc-if value="{{ showX }}">` in the UNPATCHED template and
depth-count `<sc-if>`/`</sc-if>` to its matching close, use that whole span as OLD (verify
it's a unique substring), and make sure NEW is a complete balanced block
(`<sc-if …>` … `</sc-if>`, div Δ=0, sc-if Δ=0). If NEW was authored as a partial INNER
replacement (starts mid-toolbar, lacks the outer wrapper), rebuild it as
`prefix_from_original[:inner_start] + new_inner + correct_closing_suffix` so the prefix
opens (+3) and the suffix closes (−2) net out against the inner fragment (−1) to 0.

There is a re-runnable audit for all of this: `scripts/audit_template_balance.py` (run it
after editing `_redesign_patches.py`, BEFORE the gated restart — it does steps 1–4 and the
orphan check and exits non-zero on any imbalance).

**Prevention:** after building each panel-swap NEW block, assert
`new.count('<div') == new.count('</div>')` AND that the block's net `<sc-if>` depth is 0,
BEFORE applying — but ALSO assert the OLD covers the panel's FULL `<sc-if>` span (depth-count
to the matching close) so you never leave an orphaned tail. A balanced-tag check plus the
per-panel depth trace is cheap and catches both classes before they ship. `node --check`
and "phase N/N applied" do NOT catch either — the HTML is structurally broken but the JS is
valid and the replace succeeds (a same-length partial OLD still reports "applied").

## What is NOT the bug (don't chase these)

- `button.onclick === function kd(){}` — red herring (React synthetic events; native
  onclick is unused). Check fiber `pendingProps.onClick`.
- `Root.html.length` smaller than decoded template — expected (scripts stripped).
- Handler COUNT (49 → 101 after patches) — the DC runtime has NO handler-count limit;
  `compileAttr`/`resolve`/`resolvePath` in support.js impose no cap. Adding handlers does
  not break anything by itself.
- Zero MutationObserver hits on panel switch — React concurrent mode commits in one batch;
  absence of mutations doesn't mean nothing rendered. Inspect `.sc-host` children directly.
