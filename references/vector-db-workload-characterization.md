# Vector / Memory DB Workload Characterization

**Purpose:** Characterize the live memory/vector workload to inform vector-DB selection.
Priority being evaluated: extreme efficiency with **disk-offloading** (index resident on
SSD, not RAM) + high-quality context/memory retrieval.

**Method:** All numbers below are from direct probes on the live host (read-only).
Source command noted per item. Estimates flagged `[ESTIMATE]`.

**Date captured:** 2026-06-19
**Host:** `andrew-Macmini`

---

## ⚠️ Premise correction

The box is a **Mac Mini running Linux**, not macOS — kernel `7.0.12-1-t2-noble`, x86_64
(T2 Intel Mac). This is a **Linux** tuning problem (`/proc`, `free`), not Metal/macOS.
32 GB hardware → **31 GiB usable**.
*Source: `uname -a`, `free -h`*

---

## 1. Store scale

| Metric | Value |
|---|---|
| LanceDB `knowledge` table rows | **491** |
| On-disk size (`knowledge_db/`) | **295 MB** |
| Vector dimensionality | **768** |
| Data fragments | 6,400+ files in `/data/` |
| Version manifests | **1,928** |
| Growth rate | `[ESTIMATE]` — data files span 2026-06-04 to 2026-06-19 (~15 days); 491 rows / 15 days ≈ **~33 records/day** |

*Source: `lancedb.count_rows()`; `du -sh`; `ls _versions/ | wc -l`; `ls data/ | head`*
Path: `/root/.hermes/knowledge_db/knowledge.lance` *(the real store — not the nested profile copy)*

---

## 2. Embedding — 768-dim local sentence-transformer

- Stored vector length = **768** (measured from a stored row).
- Model: `sentence-transformers/all-mpnet-base-v2` (768-dim) is the best-fit default in
  the agent code. **NOT** all-MiniLM-L6-v2 (that's 384, doesn't match). `[ESTIMATE on exact model]`
  — 768 also fits bge-base / gte-base / nomic-embed; mpnet is the strongest 768 candidate present.
- No GPU / Ollama embedding service running (nothing on :11434).

*Source: vector dim from LanceDB; `grep` of `/usr/local/lib/hermes-agent`; no :11434 response*

---

## 3. RAM budget — ~20–22 GB headroom

| Metric | Value |
|---|---|
| Total RAM | **31 GiB** |
| Available | **24 GiB** |
| Used | 7.2 GiB |
| buff/cache | 22 GiB |
| Swap | **essentially untouched** (4 KiB / 2 GiB) |
| Hermes footprint | 2 Python procs ~4.9% + 4.3% MEM ≈ **2.9 GiB combined** |
| Realistic DB ceiling before pressure | **~20–22 GiB** |

*Source: `free -h`, `ps aux` sorted by %MEM*

---

## 4. Concurrency — multi-reader by design

- **9 profiles:** `ha-bot, executor, swarm-synthesizer, swarm-verifier,
  swarm-worker-a/b/c, pre-update-2026-06 ×2`.
- Delegation: `max_concurrent_children: 12`, `max_async_children: 3`,
  `max_spawn_depth: 2`, orchestrator enabled.
- Real use = **several concurrent readers** (swarm workers + executor), not a single reader.

*Source: `ls profiles/`; `config.yaml` delegation block*

---

## 5. Retrieval shape — hybrid (vector + BM25) on LanceDB; dialectic on Honcho

- **LanceDB:** full-text **BM25 indices** built (`part_0_invert/docs/tokens.lance`
  inverted indices present alongside the vector index) → **hybrid keyword + vector**.
- **Metadata filtering available:** schema carries `tags, priority, source, context_prefix`.
- **Honcho:** adds LLM **dialectic reranking** — `recallMode: hybrid`,
  `dialecticReasoningLevel: low`, `dialecticCadence: 2`.

*Source: `_indices/*` inverted-index files; LanceDB columns; `honcho.json`*

---

## 6. Postgres / Honcho — Postgres runs, but it's not ours, and NO pgvector

| Item | Finding |
|---|---|
| Running Postgres | **`firecrawl-nuq-postgres-1`** — PostgreSQL **17.9**, port 5432 (container net 172.19.0.6) |
| Installed extensions | `pg_cron`, `pgcrypto`, `plpgsql` only |
| pgvector | **NOT installed** and **NOT in `pg_available_extensions`** |
| Other containers w/ pgvector | none |
| Honcho deployment | **CLOUD** (`app.honcho.dev`) — `honcho.json` has **no `baseUrl`**, so it does **not** use this local Postgres |

*Source: `docker ps`; `psql \dx`; `pg_available_extensions`; honcho.json*

---

## Backends behind "memory" + recall split

| Backend | Role | Recall share |
|---|---|---|
| **Honcho (cloud)** | Primary memory provider (`config.yaml memory.provider: honcho`), auto-injected every turn | majority `[ESTIMATE]` |
| **LanceDB (local)** | Knowledge / cue-store, explicit lookups | minority `[ESTIMATE]` (2 rows today) |
| **Local flat config** | MEMORY.md / USER.md injected every turn (3000 / 2250 char caps) | not a queried DB |

*Fractions are `[ESTIMATE]`: no per-backend hit counter is instrumented; based on config roles.*

---

## "Offloading" definition (confirmed)

Means: **index resident on SSD, not RAM** — memory-map the index from disk so a large
corpus doesn't consume RAM. **NOT** offloading embedding compute or model layers.

---

## Headline for DB selection

- Actual corpus = **491 rows / 295 MB / 768-dim**, growing ~**33 records/day**.
- At ~33/day, 1-year projection ≈ **12,500 rows / ~7 GB** — still comfortably small for any ANN engine.
- **~22 GiB RAM free**; swap untouched.
- **No pgvector anywhere.**
- LanceDB is already **SSD-resident (mmap)** and satisfies the disk-offload requirement at current and near-term scale.
- The 1,928 version manifests vs 491 rows indicate heavy compaction churn — may be worth a `compact_files()` pass.

**Open question for the decision:** what target corpus size is being provisioned for?
That determines whether LanceDB's mmap suffices or a dedicated disk-ANN engine earns its keep.

### Candidate next steps (not yet run)
- Stand up pgvector in a throwaway container to benchmark against LanceDB at target scale.
- Measure LanceDB mmap RSS under concurrent swarm-reader load.
- Confirm exact embedding model (resolves the one `[ESTIMATE]`).
