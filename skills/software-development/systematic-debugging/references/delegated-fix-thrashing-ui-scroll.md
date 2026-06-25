# Worked example: four delegated "fixes" for one UI bug, none verified empirically

Canonical instance of the **delegated-fix Rule-of-Three** failure mode (SKILL.md Phase 4 step 4).
A "Chat panel should open scrolled to the most recent message" bug in a React/Vite dashboard
(`hermes-dispatcher`, FastAPI :8787) took FOUR failed fix attempts before the orchestrator
stopped dispatching theories and investigated.

## What the bug actually was (symptom)
Opening the Chat tab rendered the message list at the TOP instead of pinned to the bottom
(most-recent message). Sub-symptom in early rounds: a visible smooth scroll-down animation.

## The four failed attempts (each a theory dispatched to a kanban worker)
1. `useEffect` → `scrollTop = scrollHeight` on `[thread.length, running, viewSession]`.
2. Converted to `useLayoutEffect` (pre-paint pin).
3. Added `scrollBehavior: 'auto'` inline + `el.style.scrollBehavior='auto'` to defeat the
   global CSS `scroll-behavior: smooth` (real contributing factor — killed the *animation*
   sub-symptom, but the list still opened at the wrong position).
4. Added a `ResizeObserver` (pin once when scrollHeight>clientHeight, then disconnect) PLUS a
   `setTimeout(420ms)` post-entrance-animation re-pin.

After #4 the file stacked **three redundant scroll mechanisms** and STILL failed.

## Why the Rule of Three didn't fire on its own
Each fix was authored by a **kanban worker that built green, committed, and reported success.**
From the orchestrator's seat every attempt looked "done" — clean TypeScript build, new bundle
hash, committed to master. The failure only surfaced when the user tested the live page. The
worker could not contradict the orchestrator's root-cause theory; it faithfully implemented the
spec it was handed. So four genuinely-failed fixes read as four successes until a human looked.

## The correcting signals (from the user)
- "Coder-C solution... tell me what's wrong with that." (the worker's success report was not proof)
- "still not correct do it yourself with Claude Code, no kanban, figure it out yourself."

## What actually worked
Stopped writing fix-specs. Launched an **investigate-first mandate** (Claude Code in print mode,
backgrounded) with an explicit charter: *find the real cause empirically, prove it with evidence
(log scrollHeight/clientHeight/which element actually scrolls), do NOT just re-apply the obvious
scroll trigger* — and fed it the list of four ruled-out theories so it wouldn't repeat them.

Two facts verified directly before delegating the investigation (so the investigator started from
ground truth, not another guess):
- Backend `GET /api/chat/sessions/{id}/messages` returns `ORDER BY timestamp ASC` → newest is at
  the BOTTOM → scroll-to-bottom is the correct DIRECTION. (Rules out an ordering bug.)
- `Shell.tsx` wraps each panel in `<div key={activePanel}>` → the panel **fully remounts** on tab
  switch, and the wrapper has a `hpanelin 0.38s ... both` entrance animation → strong candidate
  that the scroll container has `clientHeight: 0` while animating in, making every pin a no-op
  with nothing re-pinning once real height appears.

## The ACTUAL root cause (found on the 5th, investigate-first pass)
The list container was `display: flex; flex-direction: column`. During the async load window
(two sequential fetches: sessions list, then that session's messages) it rendered a placeholder
child styled `margin: auto` ("Loading conversation…"). **In a flex column, `margin: auto` on a
child expands to consume ALL free space** — so the container had `scrollHeight === clientHeight`
(zero overflow). Every scroll mechanism fired during this window saw nothing to scroll:
- the `useLayoutEffect` / `setTimeout` pins ran while overflow was 0 → no-op;
- the `ResizeObserver` fired on the *placeholder* layout, saw `scrollHeight === clientHeight`,
  and in attempt #4 it **`disconnect()`-ed itself before the real messages ever rendered**.

When `setViewSession` finally swapped the placeholder for real messages, overflow appeared — but
nothing was left armed to re-pin. The container entrance animation (`hpanelin`) and full remount
(`key={activePanel}`) made the timing even less predictable, which is why every *timing-based*
attempt missed.

## The winning fix (minimal, replaced all three stacked mechanisms)
A single `useEffect` keyed on the **rendered content length**, deferring the pin one frame via
`requestAnimationFrame` so it always runs AFTER React commits and the browser measures the new
message layout — independent of fetch timing or animation duration:

```tsx
useEffect(() => {
  if (displayThread.length === 0) return        // skip the empty/placeholder state
  const el = listRef.current
  if (!el) return
  const id = requestAnimationFrame(() => {
    el.style.scrollBehavior = 'auto'            // defeat global CSS smooth-scroll
    el.scrollTop = el.scrollHeight
  })
  return () => cancelAnimationFrame(id)
}, [displayThread.length])                       // fires when messages actually arrive
```

Key properties that made it robust where the others failed:
- **Keyed on the array that's actually rendered** (`displayThread.length`), not `viewSession` —
  so it fires exactly when content lands, not on an intermediate state change.
- **Guards the empty state** (`length === 0` early-return) — never runs while the `margin:auto`
  placeholder owns the height.
- **`requestAnimationFrame`** — pins after layout is committed and measured, so `scrollHeight` is
  real. No magic `setTimeout` constant racing the network.
- Kept the `scrollBehavior='auto'` override (the one genuinely-correct carry-over from attempt #3)
  to neutralize the global `scroll-behavior: smooth` in `index.css`.

The three prior mechanisms (useLayoutEffect, ResizeObserver, setTimeout) were all DELETED — once
the real cause was understood, the redundant stack collapsed to one effect.

## Generalizable technique: "scroll pin is a silent no-op"
When a programmatic `scrollTop = scrollHeight` does nothing, suspect the container has **no
overflow at the moment the code runs** — `scrollHeight === clientHeight`. Common causes:
- a flex/grid child with `margin: auto`, `flex: 1`, or `justify-content: center` filling the box
  during a loading/empty state;
- the element mounting at `height: 0` behind an entrance animation;
- async content not yet rendered when the effect fires.
Fix by keying the pin on the *rendered content* and deferring with `requestAnimationFrame` (or a
double-rAF for animation-gated layouts), NOT by adding more triggers or longer `setTimeout`s.

## Lessons (encoded into SKILL.md)
1. **Delegated fixes count on the Rule-of-Three counter.** 4 dispatched theories = 4 failed
   fixes = architecture/approach question, identical to typing them yourself.
2. **A worker's "built green + committed" is not verification of the symptom.** Server-side green
   is a false positive for client-side death (see also `verification-before-completion`). Verify
   the live result the user actually sees.
3. **After 2+ failed fixes, the next dispatch is INVESTIGATE, not FIX.** Hand the worker an
   empirical-investigation charter + the ruled-out theories; never another bare fix-spec.
4. **Stacking more triggers is the tell.** When a fix *adds another mechanism* on top of the prior
   ones (3 scroll triggers coexisting), you're symptom-patching, not root-causing. Consolidate
   only after the real cause is proven.

## Cross-refs
- `verification-before-completion` — don't claim done on server-side green.
- Hermes AGENTS.md "Verification" — existence ≠ coverage; read the live result.
