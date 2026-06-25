# DM Voice Board — Project State

**Last updated:** 2026-06-09
**Owner:** Andrew (DM)
**Status:** Scoping (architecture locked, stack TBD-pending answers)

## What it is
A real-time voice-changer **soundboard** for D&D NPC voices. The DM speaks an NPC's
line into a mic; the app converts the DM's voice into that NPC's timbre **live**, and
lets the DM switch between NPC voice profiles on the fly.

## Architecture (LOCKED)
- **Live mic input → real-time voice conversion → NPC timbre out.** Not text-driven.
- **Deployment target:** the end-user DM's **gaming laptop, NVIDIA RTX 3070 (8GB)**.
- **Dev environment needs NO GPU** — the 3070 is the runtime/ship target, not the build box.

## Superseded (pivot 2026-06-09)
Prior direction was turn-based TTS via ElevenLabs with "no local GPU." All three are
SUPERSEDED for this app's core: it's now live voice **conversion** (VC ≠ TTS), GPU is
present on the deployment side, and ElevenLabs TTS is not the conversion engine.

## Candidate stack (to confirm)
- **w-okada Voice Changer Client** (RVC real-time) — primary candidate. Light enough for
  8GB, supports hot-swapping RVC models → natural fit for per-NPC switching. Windows one-click pkg.
- **seed-vc** — newer, zero-shot real-time VC (reference clip instead of trained model).
- **so-vits-svc** — higher fidelity, heavier; real-time on 3070 is borderline.

## Real cost center
**Per-NPC voice model creation** — training data / reference clips per NPC voice. This is
where the actual production effort lives, not the runtime plumbing.

## Answers locked (2026-06-09)
1. **OS:** Windows → w-okada one-click bundle, no Python env on the DM's machine.
2. **NPC sourcing:** MIXTURE — some hero NPCs as full-trained RVC models, some one-offs
   as quick/low-data RVC models (or seed-vc zero-shot for true no-train). Single live
   engine (RVC/w-okada) preferred over running two engines.
3. **Routing:** PLAY OUT LOUD IN THE ROOM. No VAC / OBS / Discord. Output → laptop or
   tabletop speaker. Kills the routing-complexity problem entirely.

## Build path (POC-first)
1. Install w-okada VC Client (Windows one-click) on the 3070 laptop.
2. Validate latency live with ONE prebuilt RVC model before building any NPC content.
3. Set output device = room speaker; use a headset/directional mic to avoid feedback.
4. Once latency is proven, build the NPC board: full-train hero voices, quick-train one-offs.

## Open considerations
- **Mic feedback risk** (speakers loud near mic) → headset or directional/dynamic mic.
- **Switching UX** — w-okada model swap is a dropdown; confirm it's fast enough for live
  table use, or pre-stage a few models as hotkeys if it lags.
