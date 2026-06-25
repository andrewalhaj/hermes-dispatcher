# Editing the dispatcher React components — `patch`-tool & prop-interface traps

Applies to the `hermes-dispatcher` React app (`/root/hermes-dispatcher`,
`hermes-dashboard.service`, edit `.tsx` → `npm run build` → served from `app/dist`).
See `references/react-dispatcher-dashboard.md` for the app architecture and the
Chat-panel behavioral-bug class. THIS file is about HOW to edit the large
single-file React components (esp. `app/src/components/panels/Chat.tsx`, ~1900 lines)
without burning round-trips. Lessons from a long iterative Chat-panel polish session
(2026-06-23: header removal, collapsible rail sidebar, opaque sidebar, local
agent-filter search) that each cost multiple wasted cycles.

## 1. The `patch`/`mcp__hermes___patch` tool MANGLES large multi-line React blocks

When the `old_string` is a big block — a whole `interface` + `function` signature +
JSX body, especially anything with escaped `\n` or nested `{...}` style objects — the
fuzzy matcher repeatedly produced a CORRUPTED merge: it nested the new function inside
the old one's scope, duplicated `useState` declarations, and left orphaned JSX tails
(`style={{...}} ... </div>` debris with no opening tag).

Next-build symptoms:
- `TS1131 Property or signature expected`
- `TS17002 Expected corresponding JSX closing tag for 'aside'`
- `TS1382 Unexpected token. Did you mean '{'>'}'`
- `Cannot redeclare block-scoped variable`

Recovery each time: `git checkout app/src/components/panels/Chat.tsx`, then either
- (a) re-do as several SMALL single-purpose patches (one style object, one prop, one
  block at a time), or
- (b) delegate the whole restructure to a `coder` kanban card and let it author the
  file in one clean pass (this is what finally landed the collapsible-rail rewrite).

**Rule:** for a Chat.tsx structural change (extracting a sub-component, adding a mode
branch, rewriting a render block), do NOT feed one giant old/new pair. Either fan it to
a coder card or decompose into ≤15-line surgical patches. Re-read the file region right
before each patch — the tool's own `_warning: modified since you last read` means a
sibling/earlier edit already shifted the lines, and patching blind compounds the corruption.

## 2. A React prop change is a THREE-SITE edit — do all three in one turn

Adding/removing a prop on a sub-component (`ChatSidebar`) means editing:
1. the `interface ChatSidebarProps` declaration,
2. the destructure in the `function ChatSidebar({ ... })` signature, AND
3. every call site `<ChatSidebar ... />`.

Miss any one and the build fails with a specific, predictable error:
- prop in interface but not passed → `TS2741 Property 'X' is missing`
- passed but not in interface → `TS2322 Property 'X' does not exist on type`
- destructured but interface-removed → `TS6133 'X' is declared but never read` / `TS2339`

This session churned through all three variants for `onToggleSearch`, `searchMode`,
`collapsed`, `onToggleCollapsed` one at a time — 2-3 throwaway builds per prop.

**Rule:** when you touch a prop, grep the prop name across the file first
(`search_files pattern=onToggleSearch`), then patch interface + destructure + ALL call
sites in the SAME turn. The LSP diagnostics returned inline by the patch tool LAG the
real state — they re-fire stale errors for a line you just fixed. Trust
`npm run build 2>&1 | grep "error TS"`, not the inline LSP block.

## 3. Sidebar agent-filter search ≠ the global search overlay

Two different features that are easy to conflate:
- **Global/header search** (`searchMode` + an overlay that REPLACES the message thread,
  hitting sessions/references/skills) — lives in the parent `Chat` component.
- **Sidebar agent-filter** — a local `useState('')` inside `ChatSidebar` that just
  narrows the visible agent/channel/swarm rows by name/role substring.

