---
name: knowledge-store
description: "Knowledge store: semantic KB for agent institutional memory."
version: 3.1.0
author: Hermes Agent
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [knowledge, memory, vector-db, lancedb, semantic-search]
    created_by: agent
load_when:
  - "user asks about a system configuration, tool quirk, or past bug fix"
  - "agent needs to recall institutional knowledge about this user's setup"
  - "hot memory is full and knowledge offloading is needed"
---

# Knowledge Store — Supabase Semantic Memory

Persistent, searchable knowledge base for everything the agent needs to remember about this user's system, tools, and environment. Complements Honcho (user modeling) and hot memory (session-critical context).

## Quick Reference

```bash
# Search
python3 ~/.hermes/scripts/knowledge.py search "manifest routing fallback"
...

**Supabase → Hermes webhook (auto MEMORY.md append):** `references/supabase-webhook-pg-net.md` — pg_net trigger setup, Hermes FastAPI endpoint, Cloudflare Bot Fight Mode workaround, secret rotation.
**Neo4j graph layer (complements pgvector):** `references/neo4j-graph-layer.md` — Docker setup, handler pattern, relationship extraction, backfill, query patterns.

# Store a fact
KNOWLEDGE_TAGS="govee,bug" KNOWLEDGE_PRIORITY="high" \
  python3 ~/.hermes/scripts/knowledge.py store "Fact text here"

# Store with contextual prefix (overlap chunking + Haiku/synthetic prefix)
KNOWLEDGE_TAGS="infrastructure" \
  python3 ~/.hermes/scripts/knowledge.py store --contextualize "Fact text here..."

# Index vault changes (standard heading-based chunking)
python3 ~/.hermes/scripts/knowledge.py index-vault

# Index vault with contextualized chunking
python3 ~/.hermes/scripts/knowledge.py index-vault --contextualize

# Contextualize a single file (chunk → prefix → embed → store)
python3 ~/.hermes/scripts/knowledge.py contextualize-file ~/path/to/file.md

# Status
python3 ~/.hermes/scripts/knowledge.py status

# Unified tiered retrieval across ALL sources (Supabase + MEMORY.md + USER.md + reference docs)
python3 ~/.hermes/scripts/query_router.py instant "<query>"   # Supabase-only, fastest
python3 ~/.hermes/scripts/query_router.py classic "<query>"   # merge all sources, ranked + source-attributed
python3 ~/.hermes/scripts/query_router.py agentic "<query>"   # plan + graph neighbors + suggested reads
# add --json to any tier for machine-readable output. READ-ONLY (never mutates the DB).
# Honcho is NOT covered (needs live MCP) — query it separately via honcho_search.

# Recent entries
python3 ~/.hermes/scripts/knowledge.py recent 10

# Build the wikilink/cross-reference knowledge graph (v3.0)
python3 ~/.hermes/scripts/knowledge.py build-graph

# Query graph neighbors of a page (multi-hop; GRAPH_HOPS=2 default)
python3 ~/.hermes/scripts/knowledge.py graph-query infrastructure-summary

# Run benchmark evaluation (v3.0 — 12-query harness for retrieval quality)
python3 ~/.hermes/scripts/knowledge.py eval

# Check for stale infra/config facts (dry-run default; --live for connectivity probes)
python3 ~/.hermes/scripts/knowledge.py stale-check

# Index changed reference/vault files since last run (mtime-based; safe for cron)
python3 ~/.hermes/scripts/knowledge.py auto-index

# Compile search results with citations + gap analysis (no LLM, pure compilation)
python3 ~/.hermes/scripts/knowledge.py summarize "how does memory work across sessions"
```

### v2.0: Contextualized Embeddings

The contextualized embedding pipeline wraps each chunk with a **situating prefix** before embedding, so the vector captures *what document this is from and where it sits in the document structure*, not just the raw text.

**Pipeline:**
1. **Overlap-based paragraph chunking** — splits markdown into paragraphs on `\n\n+`, groups into ~800-char chunks with 1-paragraph overlap. Each chunk tracks its heading breadcrumb.
2. **Contextual prefix generation** — sends chunk + source context to Manifest's Haiku route (`claude-haiku-4-5`) for a 1-sentence situating sentence.
3. **Synthetic floor** — if Manifest/Haiku is unreachable (Anthropic provider inactive, timeout, etc.), falls back to `"This passage is from {filename}: {heading context}."` — measurably better than plain text via title-keyword re-injection.
4. **Embed** `"{prefix}\n\n{chunk_body}"` — the vector now encodes both *what* the text says and *where* it's from.
5. **Sha256 cache** — chunks are cached by body hash. Re-contextualizing the same file skips unchanged chunks.

**Columns:** `context_prefix` (the situating sentence) and `body_hash` (sha256 for cache dedup) — both added via schema migration on first v2.0 access. Existing plain-text embeddings survive untouched with NULL values.

**Cost:** Haiku prefix generation requires the Anthropic provider. Since Hermes now uses `hermes-claude-auth` for direct Anthropic access (`provider: anthropic`), Haiku is reachable. If the Anthropic provider is unavailable, the synthetic floor (`"This passage is from {filename}: {heading context}."`) handles everything automatically — measurably better than plain text via title-keyword re-injection.

### v3.0: Hybrid Retrieval + Knowledge Graph

`search()` is no longer pure vector cosine. The v3.0 pipeline:

1. **LRU embedding cache** — repeated queries skip re-encoding (256-entry cap, 30-min TTL). Transparent.
2. **Hybrid vector + BM25 fusion** — runs a Supabase FTS keyword search alongside the vector search. **Adaptive weighting:** bare-identifier queries (e.g. `DATABASE_URL`, `max_spawn_depth`, error codes — detected by underscores / all-caps / single-token) weight BM25 at 0.75; prose queries stay vector-dominant at 0.6. This fixes the long-standing "exact config-key search scores negative" failure. Degrades gracefully to vector-only if FTS is unavailable.
3. **Priority + recency scoring** — `priority` (critical/high/normal/low) and `stored_at` now actually affect ranking: importance multiplier + exponential recency boost (14-day half-life).
4. **MMR diversity** — when `top_k > 3`, near-duplicate results (cosine > 0.85) are dropped so you don't get 5 variants of the same fact.
5. **Knowledge graph boost** — `build-graph` scans `~/.hermes/references/` (and the Obsidian vault / `WIKI_PATH` if present) for `[[wikilinks]]`, bare `filename.md` cross-references, and frontmatter `related:`/`tags:`. Edges land in `~/.hermes/knowledge_db/graph.sqlite`. `search()` gives a small confirmatory boost to results whose source page is a graph-neighbor of a top-3 hit. No-op until `build-graph` runs.

