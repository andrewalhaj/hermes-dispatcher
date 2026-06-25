---
name: blite-retrieval-maintenance
description: "B-lite retrieval: operate/maintain precision search."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [retrieval, lancedb, rag, b-lite, b-full, orphan-ratio, pointer-coverage, knowledge-store, auto-rag, precision-retrieval]
    related_skills: [knowledge-store, memory-discipline]
    created_by: agent
load_when:
  - "Question about automatic retrieval / auto-RAG / per-turn RAG"
  - "Reliability or consistency of cold-store retrieval"
  - "Orphan facts, pointer coverage, or whether the store is being maintained"
  - "Whether to move from B-lite to B-full (the crossover decision)"
  - "After fast Supabase growth, to re-check retrieval health"
---

# B-lite Retrieval Maintenance

> **⚠️ STATUS CHANGE 2026-06-09: B-FULL IS NOW DEPLOYED (live core patch).** Andrew directed the switch from B-lite → B-full after the crossover gate was NOT formally met — his call, his infra. Per-turn unconditional auto-RAG is now LIVE in `gateway/run.py` (see "B-full deployment" section below). B-lite (agent-invoked search) still runs as the manual fallback and is what the trigger doctrine below describes — it did not go away; B-full layers an automatic per-turn search ON TOP of it. This skill now documents BOTH: operate the B-lite trigger AND maintain the deployed B-full patch.

B-lite is the agent-invoked cold-store retrieval strategy: **agent-invoked, precision-gated (>=0.80) semantic search**, no core patch. This skill is how you OPERATE it (the trigger) and MAINTAIN its reliability (instrument + crossover decision). The trigger doctrine itself lives in `knowledge-store` SKILL.md; this skill is the maintenance layer around it.

> Load `knowledge-store` (the trigger + the architecture findings) and `memory-discipline` (the pointer-completeness invariant) alongside this. They are the two halves B-lite depends on.

## The B-lite trigger (operate it)

When BOTH hold on the current turn:
1. it is clearly **infra / memory / config / device / topology-topical**, AND
2. the answer could depend on a **stored fact** (host spec, port, model string, past decision, tool quirk, device map),

then run `knowledge.py search "<topic>"` **BEFORE answering**. The floor is **judgment, not a flag** — `knowledge.py search` has no `--floor` arg; it prints `[score]` per hit. **Trust only hits >= 0.80**; ignore the rest (the embedding space is dense — junk queries score ~0.67). If nothing clears 0.80, answer normally.

## B-full deployment (LIVE 2026-06-09) — operate + maintain

B-full is now deployed as a **core patch** in `gateway/run.py`. It runs the cold-store search on EVERY turn and injects hits >=0.80 into the context prompt before the model sees it. This is the unconditional per-turn auto-RAG the table below calls "deferred" — that row is now historical; B-full shipped.

**Where it lives (verified seam):**
- Two helper functions inserted after `logger = logging.getLogger(__name__)` (~line 1171): `_bfull_engine()` (cached module loader) and `_bfull_retrieve(message_text, floor=0.80, top_k=3, max_chars=600)` (returns injection string or '').
- The injection call inserted right after the `if message_text is None: return` guard in the gateway run loop (~line 9480): `_bfull_inject = _bfull_retrieve(message_text); if _bfull_inject: context_prompt += _bfull_inject`.
- It calls `knowledge.py`'s real `search(query, top_k=...)` which returns `list[dict]` with `score` (float) + `text` keys. Hits >=0.80 are formatted as `- [score] text` lines, capped at 600 chars.

**THE CACHING GOTCHA (load-bearing — the spec glossed it).** The prototype's "~150ms/turn" assumes the MiniLM embedding model is loaded ONCE. A naive per-turn `exec_module` of `knowledge.py` reloads the model EVERY turn → ~2.2s tax per message, ~15x regression. The deployed patch avoids this with a module-level `_BFULL_ENGINE` / `_BFULL_ENGINE_TRIED` cache in `_bfull_engine()` — first topical turn loads it, every subsequent turn reuses it. **If you ever re-port or rebuild this patch, the cache is mandatory, not optional.** The engine loads LAZILY (first topical turn), so there is no startup log line — absence of a load message at boot is correct, not a failure.

