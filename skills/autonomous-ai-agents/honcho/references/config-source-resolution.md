# Honcho config: which file is read, and the dead-config trap (verified 2026-06-19)

## THE TRAP: `config.yaml`'s `honcho:` block is NOT read by the plugin

There are two places Honcho settings *appear* to live:
- `~/.hermes/config.yaml` → a top-level `honcho:` block (e.g. `injectionFrequency`,
  `reasoningLevelCap`, `dialecticCadence`)
- `~/.hermes/honcho.json` → `hosts.<host>` blocks

**The plugin reads ONLY honcho.json.** The `config.yaml` `honcho:` block is dead config —
it is never consulted. A user (or a past session) can set `injectionFrequency: first-turn`
in config.yaml, believe it's active, and the plugin silently runs the honcho.json value
(or the default when the key is absent). Found live this session: config.yaml claimed
`first-turn` + `dialecticCadence: 3` + `reasoningLevelCap: low`; the EFFECTIVE values were
`every-turn` + `dialecticCadence: 2` + `reasoningLevelCap: high`.

**Resolution order (plugins/memory/honcho/client.py `resolve_config_path`):**
1. `$HERMES_HOME/honcho.json` (profile-local, if it exists)
2. `~/.hermes/honcho.json` (default profile — shared host blocks live here)
3. `~/.honcho/config.json` (global)
4. env vars

`config.yaml` is nowhere in that chain. If you're tuning Honcho, edit honcho.json.

## Authoritative way to read the EFFECTIVE config — run the resolver, don't eyeball JSON

Cadence/injection fields are read straight from `raw` (honcho.json) at plugin init
(`__init__.py:314-320`), and are NOT all surfaced on the resolved dataclass. To get the
true live values, run the plugin's own resolver AND read the raw host block:

```bash
cd /usr/local/lib/hermes-agent && HOME=/root venv/bin/python -c "
import sys, json; sys.path.insert(0,'/usr/local/lib/hermes-agent')
from plugins.memory.honcho.client import HonchoClientConfig
import dataclasses
cfg = HonchoClientConfig.from_global_config()
for f in dataclasses.fields(cfg):
    if f.name not in ('api_key',): print(f'{f.name:30}=', getattr(cfg,f.name))
raw = json.load(open('/root/.hermes/honcho.json'))['hosts']['hermes']
for k in ['injectionFrequency','contextCadence','dialecticCadence','recallMode']:
    print(f'RAW {k:22}=', raw.get(k, '<default>'))
"
```

The fields read from `raw` (not on the dataclass): `injectionFrequency`, `contextCadence`,
`dialecticCadence`. Absent key → plugin default (`injectionFrequency`→`every-turn`,
`contextCadence`→1, `dialecticCadence`→1; the setup wizard writes 2 on new configs).

## Per-turn network cost — the cadence semantics that actually matter

Two independent background calls fire per substantive turn (trivial prompts like "ok"/"yes"
and slash commands are skipped via `_is_trivial_prompt`). Both are BACKGROUNDED/non-blocking
(they don't add latency to the response — the result is consumed on a later turn), but each
is a real round-trip to app.honcho.dev + Honcho-side compute:

| Layer | Gate | Default | Fires |
|---|---|---|---|
| **Context** (representation + card) | `contextCadence` | 1 | `cadence <= 1` is ALWAYS true → **every turn** (`__init__.py:804`) |
| **Dialectic** (LLM synthesis) | `dialecticCadence` | 1 (wizard:2) | every Nth turn, widened by empty-streak backoff |
| **Injection** into prompt | `injectionFrequency` | every-turn | reads cache; `first-turn` returns empty after turn 1 (`:647`) |

**`contextCadence: 1` = a context fetch every turn.** This is the usual "why is Honcho
hitting the network so much" culprit. The representation evolves ACROSS SESSIONS not turns,
and Honcho's Deriver builds it asynchronously+continuously (it is NOT gated by the
client-side dialecticCadence — that's a false coupling; dialecticCadence only controls how
often Hermes QUERIES the dialectic endpoint). So `contextCadence` is purely a
cost-vs-convenience dial: "how often do I want to pay for a representation fetch," not "how
often does the rep change." Raise it to 5–10 for a slowly-evolving artifact; the 5 honcho_*
tools cover any on-demand freshness need. Don't justify the number via dialecticCadence.

## How recalled context reaches the prompt (and why it does NOT bust the prefix cache)

Honcho's per-turn context does NOT go into the cached system prompt. Trace
(`agent/turn_context.py:374` → `agent/conversation_loop.py:723-732`): `prefetch_all()` →
`ext_prefetch_cache` → fenced block → **appended to the current turn's user message at
API-call time only.** The original `messages` list is never mutated; nothing leaks to
session persistence. The system prompt is built ONCE per session, cached on
`_cached_system_prompt`, replayed byte-identical every turn (rebuilt only on context
compression). So:
- Honcho context is dynamic but lives in the user-message tail (cache-safe position).
- The system prompt (with the frozen turn-0 Honcho block in its `volatile` layer) stays
  byte-stable → upstream prefix cache stays warm.

This refutes the "Honcho refresh rewrites Layer 3 of the cached prompt and busts the cache"
theory: that refresh path does not exist in this codebase. The freeze was verified
empirically — see the prompt-cache meter check in `ollama-inference-node-ops`
(`references/prompt-cache-verification.md`): real multi-turn sessions show 92–96%
cache-read rates on Sonnet, proving the prefix is stable across turns.

## recallMode for headless/mechanical profiles (swarm workers)

`recallMode: tools` (in the host block) disables ALL auto-injection AND background prefetch
(`queue_prefetch` returns immediately on `tools` mode, `__init__.py:792`) while keeping the
5 honcho_* tools available. Use it for profiles that run bounded mechanical sessions and
never read the user representation (e.g. swarm workers): they were firing a turn-1 context
fetch per spawn for zero behavioral effect — at N workers that's N round-trips per fan-out.
Keep `saveMessages: true` if you still want their activity to contribute observations to the
shared workspace; flip `enabled: false` only to cut them off entirely (stronger, stops
observation too). Worker profiles WITHOUT a host block inherit the root `hermes` block.
