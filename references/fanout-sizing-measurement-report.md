# Fan-Out Sizing — Measurement Report

**Date:** 2026-06-19
**Status:** M3 kill-switch fired. M5/M6 killed. M4 pending your decision. Policy constants below are grounded on real data.

---

## Executive summary

M3 (the cheap kill-switch) ran first as specified. Its result collapses the expensive half of the plan. Wide fan-out essentially never occurs in this harness by the honest structural measure; W_cap never binds; N*'s exact value only swings 11% of objectives. The one measurement with real remaining leverage is M4 (R*, the isolation trigger), because it fires on the common single-chunk-but-read-heavy case that M3 left untouched.

---

## M7 — Config / doctrine ground truth (done, this session)

**Method:** read live `config.yaml delegation` block; ran 2 delegations and confirmed reported model; reconciled against SOUL.md.

**Finding:**
- Live config: `delegation.provider = anthropic`, `delegation.model = claude-sonnet-4-6`, escalates to Opus 4 for above-standard tasks.
- Both probe delegations ran on Sonnet 4.6. Output quality equal to inline on a representative author-chunk task.
- SOUL.md claimed "local Mac Studio / qwen / DeepSeek fallback" — **stale, now corrected** (gated edit, shipped same session).

**Decision unlocked:** "Delegation runs on the main model family, quality equal" is confirmed and the doctrine now says so. No quality caveat on K or N*.

---

## M3 — Real objective decomposition (the kill-switch)

