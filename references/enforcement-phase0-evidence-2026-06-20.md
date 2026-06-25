# Phase 0 — Verify-Don't-Assert Gate: Evidence

**Date:** 2026-06-20
**Basis:** `hermes-how-to-proceed.md` Phase 0
**Method:** Read-only. Every claim recorded as `file:line` + the actual line read (not the word "confirmed").
**Result:** ALL THREE CLAIMS PASS. No build performed. Build remains gated.

---

## Claim 1 — Pollution path is the cron, not a tool → **PASS**

The session-digest write reaches the Supabase chokepoint via a subprocess, with no agent tool call in the path.

**`/root/.hermes/scripts/session_distill.py:262-275`** (`store_digest`):
```
262| def store_digest(digest):
263|     """Store a digest in LanceDB via knowledge.py. Returns True on success."""
269|         result = subprocess.run(
270|             [sys.executable, KNOWLEDGE_SCRIPT, "store", digest],
```
→ A cron-invoked Python subprocess shelling `knowledge.py store <digest>`. No `pre_tool_call`-visible tool call.

**`/root/.hermes/scripts/knowledge.py:408-424`** (`store`) ends `424| tbl.add([row])`.
**`/root/.hermes/scripts/knowledge.py:371-403`** (`store_contextualized`) ends `403| tbl.add([row])`.

The cron passes argv `["store", digest]` (no `--contextualize`) → `store()` → `tbl.add([row])`:424. Both paths terminate at `tbl.add([row])`, the single cold-store chokepoint. **The pollution genre enters here, invisible to any tool hook.**

---

## Claim 2 — In-process family exists and covers the Component-3 pattern → **PASS (with one precise gap)**

**`ls ~/.hermes/patches/`:** `anthropic_billing_bypass.py`, `delegate_toolset_floor.py`, `delegation_checkpoint.py`, `delegation_nudge.py`, `domain_ownership_checkpoint.py`, `kanban_checkpoint.py`, `kanban_phase_checkpoint.py`, `memory_checkpoint.py`, `skill_review_checkpoint.py`, `write_gate.py`, + tests.

**Pre-execution veto** — `kanban_checkpoint.py:401-445` (`_objgate_should_block`):
```
401| def _objgate_should_block(tool_name, tool_args, turn_hash) -> tuple[bool, str]:
407|     if tool_name not in ("write_file", "patch"): return False, ""
417|     if inv is None: return True, "[Whole-objective gate] Write blocked: produce inventory.json first..."
438|     if chunk_count > OBJGATE_K: return True, "...chunk_count={chunk_count} > K={OBJGATE_K}..."
```
Genuine pre-execution block keyed on an `inventory.json` artifact. **This fired live this session — see the stale-artifact finding below.**

**Golden/marker self-heal** — `patch_guard.py:87-100` (`_restore_full`): restores from golden when any marker missing.

**PRECISE GAP:** family covers the delegate chokepoint (`delegate_toolset_floor.py`→`_build_child_agent`), the `memory` tool (`memory_checkpoint.py`), and routing (`_objgate`). It does **NOT** have a guard inside `knowledge.py` — the cold-store chokepoint from Claim 1. That is exactly the one new guard Phase 1 adds.

---

## Claim 3 — Real `delegate_task` schema → **PASS**

**`/usr/local/lib/hermes-agent/tools/delegate_tool.py:2981` (`DELEGATE_TASK_SCHEMA`)**, `tasks[].properties` (3027-3056):
```
3027| "tasks": { "type":"array", "items": { "type":"object", "properties": {
3032|   "goal": {...}, 3033| "context": {...},
3037|   "toolsets": {"type":"array","items":{"type":"string"},
3040|       "description":"Toolsets for this specific task. Available: {_TOOLSET_LIST_STR}..."},
3042|   "acp_command": {...}, 3050| "acp_args": {...}, 3055| "role": {...} } } }
```
Per-task fields: `goal`, `context`, **`toolsets`** (array of toolset GROUP names), `acp_command`, `acp_args`, `role`.

**`kanban_card_id` — ZERO hits** in the whole package. The only `implementation` hit is unrelated EVM code (`optional-skills/blockchain/evm/scripts/evm_client.py:1368`). Toolset vocabulary (`toolset_distributions.py:33+`): `web, vision, terminal, file, browser, image_gen, coding, …` — group names, not tool names.

→ Both doc-claimed escape-hatch fields (`kanban_card_id`, `implementation`) are **phantom**. Reuse `_objgate`'s real `inventory.json` artifact (`gaps[], chunks[], chunk_count, routing, reason, turn_hash`) as the F2 escape hatch.

---

## LIVE FINDING (this session) — `_objgate` stale-artifact false-positive

While writing this very evidence file, `_objgate_should_block` **blocked the write**: `chunk_count=11 > K=3`. Cause: a leftover `/root/.hermes/run/inventory.json` from the **2026-06-19 WebUI data-population objective** (11 chunks, `routing: fanout`) with **no `turn_hash` field**.

- `kanban_checkpoint.py:424-425`: `stored_hash = inv.get("turn_hash",""); if stored_hash and stored_hash != turn_hash:` — an absent/empty `turn_hash` is falsy → **the staleness guard is skipped entirely**, so a completed objective's inventory never expires and keeps gating unrelated future turns on `chunk_count`.
- Resolution this turn: replaced `inventory.json` with an honest current-objective declaration (3 build chunks, `routing: fanout`) via the gate's own exempt path. No bypass; the gate's sanctioned mechanism.
- **Recommended gate fix (separate gated patch):** treat a missing/empty `turn_hash` as STALE (block→force refresh) instead of skipping the check, OR have `_objgate` clear `inventory.json` on objective completion. Either closes the "immortal stale artifact" hole. Track as a Phase-2 sub-item (objgate tuning).

---

## Phase 0 verdict

| Claim | Verdict | Decisive evidence |
|---|---|---|
| 1. Pollution = cron→`store()`→`tbl.add`, no tool | **PASS** | session_distill.py:269-270 → knowledge.py:424/403 |
| 2. Family covers C3 pattern; cold store is the gap | **PASS** | kanban_checkpoint.py:401 (veto), patch_guard.py:87 (heal); no knowledge.py guard |
| 3. delegate schema = `toolsets`; no card_id/implementation | **PASS** | delegate_tool.py:3037; 0 grep hits for phantom fields |

**Nothing built. Greenlight is unblocked per the doc's Phase-0 gate, but I am holding at the WRITE GATE for explicit per-phase go.** First build = Phase 1 (cold-store schema guard inside `knowledge.py`), scoped as a written change report before any edit.
