# Voice Satellite → Hermes (full agent by voice)

Decision record, 2026-06-11. Goal: Andrew speaks to HERMES (full agent — web, servers, Mealio, anything), not just HA intents. Execute this when the Voice PE arrives.

## Hardware decision: HA Voice Preview Edition (~$59)

- ESPHome Assist satellite: dual mic array, rotary dial, on-device wake word (stock includes **"Hey Jarvis"**; fully custom wake words via microWakeWord).
- **Internal speaker: small mono** — fine for spoken replies, not music.
- **3.5mm stereo jack, dedicated DAC (TI AIC3202, 48 kHz)** — line-out upgrade path. Era 300 accepts line-in via Sonos USB-C adapter. Alternative: keep internal speaker for short replies, TTS-announce long-form to Sonos over network (already works).
- **Verified June 2026: no successor exists or is announced.** "Preview" refers to the *software ecosystem's* maturity, not beta hardware (shipping since Dec 2024, continuous ESPHome firmware updates). Nabu Casa's most recent hardware (Nov 2025) was the Connect ZBT-2 Zigbee/Thread dongle — not a voice device. Open ESPHome device → stays supported even if a v2 ships; worst case becomes satellite #2 for multi-room.
- **HA Green is NOT a voice device** — it's a server that runs HA (no mic/speaker). Don't confuse the lineup: Green/Yellow = run HA; Voice PE = the thing you talk to; ZBT-2 = radio dongle.

### Rejected: Echo Dot path
Echo firmware is locked — Alexa backend not replaceable. Only route is a custom Alexa Skill (dev-mode): forced "ask hermes" invocation prefix, **~8-second spoken-response deadline** (incompatible with real agent runs; UX degrades to voice-ack + answer-to-Telegram), Amazon cloud in the loop. Dropped entirely in favor of Voice PE. Sonos Era mics are likewise locked (Alexa/Sonos Voice only) — usable as OUTPUT, never as input.

## Target architecture

```
Voice PE (wake word on-device)
  → HA Assist pipeline (ash-1, transport only — HA never interprets the sentence)
    → STT: Whisper container via Wyoming — RUN ON hil-1 (32GB); ash-1 (2GB) cannot host it
    → Conversation agent slot: HA supports OpenAI-compatible custom endpoints
        → small shim (~100 lines, hil-1) → Hermes webhook platform (port 8644)
        → full Hermes agent run (tools, memory, skills — same as Telegram)
    → TTS back through the device: Piper (local) / Edge TTS (free neural, current voice-note default)
        / OpenAI/ElevenLabs (paid) / any TTS + RVC post-process for a custom timbre
        (Andrew already has a real-time RVC pipeline from the D&D soundboard project)
```

- Hermes webhook platform is NOT yet enabled — needs `platforms.webhook` in config.yaml (port 8644, HMAC secret) + gateway restart. **Gated change.**
- Long agent runs: voice ack immediately, full result via TTS announce + Telegram.
- Per-channel persona: voice channel gets its own system prompt — terse spoken answers, no markdown, verbosity configurable. Telegram persona unchanged.
- HA-free variant possible (Pi + openWakeWord/Wyoming straight into a Hermes voice service) but more custom code, fewer proven parts — HA-as-transport is the chosen shape.

## Known issue at time of writing
HA 2026.1 had a latency regression with Wyoming satellites (community-reported, being worked). If responses are slow after setup, check HA core version before debugging the pipeline.

## US vendors (verified 2026-06-11)
$58.95. Fastest to SE Michigan (48310): **Apollo Automation** (Versailles KY, ~330 mi, official HA distributor) → fallback **CloudFree** (TX, 401 units in stock, same-day-processing reputation). AmeriDroid (CA) and Seeed (CA, slow 1–3 day handling) are slower options.
