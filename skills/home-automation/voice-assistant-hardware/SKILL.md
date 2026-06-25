---
name: voice-assistant-hardware
description: "Voice-to-Hermes hardware: device selection, pipeline design."
version: 1.0.0
platforms: [linux]
metadata:
  hermes:
    tags: [voice, assist, wake-word, whisper, tts, echo, voice-pe, home-assistant]
    related_skills: [home-assistant, home-assistant-best-practices]
    created_by: agent
load_when:
  - "user wants to talk to Hermes/an agent by voice"
  - "Echo Dot / Alexa / smart speaker integration questions"
  - "HA Voice PE, Wyoming satellite, Assist pipeline hardware"
---

# Voice Assistant Hardware → Hermes

Decisions and facts from the 2026-06 voice project (Andrew). Goal: speak to the FULL Hermes agent (not HA intents), with configurable wake word, voice, and persona.

## Device decision tree (settled 2026-06-11)

1. **HA Voice Preview Edition (~$59) — the answer.** ESPHome satellite: dual mics, on-device wake word (stock "Hey Jarvis", or custom via microWakeWord), rotary dial, small mono internal speaker + 3.5mm stereo jack w/ dedicated DAC (TI AIC3202, 48kHz) for external speakers. Internal speaker fine for spoken replies only; jack → Sonos Era 300 line-in (USB-C adapter) for quality.
   - Still the latest as of 2026-06 (verified live): no successor announced; Nabu Casa's Nov-2025 hardware was Connect ZBT-2 (Zigbee dongle). "Preview" = software-ecosystem maturity, NOT beta hardware. Open ESPHome device — never bricked by a v2.
   - US vendors: Apollo Automation (Versailles KY — fastest to Michigan), CloudFree (TX, deep stock, fast handling), AmeriDroid (CA), Seeed (CA, slow processing).
2. **ESP32-S3-BOX-3 / M5 ATOM Echo** — same pipeline, DIY/prototype tier only.
3. **Echo Dot — REJECTED.** Firmware locked; only path is a custom Alexa Skill ("ask hermes …" prefix, ~8s response ceiling, Amazon cloud middleman). Only viable UX there is voice-ack → answer via Telegram. Inferior on every axis; don't re-propose unless user insists.
4. **Sonos Era 300 mics** — locked to Alexa/Sonos Voice, NOT reroutable. Usable as OUTPUT (HA TTS announce) only.
5. **HA Green** — a SERVER, not a voice device (no mic/speaker). Don't confuse categories. For HA-host duty a Pi 5 8GB + NVMe beats it (2× RAM, faster, same money; microSD kills itself on recorder writes — NVMe/USB-SSD mandatory).

## Pipeline architecture (agreed)

Voice PE (wake word on-device) → Wyoming → **Whisper STT container on the biggest CPU box** (hil-1 32GB; ash-1 2GB cannot) → HA "conversation agent" slot pointed at a ~100-line OpenAI-compatible shim → **Hermes gateway** (full toolset, memory, skills) → TTS back to device (Piper local / Edge / OpenAI / RVC post-process for a custom timbre — user already runs an RVC rig).

Key framing that landed with the user: HA is **plumbing, not the brain** — the conversation-agent slot makes the voice box "just another channel like Telegram." Voice channel gets its own persona/verbosity via per-channel system prompt.

Long-agent-run reality: voice ack first, full result via TTS announce + Telegram. Never promise free-flowing low-latency agent runs by voice.

## Alexa Skill route (if ever forced)

Custom dev-mode skill → Amazon cloud → HTTPS shim (FastAPI, validate Amazon request signature) → Cloudflare tunnel hostname (Alexa requires valid CA cert; CF provides) → Hermes webhook platform (port 8644, enable in config.yaml — see webhook-subscriptions skill). 8-second spoken-response ceiling is the hard constraint.

## Pitfalls

- Don't pitch "Apple Silicon runs Whisper fast" for Intel Macs — check the actual hardware generation first (a "Mac mini" spans 2014 Intel → M4).
- Laptop screens have no video input; for headless-box installs use a $13 USB HDMI capture stick (shows firmware/boot picker, mini sees real EDID) or a TV. Network remote control can't reach pre-OS stages.