**Fail-safe design (why it can't take the gateway down):** `_bfull_retrieve` wraps everything in `try/except Exception: return ""`. Any failure (engine won't load, search throws, weird return shape) yields an empty string → no injection → the turn proceeds exactly as pre-patch (degrades to B-lite). Verified: off-topic ("tell me a joke") and empty inputs stay silent.

**Protection (or `hermes update` silently kills it):** `gateway/run.py` is a ~20k-line UPSTREAM file that `hermes update` rewrites — so this needs the SAME surgical-reapply treatment as the Honcho drift patch, NOT a whole-file golden restore (which would clobber upstream changes). Registered as `_heal_bfull()` in `scripts/patch_guard.py` (call #5 in the run-checks block):
- Golden text blocks: `references/patch-guard/bfull-helpers.golden.py` + `bfull-injection.golden.py`.
- Healthy check: marker `_bfull_retrieve(message_text)` present in live run.py → silent.
- On drift: backs up live, re-inserts BOTH blocks at their anchors (`logger = logging.getLogger(__name__)` and the `message_text is None` guard), syntax-validates, reports.
- The 05:00 self-heal cron already invokes patch_guard.py, so registration is automatic. Verified: strip-then-reheal on a copy restores a compiling file.

**Restart to activate** (any run.py edit needs it): detached drain pattern — `systemd-run --user --scope --collect bash -c 'XDG_RUNTIME_DIR=/run/user/0 systemctl --user restart hermes-gateway.service'`. Exit 124 / `deactivating` for 60-90s = the drain, NOT a failure (the gateway waits for the active session to flush before the new PID comes up). Verify: new MainPID != old, fresh ActiveEnterTimestamp, `grep -c '_bfull_retrieve(message_text)' run.py` == 1.

**Rollback (one command):** restore `run.py.bak-<ts>-prebfull` + restart. Fully reversible.

**Known caveats now that it's live:** (1) per-turn latency + token cost on ALL traffic, infra-topical or not; (2) it injects the SAME embedding scores — a fact that embeds below 0.80 (e.g. the LanceDB-install row at 0.74 under some phrasings) still won't surface, so hot pointers remain necessary for sub-floor facts; (3) core-patch fragility — survives updates only via the self-heal cron. If these costs bite, the principled de-escalation is back to B-lite (revert the patch) or forward to Stage 3 (cross-encoder reranker) to lift true hits over the floor.

## Why B-lite, not B-full (the ORIGINAL decision — superseded 2026-06-09 by Andrew's directive)

> Historical: this table drove the B-lite choice. Andrew overrode it 2026-06-09 and shipped B-full anyway (his call). Kept for the tradeoff reasoning, not as the current state.

| | B-lite (chosen) | B-full (deferred) |
|---|---|---|
| Trigger | agent judgment, topical turns only | unconditional, every turn |
| Core patch | none | yes — `gateway/run.py` ~9459, patch_guard-protected |
| Latency | only on topical turns | ~150ms every turn |
| Token cost | tool output, read-once, filtered | injected into context, re-sent, compounds |
| Noise | filtered at reasoning step | injected unconditionally |
| Value | ~90% of auto-RAG | the last ~10% |

B-lite's one failure mode is **silent omission** (agent doesn't fire the search on a soft-topical turn). Three reinforcing layers cover it: (1) hot-tier POINTERS cue the lookup, (2) the skill-review checkpoint nudges loading `knowledge-store` on complex sessions, (3) the trigger doctrine. Any one firing catches the fact.

## The reliability dependency: pointer coverage

B-lite is reliable **only while cold facts keep a hot-tier pointer**. A fact stored without a pointer is an **orphan** — retrievable but with nothing to cue the lookup, so invisible to judgment-fired search. Automated/fast storage growth is the threat: it decouples storing from pointer-leaving. **Pointer-coverage decay (NOT row count) is the real accelerant toward B-full.**

Defense is in `memory-discipline`: the **pointer-completeness invariant** — every offload lands its pointer in the same motion as the trim. No trim without its pointer. A pointerless offload is a silent deletion with extra steps.

## The instrument: orphan_ratio.py

`~/.hermes/scripts/orphan_ratio.py` — read-only, opens LanceDB directly (no embedding-model load, ~1s). Run it to measure pointer health:

```bash
python3 ~/.hermes/scripts/orphan_ratio.py          # segmented human report
python3 ~/.hermes/scripts/orphan_ratio.py --json   # machine-readable
python3 ~/.hermes/scripts/orphan_ratio.py --quiet   # just the fact-orphan ratio float
```

