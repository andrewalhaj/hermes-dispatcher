# Porting a React/lucide component into the standalone DC template

Companion to `standalone-bundle-data-wiring.md` and `chat-panel-wiring.md`. When the
user hands you a self-contained React + Tailwind + lucide-react component (e.g. an
"AI planning timeline", a thinking-steps disclosure) and wants it **in the live
WebUI Chat panel, adapted to the theme** — the live WebUI is NOT React. It's the
DC/bundler `standalone.html` served by `/root/projects/hermes-webui-new/server.py`.
You cannot drop a `.tsx` in. You re-express the component as **real DC template
nodes** (`sc-if` + `{{ }}` bindings) driven by **per-element computed state values**.
Proven 2026-06-19 (chat planning timeline replacing the 3-dot typing indicator).

## ⚠️ CRITICAL: the DC runtime has NO `sc-html` / innerHTML binding

This is the bug that cost this whole session ("still broken now nothing is appearing").
A prior version of this reference told you to inject a raw HTML string via an
`sc-html="{{ key }}"` attribute. **That attribute does not exist.** The DC runtime
(`dc-runtime/src/*.ts`, in the gzip'd manifest asset, `mime=text/javascript`) renders
to **React**. Its element walker special-cases ONLY these tags:

```
sc-for, sc-if, x-import, sc-helmet, dc-import
```

Everything else goes through `walkElement → collectProps`, which maps `class→className`,
`for→htmlFor`, `on*→onX` React handlers, `style-*→pseudoClass`, and passes every other
attribute through **as a literal React prop**. React silently drops unknown props like
`sc-html` on DOM elements. Result: your `<div sc-html="{{ chatPlanHtml }}">` renders an
empty `<div>` — nothing appears, no error. And a text node `{{ chatPlanHtml }}` would
render the HTML **escaped as visible text** (via `walkText → String(v)`), not as markup.

There is no `dangerouslySetInnerHTML` path reachable from a template attribute either.

**So: never inject an HTML string. Build the component out of real template nodes.**

## STEP 0 — confirm which codebase is live (the React project is a decoy)

Multiple "WebUI-looking" trees coexist. `hermes-ui-fresh` / `hermes-react` are React
SOURCE projects; editing them and running `tsc`/`vite build` compiles clean and
changes NOTHING the browser sees. The LIVE served bytes come from
`hermes-webui-new/server.py` patching `standalone.html` at startup. ALWAYS read the
live unit's `WorkingDirectory` + the served page before authoring. A whole React
component built, type-checked, and "verified" against the wrong tree is wasted work —
the user's "doesn't seem to be working" screenshot is the tell you edited a decoy.
(If you DID build the React version first, keep it — it's a faithful reference for the
markup/colors you now translate into the template nodes + state values.)

## The CORRECT pattern: per-element state values → real `sc-if`/`{{ }}` template nodes

The DC component is a `class Component` whose `{{ name }}` template bindings map to keys
returned from a big per-render state object (search for `chatRunning: s.chatRunning`).
`<sc-if value="{{ boolKey }}">` gates a subtree; `{{ key }}` substitutes a string into an
attribute value or text. **All dynamic-ness must be expressed as one of these two** — there
is no escape hatch for "compute this whole blob in JS and inject it."

To port a stepped/animated component (the planning timeline is the worked example):

1. **Add raw state** for what the component animates, next to `chatRunning: false` in the
   state init: `chatPlanProgress: 0, chatPlanQuery: ''`.
2. **Expose EVERY dynamic value as its own computed key** in the per-render state object
   (next to `chatRunning: s.chatRunning && !viewing`). Because the template can only
   substitute scalar strings/bools, you precompute — in JS — every per-step color, opacity,
   font-weight, boolean, and label. For a 3-step timeline that's ~25 keys, e.g.:
   ```js
   chatPlanVisible: s.chatRunning && !viewing,
   chatPlanLabel: s.chatPlanProgress >= 3 ? 'Thought process' : 'Agent is planning\u2026',
   chatPlanCount: Math.min(s.chatPlanProgress, 3) + '/3',
   chatPlanSpin: s.chatPlanProgress < 3,
   chatPlanS1Done: s.chatPlanProgress > 0, chatPlanS1Active: s.chatPlanProgress === 0, chatPlanS1Pend: false,
   chatPlanS2Done: s.chatPlanProgress > 1, chatPlanS2Active: s.chatPlanProgress === 1, chatPlanS2Pend: s.chatPlanProgress < 1,
   // …S3…, plus per-step DotBg/DotBo/DotC/LabelC/LabelW/Opacity strings via ternaries
   chatPlanQueryText: s.chatPlanQuery && s.chatPlanQuery.length > 50 ? s.chatPlanQuery.slice(0,50)+'\u2026' : s.chatPlanQuery || '',
   ```
   This is verbose but it's the ONLY mechanism. Push all conditional logic into these JS
   ternaries; the template just consumes the results.
3. **Write the card as real template HTML** (replacing the old indicator block). Use
   `style="…{{ chatPlanS1DotBg }};border:1px solid {{ chatPlanS1DotBo }};…"` for dynamic
   inline styles, and `<sc-if value="{{ chatPlanS1Done }}">…</sc-if>` to switch the dot
   icon (check vs spinner vs pending dot) and to show/hide the query detail. lucide icons →
   inline `<svg>` literals (spinner path `M21 12a9 9 0 1 1-6.219-8.56`, check
   `polyline points="20 6 9 17 4 12"`). Glass: `backdrop-filter:blur(20px)` +
   `rgba(13,18,28,.65)`. Reuse the `hspin` keyframe (already in the template's `<style>`)
   for spinners — do NOT invent new keyframes.
   - Generate the repetitive per-step markup with a Python helper (`_plan_step(n, icon,
     label, show_query)`) that string-concatenates the `{{ chatPlanS<n>… }}` bindings.
     **Build it with plain `'…' + str(n) + '…'` concatenation, NOT an f-string** —
     Python 3.11 forbids backslashes inside f-string expression parts, and you WILL hit
     `SyntaxError: f-string expression part cannot include a backslash` the moment a `\n`
     or unicode escape lands in there. (Move unicode escapes like `'\U0001f50d'` to plain
     string args passed into the helper.) `py_compile` the server before any restart.
4. **Drive the animation** from the action handler (`sendChat`): on send, set
   `chatPlanProgress: 0` and fire `setTimeout`s stepping it 1→2→3 over ~1s; reset to 0 in
   the completion path (SSE `finish()` callback, or the canned-reply timeout).

## PITFALLS (each cost a cycle this session)

- **`sc-html` IS NOT A THING — see the CRITICAL box at top.** If you find yourself wanting
  to inject an HTML string, stop: re-express as `sc-if` + `{{ }}` nodes with precomputed
  state values. Confirm what the runtime supports by decoding the manifest's
  `text/javascript` asset and grepping the `walk()` dispatcher for the tag list — don't
  assume an attribute exists.
- **Patch-ordering: an earlier patch may have already replaced your anchor.** The chat
  SSE-wiring patch rewrites `sendChat()` BEFORE a later "add plan progress" patch tries to
  match the ORIGINAL mock `sendChat`. The later `str.replace` silently no-ops
  (`marker not found` warning). FIX: fold the new behavior INTO the earlier patch's
  replacement string (add the `chatPlanProgress`/timer lines to the SSE `_SC_NEW`), rather
  than adding a second patch that assumes the pristine original is still present. When you
  see a `plan-C: anchor not found` warning, check whether an upstream patch already
  transformed that region — don't re-target the original.
- **HTML edit must apply to `new_inner` AFTER the script splice.** The template HTML you
  want to edit (the dots block) sits BEFORE the `<script>` whose offsets you splice
  (`new_inner = template_str[:sm.start(1)] + js + template_str[sm.end(1):]`). Mutating
  `template_str` before that splice shifts `sm.start/end` and corrupts the splice. FIX:
  define the OLD/NEW HTML strings early but apply the `.replace` to `new_inner` AFTER the
  splice (same as the swarm-legend and memory-header patches already do).
- **Escape level — same trap as chat-panel-wiring.** Replacement strings that become JS
  code-body text need REAL newlines (single backslash-n in Python source); a
  double-backslash-n embeds a literal backslash-n into the running JS (browser throws
  `Unexpected token ':'` / blank panel). SVG/HTML strings with embedded `"` must be escaped
  for the Python literal but stay plain `"` in the emitted HTML.
- **Verify by decode + node --check, then CDP screenshot.** Re-extract `__bundler/template`
  from the SERVED page, json.loads, pull `scripts[-1]`, `node --check` the decoded JS. Then
  confirm: the per-step bindings are present in js, the `<sc-if value="{{ chatPlanVisible }}">`
  card is in the template, and the old dots are GONE. **Save the served page to a file and
  parse from the file** — piping a 1.1 MB page through `curl | python3 -c` can truncate and
  give a spurious `Expecting value` JSON error. A headless-Chromium screenshot lands on the
  LOGIN page unless you set the `hermes_session` cookie — code-level checks (all bindings
  present + node clean) are the reliable proof; the public URL serving the login page to an
  unauthenticated curl is EXPECTED, not a failure.

## The post-restart "nothing appears" RED HERRING (cost a whole session 2026-06-19)

After the `sc-html→sc-if` fix was deployed and the server restarted, the user reported
"still broken now nothing is appearing" — and many cycles were burned re-verifying
already-correct code (decode template, `node --check`, confirm bindings present, walk the
DC engine source) before realizing **the code was fine and the symptom was a stale browser
session**. Two distinct causes that BOTH look like "the page is blank/broken":

1. **`server.py` regenerates `SECRET_KEY` on every restart** when it's not persisted —
   `SECRET_KEY = os.getenv("HERMES_WEBUI_SECRET_KEY", secrets.token_hex(32))`. The session
   cookie is HMAC-signed with that key, so EVERY restart invalidates all existing browser
   sessions. The user's open tab then silently shows the LOGIN page (or 401s on every
   `/api/*` call: `journalctl`/status shows a wall of `401 Unauthorized` for
   `/api/galaxy`, `/api/swarm`, `/api/kanban/events/stream`). They read this as "the UI
   broke," but they just need to log in again. **The durable FIX** (gated `.env` edit):
   add a stable `HERMES_WEBUI_SECRET_KEY=<token>` to the served project's `.env` so sessions
   survive restarts — propose it the first time a restart logs the user out.
2. **The screenshot the user sends may predate your fix.** A red `Root: Unexpected token
   ':'` banner / blank main panel from BEFORE the deploy is identical-looking to a live
   bug. Don't trust the image as current state — verify the SERVED bytes yourself.

**Triage order when the user says "still nothing" after a restart** (don't re-debug code first):
- `systemctl is-active hermes-webui` + tail the journal. A wall of `401 Unauthorized` on
  `/api/*` = the browser session is invalid (SECRET_KEY rotated) → tell them to log in again.
- Authenticate via curl (`POST /api/auth/login {"password": <pw from .env/unit>}` → cookie)
  and hit `/api/chat`, `/api/kanban/board`, `/api/swarm`. All 200 with real data = backend
  is healthy; the "blank" is purely the unauth'd browser, NOT your template.
- Only AFTER backend+auth check out, decode the served template and confirm your bindings.
  If the served bytes are correct and the APIs return data, **say so plainly and tell the
  user to re-login** — do not keep re-deriving a fix for code that already works.

## The DC engine internals ARE recoverable — decode the gzip'd runtime asset

When you need to know exactly what the template engine supports (which is the only way to
kill an `sc-html`-class assumption for good), the runtime source is in `standalone.html`'s
`__bundler/manifest` as a base64+gzip asset with `mime: application/javascript`. Decode it:
```python
import json, base64, zlib, re
html = open('standalone.html').read()
i = html.find('type="__bundler/manifest">'); s = i + len('type="__bundler/manifest">')
manifest = json.loads(html[s:html.find('</script>', s)].strip())
for k, v in manifest.items():
    if v.get('compressed'):
        js = zlib.decompress(base64.b64decode(v['data']), 16+zlib.MAX_WBITS).decode()
        if 'function walk(' in js: print(k, len(js))  # this bundle is dc-runtime
```
Key facts confirmed by reading it (so you stop guessing):
- `walk()` dispatches only `sc-for / sc-if / x-import / sc-helmet / dc-import`; everything
  else → `walkElement → collectProps`. No `sc-html`.
- `compileAttr(raw)` DOES handle **mixed content**: whole-`{{expr}}` → value getter;
  `"a{{x}}b"` → split on the `{{ }}` regex and `.join('')` to a string. So an inline
  `style="background:{{ k }};border:1px solid {{ j }};"` is FINE — the literal CSS `:`/`;`
  are just string parts, not parsed as an expression. Mixed-content styles are supported.
- `walkElement` then does `if (k==="style" && typeof v==="string") v = cssToObj(v)` — the
  joined CSS string is converted to a React style object. So precomputed inline styles work.
- `resolve(vals, src)` (the `{{ }}` evaluator) supports ONLY: property paths (`a.b[c]`),
  `===/!==/==/!=` equality, `!` negation, literals (`true/false/null/undefined`, numbers,
  quoted strings), and `( )` grouping. **It does NOT support ternaries (`? :`)** — never put
  a `cond ? a : b` inside `{{ }}`; a lone `:` will trip it. Precompute ternaries in the JS
  state object (per the per-element-state pattern) and bind only the resulting scalar.
- A `"<Name>: <error>"` banner (e.g. `Root: Unexpected token ':'`) is the DC `Placeholder`
  error path: `name` is the component, the rest is a JS parse error from `new Function(src)`
  in `evalDcLogic`. Reproduce it locally by wrapping the decoded `scripts[-1]` exactly as
  `evalDcLogic` does — `(function(DCLogic, StreamableLogic, React){<src>;return Component})`
  — and `node --check`. If THAT passes, the class JS is syntactically fine and the banner is
  stale (see red-herring above), not a current bug.

## Why per-element state, not a string builder or a real component

The DC runtime only re-runs the draw on `setState`, bindings are string-substitution, and
there is no innerHTML/dangerouslySetInnerHTML path. So a "component" is: real template nodes
(authored once, in the patch) + a fan of precomputed scalar state keys that the nodes
consume + state that drives re-render. This keeps the whole port inside the existing patch
mechanism (state init + computed keys + one template-block swap + handler timers) with no
new runtime, no React, no build step. The verbosity of precomputing ~25 keys is the price
of the template engine's deliberate simplicity — embrace it rather than trying to outsmart
it with string injection.