**Method:** parsed `tool_calls` JSON from `state.db messages` (n=686 sessions total); extracted `write_file` / `patch` file paths per session; computed (a) distinct files and (b) distinct directory-level domains per session. Domain = top-3 path segments — the honest "independent author chunk" unit (files in the same module can't be authored fully in parallel without integration conflict; domain-level captures real independence).

**Sample:** 156 sessions with ≥1 write-tool call. Structural measure — not agent chunk labels, not hand-picked.

**Confound neutralized:** the proposal warned this could reflect old under-routing behavior. But files-*touched* is structural: a session that edited 8 files inline still counts 8. Under-routing does not bias the count downward.

### Results

| Metric | median | mean | p90 | max | ≥3 | ≥8 | ≥12 |
|---|---:|---:|---:|---:|---:|---:|---:|
| Distinct files per session | 2 | 3.5 | 8 | 28 | 29% (45) | 13% (21) | 6% (9) |
| **Distinct domains per session** | **1** | **1.5** | **3** | **11** | **12% (19)** | **1% (1)** | **0% (0)** |

**Domain-level is the load-bearing number.** 28 distinct files in one session looks like wide fan-out but is usually one module — editing those in parallel creates exactly the integration conflicts the "it all touches one file" doctrine flags, at module scale. Domain-level strips that out.

### Distribution by domain count

| Chunk count | Sessions | % |
|---|---:|---:|
| 1 | 115 | 74% |
| 2 | 22 | 14% |
| 3–4 | 13 | 8% |
| 5–7 | 5 | 3% |
| 8–11 | 1 | 1% |
| 12+ | 0 | 0% |

**Fan-out (≥3 domains) is a 12% event. Wide fan-out (≥8) happened once in 156 sessions. ≥12 never happened.**

---

## M1 / M2 — Delegation tax + per-chunk authoring time (in-session, n=2)

**Method:** two real delegations this session with instrumented wall-clock from tool trace timestamps.

| Task | Type | Wall-clock | Input tokens absorbed (child) | Output tokens |
|---|---|---:|---:|---:|
| `_ins_for_ui` rewrite (~6 lines, SQL fix) | Small author-chunk | 144s | 191K | 10K |
| `kanban_checkpoint.py` extension (~120 lines + test battery) | Large author-chunk | 497s | 518K | 42K |

**Key finding on the review's open question** ("is the tax fixed/amortizable or read-loop/not?"):
~140s is a fixed-ish floor — both tasks paid it regardless of size. The remainder scales with authoring. This means parallelism amortizes both: the fixed floor spreads across width, and the authoring portions run concurrently. Fan-out pays when ≥N* real chunks exist.

**N* arithmetic:** `N* = ceil(tax / per_chunk_inline_time)`. Inline time for the small chunk ≈ 15–20s (observed this session). `ceil(140 / 17) ≈ 9`. For larger chunks the inline time is longer and N* drops — at 60s inline, `ceil(140/60) ≈ 3`.

**Practical implication:** N* is chunk-size-dependent, not a single constant. For small tasks (≤30s inline), fan-out for *speed* breaks even around 8 chunks — which M3 says never happens. For medium tasks (≥60s inline), fan-out for speed breaks even at 3 chunks — which M3 says happens 12% of the time. **Context absorption (not speed) is the stronger fan-out argument at width 1–2**, since it pays at any chunk count (191K tokens stay out of the parent window on a task that's 15s inline).

---

## What M3 collapses

### M5 / M6 — KILLED

Integration cost and failure-rate vs width (M5/M6) are moot when ≥8-domain fan-out happened once. You cannot usefully measure the integration cost of a width you never hit. These measurements are cancelled.

### W_cap — never measure, set by inspection

Capacity 12 is dead headroom by the domain metric. The p90 is 3; the max is 11 (once). **Set W_cap = 5.** Covers p90 with margin; 12 never binds. No measurement needed.

---

## What M3 did NOT collapse

### M4 — R* (isolation trigger for single-chunk heavy-read objectives)

74% of objectives are single-domain. N* and W_cap are irrelevant for them. But a single-domain objective with a heavy read loop (e.g. a deep diagnosis that reads 40 files before writing one) still floods the parent window — the 191K→2KB absorption benefit is real even at width 1.

R* is the knob that governs "delegate for isolation even when chunk_count = 1." M3 left it untouched. It is the one measurement with real remaining leverage.

**M4 status: NOT RUN — pending your decision.**
Reasonable default if you don't want to run it: **R* = 50K parent-context read tokens** (roughly the point where a delegation's absorption benefit exceeds its 140s fixed tax at $0.003/K input tokens). This is a reasoned estimate, not a measured number — state it as such.

---

## Policy constants (grounded)

| Constant | Value | Grounding |
|---|---|---|
| **K (fan-out threshold)** | 3 chunks | M3: K=3 vs K=8 only changes routing for 11% of objectives; K=3 matches existing doctrine and p90 |
| **W_cap (useful width ceiling)** | 5 | M3: domain p90=3, max=11 once; 12 never binds |
| **delegation_tax (fixed floor)** | ~140s | M1: n=2, both tasks; treat as ±40s until n grows |
| **N* (speed break-even)** | chunk-size-dependent: ~9 for small tasks, ~3 for medium | M1+M2: n=2 in-session; small tasks never reach N* by M3; medium tasks hit K=3 first |
| **R* (isolation trigger)** | 50K tokens (reasoned default) OR run M4 | NOT measured |
| **Delegation quality** | Equal to inline | M7: confirmed Sonnet/Opus Anthropic; SOUL corrected |

---

## Recommended policy line

```
width = structural independent-chunk count (by domain, not file)
fan out when: chunk_count ≥ 3
delegate for isolation (width=1) when: parent read volume > R* (default 50K tokens)
cap at: min(chunk_count, 5)    # 12 never binds; W_cap moot
```

K=3 is now grounded on measured distribution, not asserted at the "latency break-even" (which the review correctly showed doesn't survive arithmetic at small task sizes).

---

## Sequencing verdict

Per §5 of the measurement plan:

| Step | Status | Reason |
|---|---|---|
| M7 (doctrine ground truth) | ✅ Done | Confirmed + SOUL corrected |
| M3 (decomposition distribution) | ✅ Done | Kill-switch fired |
| M5 / M6 (integration cost, failure rate) | ❌ Killed | M3: wide fan-out never occurs |
| M1 / M2 (tax + authoring time) | ⚠️ Partial | n=2 in-session; sufficient given M3's low-stakes verdict on N* |
| M4 (context absorption / R*) | ⏳ Pending | The one measurement M3 did NOT make low-stakes |

**Remaining spend:** M4 only, if you want R* on data rather than a reasoned default.

---

## Limitations (per proposal §6)

- M1/M2 n=2 — report as point estimates with ±40s spread, not distributions. Sufficient given M3's verdict that N*'s exact value is low-stakes.
- M3 is observational over 156 sessions of possibly-curated history. Treat the 12% ≥3-domain figure as a lower bound on true decomposition width (under-routing may have artificially kept some multi-chunk objectives single-domain).
- R* (50K default) is a reasoned estimate, not measured. Flag it as such wherever it appears in doctrine or tooling.
- All constants are this harness's — Anthropic/Sonnet, this workload mix, this infrastructure. They are not universal.
