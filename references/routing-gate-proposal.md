# Whole-Objective Routing Gate — Implementation Proposal (v2, post-review)

Status: approved for implementation. Three gated files: SOUL.md, AGENTS.md, patches/kanban_checkpoint.py.

---

## 1. Delegation-friction finding and its design implications

**Method:** one live probe (a representative pure-Python/SQL builder rewrite) delegated via
`delegate_task`, plus a read of the live `delegation` config block. n=1.

**Findings:**

1. **Delegation runs on claude-sonnet-4-6 (Anthropic), switching to Opus 4 for above-standard
   tasks.** Source: live `config.yaml delegation.{provider,model}`, confirmed by probe output
   quality. The SOUL.md reference to "mac-studio / qwen / DeepSeek fallback" is stale and being
   removed. **The quality-parity claim holds as long as delegation points at the main-model
   family — verify `config.yaml` before tuning K if this is ever repointed.**

2. **Quality: equal to inline.** Probe produced correct SQL, reused existing helpers, verified
   against live DB, caught an ambiguity in the brief.

3. **Latency: a real fixed tax.** ~144s end-to-end vs ~15-20s inline.

4. **Context isolation: large benefit.** 191K input tokens stayed in subagent window; parent
   received ~2KB summary.

**Design implication — K=3 justified on context economics, not latency break-even:**
Latency break-even is ~144s / 18s ≈ 8 chunks — K=3 is below it for small tasks. K=3 is
justified instead on (a) context absorption: every chunk run as a subagent keeps its
entire read/explore/write loop out of the main window, a benefit that holds at any chunk
count ≥ 1; (b) existing doctrine boundary (AGENTS.md already names "3+ independent parallel
chunks → fan-out"); (c) parallelism at 3+ yields real overlap benefit when chunks take
>50s each (characterize chunk sizes if K ever needs retuning). Do not re-introduce the
latency-break-even argument without measuring typical chunk duration first.

---

## 2. Layer 1 — Doctrine (paste-ready for AGENTS.md)

Insert after the "Task routing reflex" section, before "WRITE GATE":

```markdown
## ⚠️ WHOLE-OBJECTIVE ROUTING GATE (never skip)

When a multi-part or open-ended objective lands (inventory, "surface all X",
"bring it all in", audits, any "do A across B"):

1. **Inventory the ENTIRE surface to a structured artifact before routing.**
   Produce `$HERMES_HOME/run/inventory.json`:
   ```json
   {"gaps":[{"id":"<name>","source_ref":"<tool-output excerpt>","chunk":"<builder-name>"},...],
    "chunks":["<builder-a>","<builder-b>",...],
    "chunk_count":<N>,
    "routing":"fanout|inline",
    "reason":"<one line — required for inline>"}
   ```
   Each gap cites its evidence. Chunk labels group gaps by independent author unit
   (different source files / builders = different chunks; integration = not a chunk).

2. **Route on `chunk_count`, not gap count:**
   - `chunk_count ≥ 3` → FAN OUT: parallel `delegate_task` per chunk + integrator turn.
   - `chunk_count ≤ 2` → inline is allowed.

3. **These rationalizations are BANNED as inline justifications:**
   - "Tier 1 / quick win / the easy part first" — curating the objective to shrink
     it into an inline-able shape. The objective is the whole surface.
   - "It all touches one file" — integration concern, not authoring constraint.
     Authors write chunks in parallel; one integrator splices. Never inline justification.
   - "It's sequential / interactive" — valid only with a written one-line reason
     against the FULL surface, not a curated subset.

4. **Delegation currently runs on the main Anthropic model family (see `config.yaml`
   `delegation.provider/model`). Quality is equal to inline. "Delegation gives worse
   results" is not a valid justification while this config holds.**

Vehicle by horizon: same-session interactive → `delegate_task` fan-out.
Cross-session / overnight / human-gated phases → kanban DAG.
```

---

## 3. Layer 2 — Enforcement spec (extend `kanban_checkpoint.py`)

### 3.1 Trigger
Arms when: existing multi-part score ≥ `SIGNAL_THRESHOLD` AND inventory-intent
regex matches the user message:
```python
_OBJ_INTENT = re.compile(
    r'inventory|surface|bring\s+.{0,20}\s+in|every\s+(dataset|field|gap|table|column)'
    r'|what.{0,5}(missing|unsurfaced|not\s+surfaced)|populate|fill\s+in',
    re.IGNORECASE
)
```
Outside this class the gate does not arm (no honest gap-count exists for e.g. "debug
this test"). Stated honestly in block messages.

### 3.2 Arm lifecycle
- Arm sets session-level `self._objgate_armed` (sticky across turns until cleared).
- Arm records `self._objgate_turn_hash = hash(user_text + str(turn_index))`.
- Clears on: `delegate_task`/`kanban_create` called, OR `inventory.json` present with
  matching `turn_hash`, `chunk_count ≤ K`, and non-empty `reason` for inline.
- Per-turn latch (`_kanban_ckpt_last_turn`) still governs nudge frequency; arm governs
  enforcement and is sticky.

### 3.3 Interceptor behavior (pre-execution, mirrors write_gate.py)
On an armed session, intercept the FIRST `write_file`/`patch` whose target is NOT
`$HERMES_HOME/run/inventory.json`:

| Condition | Action |
|---|---|
| `inventory.json` absent | Rewrite to `echo '<block msg>'`, append to tool result |
| Present but `turn_hash` mismatch (stale artifact) | Same block |
| Present, hash match, `chunk_count > K`, no routing tool fired, `routing != "inline"` | Block |
| Present, hash match, `routing == "inline"`, non-empty `reason` | Pass (escape path) |
| `chunk_count ≤ K` | Pass |
| Routing tool already fired this session | Pass |

Block message: "Whole-objective gate: write inventory.json first / declare routing."
Uses `echo '<msg>'` (not `/dev/null`) so the block surfaces as visible tool output.
The agent reads the block; a silent sink would let it believe the write succeeded.

### 3.4 Checker (post-hoc, separate cron) — aims re-targeted per review

The gate forces legibility; the checker audits it. Two signals, in priority order:

1. **Inline-override alarm (loudest):** `chunk_count > K, routing: "inline"` in any
   `inventory.json`. This is the single highest-signal event. Flag for human review
   every time, log prominently. No silent pass.

2. **Chunk-count lower bound:** derive distinct source-file domains from each gap's
   `source_ref`. Flag when `declared_chunk_count < floor(distinct_domains / 2)`.
   Legitimate grouping is allowed; collapsing 5 source domains into chunk_count=1 is
   the suspicious move.

   (Gap population check dropped as primary signal — gap count doesn't drive the
   routing outcome; chunk count and the inline flag do.)

### 3.5 Fail-open + ops parity
- Any guard exception → allow the action, log to stderr. A buggy gate never bricks.
- `HERMES_OBJGATE=off` disables; `HERMES_OBJGATE_K` tunes K (default 3).
- Golden copy at `references/patch-guard/kanban_checkpoint.golden.py`; add new
  markers to `patch_guard.py` restore list; daily self-heal covers it.
- Synthetic test battery (see §4 risk treatment) before deploy; `cp live golden` after.

---

## 4. Risk treatment

**Displacement (curation moves into the plan).** Primary defense: the checker's
chunk-count lower bound derived from `source_ref` domains — a structurally-derived
floor the agent can't easily game without fabricating source refs. Secondary: the
inline-override alarm makes any upstream curation that results in inline-with-K>3
the loudest event in the audit log. Neither certifies completeness — that's the
human's catch, now with an artifact to catch on.

**Complacency.** State in block messages and checker output: *this gate certifies a
routing decision was declared and is legible. It does NOT certify the inventory is
complete or the routing is correct.*

**Test synthesis.** The trigger is deterministic — three independently-testable
conditions (regex intent match, multi-part score, artifact state). Battery constructs
trip/no-trip inputs as a table of `(user_text, inventory_json_state, tool_calls_so_far,
should_block, desc)`:

Required cases (block):
- Armed + no artifact → block
- Armed + stale artifact (turn_hash mismatch) → block
- Armed + artifact + chunk_count > K + no delegate fired + routing != "inline" → block

Required cases (pass — fail-open correctness):
- chunk_count ≤ K → pass
- routing == "inline" + non-empty reason → pass
- delegate_task already fired → pass
- HERMES_KANBAN_TASK set → pass
- Guard exception (simulated) → pass, log to stderr
- Non-objective user message (no intent match) → never arms

Fail-open makes the block cases non-negotiable — a silently-broken gate leaves the
high-stakes cases unguarded. Run the battery; demand 100%; then `cp live golden`.

**Latch & suppression edges.** Multi-turn: arm is sticky (§3.2). Old artifact from
turn-1 can't satisfy arm set on turn-5 (turn_hash check). `HERMES_KANBAN_TASK`
suppression: accepted limitation in Phase 2; workers are single-task by contract.
Phase 3 can arm inside workers whose card body itself describes a multi-surface
objective.

---

## 5. Appendix — Role separation (not recommended phase 1)

Run inventory as a distinct invocation (output only); a separate invocation routes
from an inventory it didn't author. Marginal value over the gate for the common case
given the context-economics argument (the parent already offloads 191K tokens). Revisit
only if the checker shows displacement materializing in practice.

---

## 6. Phased rollout

| Phase | What ships | Gate condition to next |
|---|---|---|
| **1 — Doctrine** | AGENTS.md block + SOUL.md stale-line removal | Doctrine merged |
| **2 — Enforcement** | kanban_checkpoint.py extension + checker cron | ≥2 weeks data: FP rate characterized, escape-justified curation tracked |
| **3 — No-escape** | Drop inline escape for chunk_count > K | Phase 2 data shows trigger precise enough; no pattern of escape misuse |
