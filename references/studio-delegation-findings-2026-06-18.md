# Studio Delegation — Definitive Findings (2026-06-18)

**Status:** Local Studio delegation CONFIRMED WORKING end-to-end. This file is the
authoritative record of the multi-hour root-cause investigation. If delegation breaks
again, read this FIRST.

---

## TL;DR — the working recipe

Local `delegate_task` on the Mac Studio works IFF all of these hold:
1. **Model declares ≥64k context** — `custom_providers[mac-studio].models.<model>.context_length: 65536` AND Modelfile baked `num_ctx 65536`. (Hermes hard-rejects <64k at child init.)
2. **`delegation.child_timeout_seconds ≥ 900`** — cold ingest of a ~13k-token agent prompt takes ~100-136s; the default 600 kills 4-wide batches.
3. **No stale `api_key_env` in the delegation block** — a leftover `DEEPSEEK_API_KEY` silently routes children to DeepSeek cloud.
4. **Model emits structured `tool_calls`** — the general Qwen 32B does; coder variants do NOT (they return tool calls as plain text → child can't parse → fallback).

Current live config: `delegation.model: qwen2.5-32b-64k`, `provider: custom:mac-studio`,
`base_url: http://100.93.2.43:11434/v1`, `child_timeout_seconds: 900`, `max_concurrent_children: 12`.

---

## The full failure chain (in order discovered)

1. **Stale `api_key_env: DEEPSEEK_API_KEY`** in delegation block → children routed to DeepSeek cloud regardless of `provider: custom:mac-studio`. REMOVED.
2. **64k context gate** (`agent/model_metadata.py: MINIMUM_CONTEXT_LENGTH = 64_000`). When we rebuilt the 32B from 64k→32k to fix VRAM, delegation SILENTLY BROKE: child init raised `ValueError` BEFORE any TCP connection (Studio access log showed only `127.0.0.1`, never the mini's IP). Parent fell through to DeepSeek fallback. The original `qwen2.5-32b-64k` name existed precisely to clear this gate. FIXED by rebuilding at `num_ctx 65536` + declaring `context_length: 65536`.
3. **`child_timeout_seconds: 600`** too tight. Single task ~115-136s; 4-wide batch ~500s/child → all hit 600s cap → `status: timeout`. RAISED to 900.
4. **14B-coder tool-call format.** `qwen2.5-coder:14b` is 2.15× faster at raw generation but returns tool calls as plain-text `content` instead of structured `tool_calls` → unusable as a delegation target. REJECTED. (Detection: curl the `/v1/chat/completions` endpoint with a `tools` payload, check response shape.)

**Silent-fallback detection:** read the `model` field in the `delegate_task` result JSON.
If it says `deepseek-v4-pro` when you configured the Studio, delegation is NOT running local.
config-says-Studio + result-says-cloud = one of the four failures above.

---

## Prefix-cache investigation (the throughput question)

**Question:** can sequential subagents reuse a cached prompt prefix to skip the ~100s ingest?

**Engine-level (raw curl):** YES, dramatically. Fixed prefix + varying suffix → ingest dropped
from ~100s to ~0.5s (≈190×). llama.cpp uses LCP (longest-common-prefix) slot matching.

**Agent-path (real delegate_task):** PARTIAL. Measured 136s → 104s → 110s → 106s (only ~24%).
Studio slot logs explained why:
- P=4 round-robins sequential calls across 4 separate slots, each with its own cold KV cache → almost no reuse.
- At **P=1**, all calls lock to slot 0. Logs showed `selected slot by LCP similarity, sim_best = 0.255` and `cached n_tokens = 3402` reused on calls 2/3/4 — a STABLE floor.

**Why only 3,402 tokens cached THIS session:** we were actively editing skills all session.
The `<available_skills>` block sits ~token 3,400 in the prompt; every skill description edit
shifts tokens there and invalidates the cache from that point on.

### System prompt layer breakdown (measured live)

| Layer | chars | tokens | cacheable? |
|---|---|---|---|
| stable (SOUL.md + skills list + tool schemas) | 23,895 | 5,973 | ✅ if no skill edits |
| context (AGENTS.md + project files) | 18,303 | 4,575 | ✅ if no file edits |
| volatile (MEMORY.md + USER profile + Honcho + session id/date) | 5,084 | 1,271 | ❌ always re-ingested |
| **total** | 47,282 | 11,820 | |

The prompt is deliberately ordered stable→context→volatile (`agent/system_prompt.py`,
"maximizing prefix cache hits") with `Session ID`/date in the volatile tail (day-precision date,
not minute, on purpose). Architecture is correct.

### The real production numbers

- **Quiet session (no skill/file edits): cache floor = ~10,549 tokens** (89% of prompt). Only the
  1,271-token volatile block re-ingests. Per-task ≈ 13s ingest + ~17s gen = **~30s/subagent**.
- **Edit-heavy session (like today): cache floor ~3,400 tokens.** Per-task ~104-110s.
- **Cold (first call / cache evicted): ~136s.**

So local sequential delegation is ~30s/task in normal use, NOT the 136s that cold benchmarks
suggested. Still slower than Sonnet (~10-15s) but viable and fully on-box.

---

## Concurrency / parallelism (P) findings

The M2 Max is **memory-bandwidth-bound** on weight reads. Aggregate throughput on a realistic
13k payload DECREASES with concurrency (each slot re-ingests cold, contending for the bus):

| Concurrent requests | aggregate t/s | per-task |
|---|---|---|
| 1 (warm slot) | 661 | 12.5s* |
| 2-wide | 160 | ~103s |
| 4-wide | 107 | ~310s |

*N=1 warm number is cache-inflated; uncached single ≈115-136s.

**P=1 enables prefix-cache reuse (sequential); P>1 defeats it (slot scatter).** The earlier
P=2/3/4 "P=4 optimal" result was measured with a TINY prompt where ingestion was negligible —
it does not hold for real agent payloads. Disregard it.

---

## Studio model inventory (as of this investigation)

Working: `qwen2.5-32b-64k` (num_ctx 65536, delegation target), `qwen2.5:72b` (heavy).
ORPHANS to clean up (~37GB): `qwen2.5-32b-65k` (dup blob of 64k — config name mismatch to
reconcile), `qwen2.5-32b-32k` (broke delegation via 64k gate), `qwen2.5-coder-14b-32k` +
`qwen2.5-coder:14b` (non-viable — text tool-calls).

NOTE: warm model showed as `qwen2.5-32b-65k` while config says `qwen2.5-32b-64k`. Same blob,
different manifest name. Reconcile to ONE name before declaring final.

---

## Decision still open: P=1 vs P=2 (see chat for trade-off explanation)
Studio left at P=1 pending Andrew's decision. Whichever is chosen, restore via plist edit +
bootout/bootstrap (NOT plain kill — see ollama-inference-node-ops skill for the launchctl pitfall).