It reports **THREE segmented metrics** — keep them separate, never collapse to one headline number (that was the original mistake; see pitfall below):

1. **Fact-orphan ratio** = uncued standalone facts / total standalone facts. **THIS is the B-lite reliability metric.** Baseline 2026-06-09: **25%** (12/48) after the first remediation pass (prune 6 + pointer 6 default-domain + hand 7 HA facts to ha-bot). The remaining ~25% are sister-profile-domain facts correctly NOT pointered into default. The live baseline always lives in `orphan-ratio-baseline.json` — read that, don't trust this number.
2. **Doc coverage** = reference DOCUMENTS reachable from hot/skills / total docs. A document-level question — multi-chunk docs (e.g. `gbrain-cherry-pick` = 13 chunks) do NOT each need a MEMORY.md pointer. Baseline: 44% (4/9 docs).
3. **Stale prune-bait** = session-progress junk that should never have been stored ("shrunk hot memory to N chars", "built X script"). Prune these, don't pointer them.

Baseline stored in `~/.hermes/references/orphan-ratio-baseline.json`. **Re-baseline whenever the metric DEFINITION changes** (not when the value drifts — drift is the signal).

## The watchdog hook

`infra_watchdog.py` section 8 calls `orphan_ratio.compute()` every 15 min and pages P1 **only if the fact-orphan ratio rises >= 15 percentage points above baseline** — a trend alarm, not an absolute threshold (the baseline is intentionally noisy-but-stable; movement is what matters). Wrapped so the probe can never break the watchdog chain. Silent at baseline.

## The crossover decision (B-lite -> B-full)

B-full earns its fragility ONLY when ALL THREE hold — not before:
1. **Reteach rate rising** — Andrew says "what happened to X?" / "I told you this" recurringly. The symptom of coverage-blindness.
2. **Orphan ratio climbing** despite the pointer-completeness invariant — the instrument shows decay the doctrine can't keep up with.
3. **Noise floor dirtying** — re-run `auto_retrieve_proto.py`; junk queries start clearing 0.80.

Rough gate: **~800-1,500 rows AND the cross-encoder reranker (knowledge-store Item 5) already in place AND recurring reteach events.** Below that, the cheaper fix is always **Stage 2** (pointer-on-every-offload) — attack the decay, don't patch the core.

Staged path: **Stage 1** B-lite + 3-layer redundancy (now) -> **Stage 2** pointer-complete offload (when orphans climb) -> **Stage 3** cross-encoder reranker (when floor dirties) -> **Stage 4** B-full core patch (last resort, only with reranker in place).

> **If B-full IS greenlit:** the concrete wiring — verified `run.py` injection seam (~9479), the fail-safe patch block, the embedding-model caching gotcha (naive wiring = 2.2s/turn, not the advertised 150ms), patch_guard protection, and the apply/rollback sequence — is in `references/b-full-implementation-recipe.md`. Note that recipe's closing point: B-full does NOT fix the orphan-below-floor symptom that usually motivates the request.

## Remediating orphans (the fix workflow, proven 2026-06-09)

When the instrument flags fact-orphans, do NOT naively "add a pointer for each." Segment first, then act:

1. **Segment orphans by DOMAIN before pointering.** Many cold facts belong to a SISTER profile's hot tier, not the current one. HA-domain facts (Govee, Sonos, Plex, Prime Video, LG ThinQ, Shield) belong in **ha-bot's** MEMORY.md — pointering them into `default` is overreach (violates least-astonishment + the "HA is HAJarvis's domain" rule). Only pointer facts that are genuinely THIS profile's. Hand the rest to the owning profile via the kanban board.
2. **Detect true duplicates** — older terse rows superseded by a fuller later row (e.g. "Connected Govee 9 devices" vs the full device map). Prune the dupes, don't pointer them.
3. **One COMPACT cue line, not N verbose pointers.** A pointer is a CUE, not the content. Collapse several facts into a single `§ Cold facts (knowledge.py search): A / B / C.` line — costs ~40 chars/fact, keeps MEMORY.md under cap. Draft-to-measure (`wc -m`, chars not bytes) BEFORE writing; if it pushes past ~95%, trim the lowest-value cues, don't force it.
4. **Pruning is REVERSIBLE-then-delete.** `knowledge.py` has NO CLI delete command. Delete via direct lancedb: export the doomed rows to `references/_archive/lancedb-pruned-<ts>.json` FIRST (drop the `vector` column, `default=str` for json-safety), then `tbl.delete("id = '<id>'")` per row, then verify `count_rows()` dropped by exactly N and none remain. The export is the restore path — this is what makes the delete reversible (autonomous-safe).
5. **Re-baseline + log after remediation.** Re-run the instrument, write the improved ratio to `orphan-ratio-baseline.json`, and append the move to `references/memory-offload-audit-log.md` (what pruned, what pointered, what left for which profile, ratio before→after).