**Rebuild the graph** after adding or heavily cross-linking reference docs: `python3 ~/.hermes/scripts/knowledge.py build-graph`. It's cheap (zero LLM, pure file scan + SQLite).

### Synthesis convention: name the gaps (anti-fabrication)

When synthesizing an answer from `search()` results, **explicitly flag what the knowledge base does NOT contain** rather than papering over it. After presenting what was found, add a short "Gaps" note listing query terms that returned zero or weak (low-score) hits. This is the anti-fabrication principle (SOUL.md) applied to retrieval — borrowed from GBrain's `think` command. A retrieval answer that hides its blind spots is worse than one that names them. If every relevant query came back empty, say so plainly: "Nothing in the knowledge base covers X" — don't improvise.

## How Hermes Uses It

**Session-start ritual (MANDATORY):**
When the user's first message relates to infrastructure, system config, tools, or any topic that might have been discussed before, query Supabase BEFORE responding:
```bash
python3 ~/.hermes/scripts/knowledge.py search "<topic from user's first message>"
```
This prevents reteaching. The most common failure mode: agent answers from hot memory only, misses 77 relevant facts in Supabase, user has to repeat themselves. Do NOT wait until you "need" deeper knowledge — assume the user's first infrastructure question needs a Supabase check.

**During a session:**
- Hot memory (injected every turn) contains 2-3 critical pointers only
- When anything technical arises — even if it feels familiar — do a Supabase search. The hot memory store (config-driven cap, ~3,000 chars) is NOT a reliable source for config details, server topology, or tool quirks. Hot memory is a pointer to the real knowledge in Supabase.
- New things I learn get stored immediately with appropriate tags and priority

**Post-session auto-capture:**
After each session with significant changes, run the session capture script to auto-extract learnable facts:
```bash
python3 ~/.hermes/scripts/session_capture.py "<summary of session changes and decisions>"
```
Use `--dry-run` first to preview, then without it to store permanently. The script identifies:
- Changes, fixes, additions, removals
- Corrections and clarifications
- Command invocations with explanations
- Config changes

**Search is semantic** — "env secrets file" finds ".env read_file restriction" because the embedding matches conceptually, not literally.

## Priority Levels

| Priority | When to use |
|----------|------------|
| `critical` | The one thing that prevents disaster if forgotten |
| `high` | Config details, tool quirks, device maps — reviewed every related query |
| `normal` | Procedural notes, historical context |
| `low` | Nice-to-have but not essential |

## Tags (Current)

`govee`, `config`, `env`, `secrets`, `gateway`, `discord`, `telegram`, `obsidian`, `vault`, `honcho`, `memory`, `cron`, `jobs`, `profiles`, `executor`, `user`, `preferences`, `communication`, `bug`, `workaround`, `script`, `commands`, `system`, `server`, `routing`, `devices`, `audit`, `skills`, `rules`, `factual`

## Storage

- **Location:** `~/.hermes/knowledge_db/` (Supabase pgvector backend)
- **Embedding model:** `all-mpnet-base-v2` (768-dim, best local quality — upgraded from MiniLM 2026-06-04). Rollback via `knowledge_minilm_backup.parquet` + reverting MODEL_NAME in knowledge.py.
- **Concurrent-safe:** Supabase supports multi-process reads/writes
- **Backup:** Included in `hermes-backup-*.tar.gz` via the daily backup cron

## Indexing the Vault

After writing new changelogs or snapshots to the Obsidian vault, re-index:

```bash
# Standard heading-based chunking (legacy, plain text embeddings)
python3 ~/.hermes/scripts/knowledge.py index-vault

# Contextualized chunking (overlap chunks + situating prefixes)
python3 ~/.hermes/scripts/knowledge.py index-vault --contextualize
```

The contextualized mode chunks all markdown files by paragraph overlap, generates situating prefixes via Manifest Haiku (with synthetic fallback), and embeds `{prefix}\n\n{body}` instead of raw text. Archive and backup directories are excluded in both modes.

## Memory Architecture

| Layer | System | Purpose | Size Limit |
|-------|--------|---------|------------|
| Hot | `MEMORY.md` | Session-critical pointers only | 3,000 chars (USER.md 1,375) |
| Knowledge | Supabase | Agent institutional knowledge | Unlimited |
| Person | Honcho | User patterns, preferences | Cloud, managed |

Caps are config-driven (`memory.memory_char_limit` / `memory.user_char_limit` in config.yaml) — read them live rather than trusting any number written here; this table goes stale when the cap changes.

Hot memory should NEVER contain knowledge that Supabase can serve. If you see a fact in hot memory that belongs in Supabase, move it.

## Staleness Audit Methodology (proven 2026-06-08)

The cold store rots silently: a fact stored as true in June is false in July when the system changes outside your view. Before relying on cold-tier recall — and ESPECIALLY before offloading fresh hot-tier facts into Supabase — audit it. A polluted store buries good data among contradicting stale rows, and semantic recall surfaces both with no signal which wins. Reusable probe: `scripts/staleness_scan.py` (see below). The method, in order:

