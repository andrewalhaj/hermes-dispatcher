# Contextual Retrieval Pattern (Contextual-Prefix Chunking)

**Source:** [AgriciDaniel/claude-obsidian](https://github.com/AgriciDaniel/claude-obsidian) — MIT · 2026-06-03
**Upstream:** NOT installed. Skipped — Claude Code plugin, env-incompatible with Hermes, and core premise (AI second brain + Obsidian vault) overlaps 1:1 with Hermes' native memory tier (Hot/MEMORY.md + Honcho + Cold/Obsidian + Supabase knowledge-store).
**Cherry-picked:** The contextual-prefix chunking technique from `scripts/contextual-prefix.py`.

## The Technique

Per **Anthropic's Sept 2024 Contextual Retrieval research** ([link](https://www.anthropic.com/news/contextual-retrieval)): before embedding a chunk, prepend an LLM-generated 1-2 sentence context blurb that situates the chunk within its source document. The "contextualized text" (prefix + raw chunk) is what gets embedded and BM25-indexed.

Anthropic measured **35–49% failure reduction** vs embedding plain chunks.

### Three-tier prefix generation (chosen per-run automatically)
1. **Tier 1 — Anthropic Haiku 4.5** (~$12/1000 docs): prompt-cached page body in system, chunk in user message, output 1 sentence
2. **Tier 2 — Claude CLI subprocess** (free, uses CC subscription): same logic via `claude -p`
3. **Tier 3 — Synthetic fallback** (free, local-only): page title + first sentence of body. Hermetic, deterministic, provides modest BM25 lift via title-word re-injection

### Key implementation detail
Chunks are processed **sequentially** within a page so Tier 1's Anthropic prompt caching works: chunk 0 warms the prefix, chunks 1..N read from cache. Parallelizing zeros every cache read.

## Mapping onto Hermes

Hermes' knowledge-store (`python3 ~/.hermes/scripts/knowledge.py search "q"`) currently embeds plain document chunks into Supabase. The upgrade path:

1. **Chunk with prefix generation.** When ingesting a document into Supabase, first run it through a contextual-prefix pass. Use Manifest's Haiku route (already cost-routed via Manifest LB) for Tier-1 quality; fall back to manifest-routed Claude if Haiku unavailable; synthetic as floor.

2. **Index the contextualized text.** Replace the plain chunk text in Supabase with `{prefix}\n\n{raw_chunk}`. The vector embedding and BM25 tokenization now operate on the contextualized text. Title-keyword re-injection means even the synthetic floor measurably improves recall.

3. **Cost discipline.** The upstream splits prefix generation from retrieval — only run prefix generation once at ingest. Haiku cost ~$12/1000 docs is affordable and absorbed into Manifest's existing provider routing. Synthetic floor ensures zero cost with modest gain if Haiku is down.

4. **Cache invalidation.** Store `sha256(source_document)` per chunk. On re-ingest, only regenerate prefixes for chunks whose source document hash changed — same pattern as upstream's `body_hash` / `page_body_hash` mechanism.

## Why this matters
The cold tier (Supabase knowledge-store) is Hermes' retrieval backbone for cross-session institutional knowledge. A 35–49% failure reduction on retrieval means measurably fewer "I don't remember that" / hallucinated answers — directly addresses the factual-discipline skill's mandate.