## When two memory sources conflict on a VERIFIABLE fact — query, don't arbitrate (proven 2026-06-09)

The single worst B-lite failure is **arbitrating between two stale memory snapshots instead of asking the world.** Live case: my injected hot-MEMORY block said "LanceDB never installed" while the Honcho/identity context implied it WAS in the stack. I trusted the hardcoded note and dismissed Honcho as the usual confabulator — and was wrong (LanceDB 0.33.0 was installed and populated). Root cause was NOT "forgot to fire the search"; it was **resolving a conflict by judgment when the fact was checkable in one command.**

Rule: **install-state / config / version / port / path facts are verifiable — verify, never arbitrate.** When two memory sources disagree on such a fact, the tiebreaker is the world, not whichever memory you trust more:
- install/import state → `python3 -c "import <pkg>; print(<pkg>.__version__)"`
- file/dir existence → check the path directly
- only THEN fall back to B-lite search or memory.

This is cheaper than the arbitration you'd otherwise do, and it's the user's standing rule ("the world is the source of truth"). The injected hot-MEMORY block is a **session-start snapshot that lags the live MEMORY.md** — treat a suspicious entry in it as a hypothesis to verify, not ground truth.

## The 0.80 floor can SILENTLY HIDE a present fact (orphan-below-floor, proven 2026-06-09)

B-lite trusting only ≥0.80 has a second failure mode beyond not-firing: **the fact is in the store but embeds below 0.80, so the floor correctly ignores it and you still answer wrong.** Live: the LanceDB install fact existed as auto-captured row `820b488c` ("Installed lancedb and sentence-transformers…") but scored **0.7356** for a reasonable query — under floor, so B-lite would have skipped it. Low-value auto-captured one-liners embed poorly. This is the documented orphan failure wearing a different mask: retrievable in principle, invisible in practice.

Diagnosis when you suspect a known fact isn't surfacing: run the search and **read the sub-0.80 hits too** — if the fact is sitting at 0.70–0.79, it's an orphan-below-floor, and the fix is a **hot-tier POINTER** (cue line in MEMORY.md) so judgment, not embedding score, surfaces it. Do NOT lower the global floor to catch it (that dirties the noise floor for every other query).

⚠️ **Run knowledge.py from the DEFAULT profile, never a snapshot's copy.** `find ~/.hermes -name knowledge.py | head -1` can grab `profiles/pre-update-2026-06/scripts/knowledge.py` or another rollback snapshot's stale engine/store. The canonical engine is the **default profile's** `knowledge.py` against the default `knowledge_db/`. Resolve the path explicitly (default profile), don't `find | head`.

## Honcho and Supabase are NOT interchangeable layers — "swap/reorder" is a category error (proven 2026-06-09)

When asked to "switch up" / "reorder precedence between" the memory layers, do NOT accept the framing that they're peer subsystems you can swap. Live investigation (grep the whole codebase for memory-layer "precedence" — you'll find only model-provider and approval precedence, nothing for memory ordering) proved:

- **Honcho is the `memory.provider`** — one pluggable slot (`plugins/memory/<provider>/`: honcho, mem0, hindsight, supermemory, …). It auto-injects a user-MODELING block. It SYNTHESIZES (dialectic) — which is why it confabulates.
- **Supabase/B-full is NOT a memory provider** — it's a separate per-turn retrieval core-patch in `gateway/run.py`. It can't occupy the provider slot; it returns only facts explicitly stored (deterministic, never invents).
- **No shared recall pipeline, no precedence knob, no fallback between them.** Both blocks just get appended to the context prompt independently.