1. **Deterministic dead-term scan FIRST — not LLM judgment.** Build a `(dead_pattern, why_dead, correct_fact)` list from VERIFIED-dead literal strings (retired services, decommissioned ports, renamed hosts), then pure-substring scan every row + reference doc. Zero hallucination — a regex can't confabulate. This catches the bulk. Do NOT open with "ask a subagent to judge staleness from its own knowledge" — that just launders the model's stale priors into the kill list.
2. **VERIFY the kill-list premise against the LIVE filesystem before trusting it.** The dead-term set is built from your own notes/memory — and the standing rule is *the filesystem wins over stored notes*. Before nuking 9 docs on the premise "service X is dead," prove X is actually gone on the live host (`docker ps`, port probe, `ls` the dir). This session the premise held (Manifest/ha-fusion confirmed absent, wall-dash live) — but if it had inverted, the entire kill list would invert. One live check guards against acting on a stale dead-term set.
3. **FLAGGED ≠ KILL. Classify every hit into four buckets** — a raw flag list presented as a kill list is the trap:
   - **CORRECT** — a stale *current-state claim* (e.g. "dashboard is ha-fusion at :5050"). Rewrite the fact in place; don't delete the row.
   - **KEEP-historical** — session transcripts, changelogs, post-mortems. These are TRUE records of past events; the dead term appears because the event really happened. Deleting them erases history.
   - **PROTECT-meta** — the confabulation blocklist, staleness-audit logs, `.bak` files, and a doc's own "the prior version described X / there is no X" correction preamble. These are SUPPOSED to name dead terms; killing them guts the defense that records what's false.
   - **REINGEST-chunk** — chunked copies of a reference doc that was already rewritten. The source doc is fixed but the cold store still serves the dead version. Re-chunk from the current doc (don't hand-edit the chunk).
4. **Keyword classification needs a content read for the borderline cases.** Auto-bucketing by keyword mislabels a blocklist row that *asserts* "X is false" as a stale-X claim, and can miss a meta-row that itself went stale (e.g. a blocklist line listing "LanceDB usage" as a confabulation — now wrong, LanceDB is real). Read the handful of borderline rows before finalizing.
5. **Split the fix into mechanical vs reasoned (this is the Phase-B shape).** Mechanical = literal dead-string swaps ("Manifest router"→"direct routing", ":5050"→":5051", "backup VPS 178"→"prod host 178") — scriptable, low-judgment, one gated diff. Reasoned = docs ABOUT a system that no longer exists (rewrite-vs-archive is a user decision, not a find/replace) + surgical row corrections. Only the reasoned half is swarm-shaped.

The whole sequence is read-only through classification; mutation (delete/rewrite/reingest) is a separate gated phase presented as a kill/correct ledger. Write the ledger to a durable `references/staleness-audit-<date>.md` so it survives compaction.

**Reusable probe:** `scripts/staleness_scan.py` runs step 1 (read-only dead-term flag report over the cold store + reference docs). Edit its `DEAD` list to the currently-verified-dead facts, run it, then do steps 2–4 by hand. It deliberately prints FLAGS, not a kill list.

## Pitfalls

**CLI `knowledge.py search` latency is COLD-START, not the DB — profile before "optimizing" retrieval (proven 2026-06-17).** A baseline measured `knowledge.py search` at **7.9s** and the instinct was "the DB is slow, build an index / switch models." Profiling the call into phases proved the opposite — the vector search itself is **~70ms**; the other ~6.7s is pure per-process cold-start:

| Phase | Time | Nature |
|---|---|---|
| `import sentence_transformers` (pulls torch) | ~3.6s | cold-start tax |
| `SentenceTransformer('all-mpnet-base-v2')` load (420MB) | ~1.9s | cold-start tax |
| `import lancedb` | ~1.2s | cold-start tax |
| db connect + open_table | 0.016s | instant |
| embed query | 0.039s | instant |
| **vector search (438 rows)** | **0.031s** | the actual retrieval |

Drop-in profiler (run via the venv python so torch/lancedb resolve):
```python
import time; t0=time.perf_counter()
import lancedb; t1=time.perf_counter()
from sentence_transformers import SentenceTransformer; t2=time.perf_counter()
m=SentenceTransformer('all-mpnet-base-v2'); t3=time.perf_counter()
db=lancedb.connect('/root/.hermes/knowledge_db'); tbl=db.open_table('knowledge'); t4=time.perf_counter()
qv=m.encode(['<query>'],normalize_embeddings=True)[0]; t5=time.perf_counter()
r=tbl.search(qv).limit(16).to_list(); t6=time.perf_counter()
for label,a,b in [('lancedb-import',t0,t1),('st-import',t1,t2),('model-load',t2,t3),('connect',t3,t4),('embed',t4,t5),('SEARCH',t5,t6)]:
    print(f'{label}: {b-a:.3f}s')
```

**The conclusions that follow from this (do NOT skip the profiling step and jump to a fix):**
1. **The hot path is ALREADY warm — verify before declaring a user-facing latency problem.** B-full's per-turn RAG loads the model ONCE at gateway start (`_bfull_engine()` caches it module-level in `gateway/run.py`, ~line 1488) and reuses it. Live in-conversation retrieval is ~70ms, NOT 7.9s. The 7.9s only hits **cold callers**: manual CLI `search` and crons that shell out (`auto-index`, dedup, KB audit). So this is a cron/CLI-efficiency question, not a latency emergency — reframe urgency accordingly.
2. **At small scale (438 rows) brute-force kNN at 31ms beats any ANN index.** Do NOT build an IVF_PQ vector index to "speed up search" here — it's premature until ~50–100k rows. The FTS index already present (for BM25 hybrid) is the only index this scale needs.
3. **Don't downgrade the embedding model for speed.** Switching mpnet→MiniLM saves only ~1.4s (the torch import dominates and stays) and sacrifices the recall the mpnet upgrade was made for. Reject it.
4. **The only real latency fix is killing the cold-start, not touching the DB:** a long-running warm search daemon (holds model + lancedb connection, exposes a localhost/socket endpoint; CLI becomes a thin client → 7.9s→~100ms for all callers — same pattern as B-full's warm engine and the codegraph daemon), OR offload embedding to a Metal `nomic-embed-text` on the inference node over the tailnet (kills torch entirely but couples ALL KB reads to that node being up — a resilience hit; usually not worth it). Gate either as a new supervised service + watchdog entry.

**Daemon SILENT-DEGRADATION failure: orphaned socket → every search cold-loads again (proven 2026-06-18).** The daemon can report `active (running)` for hours while `knowledge.py search` silently falls back to the 7.7s cold path — because the *socket file* `~/.hermes/run/kb.sock` got deleted out from under the live process (a previous restart's `_cleanup` unlinked it, a tmp sweep, or a manual `rm` of the run dir). The kernel socket (inode) stays open on the daemon's fd, but the filesystem entry is gone, so clients `connect()` → `FileNotFoundError` → transparent fallback to in-process cold load. Nothing errors; it's just slow forever. **Tells:** (a) `ls -la ~/.hermes/run/kb.sock` → "No such file or directory" while the unit is active; (b) `knowledge.py search` prints `Loading weights: 100%` and takes >7s; (c) `grep kb.sock /proc/net/unix` still shows the daemon bound to the path (kernel-side) but the dir entry is missing. **Diagnosis one-liner:** `ls -la ~/.hermes/run/kb.sock 2>&1; time python3 ~/.hermes/scripts/knowledge.py search test 2>&1 | grep -c Loading` — missing file + a `Loading` line = orphaned socket. **Fix:** restart the daemon (`systemctl --user restart hermes-kb-daemon`) — it re-creates the socket on boot. Verify: `ls -la ~/.hermes/run/kb.sock` shows a fresh `srw-` file, and a second `knowledge.py search` returns in ~0.5s with no `Loading weights` line. **Hardening gap to close if it recurs:** `infra_watchdog` checks the *unit* is active but NOT that the socket file exists AND answers — add a probe that `connect()`s to the socket (not just `os.path.exists`, since the orphaned case can leave a stale file too) and restarts on failure. The unit being "up" is not proof the fast path works.

**→ The warm daemon is BUILT and LIVE (2026-06-17). `knowledge.py search` is now ~0.5s.** Don't rebuild it — operate it. Full build details, the two correctness traps, and the verification recipe are in `references/warm-search-daemon.md`. Capsule:
- **Two-part fix, BOTH required.** (a) `scripts/kb_daemon.py` = Unix-socket server at `~/.hermes/run/kb.sock` holding model+lancedb warm; `scripts/kb_client.py` = thin pure-stdlib client. (b) **The bigger win was making `lancedb`+`sentence_transformers` imports LAZY in `knowledge.py`** (moved inside `get_db()`/`get_model()`). Without the lazy-import half, `knowledge.py search` still paid ~4.8s just *importing* the heavy libs before it could even reach the daemon — the daemon alone only got it to 5.9s. Lazy imports + daemon together = 0.5s. **If you ever see `knowledge.py search` slow again, first check those two imports are still lazy** (a refactor that hoists them back to module top silently kills the fast path).
- **Supervision:** `~/.config/systemd/user/hermes-kb-daemon.service` (`Restart=always`, enabled at boot). `infra_watchdog.py` auto-restarts it if down — SILENT on clean heal, P1 only if restart fails (pure-acceleration service: in-process fallback means a dead daemon degrades, doesn't break).
- **Transparent fallback:** `knowledge.py search` tries the daemon via `kb_client`, falls back to in-process `search()` on ANY `DaemonUnavailable`. Force in-process for benchmarking with `KB_NO_DAEMON=1`. The daemon is never a hard dependency.

**Quality benchmark already exists — run `knowledge.py eval` before assuming retrieval is "good enough."** There's a 12-query harness (`benchmark_queries.json` in the DB dir, invoked via `knowledge.py eval`). When the question is "how do we improve the KB," the latency number is usually a distraction — measure retrieval QUALITY (are the right facts ≥0.80?) with the eval harness first; quality matters more than shaving cron seconds.

**The benchmark MUST match on `expected_substring`, NOT `expected_id` — IDs are volatile and a stale benchmark fakes a quality regression (proven 2026-06-17).** This bit hard: a baseline `eval` showed **P@5=50%, MRR=0.5** and the obvious read was "retrieval is broken, half the queries fail." It was a LIE. Every "failure" had an `expected_id` that **no longer existed in the DB** — the weekly dedup cron re-chunks facts and assigns NEW ids on every run, so an id-based benchmark self-invalidates after the first dedup. The facts were all still present and retrieving correctly under new ids; only the test's ground-truth pointers were dead. Diagnosis tell: when `eval` fails, check whether the `expected_id`s still exist (`tbl.search().where("id='<id>'")`) BEFORE concluding retrieval degraded. The fix (now in place):
  - Benchmark entries use `{"query": "...", "expected_substring": "<durable unique phrase from the target fact>", "description": "..."}`. Content survives re-chunking; ids don't.
  - `eval_benchmark()` matches `expected_substring.lower() in hit.text.lower()` (rank = first matching hit), backward-compatible with legacy `expected_id`.
  - **True quality after the fix: P@5=100%, MRR=0.92.** Retrieval was excellent the whole time. The lesson generalizes: **any benchmark/test keyed on a mutable surrogate id will rot into false failures — key it on durable content.** When a long-untouched eval suddenly "regresses," suspect the harness before the system.

 every infrastructure question triggers rediscovery — the user teaches you again, you store it again, and the cycle repeats. The fix is the session-start ritual above. If the user ever says "I have to reteach you" or "what happened to this?", the agent failed to query Supabase. Fix immediately.

**The reteaching trap applies to the SKILL too, not just the data (proven 2026-06-08).** Andrew corrected this twice in one session: asked to build a LanceDB auto-retrieval feature, the agent went straight to reading raw `knowledge.py` + gateway source and built a prototype — **without loading THIS skill first.** The skill already documented every finding the agent "discovered": the `auto-index` corpus-wide over-ingest pitfall (which the agent then hit and had to recover from), the `staleness_scan.py` reusable probe (which the agent hand-rolled from scratch in `/tmp`), and `references/auto-retrieval-architecture.md` (the entire cue-driven-retrieval investigation, already written). The lesson: **when a task touches LanceDB / the knowledge store, `skill_view('knowledge-store')` is step ONE — before reading source, before prototyping.** Re-deriving from source what a skill already holds IS the reteaching trap, just aimed at institutional knowledge instead of user data. Generalize: for any task in a documented domain, load + sweep the relevant skills before acting; the skill may already contain the answer, the pitfall, or the reusable script. Note also: the skill library is curated in near-real-time (reference docs appear mid-session), so a skill may already hold work done minutes ago — another reason to load before re-deriving.

**CLI `store --contextualize` yields only the SYNTHETIC-FLOOR prefix, not a real breadcrumb (proven 2026-06-08).** Running `knowledge.py store --contextualize "<fact>"` from the command line produces the generic fallback prefix `"This passage is from cli input."` — NOT a topic-aware situating sentence. The contextual-prefix pipeline derives its situating sentence from document structure (heading breadcrumb + surrounding chunks); a bare CLI string has no structure to anchor to, so it falls to the synthetic floor. Consequence: offloading a hot-memory fact via CLI `--contextualize` gives only a marginal retrieval gain over plain `store`. The REAL contextualization value comes from the fact living in a reference doc (e.g. `infrastructure-summary.md`) that gets chunked via `contextualize-file`/`auto-index`, where the heading context is real. So when offloading topology/infra facts: put the authoritative copy in the reference DOC (chunked, real breadcrumbs) and treat the CLI row as a secondary backstop — don't expect the CLI `--contextualize` flag alone to deliver the prefix benefit.

**Durable reference files beat Supabase for topology.** For complex infrastructure (multi-host, nginx configs, DB locations), write a reference file under `~/.hermes/references/` in addition to Supabase facts. Supabase is semantic search — great for "how do I reset the admin password?" but less reliable for "what's the current state of ALL my servers?" A single markdown file read at session start is stronger than 10 fragmented Supabase facts.

**Indexing coverage silently lags — audit it, don't assume the cron caught everything (proven 2026-06-16).** A retrieval-improvement pass found only **8 of 28** `references/*.md` docs actually had chunks in Supabase, and the every-turn-injected `AGENTS.md` + `SOUL.md` had NEVER been indexed (so their dense rule/procedure content was un-searchable — you could only get it from the raw injected blob, not a targeted `knowledge.py search "write gate procedure"`). The `auto-index` cron is a backstop, not proof of coverage. To audit which docs are missing:
```python
import lancedb, os
df = lancedb.connect('/root/.hermes/knowledge_db').open_table('knowledge').to_pandas()
indexed = set((s or '').split('/')[-1] for s in df['source'].fillna(''))
refs = {r for r in os.listdir('/root/.hermes/references') if r.endswith('.md')}
print('UNINDEXED:', sorted(refs - indexed))
```
Then `contextualize-file` each missing doc (targeted, NOT `auto-index` — see the corpus-wide over-ingest pitfall). **Deliberately SKIP from indexing:** drafts (`*-draft.md`), dated audit logs (`staleness-audit-YYYY.md`), archives, the `honcho-confabulation-blocklist.md` (indexing a doc that NAMES false facts risks retrieval surfacing them as true), and offload audit-logs — these are frozen history/meta, not retrieval targets. AGENTS.md/SOUL.md DO belong indexed but score ~0.76–0.79 (just below the 0.80 B-full floor), so they're manually searchable without B-full double-injecting content that's already in the system prompt — exactly right.

**`stale-check` is mtime-based and misses CONTENT staleness — a recently-touched doc can hold badly-wrong facts (proven 2026-06-16).** `knowledge.py stale-check` reported "0 stale facts" while `infrastructure-summary.md` still described the OLD Hetzner `hil-1` topology (Hermes had migrated to the local Mac mini) and a `2026-06-02-state` snapshot still served "Manifest at localhost:2099" (decommissioned). mtime says "fresh"; the CONTENT is a lie. The tell: a retrieval probe returns a high-scoring hit whose facts contradict the live system. Fix pattern (two distinct cases):
  1. **Live-state reference doc** (`infrastructure-summary.md`): verify against the live system FIRST (`hostname`, `pgrep`, `tailscale status`, port probes — never trust the injected memory block, which itself lagged this session), back up the doc + full-row LanceDB JSON, patch the stale lines in the doc, then PURGE its old chunks and re-index: get the chunk IDs by source basename, `tbl.delete('id IN (...)')`, then `contextualize-file` the corrected doc. Re-`build-graph`. Verify with a probe that the corrected fact now ranks #1.
  2. **Dated snapshot** (`YYYY-MM-DD-state.md` in the Obsidian archive): this is FROZEN HISTORY — do NOT edit the file (deleting a record of a past state is wrong). Instead purge ONLY its LanceDB chunks so retrieval stops serving stale state as current; the archive file stays intact. Verify 0 chunks remain for that source.
  Always: full-row JSON backup before the delete, verify the row-count delta matches expectation, re-`build-graph` after.

**Contextualized vs plain-text coexistence:** The v2.0 schema adds `context_prefix` and `body_hash` columns to the existing table via auto-migration. Old rows get NULL values — they continue to work for search but lack the situating prefix. Re-indexing with `--contextualize` will add new contextualized entries alongside them (different body hashes due to different chunking, so no collisions). Old entries can be deleted manually if desired, but coexistence is harmless — search returns both.

**Bulk-delete by filter (e.g. purging stale source rows):** LanceDB's `tbl.delete()` takes a SQL-like WHERE expression. To delete rows matching specific IDs:
```python
import lancedb
db = lancedb.connect('/root/.hermes/knowledge_db')
tbl = db.open_table('knowledge')
df = tbl.to_pandas()
ids = df[df['source'].str.contains('stale-topic', na=False)]['id'].tolist()
tbl.delete('id IN ("' + '", "'.join(ids) + '")')
print(f'Remaining: {tbl.count_rows()}')
```
This is the safe pattern for purging all rows from a removed reference file — get IDs via pandas filter, then delete with the IN expression. Do NOT delete by `source` regex directly (LanceDB SQL dialect is limited) — get IDs first, then delete.

**`auto-index` is CORPUS-WIDE, not single-file — use `contextualize-file` for targeted reingest (proven 2026-06-08).** To reingest ONE rewritten reference doc (e.g. after correcting `infrastructure-summary.md`), do NOT reach for `knowledge.py auto-index`. Despite the "index changed files since last run" framing, in practice it re-chunked ALL 21 reference docs in one pass and ballooned the store 143 → 348 rows (~205 duplicate chunks: 41 exact-text, 100 by body_hash). The correct tool for one doc is `python3 ~/.hermes/scripts/knowledge.py contextualize-file references/<doc>.md` — it touches only that file.
  **Recovery if you over-ingest (this is the reusable rollback):** the bad batch shares one ingest timestamp window. Find it via `Counter(str(x)[:16] for x in df['stored_at'])`, identify the boundary (the over-ingest rows all have `stored_at >= <this-session-start-epoch>`), then `tbl.delete('stored_at >= <epoch>')` to peel the entire batch back to the pre-call count in one op — far cleaner than trying to dedup-untangle. Then redo the intended stores surgically. The full-row JSON backup (below) is what makes this a non-event: ALWAYS export every row to `references/_archive/lancedb-full-<ts>.json` BEFORE any batch mutation, so any delete is one re-insert from undo.
  General rule: before any cold-store batch op, (1) full-row JSON backup, (2) note the row count, (3) verify the count delta matches expectation on the very next call — catching a 143→348 surprise immediately is what kept it a 2-minute fix instead of a corrupted store.

**GIL cleanup crash is benign:** Iterating LanceDB rows with `tbl.search().limit(N).to_list()` inside a Python `-c` one-liner can produce `Fatal Python error: PyGILState_Release` on interpreter exit. This is a cleanup artifact from PyArrow/numpy GIL teardown — the data was read successfully and the exit code may still be 0. If you see this, extract what you need before the loop ends, or use `tbl.to_pandas()` (processes all rows at once, less teardown contention). The script-file form (`python3 script.py`) is cleaner for large iterations.

**Data quality audit (2026-06-06, post-cleanup: 155 rows):** Three known issues in the live `knowledge` table:
1. **43 rows with empty source** — writes that didn't pass a `source` tag (as of pre-cleanup count; may be lower now). Data intact and searchable, just unattributed. The `knowledge.py store` command uses the `source` kwarg; always pass it.
2. **83 rows with `NaN` body_hash** — pre-v2.0 entries written before dedup was implemented. These can't be dedup-checked but don't cause errors.
3. **9 actual duplicate rows** — all have empty body_hash string (distinct from `NaN`). Appear to be a bug in the capture script when `source` is also empty. Low impact at current scale (169 rows) but will compound over time.
To audit: `python3 -c "import lancedb,pandas; db=lancedb.connect('/root/.hermes/knowledge_db'); df=db.open_table('knowledge').to_pandas(); print(len(df[df['source'].str.strip()=='']),'empty source;', len(df[df['body_hash']=='NaN']),'NaN hash;', len(df[df['body_hash']!='NaN'][df[df['body_hash']!='NaN'].duplicated(subset=['body_hash'], keep=False)]),'dups')" 2>/dev/null`

**Dedup scanning must strip the contextual prefix before scoring (proven 2026-06-08).** The v2.0 situating prefix (`"This passage is from {doc}: {heading}."`) is IDENTICAL across every chunk of one source doc, so a naive cosine dedup scan on the stored `text` inflates similarity between otherwise-distinct chunks — producing a flood of phantom "duplicates" that are really just adjacent sections of one note. Acting on that report (deleting "the less-informative entry") punches holes in a multi-chunk doc's retrieval coverage. The corrected `~/.hermes/scripts/dedup_scan.py` (report-only, never mutates the DB):
  1. **Re-embed prefix-stripped text IN MEMORY for scoring only** — stored vectors are never read or altered (prefix stays in the DB where it helps retrieval). Strip the leading `"This passage is from …"` line, re-encode with the same model, score on real content. In one run this cut 23 phantom pairs → 10 honest ones.
  2. **Tier the output** — HIGH (≥0.95, review for deletion) vs REVIEW (0.85–0.95, usually fine). Don't present a flat list that implies every pair is a dup.
  3. **Annotate `[same-source]` vs `[cross-doc]`** — same-source pairs are almost always normal chunk overlap (keep both); a same-source HIGH can mean a whole doc was ingested twice (real dup); a cross-doc HIGH is a genuinely redundant note worth collapsing. This makes the one interesting signal visible instead of buried.
  General rule for any same-document chunk comparison: a shared boilerplate prefix is noise — score on the body, not the stored text.

**ROOT CAUSE of the duplicates: the overlap chunker manufactures headerless twins that exact-hash dedup can't catch (root-caused + fixed 2026-06-08).** The dedup scan above treats the SYMPTOM; this is the source. Mechanism: `chunk_overlap()` overlaps consecutive chunks by 1 paragraph (`i = max(i+1, j-1)`) for retrieval continuity. Markdown headings are standalone paragraphs (split on `\n\n`). On a SHORT section (heading + one table/list, then the section ends), the overlap produces two chunks that are identical except one leads with the `## Header` line and the other doesn't:
  - Chunk N = `"## Manifest\n\n<table>"`  ·  Chunk N+1 = `"<table>"` (the orphaned content paragraph)
  - `body_hash` is `sha256(chunk_body)` — an EXACT hash. The two strings differ by the heading line → different hashes → `find_by_hash` returns nothing → BOTH stored. The dedup only catches byte-identical re-ingestion (same file re-run unchanged), NOT near-identical overlap twins. Tell-tale signature in the data: paired rows where A has `## Heading`, B doesn't, bodies otherwise identical, `stored_at` ~0.7s apart (same ingest pass).
  **Fix (Option A1 — make the existing dedup work, don't add a second one):** normalize every overlap chunk to lead with its leaf heading, so twins become byte-identical and `body_hash` collapses them at ingest. Two helpers in `knowledge.py`: `_leaf_heading_line(heading_stack)` rebuilds `"## Manifest"` from the deepest `(level, heading)`; `_normalize_chunk_heading(body, heading_stack)` prepends it iff the body doesn't already start with that line. Apply it right where `body = '\n\n'.join(chunk_paras)` is built (covers both the normal and internal-sentence-split paths). No cron-schema change, no second dedup pass — it makes the `body_hash` mechanism you already have actually fire.
  **Verify on a THROWAWAY harness before touching the live DB** — the fix is preventive (future ingests), so the live table needs no re-ingest. Load old + new `knowledge.py` as separate modules via `importlib` (copy the `.bak` to a temp `.py` first — importlib can't load a `.bak-*` filename, it needs a `.py` extension), run BOTH `chunk_overlap()` on the REAL source docs that produced the dupes (`~/.hermes/references/infrastructure-summary.md` etc.), and assert: (a) new headerless-near-twin count → 0, (b) zero content lost (every old chunk's core still present in the new corpus). One run: 5 near-twins across 3 docs → 0, no content loss. Only after that passes is the chunker change safe.

**Matching a query against the SKILL corpus must read `tags:` and split hyphens — name+description alone mis-ranks (proven 2026-06-09).** When semantic/keyword-matching a task against on-disk `SKILL.md` frontmatter (e.g. a skill-review/auto-suggest matcher), two defects silently surface the WRONG skill:
  1. **Reading only `name:` + `description:` ignores `tags:`** — where the load-bearing domain terms live. `knowledge-store`'s description says "LanceDB-backed" but its discriminating signals (`lancedb`, `semantic-search`, `vector-db`) are ONLY in `tags:` (under `metadata.hermes.tags`, several lines past `description:`). A "build a lancedb prototype" query lost to `gateway-platform-setup` because the matcher never read the tags. Fix: parse `tags:` too — and scan ~40 frontmatter lines, not ~25, since tags sit in the metadata block well below description.
  2. **Treating `-` as a word char glues compound tags into unmatchable tokens** — `lancedb-backed` / `semantic-search` tokenize as ONE token, so a query word `lancedb` never matches. Fix: hyphens are SEPARATORS in the tokenizer; `semantic-search` → `{semantic, search}`.
  3. **Weight tags+name above description.** A curated tag or the skill name is a far stronger domain signal than an incidental description word — weight them ~3× (require ≥1 tag/name hit, OR ≥3 description hits, to qualify). Flat overlap counting lets a skill with a few coincidental description words outrank the true domain match.
  Lock the fix with a calibration fixture set (the motivating query must surface the right skill) that runs BEFORE any future edit to the matcher — a threshold/weight tweak silently regresses ranking otherwise.

**Heading context stability:** The overlap chunker anchors heading context to the FIRST paragraph in each chunk, not the last. Using the last paragraph is wrong — a high-level heading like "## Cron Jobs" resets the breadcrumb from "Infrastructure > Routing > DB Topology" to "Infrastructure > Cron Jobs", losing the earlier structure. First-paragraph anchor is the most stable descriptor of where the chunk begins. Do not "fix" this to track the deepest or last heading — it's intentionally first.

**Retrieval pipeline (v3.0 — implemented):** `~/.hermes/references/retrieval-pipeline-techniques.md` documented 5 post-retrieval scoring techniques cherry-picked from the memory-lancedb-pro OpenClaw plugin. Items 1-4 (LRU embedding cache, priority/recency scoring, BM25 hybrid fusion, MMR diversity) are now LIVE in `search()` as of v3.0. The knowledge-graph layer (from the GBrain cherry-pick, `~/.hermes/references/gbrain-cherry-pick.md`) is also live via `build-graph`/`graph-query`. Item 5 (cross-encoder rerank, ~80MB model download) remains the only un-implemented future option — gate it behind a flag if ambiguous-query quality ever needs it.

**Retrieval: B-full auto-RAG is LIVE (since 2026-06-10; doctrine updated 2026-06-11 — supersedes the old "cue-driven only" rule).** A gated core patch in `gateway/run.py` (`_bfull_retrieve`, healed by patch_guard via `bfull-helpers.golden.py` + `bfull-injection.golden.py`) semantic-searches Supabase on each incoming message and injects hits scoring **≥0.80** into context. Verify live before relying on it: `grep -c '_bfull_retrieve' /usr/local/lib/hermes-agent/gateway/run.py` (≥1 = installed). Consequences:

**⚠️ B-full runs ONLY in the gateway/Telegram path, NOT in the WebUI (proven 2026-06-18).** `_bfull_retrieve` is wired into `gateway/run.py` — the Telegram/CLI message handler. The Hermes WebUI uses a SEPARATE codepath (`hermes-webui/api/streaming.py`) that has **zero** b-full integration: `grep -c bfull api/streaming.py` → 0. Hard evidence: querying the session DB for the injection marker — `SELECT COUNT(*) FROM messages m JOIN sessions s ON m.session_id=s.id WHERE m.content LIKE '%Cold-store auto-retrieval%' GROUP BY s.source` — returns 7 for `telegram`, **0 for `webui`**. This is the dominant reason "the WebUI me feels dumber": on Telegram every message gets relevant Supabase facts auto-injected before the model sees it; on WebUI the model gets only the frozen MEMORY.md/USER.md snapshot + whatever it explicitly tool-calls. **The same hot/cold memory files load fine in both** (verified: `MemoryStore.load_from_disk()` reads the same `~/.hermes/memories/*.md` regardless of surface) — the asymmetry is purely the per-turn RAG injection. **Diagnostic when "WebUI seems less aware than Telegram":** it's almost never a memory-loading bug — check (1) is the b-full marker present in webui sessions (it won't be), (2) is the KB daemon socket alive (orphaned-socket pitfall above), (3) did the offload cron strip behavioral entries from MEMORY.md that the WebUI snapshot then froze. **Fix for the asymmetry:** mirror the `run.py` injection into `streaming.py` — inject `_bfull_retrieve(message_text)` into the context prompt before each WebUI turn (same helper, imported from the agent package). Gate it as a core/webui patch; until then, WebUI sessions must lean harder on explicit `knowledge.py search` tool calls.

Consequences:
  - The old hard rule "an offloaded fact with no hot pointer is effectively forgotten" is now SOFT. The binding constraint is **retrievability at the 0.80 floor**, not pointer coverage. A fact that probes ≥0.80 on realistic query phrasings can be fully trimmed from MEMORY.md with no pointer.
  - **Probe-then-trim protocol (the aggressive-offload procedure):** per hot fact: (1) write it into the topical reference doc under a real heading and `contextualize-file` it; (2) probe with 2–3 realistic query phrasings via `python3 ~/.hermes/scripts/offload_probe.py` (NOT in this skill dir — lives beside knowledge.py) or manual `knowledge.py search`; (3) ALL phrasings ≥0.80 → delete the hot line entirely; ANY marginal → keep a one-line cue. Never trim blind.
    `offload_probe.py` usage (built + proven 2026-06-11): `probe --fact "..." [--queries q1 q2 q3]` (omitting --queries auto-generates 3 deterministic phrasings — high-info tokens, literal identifiers, first content words — and prints them for realism judgment) · `scan` (parses MEMORY.md on `§` separators, skips pointer-style entries containing "knowledge.py", reports TRIM-SAFE/POINTER/KEEP-HOT per entry + projected % after trim, reads the live cap from config.yaml) · `--json`. READ-ONLY against both stores; ~13s for a full scan (embedding model loads once via importlib of knowledge.py). First real run: 8 probed → 3 TRIM-SAFE (528 chars, 80%→64%), executed and verified.
    **API fact that bit during the build:** `knowledge.search()` result dicts carry the relevance score in the **`score`** field (plus `id`, `text`, `tags`, `priority`, `source`, `stored_at`, `context_prefix`) — NOT `_relevance_score`. Anything post-processing search results must read `score`.
  - **Store query-shaped:** include literal identifiers (config keys, ports, hostnames) AND aliases in the stored text — v3.0's adaptive BM25 weighting rewards exact tokens. Set `KNOWLEDGE_PRIORITY=high` on offloaded hot facts; run `build-graph` after each doc pass.
  - **B-lite remains the FALLBACK doctrine** whenever B-full is absent (fresh install, un-healed `hermes update`, patch_guard reporting a missing anchor): on infra/config/topology-topical turns, run `knowledge.py search` before answering, trust only hits ≥0.80. The pointer model below still applies in that state.
  For the original investigation (why a clean hook can't do per-turn injection without a core patch, latency/relevance findings, B-lite vs B-full decision), see `references/auto-retrieval-architecture.md` + `scripts/auto_retrieve_proto.py`.

**B-lite — the FALLBACK TRIGGER (applies when B-full is absent — see live-check above).** When BOTH hold:
  1. the current turn is clearly **infra / memory / config / device / topology-topical**, AND
  2. the answer could depend on a **stored fact** (a host spec, port, model string, past decision, tool quirk, device map),
then **run `knowledge.py search "<topic>"` BEFORE answering** — don't answer from assumption first. Reading the result is the cue-driven retrieval the pointer model relies on; a topical turn IS a cue, even with no hand-written pointer.

- **The floor is judgment, NOT a flag.** `knowledge.py search` has no `--floor` arg — it prints top-K hits with their scores (`[0.86] …`). Apply the floor yourself: **trust only hits scoring ≥ 0.80** as authoritative cold facts. Treat 0.80 as the precision line proven by the proto — below it the embedding space is dense noise (junk queries score ~0.67), not signal.
- **Silent when nothing clears 0.80.** If no hit reaches the floor, drop retrieval and answer normally. Do not surface or lean on sub-floor hits — that's the noise B-full would inject and B-lite deliberately filters at the reasoning step.
- **Why this and not B-full:** ~90% of auto-RAG's value (cold facts surface without depending on a perfect breadcrumb) at none of the cost — no core patch, no per-turn latency tax, no context noise, no per-turn token tax. Paid once as tool output on the minority of topical turns, read-and-filtered, never re-injected.
- **Reliability honesty:** B-lite's one failure mode is *silent omission* — the agent answers without firing the search on a soft-topical turn. Three reinforcing layers cover that gap: (1) hot-tier POINTERS cue the lookup, (2) the **skill-review checkpoint** nudges loading this skill on complex sessions, (3) this trigger doctrine. Any one firing catches the fact. If Andrew ever says "what happened to X?" or "I told you this," a topical turn slipped the trigger — fix the reflex, and log it as a crossover signal (see below).
- **Crossover watch (when B-full's gated core patch finally earns its fragility):** NOT row count — it's *pointer-coverage decay*. Watch three signals: rising **reteach rate** ("what happened to X?"), climbing **orphan ratio** (cold facts with no hot pointer — instrumented in `infra_watchdog`), and a dirtying **noise floor** (re-run `auto_retrieve_proto.py`; junk queries clearing 0.80). B-full is justified only at ~800–1,500 rows AND with the cross-encoder reranker (Item 5) already in place AND recurring reteach events — until then, the cheaper fix is always Stage 2 (pointer-on-every-offload, in `memory-discipline`).

**Orphan-ratio instrument — measuring pointer-coverage decay (built 2026-06-09).** The crossover signal above is now measurable, not guessed. `~/.hermes/scripts/orphan_ratio.py` counts cold rows with NO hot-tier cue (orphan facts): `orphan_ratio.py` (human report) · `--json` · `--quiet` (just the float). Key design points future agents must know:
  - **Reads LanceDB DIRECTLY (`lancedb.connect`), not via `knowledge.py`** — so it does NOT trigger the ~2s embedding-model load. This is what makes it cheap enough to run from the 15-min `infra_watchdog` (§8). Importing `knowledge.py` for a count-only job is the trap; the orphan check needs the table, not embeddings.
  - **A row is "cued" (not orphan) if ANY of:** its 8-char id is in MEMORY.md, its `source` basename is named in MEMORY.md, or ≥2 of its salient terms appear in MEMORY.md (a plain hot mention or a `knowledge.py search "<q>"` pointer query both count).
  - **Excludes frozen-history rows by `source` pattern** (`state`, `snapshot`, `changelog`, `user-model`, `peer-card`, `session`, `-archive`, `backup`) — those are never meant to be cue-retrieved, so scoring them as orphans inflates the number meaninglessly. The baseline is intentionally noisy (reference-doc chunks still count) — do NOT over-tune the filter chasing a prettier number; a stable-but-noisy baseline still detects the TREND, which is all the watchdog needs.
  - **Baseline lives in `~/.hermes/references/orphan-ratio-baseline.json`** — ALWAYS read the file, never trust a number written here (initial 2026-06-09 recording was 50.3% (76/151); re-baselined same day to 25.0% (12/48) after a prune+pointer pass).

**Correcting a stale row = DELETE + RE-STORE, never in-place text edit.** Editing only the `text` column leaves the embedding vector pointing at the OLD content — retrieval keeps matching the dead premise. Procedure (proven 2026-06-09): (1) read the old row, note its priority/tags and anything still true to carry over; (2) `tbl.delete('id IN ("<id>")')`; (3) re-store the corrected text via `scripts/knowledge.py store` (env `KNOWLEDGE_TAGS`, `KNOWLEDGE_PRIORITY`) so it re-embeds; (4) verify with a retrieval probe — corrected fact should be the top hit ≥0.80; (5) re-run the dead-term scan to confirm zero stale current-state claims remain. For 1.000-similarity same-source duplicates: read BOTH rows first, delete the chunk from the OLDER doc-version ingest, keep the newer. `infra_watchdog` §8 alerts only on **≥15pt RISE above baseline** (a trend-delta alarm, see general pattern below), never an absolute threshold — and is wrapped so a probe failure can't break the watchdog chain.
