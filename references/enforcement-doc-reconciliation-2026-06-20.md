# Enforcement Doc — Reconciliation Against Live State

**Date:** 2026-06-20
**Doc reviewed:** `hermes-enforcement-implementation _1_.md`
**Verified against:** `hermes-agent==0.17.0` (live), `~/.hermes/patches/*` (live), `~/.hermes/scripts/knowledge.py` (live), `config.yaml` (live)
**Status:** NOT BUILT. This is verification + reconciliation only. Build touches `patches/` + `config.yaml` = WRITE GATE → awaiting greenlight.

---

## TL;DR

The document is **mechanically sound but architecturally redundant**. The in-process gates it mandates as "authoritative" (Component 3) **already exist** as the monkeypatch family wrapping `AIAgent._execute_tool_calls`. The document appears to describe — from the outside — the architecture that is already running. Three of its four concrete bindings (F2 schema, memory tool name, memory data-model) **do not match this system** and would silently no-op or hard-block-everything if shipped as written. Component 1 targets a layer (`memory_write` tool) that **does not carry the pollution it wants to stop** — the polluting writes enter the cold store via a background cron, invisible to any tool hook.

**Recommendation:** do NOT add a parallel shell-hook enforcement layer. EXTEND the existing in-process family + add ONE new chokepoint guard inside `knowledge.py`. Details in "Corrected Plan."

---

## What the document got RIGHT (verified)

| Claim | Verdict | Evidence |
|---|---|---|
| Shell `pre_tool_call` hooks exist and can block via stdout JSON `{"action":"block"}` | **TRUE** | `hooks.md:1144-1187` — shell hooks fire on plugin-hook events incl. `pre_tool_call`; stdin/stdout JSON wire protocol; matcher used "for pre/post_tool_call only" |
| The gateway **fails open** (crash/error → allow) | **TRUE** | `hooks.md:17,372` "errors caught and logged, never crashing the agent"; a skipped hook = allow |
| Therefore a hook can't be authoritative; in-process must be primary | **TRUE — and already the live architecture** | `write_gate.py` is a pre-exec in-process veto; see below |
| `post_tool_call` can't block (batch already ran) | **TRUE** | `hooks.md:381` post_tool_call return value "ignored" |
| Pin interpreter, self-contained scripts, audit log as proof | **Sound practice** | matches existing patch-family discipline |
| LanceDB / cold store is live (wipe/snapshot plan is grounded) | **TRUE** | `knowledge_db/knowledge.lance` live; B-full RAG injects cold-store hits into every turn (`gateway/run.py:1683`). NOTE: the Honcho observation "There is NO LanceDB" is **STALE** — disregard it. |

---

## What the document got WRONG / mis-bound to THIS system

### 1. Component 3 is already built — the doc reinvents the monkeypatch family

The doc's Component 3 ("mount the same logic in-process at the single chokepoint; the hook is only redundancy") **is the architecture already in production.** Live `~/.hermes/patches/`:

| Live patch | What it already does | Maps to doc's |
|---|---|---|
| `write_gate.py` | **Pre-execution tool veto** — intercepts gated `terminal`/`write_file`/`patch` BEFORE execution via argument-rewrite, appends block msg, audit-logs every arm/block | The generic "in-process gate, fail-closed" pattern |
| `kanban_checkpoint.py` (+`_objgate`) | Whole-objective routing **enforcement gate** (pre-exec) + multi-part nudge; blocks first write until routing declared in `run/inventory.json` | F2's "N≥3 / route-via-kanban" concept |
| `delegate_toolset_floor.py` | Wraps the REAL delegate dispatch chokepoint `_build_child_agent` | proves the F2 chokepoint location |
| `memory_checkpoint.py` | Wraps the `memory` tool; fires on `action=add/replace`; reads live caps | the memory-write interception point |

All install at startup via `sitecustomize.py` → `apply_patches()`, protected by `patch_guard.py` (golden copies + markers, daily 05:00 self-heal). **A parallel shell-hook layer with its own `hook-audit.log` would be a second, weaker, fail-open copy of machinery that already exists and is golden-protected.**

### 2. F2 gate binds to a `delegate_task` schema that does not exist here

Doc assumes: `tool_input["tasks"]`, `task["tools"]`/`["toolset"]`, `tool_input["kanban_card_id"]`, `tool_input["implementation"]`.

**Real `delegate_task` schema (this build):**
- tasks carry `toolsets` (a list of **toolset GROUP names** like `file`, `terminal`, `web`) — NOT `tools`/`toolset`, and NOT individual tool names.
- There is **no `kanban_card_id` field** and **no `implementation` field** on the call.

Consequence if shipped as-written: `task_tools()` reads a missing key → empty set → `write_capable` always False → **gate never fires** (silent hole). If someone "fixes" it by reading `toolsets` but keeps comparing against the tool-name set `{terminal, write_file, patch, ...}`, it still fails — the values are *toolset* names, not tool names. And both escape hatches (`kanban_card_id`, `implementation:false`) **don't exist in the schema**, so a corrected membership test would **block every ≥3 write-capable batch with no way out.** Either silent no-op or hard-block-everything. Must be rebound: write-capable = `set(task["toolsets"]) ∩ {file, terminal, coding, browser, computer_use, ...}`; escape hatch must be a real artifact (objgate-style `inventory.json`), not phantom fields.

