# Populate-phase SECOND PASS — finding inline mock the inventory script misses

On a "populate the remaining data into the WebUI" ask, `scripts/inventory_standalone_wiring.py`
is the right FIRST step but it is **necessary, not sufficient**. Proven 2026-06-19
populating the live WebUI (`/root/projects/hermes-webui-new/server.py` +
`standalone.html`): the script reported only `COMMANDS`/`TABS` left as mock (both
real static scaffolding — NOT gaps) and looked "done," yet a panel-by-panel render
audit found **7 inline-literal gaps the script is structurally blind to.**

## Why the script misses them

The script's gap regex is `\n\s+([A-Z][A-Z0-9_]{2,})\s*=\s*\[` — it only catches
UPPER_CASE class-field mock arrays (`SESSIONS`, `LOGS`, `PLUGINS`, `MEMORY`…).
It cannot see **hardcoded fixture VALUES living inline inside `renderVals()`
computed-state blocks**: lowercase keys, object literals, and `(() => {...})()`
IIFEs whose returned values are fabricated. Those render as real-looking data and
pass every `__RD_*` reconciliation check.

## The mandatory second pass (do this AFTER the script, every populate ask)

1. **Extract both layers to disk.** Decode the `__bundler/template` JSON string
   (byte-walk, don't regex), take `scripts[-1]` as the component JS, and keep the
   inner template HTML too. Run against the **patched** JS (`server._patch_standalone`)
   so you see post-patch state, not raw.

2. **Trace every panel's bindings.** For each `s.panel === 'X'`, pull the `{{ }}`
   bindings from the template's `<sc-if value="{{ showX }}">` block, then find where
   each binding is computed in `renderVals()`. Any value assigned a string/number/
   array LITERAL — not derived from a `window.__RD_*` global or a real DB-fed
   `this.<field>` — is a gap.

3. **Known recurring gap shapes** (all were live mock in v4 standalone):

   | Gap | Fix |
   |-----|-----|
   | `profiles: [{name:'voice-rt'…}]` fully-mock array | new `_profiles_for_ui()` reading `~/.hermes/profiles/` + `task_runs` stats → `__RD_PROFILES__`; patch `profiles: (window.__RD_PROFILES__||[]).map(...)` |
   | `agentSummary = [{value:'5'…}]` hardcoded stat bar | recompute from `__RD_AGENTS_OPS__` (`len`, active count, sum(today), avg success, sum(total)) |
   | Overview chips `'3 ready'` / `'2 blocked'` literals | read `__RD_KANBAN__` status counts in JS IIFE |
   | Overview heatmap from `Math.sin()` synthetic wave | drive cells from `__RD_INS_DAYS__` (14-day real msg counts) |
   | `val: '7', lbl: 'Day Streak'` | compute consecutive `__RD_INS_DAYS__[i]>0` from the tail |
   | Insights `tokInPct/tokOut/tokTotal/peak` literals | split `input_tokens` vs `output_tokens` in `_ins_for_ui()` → `__RD_INS_IN_TOKS__` + `__RD_INS_OUT_TOKS__`, format in JS |
   | fake `skills:[{skill:'web-fetch'…}]` table | tally `tasks.skills` (JSON-or-CSV) from kanban → `__RD_INS_SKILLS__` |

4. **Distinguish real fixtures from INTENTIONAL skips.** A synthetic time series
   with no backend source — e.g. `sysData`/`sysMetrics` CPU/GPU/VRAM sparklines that
   would need `psutil` + a new `/api/system` endpoint — is a *deliberate skip*, not
   a gap. Call it out as "intentionally not surfaced (would be a new feature, not
   populating existing data)" rather than fabricating a metrics source. The user
   (Andrew) explicitly asks you to list what you intentionally didn't surface and
   why — name these.

## Fix pattern (same as the rest of the file)

Each fix = (a) a builder fn + a key in `_build_global_data()`, (b) a
`_replace_block`/`js.replace` in `_patch_standalone()` reading
`window.__RD_*__ || <original mock>` (graceful fallback). For `_replace_block`, the
END marker is NOT repeated in the replacement (`js[ei:]` supplies it) — end the
replacement string before that text.

## Verification false-positive trap (cost a spurious "patch failed")

When confirming a mock is gone, a survivor token can mislead you. Example: after
replacing the `profiles` mock, `voice-rt` STILL appears in the patched HTML —
because the same token is also a `pluginOn` settings key AND a `CHAT_AGENTS`
mock-fallback `platform:` field. Do NOT conclude the patch failed. Grep each
occurrence's surrounding context; confirm the SPECIFIC mock block signature is gone
(here: `'Primary operator', model: 'Claude Sonnet 4.6', sessions: '86'`) and the
real wiring (`window.__RD_PROFILES__`) is present. **Verify by the unique block
signature, not a shared token.**

## Verify harness (before the gated restart)

```python
import server
d = server._build_global_data()                       # builders run clean?
html = open('standalone.html').read()
patched = server._patch_standalone(html)              # all markers found? (check warnings)
# assert each new "window.__RD_X__" in patched  AND  each old mock signature NOT in patched
```

A landed patch produces NO `logger.warning("... marker not found")` lines. Then the
gated `systemctl restart hermes-webui` (blips the live chat ~5s — get greenlight,
back up `server.py.bak-<ts>` first).
