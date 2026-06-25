# Retrieval Pipeline Techniques for knowledge.py v3.0

> Cherry-picked from [win4r/memory-lancedb-pro-skill](https://github.com/win4r/memory-lancedb-pro-skill) (MIT) on 2026-06-03.
> The *retrieval pipeline patterns* were absorbed into Hermes' knowledge-store roadmapping — the upstream artifact itself was NOT installed (3-commit documentation skill for a TypeScript OpenClaw plugin; wholly incompatible with Hermes).

## The pattern

memory-lancedb-pro applies 6 post-retrieval scoring stages (Recency Boost, Importance Weight, Length Norm, Time Decay, Hard Min, MMR diversity) on top of hybrid vector+BM25 search with cross-encoder reranking. The insight: **raw LanceDB cosine distance is a weak relevance signal — post-processing the top-K with lightweight scoring math produces measurably better results without external API calls.**

## Hermes mapping (actionable, prioritized)

### 1. Priority/recency scoring (drop-in — columns already exist)
Our `store()` writes `priority` and `stored_at` to every row, but `search()` never reads them back for scoring. Two trivial multipliers:

```
recency_boost = exp(-ageDays / 14) * 0.10           # add to score
importance = 0.7 + 0.3 * importance_score           # multiply score
```

Where `importance_score` = `{critical: 1.0, high: 0.7, normal: 0.5, low: 0.3}`. This costs zero additional infrastructure and makes `priority` actually matter. Apply after LanceDB vector search, before returning results.

### 2. LRU embedding cache (one dict, zero deps)
`embed()` re-encodes text on every invocation — including repeated queries. A simple `{sha256(text): vector}` dict with 256-entry cap and 30min TTL eliminates redundant embedding work. Pure Python, no dependencies, transparent to all callers.

### 3. BM25 keyword search (LanceDB FTS)
LanceDB natively supports full-text search (FTS) indices via `tbl.create_fts_index("text")`. Adding a BM25 path in parallel with vector search fixes the "exact config key name search fails" problem — `search("JINA_API_KEY")` would match keyword hits that the embedding vector misses entirely. Fuse with RRF: vector-score-dominant, BM25 hit adds a 15% confirmatory boost.

### 4. MMR diversity dedup (post-hoc filter)
When top-K results are near-duplicates (cosine similarity > 0.85), deprioritize the later one. Prevents returning 5 variants of the same fact. Implemented as a greedy pass over `search()` results — no model needed, just the existing vectors.

### 5. Cross-encoder rerank (future: model download)
Re-rank top-20 results with a local cross-encoder (`cross-encoder/ms-marco-MiniLM-L-6-v2`, ~80MB). Blend: 60% cross-encoder score + 40% original distance. Higher compute cost but significant quality gain for ambiguous queries. Gate behind a flag — not worth it for every search.

## When to apply (gates)

- **Priority/recency (#1)**: always-on — applies to all `search()` calls, no config needed
- **LRU cache (#2)**: always-on — transparent performance win
- **BM25 (#3)**: most valuable for exact-match queries (config keys, error strings, CLI commands)
- **MMR (#4)**: when top_k > 3 and results look repetitive
- **Cross-encoder (#5)**: gated behind `--rerank` flag or `top_k > 10` — unnecessary for most lookups

## Caveats / dependencies

- Priority scoring requires `stored_at` to be meaningful (it is — populated on every `store()`)
- BM25 depends on LanceDB FTS support (available in LanceDB 0.33.0, which we run)
- Cross-encoder needs `pip install sentence-transformers` for the reranker model (install gate: 80MB download, adds ~2s to search latency)
- None of these require new API keys, external services, or schema migrations — all work on the existing `knowledge` table