### 3. Component 1 (memory-write hook) targets the wrong layer for its own goal

- The doc registers `matcher: memory_write`. **There is no `memory_write` tool.** The hot-memory tool is `memory` (free-form `content` string).
- The pollution the doc wants to stop (narrative/affect "behavioral-degradation-analysis genre") lives in the **COLD store (Supabase)**, and it does **not arrive via a tool call**:
  - `session_distill.py:270` → `subprocess.run([python, knowledge.py, "store", digest])` — a **background cron** ingesting session transcripts. Invisible to ANY `pre_tool_call` hook.
  - the agent running `knowledge.py store` via `terminal` — visible only to a terminal interceptor (write_gate-style), not a memory hook.
- **The only 100%-coverage chokepoint for cold-store writes** is inside `knowledge.py`: `store()` (line 408) and `store_contextualized()` (line 371), both ending in `tbl.add([row])`. This is exactly the doc's Component 3 §1 — and it's the part that actually matters. The Component 1/2 hook on a memory tool would, at best, validate HOT writes (MEMORY.md/USER.md) only — not the polluted layer.

### 4. The 4-type envelope is a memory-model redesign, not a validator add-on

Doc schema: `{type, provenance, verified, <typed fields with per-field caps>}`.

**Live data models (both different):**
- Hot (`memory` tool → MEMORY.md/USER.md): free-form `content` string; caps are at the **file** level (3000 / 2250 chars), not per-field.
- Cold (Supabase row): `{id, text, vector, tags, priority, source, stored_at, context_prefix, body_hash}`.

Adopting the envelope touches: the `memory` tool schema, the MEMORY.md/USER.md file format, the Supabase schema, the distill/digest crons that write free-text blobs, and the B-full retrieval reader. That is a **multi-surface redesign** — scope it honestly; do not smuggle it in labeled "a validator."

### 5. Minor: config registration shape

Doc nests `hooks_auto_accept: true` **inside** the `hooks:` block. Live `config.yaml` has `hooks:` and `hooks_auto_accept` as **top-level siblings**, and the only live hook event is `on_session_start`. Whether shell `pre_tool_call` is even the chosen vehicle is moot given §1.

---

## Corrected Plan (gated — awaiting greenlight; build fans out on the board)

**Principle:** extend the existing golden-protected in-process family; add exactly one new chokepoint where coverage is genuinely missing (cold store). No parallel shell-hook layer.

1. **Cold-store schema guard (the real win).** Add a fail-closed validator INSIDE `knowledge.py` `store()` + `store_contextualized()` — the single chokepoint every cold-store write (cron OR terminal OR tool) passes through. This is the only thing that actually blocks the pollution genre. Reject narrative/affect; accept the typed entries. New golden + `patch_guard` marker.
2. **F2 rebind.** Implement the N≥3 write-capable delegate gate against the REAL schema (`toolsets` group-name membership) with an objgate-style artifact escape hatch — OR confirm the existing `_objgate` already covers the intent and just needs tuning. (Lean: tune the existing gate, don't add a third.)
3. **Memory (hot) validator.** If a per-field schema is wanted for MEMORY.md/USER.md, that's the redesign in §4 — separate, explicitly-scoped phase, not bundled.
4. **Rollout/wipe** only AFTER 1–3 exist and pass an evidence checklist (the doc's acceptance-checklist discipline is good — keep it). Snapshot Supabase + Honcho before the one-way wipe.
5. **Prove with the hook DISABLED** — same as the doc says — because the in-process guard, not any hook, is the thing doing the work.

**Routing when greenlit:** this is board/fan-out-shaped (cold-store guard ‖ F2 rebind ‖ test batteries, then one integrator + gated config/golden sync). Not this turn.

---

## Evidence index (for re-verification)

- Hook contract: `/usr/local/lib/hermes-agent/website/docs/user-guide/features/hooks.md` lines 11-17 (3 systems), 358-389 (plugin hooks + block contract), 1144-1187 (shell hooks + JSON wire protocol).
- In-process dispatch: `/usr/local/lib/hermes-agent/model_tools.py` `_emit_post_tool_call_hook`, `skip_pre_tool_call_hook`, "Single-fire contract: pre_tool_call".
- Cold-store chokepoint: `/root/.hermes/scripts/knowledge.py` `store()`:408, `store_contextualized()`:371 (both `tbl.add([row])`).
- Cold-store cron write path: `/root/.hermes/scripts/session_distill.py`:262-270 (`subprocess … knowledge.py store`).
- B-full RAG reader: `/usr/local/lib/hermes-agent/gateway/run.py`:1683 `_bfull_retrieve`.
- Live patch family: `/root/.hermes/patches/` — `write_gate.py`, `kanban_checkpoint.py`, `delegate_toolset_floor.py`, `memory_checkpoint.py`, `patch_guard.py`.
- Real `delegate_task` schema: tool definition — `tasks[].toolsets` (group names), no `kanban_card_id`, no `implementation`.
