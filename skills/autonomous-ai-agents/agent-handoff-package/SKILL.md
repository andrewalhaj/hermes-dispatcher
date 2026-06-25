---
name: agent-handoff-package
description: "Author a self-contained agent handoff/knowledge package."
version: 1.0.0
author: Hermes Agent
metadata:
  hermes:
    tags: [handoff, knowledge-package, bootstrapping, dedicated-bot, profiles, documentation]
    related_skills: [gateway-platform-setup, hermes-maintenance, knowledge-store]
load_when:
  - "user asks for handoff / knowledge-transfer / bootstrap docs for a domain"
  - "user wants a dedicated/separate bot or profile scoped to one domain (HA, finance, a project)"
  - "user says 'document everything so another agent can take over X'"
  - "you need to hand institutional knowledge to a future zero-context session"
---

# Agent Handoff Package

A handoff package is a **doc set that bootstraps a fresh agent** — a new platform bot, a new Hermes profile, or a future session that starts cold. The reader has NONE of your conversation history. Everything it needs must be on disk, accurate, and self-contained. The deliverable is operational competence in the target domain, not a narrative of what you did.

## When to use
- User is standing up a **dedicated bot** (e.g. "an HA-only Telegram bot", "a finance bot") and wants it "capable for that."
- User asks to "make handoff documents for all the X stuff you've done."
- You're consolidating cross-session domain knowledge so the next agent doesn't re-discover it.

## Core principles (each one was a real lesson)

### 1. VERIFY AGAINST LIVE STATE — never write from memory
This user (and good practice generally) demands docs grounded in reality. Before writing, pull ground truth: `docker ps`, the integration/entity registry, bind addresses, config files, container images, actual IDs. Memory and prior summaries drift; a handoff written from them ships stale facts that bite the new agent on day one. Put a "verified live YYYY-MM-DD" stamp on data-bearing docs and include the exact command to re-derive each inventory, so the next agent can refresh it.

**Live verification also surfaces ACTIVE FAULTS, not just confirms architecture — capture them as handoff content.** When you pull ground truth you may find a subsystem is currently BROKEN (e.g. an integration with `state=None` / zero entities, a service erroring in `docker logs`). Don't silently omit it or treat it as out of scope. Diagnose the root cause then and there (read the actual exception + the relevant config/registry), and record a dated "CURRENT STATE: broken — symptom, root cause, fix options (gated on approval)" entry in BOTH the subsystem doc and the new bot's seeded memory. The new agent then starts troubleshooting from a finished diagnosis instead of rediscovering it. (This session: standing up an HA bot, the live check revealed Sonos failing with `412 Precondition Failed` on `/ZoneGroupTopology/Event` — the one-way-route/UPnP-callback trap — so the diagnosis + both fix paths went straight into the handoff and the bot's memory.)

### 2. Structure: numbered, README-led doc set under ~/.hermes/references/<domain>-handoff/
- `00-README.md` — purpose, **read order**, the non-negotiable **Golden Rules** (the user's standing policies: approval gates, security invariants, "don't claim what you can't verify"), and a one-paragraph system summary.
- `01-infrastructure.md` — hosts, containers (mark which are IN scope vs leave-alone), networking, access, **token/auth model** (which credential works for what — read vs write).
- `02-<inventory>.md` — every entity/resource the agent acts on, with REAL IDs pulled live + a re-derive command + a service-call/action cheatsheet.
- `03..0N` — one doc per subsystem (each major feature/integration): what it is, how it's wired, how to edit/deploy/rollback, its pitfalls.
- `06-operations-runbook.md` — common tasks, **verification gates**, and a consolidated **pitfall index** (every expensive lesson, one line each).
- `0X-new-bot-setup.md` — how to actually STAND UP the new bot/profile (see §4). A handoff that documents the domain but not how to instantiate the agent is half-done.
- `references/<topic>.md` — deep/verified schemas and session-specific detail the main docs point to.

Keep each doc skimmable: tables for inventories, fenced commands that run as-is, bold the traps. ~50-90 lines each beats one giant file.

### 3. Carry the user's standing policies forward as GOLDEN RULES
The new agent must inherit the user's hard constraints, not just the technical facts. Put them up front in 00-README AND bake them into the new bot's personality (§4): approval-before-changes gates, security invariants (e.g. "Tailscale-only bind, never 0.0.0.0"), "browser-verify fragile UI before prod", "state plainly when you can't verify a result." Memory says who the user is; the handoff's Golden Rules say how the NEW agent must behave in this domain.

### 4. Dedicated bot = a separate Hermes PROFILE, not a second token on the main gateway
A single gateway maps ONE platform token per platform. To run an independent, domain-scoped bot, create a profile and give it its own gateway service. The **full, verified step-by-step (including the `--clone` token-collision trap that bites every time) lives in the `gateway-platform-setup` skill → "Running a SECOND, separately-scoped bot (dedicated profile)".** Load it before doing the setup. Key points that intersect the handoff:
- Create with `hermes profile create <name> --clone` so it inherits config + API keys + skills.
- **`--clone` copies the PARENT bot's token + `*_ALLOW_ALL_USERS=true`** — you MUST swap in the new token, comment out unwanted-platform tokens, and tighten the allowlist, or the two bots fight over one token and the new one runs wide open.
- Copy/symlink ONLY the relevant skills + the handoff package into the profile; seed its `memories/MEMORY.md` with the Golden Rules + host/token facts (writing another profile's memory needs `cross_profile=True` — expect a soft-guard block first).
- Scope behavior via the profile's `SOUL.md` persona (role + scope + Golden Rules), loaded fresh each turn — this is what keeps the bot domain-only.
- Trim toolsets to the domain (smaller context, smaller blast radius), then install: `printf 'Y\nY\n' | hermes --profile <name> gateway install --force` (distinct `hermes-gateway-<name>.service`, linger on).
- **Validate the new token up front** (`curl .../getMe` → `ok:true` + username) and **flag shared API budget** (a cloned profile draws the same key/Manifest pool as the parent).

### 5. End-to-end verify the handoff is USABLE, not just present
Don't stop at "files written." Confirm the package is coherent: list it, check every cross-reference resolves, and (if standing up the bot) prove the new agent responds, reads real state, and refuses an out-of-policy change. A handoff is done when a cold reader could operate from it — not when the last file saves.

## Pitfalls
- **Writing from memory/summaries** → stale facts. Always re-pull live. (#1)
- **Omitting the auth model** → the new agent burns time on 401s. Spell out which token is read-only vs write-capable.
- **Documenting the domain but not how to instantiate the agent** → user still can't get the bot running. Always include the stand-up doc.
- **Forgetting the user's policy gates** → the new bot makes unapproved changes. Bake Golden Rules into 00-README AND the personality.
- **One giant file** → unskimmable. Numbered doc set, one subsystem per file.
- **Memory store full when saving the durable intent** → replace/condense an existing entry (drop facts already captured in the handoff docs) rather than fighting to append; a replacement must remove at least as many chars as it adds.

## Related / overlap
`gateway-platform-setup` (the mechanics of wiring a token + allowlist + install — this skill references it for §4), `hermes-maintenance` (profile snapshots / config hygiene), `knowledge-store` (semantic KB as an alternative home for domain facts). This umbrella is the *authoring discipline* that ties them together for the bootstrap-a-new-agent use case.