So "reorder precedence" is unimplementable as stated, and "swap them" is impossible (Supabase can't model the user; Honcho can't be a trustworthy deterministic store). When the user's framing contradicts the architecture, surface it and re-map to what IS achievable before building.

### "Lean toward Supabase / away from Honcho" — the real implementation (tiered, all gated)

The achievable goal is *shrink Honcho's per-turn footprint + confabulation surface, elevate the deterministic store* — NOT blind Honcho to the user (its peer card holds modeled preferences; losing every-turn injection means a preference can miss a turn until B-full/hot-pointers cover it).

**Honcho knobs (config-driven, `config.yaml` `honcho:` block — raw camelCase keys, parsed in `plugins/memory/honcho/client.py`):**
- `injectionFrequency: first-turn` (vs `every-turn`) — biggest lever; injects once per session (guard at `__init__.py` `_turn_count > 1` returns empty). Kills per-turn drift + token cost.
- `reasoningLevelCap: low` (vs `high`) — caps the synthesizing dialectic that confabulates.
- `dialecticCadence: N` — run dialectic every Nth turn.
- `contextTokens` — injected-block size budget.

**B-full knobs (HARDCODED in `gateway/run.py` `_bfull_retrieve(message_text, floor=0.80, top_k=, max_chars=)` — NOT config):** raising `top_k`/`max_chars` elevates deterministic recall. This is a core-patch edit → **you MUST mirror the change in the patch_guard golden file** (`references/patch-guard/bfull-helpers.golden.py`) or the 05:00 self-heal cron reverts it on the next `hermes update`. Leave `floor=0.80` (lowering it dirties the noise floor for every query — see the orphan-below-floor pitfall). Activation needs a gateway restart (detached drain).

**Renumber the docs after:** `infrastructure-summary.md` Memory System table + the Honcho AI identity card (`honcho_profile(peer="ai", card=[...])`, full-array rewrite — `honcho_conclude` needs IDs you don't have). Correct any stale `Retrieval Strategy: B-lite` → B-full there too.

## Pitfalls

- **Don't collapse the orphan metric to one headline number.** The original instrument reported a single "50.3%" that conflated three different things: reference-doc chunks (68% of the count — a category error, they don't need per-chunk pointers), genuine uncued facts (the real signal), and stale junk (prune-bait). Segment them. The honest fact-orphan number was 40%, not 50%.
- **Don't over-tune the filter to chase a prettier number.** The watchdog tracks a TREND (delta from baseline). A noisy-but-stable baseline still detects decay. Spend effort on the segmentation that makes the number *mean the right thing*, not on cosmetic reduction.
- **`knowledge.py search` has NO `--floor` flag.** Hand-rolled argv parsing, prints top-K with scores. Apply the 0.80 floor by judgment when reading hits.
- **NEVER replace `table_names()` with `list_tables()` to silence the DeprecationWarning — it WILL break (proven twice 2026-06-09, including once right after writing this pitfall).** `table_names()` emits a cosmetic `DeprecationWarning` but returns a list of STRINGS. `list_tables()` returns a different shape that, after `list(...)`, yields TUPLES — so `db.open_table(tname)` dies with `TypeError: argument 'name': 'tuple' object is not an instance of 'str'`. The deprecation is harmless; the "fix" is the bug. Keep `table_names()` and wrap it in `warnings.catch_warnings(); warnings.simplefilter("ignore", DeprecationWarning)` if the warning noise matters. Do not touch this again.
- **Read LanceDB directly for counting** (`lancedb.connect()` + `to_pandas()`), NOT via `knowledge.py` import — the latter loads the ~2s embedding model, too heavy for a 15-min watchdog. Only fall back to `knowledge.py` if the direct path fails.
- **Don't store session-progress as facts.** "Shrunk hot memory", "built X script", "Phase N done" are exactly the prune-bait the instrument flags. Memory doctrine already forbids it; the instrument just makes the violations visible.

## Files

- `~/.hermes/scripts/orphan_ratio.py` — the segmented instrument (read-only)
- `~/.hermes/scripts/infra_watchdog.py` §8 — the trend alarm
- `~/.hermes/references/orphan-ratio-baseline.json` — current baseline
- `~/.hermes/scripts/auto_retrieve_proto.py` — the precision/recall harness (re-run to re-measure the 0.80 floor)
- `knowledge-store` `references/auto-retrieval-architecture.md` — the full B-lite vs B-full investigation