When the user says "the sidebar search only filters agents — type Hermes, only Hermes
shows," that is the SECOND feature. Do NOT wire the sidebar input to the parent's
`setSearchMode`. Build it self-contained:
```
const [filter, setFilter] = useState('')
const q = filter.trim().toLowerCase()
const matchAgent = (a, label) => !q || (label ?? a.name).toLowerCase().includes(q) || (a.role ?? '').toLowerCase().includes(q)
const showHermes    = !q || matchAgent(hermes, 'Hermes')
const showCron      = !q || 'cron jobs'.includes(q)
const visibleAgents = nonSwarm.filter(a => matchAgent(a))
const visibleSwarm  = swarm.filter(a => matchAgent(a))
```
Then gate each section's `GroupHeader` + rows on `showHermes` / `showCron` /
`visibleAgents` / `visibleSwarm`. A clear-✕ button resets `filter`.

## 4. Stars/aurora canvas bleeding THROUGH a panel = stacking context, not opacity

`StarsBackground` (and the aurora GLSL layer) mount at the app root as
`position:fixed; z-index:0`. A Chat sidebar/panel with a solid `background` but NO
`position`/`zIndex` sits in normal flow with no stacking context — so the fixed canvas
paints OVER it and the stars show through no matter how opaque the bg is. Bumping
`var(--s3)` to a lighter hardcoded hex does NOT fix it (the user reported "you can still
easily see the stars through it" after a hex bump).

**Fix:** give the panel a stacking context ABOVE the canvas — `position:'relative',
zIndex:1` on the Chat outer row wrapper (and/or the `<aside>`). Once it's above the
canvas, set the background to `var(--s3)` (`#0e131e`, the dashboard tile color) and it
reads as fully solid and matches the overview tiles.

**Color rule:** match dashboard tile surfaces with `var(--s3)`, never a one-off hex —
the user explicitly wants the Chat sidebar "to match the tiles on the dashboard / like
the overview tab," and the design tokens already encode that surface.

## 5. `toLocaleTimeString` shows 24h — `hour: 'numeric'` does NOT force 12h

When the user says "make the timestamps 12-hour / like the sidebar" and the chat
messages still render `23:08` after you've set `{ hour: 'numeric', minute: '2-digit' }`,
the cause is the SERVER/OS LOCALE. `hour: 'numeric'` only controls digit padding; the
AM/PM-vs-24h decision defaults to the runtime locale, and this host's locale is 24h. So
`new Date().toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })` yields
`23:08` here while it yields `11:08 PM` on a US-locale browser. **The fix is to pass
`hour12: true` EXPLICITLY** on every options object:
`{ hour: 'numeric', minute: '2-digit', hour12: true }`. A bare `toLocaleString()` /
`toLocaleTimeString()` with no options is the same trap and also needs it.

**This is a SCATTERED edit — grep ALL call sites before claiming done.** The dispatcher
formats time in 7+ places across two files and they drift independently:
`grep -n "toLocaleTimeString\|toLocaleString" app/src/data/chat.ts app/src/components/panels/Chat.tsx`.
This session they were: `nowTime()` + `epochToWhen()` in `data/chat.ts`; `isoToWhen()`,
the AgentRow `timeStr`, the GroupHeader `timeStr` (these two are IDENTICAL lines in
different functions → `replace_all`), `cronEpochWhen()` (a bare `toLocaleString()`), and
the report-mapping `at:` in `Chat.tsx`. Fixing only the obvious message-render site left
the sidebar/cron/past-session stamps still in 24h and cost two extra rounds. Patch every
site in one pass, then `grep -c "hour12: true"` the count == the call-site count.

## 5b. Scroll-jumps-to-top when CLOSING an overlay = auto-scroll effect keyed on a value that MUTATES during the transition

Symptom class: opening the in-message search icon (top-right of the Chat panel) and
then closing it scrolls the thread to the TOP instead of staying at the bottom. Same
shape can bite any transition where the rendered list swaps (search results ⇄ real
thread, filter on/off, agent switch).

Root cause: the bottom-pin effect was
```
useEffect(() => {
  if (displayThread.length === 0) return
  bottomRef.current?.scrollIntoView({ behavior: 'instant' })
}, [displayThread.length, isActive])
```
`displayThread` resolves to the SEARCH RESULTS while `searchMode` is true and to the
REAL thread when it's false. Closing search flips `searchMode`, which changes
`displayThread.length`, which RE-FIRES this effect mid-transition — but the scroll
container is mid-page and the DOM hasn't settled, so it lands at the top before the
sentinel exists at the bottom. The effect was doing exactly what it was told; the bug is
that its dependency (`length`) is a value that changes as a SIDE EFFECT of the overlay
toggling, not because new messages arrived.

Fix (two effects, both keyed on `searchMode`):
```
// 1. suppress the normal bottom-pin while search is open / mid-exit
useEffect(() => {
  if (displayThread.length === 0) return
  if (searchMode) return                              // <-- the guard
  // Defer past paint: when display flips none→flex, scrollIntoView in the same
  // render cycle is a no-op (the element has no layout yet).
  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      bottomRef.current?.scrollIntoView({ behavior: 'instant' })
    })
  })
}, [displayThread.length, isActive, searchMode])

// 2. a dedicated effect that re-pins to bottom the moment search CLOSES
useEffect(() => {
  if (searchMode) return
  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      bottomRef.current?.scrollIntoView({ behavior: 'instant' })
    })
  })
}, [searchMode])
```
The guard alone is not enough — without effect #2, closing search leaves you wherever
the overlay scrolled to. Effect #2 fires on the `searchMode → false` flip and lands
clean at the bottom.

### 5b-i. `display:none` → `scrollIntoView` is a NO-OP — double-RAF needed

**This is the subtle sub-trap that made 5b/5c still fail AFTER both the effect guard
and the hide-don't-unmount fix were live (2026-06-24).** When a scroll container flips
from `display:none` to `display:flex`, `scrollIntoView()` called in the SAME render
cycle silently does nothing — the element has no layout box, no scroll height, no
position. The browser needs at least one paint frame before `scrollIntoView` can act.

**Fix: defer past paint with `requestAnimationFrame` × 2.** One RAF yields after the
current frame but before the next paint; two RAFs guarantees the element has been
laid out and painted. Without this, every `scrollIntoView` on a `display`-flipped
container is dead code.

```jsx
requestAnimationFrame(() => {
  requestAnimationFrame(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'instant' })
  })
})
```

**Verify:** `scrollHeight - scrollTop - clientHeight < 150` at the container level
after the transition confirms the scroll landed. Values like `scrollTop: 43837` /
`scrollHeight: 44114` / `clientHeight: 277` with a 277px gap = at-bottom. Without
the double-RAF, `scrollTop` stays at 0 (or wherever the container was).

**The `display:none` trap also makes the `isActive`-keyed effect a no-op on the
VERY FIRST Chat open** — Chat sits at `display:none` on page load (Shell starts on
Overview), so the first `isActive → true` fires scrollIntoView on a still-hidden
container. The fixes documented in `references/react-dispatcher-dashboard.md` (pass
`isActive` + pin on visible transition) MUST include the double-RAF or they silently
fail every fresh page load.

### 5b-ii. Fresh-URL load doesn't pin to bottom = the combined-deps effect never re-fires (needs a DEDICATED `[isActive]` effect)

**Confirmed 2026-06-24, the residual fresh-load bug AFTER 5b-i's double-RAF was live.**
Symptom: \"Chat doesn't stay at the bottom on a fresh URL load — only works between tabs
after you've manually scrolled it down once.\" The main bottom-pin effect is keyed
`[displayThread.length, isActive, searchMode]`. On a fresh page load the sessions fetch
populates `viewSession` (and thus `displayThread.length`) while `isActive` is still
`false` (Shell starts on Overview). When the user then clicks Chat, `isActive` flips
`false → true` — but `displayThread.length` is UNCHANGED (the messages were already
loaded). React's dep-array comparison sees only `isActive` changed... which DOES re-fire
the combined effect, EXCEPT the timing races the panel reveal and the scrollIntoView on
the sentinel lands short. The robust fix is a **separate effect keyed on `isActive`
ALONE** that forces the scroll at the container level (not the sentinel):
```jsx
// Dedicated pin for when the panel becomes visible: force scroll regardless of
// whether displayThread.length changed (fresh-URL load has identical length across
// the isActive false→true flip, so the combined effect's timing is unreliable).
useEffect(() => {
  if (!isActive) return
  if (searchMode) return
  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      const el = listRef.current
      if (el) el.scrollTop = el.scrollHeight   // container-level, not bottomRef.scrollIntoView
    })
  })
}, [isActive])
```
Two things make this reliable where the combined effect wasn't: (1) it's keyed on
`isActive` ONLY, so it always runs on the reveal regardless of length deltas; (2) it sets
`el.scrollTop = el.scrollHeight` directly on the scroll container instead of relying on a
sentinel `<div ref={bottomRef}>` that may not yet be at its final layout position. Keep
the double-RAF (5b-i) — the container is still transitioning out of `display:none`.

**General rule for this app's scroll effects:** an auto-`scrollIntoView` must depend ONLY
on signals that mean "new content the user should see" (`displayThread.length` for new
messages, `isActive` for the panel becoming visible). When a value like `searchMode` /
a filter flag / the active-agent key ALSO changes `displayThread`, guard the main effect
against that transition and add a separate effect to restore the intended scroll position
when the transition completes. Note the existing scroll bugs in
`references/react-dispatcher-dashboard.md` (tab-switch remount, fresh-load hidden-panel)
are a DIFFERENT root cause (mount/visibility timing) — this one is dependency-driven
re-fire; don't conflate them.

## 5c. Overlay that CONDITIONALLY UNMOUNTS the message list = scroll wipe AND history-clear that survives a tab round-trip

This is the deeper variant of 5b, and the 5b effect fix does NOT cover it. Confirmed
2026-06-23: after 5b's two `searchMode`-keyed effects were already in place, the user
reported a NEW symptom — "click the search icon, exit it, click another tab, come back
to Hermes, and the chat history is CLEARED." The two-effect scroll fix was live and
correct; the history-wipe was a separate root cause.

Root cause: the entire message-list scroll container was wrapped in a conditional MOUNT:
```
{!searchMode && (
  <div ref={listRef} style={{ ...overflowY:'auto'... }}>
    ...displayThread.map(...)...
    <div ref={bottomRef} />
  </div>
)}
```
When search opens, `searchMode` flips true and React UNMOUNTS the whole `<div>` —
`listRef`, `bottomRef`, and all the rendered message nodes leave the DOM. When search
closes it REMOUNTS fresh at scrollTop 0. The 5b effects try to re-pin but they're racing
a brand-new subtree. Worse: a subsequent tab-switch-and-back (the Chat panel itself is
always-mounted via `display:none` in `Shell.tsx`) re-runs the mount/remount churn and the
list comes back empty-looking until the next state change — reading as "the history got
cleared."

**Fix: never conditionally unmount the message list. Keep it mounted and toggle
visibility with `display`**, exactly like the always-mounted Chat panel pattern in
`Shell.tsx` (`display: activePanel==='chat' ? 'flex' : 'none'`):
```
{/* always mounted — preserves scroll position + DOM nodes; hidden behind the overlay */}
<div ref={listRef} style={{ ...overflowY:'auto', display: searchMode ? 'none' : 'flex', ... }}>
  ...displayThread.map(...)...
  <div ref={bottomRef} />
</div>
```
Remove the wrapping `{!searchMode && (` / `)}` entirely. The search overlay block stays
its own `{searchMode && (...)}` sibling (the overlay genuinely should mount/unmount; it's
the THREAD list that must persist).

**The general principle (it recurs all over this app):** anything whose scroll position,
input state, or rendered children must survive a transition (overlay open/close, tab
switch, agent switch) should be hidden with `display:none`, NOT removed with
`{!cond && (...)}`. Unmounting throws away DOM + local state; `display:none` keeps both
and is free to toggle. This is the SAME lesson as Shell.tsx keeping `<Chat>` always-mounted
and as the `key={activePanel}` remount bug in `references/react-dispatcher-dashboard.md` —
when in doubt on this dashboard, prefer hide-don't-unmount for stateful subtrees.

**Two-trap sequence to remember:** a scroll-on-overlay-close report can have BOTH a 5b
cause (effect keyed on a value that mutates during the transition) AND a 5c cause (the
list is conditionally unmounted). Fixing 5b can leave 5c still biting on the tab round-trip.
If the scroll/history still misbehaves after the 5b effects are correct, grep the panel for
`{!searchMode && (` / `{!<flag> && (` wrapping the scroll container and convert it to
`display`.

**Build pitfall during the unmount→display conversion:** removing the `{!searchMode && (`
wrapper means deleting the matching `)}` after the list's closing `</div>`. The patch
tool's inline LSP will likely flag a phantom `Unexpected token … Did you mean '}'` on the
sibling line — it's a stale parse. Confirm with `npm --prefix app run build 2>&1 | grep -E
"error TS|✓ built"`; a clean `✓ built` is the truth, the LSP block lags (same lesson as §2).

## 5d. History-clear-on-tab-switch can ALSO be a STATE clear (`viewSession` nulled), not just an unmount

Confirmed 2026-06-23, immediately after the 5c `display:none` fix shipped: the user STILL
reported "switch tabs and the chat history clears out with Hermes." 5c (keep the list
mounted) was live and correct, so the remaining wipe is NOT a DOM unmount — it's the
RENDERED-FROM state going empty. For the Hermes channel, `displayThread` resolves to
`viewSession.msgs` when `viewSession` is set, and falls back to `thread`
(`threads['default']`, which is `[]` because `INITIAL_THREADS` has no `default` key). So
the instant `viewSession` becomes `null`, the panel renders the empty "Pick up where you
left off" state — indistinguishable from "history cleared."

`viewSession` is nulled in exactly three places: `selectAgent` (line ~1071),
`selectCron` (~1077), and the `/new` command (~1167). The dashboard's sibling reference
(`references/react-dispatcher-dashboard.md`) already documents the FIX for this exact
class: **`selectAgent` nulls `viewSession` unconditionally → make the clear conditional on
the destination, and keep a `lastViewSessionRef` that's restored on return-to-Hermes.**
Don't re-derive it — that reference has the pattern (mirror Chat's `hermes-chat-*`
localStorage seeding so the last Hermes session survives an agent/tab round-trip).

**Diagnostic that pinpoints it fast (use this instead of guessing which call site fires):**
drop a one-shot effect right after the `useState` and rebuild —
```
const [viewSession, setViewSession] = useState<PastSession | null>(null)
useEffect(() => {
  console.log('[Chat] viewSession changed:', viewSession ? `${viewSession.id} (${viewSession.msgs.length} msgs)` : 'null')
}, [viewSession])
```
Then reproduce in the browser with the console open (search → exit → switch tab → back)
and read which transition logs `null`. That log line names the offending call site
directly. REMOVE the probe once the conditional-clear fix lands — leaving a `console.log`
in the shipped bundle is noise.

**To read that console YOURSELF** (instead of asking the user to copy-paste it): the
dispatcher dashboard's `localhost:8787` is on the USER'S machine, and neither the sandbox
`browser_navigate` tool (its proxy can't route to the user's localhost) nor the
host-side headless-Chromium recipe (wrong machine) can reach it. The fix is **Playwright
MCP running on the user's Mac, bridged to Hermes over Tailscale** — then `navigate`/`console`
calls hit the user's real browser. Full setup (the `npx @playwright/mcp --host 0.0.0.0`
command, the gated `config.yaml` wiring, and the gateway-restart self-block that forces the
user to run the restart from an outside shell) is in `references/remote-browser-mcp-bridge.md`.

**Triage order for any "history cleared on tab/agent switch" report on this Chat panel:**
(1) is the message list conditionally unmounted (`{!flag && (`)? → 5c, convert to
`display`. (2) Still wiping after that? → it's a STATE clear; grep `setViewSession(null)`
and make each call conditional on the destination + restore on return. The two fixes are
independent and a hard case needs both.

## 5e. Janky scroll ANIMATION on tab/channel switch = competing scroll mechanisms + ungated bulk-load pins

Confirmed 2026-06-24, the residual symptom after 5b/5c/5d were all live: "weird scroll
animation when switching between chats," ultimately localized by the user to "just on
the executor and cron job channel." Two distinct causes, fix BOTH:

**Cause 1 — two scroll mechanisms racing.** The code had `bottomRef.scrollIntoView(...)`
(sentinel-based) in some effects and `listRef.scrollTop = listRef.scrollHeight`
(container-based) in others, each on its own double-RAF chain. When `isActive` flips true
they fire simultaneously, and the two competing scroll paths produce a VISIBLE animated
scroll instead of an instant snap. **Fix: collapse every pin into ONE helper, container-level,
no sentinel:**
```jsx
const pinToBottom = () => {
  const el = listRef.current
  if (el) el.scrollTop = el.scrollHeight
}
// every effect calls requestAnimationFrame(() => requestAnimationFrame(pinToBottom))
```
Delete the `bottomRef.scrollIntoView` calls entirely (the `<div ref={bottomRef}>` sentinel
can stay as a layout anchor but nothing should scroll TO it). One mechanism = no race = no
animation.

**Cause 2 — the length-change pin fires on async BULK loads.** Worker channels load their
content asynchronously: `setAgentReports` (executor/coder reports) and `setCronOutput`
populate `displayThread` AFTER you switch to the channel. That changes
`displayThread.length`, which re-fires the `[displayThread.length]` pin effect — so merely
SWITCHING to executor/cron triggers a scroll-down animation as the reports arrive, even
though no live message happened. **Fix: gate the length-change pin behind a `liveMessageRef`
flag that ONLY the live-message paths set:**
```jsx
const liveMessageRef = useRef(false)

// length-change effect — only pins when a live SSE delta / user send caused it
useEffect(() => {
  if (displayThread.length === 0 || searchMode) return
  if (!liveMessageRef.current) return     // bulk async load → skip
  liveMessageRef.current = false
  requestAnimationFrame(() => requestAnimationFrame(pinToBottom))
}, [displayThread.length, searchMode])    // note: isActive REMOVED from deps here
```
Set `liveMessageRef.current = true` in exactly two places: the SSE `ev.type === 'delta'`
handler (incoming agent text) and the user-`send()` path right before the `setThreads`
that appends the user bubble. Reports/cron bulk-loads never set it, so they no longer
animate.

**Keep the dedicated `[isActive]` and `[searchMode]` effects ALWAYS-pinning** (those are
intentional instant snaps on panel-reveal / overlay-close, not content-driven) — only the
`[displayThread.length]` effect needs the `liveMessageRef` gate. Removing `isActive` from
the length-effect's deps is correct: the `[isActive]` effect already owns the reveal pin.

**General principle (extends 5b's rule):** an auto-scroll keyed on `displayThread.length`
will fire on EVERY content change including async bulk loads you didn't initiate. If a
channel populates its thread from a fetch (reports, cron, paginated history), the raw
length-change is NOT a "new message the user is watching arrive" signal — gate it behind a
ref that only the genuinely-live paths (SSE delta, user send) set.

## 5f. Chat opens on a STALE session = `localStorage` last-session pin never updated for new sessions

Confirmed 2026-06-24. Symptom: "Hermes Chat channel isn't displaying the latest/most
recent messages" — the panel loads, scrolls to the bottom correctly, but the bottom-most
message is from a PREVIOUS day's conversation, not today's. This is NOT a scroll-timing
bug (5b–5e) and NOT the backend sort bug — the API returns the right session as
`sessions[0]`, but the frontend overrides it with a stale `localStorage` value.

Root cause, in the initial-load effect (`Chat.tsx`, the `useEffect(() => {...}, [])` that
fetches `/api/chat/sessions`):
```jsx
const savedId = lsGet('hermes-chat-last-session', '')
const target = (savedId ? sessions.find(s => s.id === savedId) : null) ?? sessions[0]
```
`hermes-chat-last-session` is written ONLY when the user explicitly clicks a session
(`openSession` → `lsSet`). It is NEVER updated when a new Hermes session is *created*. So
on every page load the panel re-opens the last MANUALLY-clicked session — which can be days
old — instead of the most-recent one the API already sorted to `sessions[0]`. The user's
mental model is Telegram ("show me the latest"), so the localStorage preference silently
fights that expectation.

**Fix: on initial mount, always open `sessions[0]` (the API already sorts
`ORDER BY started_at DESC`). Drop the localStorage override from the load path:**
```jsx
const target = sessions[0]   // most recent; API is already sorted DESC
```
Keep `lsSet('hermes-chat-last-session', …)` in the explicit-click handler if you still want
manual selection to persist WITHIN a session's navigation — but it must NOT win over
`sessions[0]` on a fresh load. (If you want both "resume last click" AND "jump to newest on
a genuinely new session," compare the saved session's timestamp to `sessions[0]` and prefer
the newer — but the simplest correct behavior the user asked for is "always newest.")

**This is a DIFFERENT root cause from the three already documented for "Chat opens on the
wrong session":** (a) `key={activePanel}` remount (react-dispatcher-dashboard.md), (b)
backend sorting by `started_at` instead of `MAX(messages.timestamp)`
(react-dispatcher-dashboard.md), (c) `setViewSession(null)` clear on agent switch (§5d).
This 5f one is the FRONTEND localStorage pin overriding a correctly-sorted API. When
triaging a "wrong/stale session" report, check all four — and check 5f FIRST because it's a
one-line frontend fix with no backend restart needed.

### 5f-i. Diagnostic: prove API-returns-latest vs DOM-shows-stale with a Playwright DOM probe

The technique that pinned 5f fast (instead of re-reading the React source guessing): use the
Playwright MCP `browser_evaluate` to read the live scroll container AND re-fetch the messages
endpoint from inside the page, then compare. This separates "API is wrong" from "frontend
ignored the API."

1. Read the scroll container's actual position + the last rendered message text:
   ```js
   () => {
     const el = [...document.querySelectorAll('*')].find(e => {
       const s = getComputedStyle(e);
       return (s.overflowY === 'auto' || s.overflowY === 'scroll') && e.scrollHeight > 2000;
     });
     // last text near the bottom tells you WHAT session/era is rendered
     return { scrollTop: el.scrollTop, scrollHeight: el.scrollHeight,
              atBottom: el.scrollHeight - el.clientHeight - el.scrollTop < 10 };
   }
   ```
2. From inside the page, re-fetch what the API actually returns for the expected session
   (the page's own cookie auth applies):
   ```js
   async () => {
     const r = await fetch('/api/chat/sessions/<sid>/messages');
     const m = await r.json();
     return { count: m.length, last: m[m.length-1]?.text?.slice(0,80), lastAt: m[m.length-1]?.at };
   }
   ```
3. Read `localStorage.getItem('hermes-chat-last-session')` — if it's an OLDER session id than
   `sessions[0]`, that's the smoking gun for 5f.

If the API's last message is today's but the DOM's last message is older → the frontend loaded
the wrong session (5f), not a scroll or backend-order bug. The API field name is `text` (not
`content`) and timestamps are `at` — the backend `/api/chat/sessions/{id}/messages` maps
DB `content`→`text` and formats `timestamp`→`at`.

### 5f-ii. Sessions list is dominated by cron/subagent rows (telegram sessions buried)

While diagnosing 5f, noted but separate: `/api/chat/sessions` returns ALL non-archived
sources. On this host `state.db` has ~785 `cron` + ~243 `subagent` sessions vs ~86
`telegram` (user) sessions. If a future change makes the Chat sidebar list "recent sessions"
without a source filter, the cron/subagent runs will bury the actual user conversations.
The Chat panel's "Hermes channel" specifically wants `source='telegram'` sessions. If asked
to fix "the session list is full of junk runs," filter by source server-side
(`WHERE source='telegram'`) rather than client-side after a LIMIT.

## 6. The global `--tile-border` token

Tiles across the whole dashboard share `--tile-border` (was gold
`rgba(246,183,60,0.18)`). To remove the gold outline from ALL tiles at once, change the
token in `app/src/styles/tokens.css` (one line: `--tile-border` + `--tile-border-hover`)
— every tile (overview, kanban, agents, chat sidebar) inherits it. Do NOT hunt
per-component border styles; the token is the single source of truth.

## Build + verify (every change)
```
cd /root/hermes-dispatcher && rm -rf app/dist && npm --prefix app run build 2>&1 | grep -E "error TS|✓ built"
ls app/dist/assets/index-*.js
```
Report the new `index-<hash>.js` and tell the user to hard-refresh (Cmd+Shift+R) — the
browser caches `index.html` → the old bundle keeps serving otherwise. `app/dist/` is
gitignored, so a worker that only pushes source leaves the live site on the OLD bundle;
ALWAYS rebuild after editing.
