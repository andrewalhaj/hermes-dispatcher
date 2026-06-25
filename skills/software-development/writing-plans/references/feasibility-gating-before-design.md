# Feasibility-Gating Before Design

A design-phase discipline that sits *between* brainstorming and plan-writing: before
you commit to any architecture, **verify the load-bearing technical premise against
reality, and surface feasibility walls early** so the user's stated approach can
collapse into the one that's actually buildable. Costs minutes; saves building the
wrong app.

## The core move

For any "build X" request, identify the ONE fact that decides whether X is even
possible as stated, and verify it *before* asking design-detail questions. Don't
refine the layout of a feature that can't exist.

- Probe the environment for the load-bearing fact (hardware, API capability, audio
  I/O, network path) with a real check — not an assumption.
- If a wall appears, **name it plainly and immediately**, then offer the reframe.
  A feasibility wall surfaced now is worth more than a polished design that dies in
  implementation.
- Re-derive what "real-time" / "live" / "instant" actually *requires* for THIS use
  case. The same word means different things across use cases and that distinction
  often dissolves (or confirms) the wall.

## Worked example (D&D NPC TTS, 2026-06)

The request evolved: "real-time voice changer" → target-voice (RVC) → ElevenLabs →
TTS → **D&D DM giving NPCs voices**. Three feasibility checks each reframed it:

1. **GPU check** (`nvidia-smi`): no GPU on the server → real-time *neural* voice
   conversion off the table server-side. Reframe: the run-time GPU must live near
   the user's mic anyway — it's a client-side problem, not a Hetzner problem.
2. **The build-vs-run split:** "do we need a GPU?" → building the app needs none;
   *training* a voice model is a one-time rentable/skippable batch job; only
   *live inference* needs a local GPU. Separating these three dissolved the
   "Hetzner has no GPU" blocker for everything except live run-time.
3. **ElevenLabs streaming vs segment** (verified against their API docs): their
   speech-to-speech "streaming" streams the *output* of a complete uploaded
   segment — it is NOT a continuous bidirectional voice-changer. Surfaced plainly:
   "you cannot talk over someone live in a target voice; no managed API can,
   because cloud round-trip + segment model forbids it." This pre-empted building
   a "live call" app that was actually walkie-talkie.
4. **The use-case collapse:** once the real goal landed (turn-based D&D NPC voices),
   the latency wall **didn't apply at all** — a 1-2s beat to voice a line is natural
   at the table. TTS became the *correct* tool, not a fallback.

## The recurring fork to surface for any voice/audio build

- **Live conversational target-voice** (overlap, calls, gaming) → REQUIRES local GPU
  (w-okada/RVC client-side). No cloud API does this; physics (round-trip + segment).
- **Segment / push-to-talk** (say a line → ~1s beat → playback) → buildable now via
  ElevenLabs speech-to-speech, no GPU.
- **TTS** (text → speech in a chosen/cloned voice) → buildable now, lowest effort;
  the right tool for turn-based use (tabletop NPCs, narration, voice messages).
- **Voice-model training** → one-time GPU batch job; rent by the hour
  (Vast.ai/RunPod ~$0.30-0.50/hr) or Colab, or grab an existing community model.

## The generation-timing fork (for any "generate media on demand" app)

Once feasibility is settled, the next architectural fork is *when* assets are made:
- **Live** — generate per-request in-session (max flexibility, per-use cost, needs net).
- **Pre-rendered** — batch ahead of time, fire instantly like a soundboard
  (zero latency/cost, offline, but only pre-scripted content).
- **Hybrid** — pre-render the predictable, live-generate the improvised. Best UX,
  most to build. Often the right answer for improv-heavy domains (tabletop, etc.).

## Anti-pattern

Do NOT design or scaffold on an unverified premise to "keep momentum." If the
load-bearing fact is unconfirmed, confirming it IS the next step. Fabricating a
plausible capability the tool doesn't have (e.g. "live voice-changer on ElevenLabs")
is the one unforgivable failure — surface the limit instead.
