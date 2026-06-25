# Headroom — Cherry-Picked Compression Patterns

**Source:** [chopratejas/headroom](https://github.com/chopratejas/headroom) v0.22.3, Apache 2.0, reviewed 2026-06-16 (29.7k★, 1,601 commits, actively maintained).
**Upstream artifact NOT installed.** Why: the proxy is a single point of failure for all Anthropic API traffic (if it crashes, the agent loses model access), and `headroom learn` autonomously writes to AGENTS.md/CLAUDE.md — an auto-steering red flag we don't accept from third-party tooling. The compression *ideas* are durable; the standing process is not worth the risk today. A conditional flip-to-install path is recorded in `references/evaluated-tools-log.md` (Docker proxy on localhost + the native `plugins/hermes/headroom_retrieve` plugin only, `HEADROOM_EXCLUDE_TOOLS=read_file,headroom_retrieve`).

Two patterns extracted, mapped onto Hermes tooling.

---

## 1. CacheAligner — stable-prefix discipline for KV cache hits

**Upstream idea:** Anthropic (and OpenAI) bill cached prompt-prefix tokens at a large discount and serve them faster, but the cache only hits when the *leading bytes* of a request are byte-identical to a prior request. Headroom's `CacheAligner` stabilizes prefixes so provider KV caches actually hit. Prepending volatile data (timestamps, session IDs, request counters, ISO datetimes) to otherwise-repeated content silently busts the cache on every call.

**Mapped onto Hermes (no install — this is a framing discipline):**
- When emitting repeated tool-output headers, status banners, or system-prompt-adjacent blocks, keep the **first N characters byte-stable across calls**. Do NOT prepend per-call timestamps, PIDs, or counters to the *front* of content that otherwise repeats — put volatile fields at the END or in a trailing metadata line.
- Applies to: cron job output framing, watchdog alert templates, any reference block injected every turn, and skill/reference note headers that get re-read.
- This is free cost savings — no dependency, just ordering hygiene. The win scales with how often the prefix repeats (system prompt, memory blocks, recurring tool outputs).

**Verification when applied:** Anthropic API responses report `cache_read_input_tokens` — a non-zero value on a repeated request prefix confirms the cache hit. If it's zero on content you expected to be cached, something volatile leaked into the prefix.

---

## 2. CCR (Compress-Cache-Retrieve) — marker + on-demand retrieval for large tool outputs

**Upstream idea:** Instead of dumping a 10K-token tool result into context (or truncating it and losing data), Headroom replaces it with a short marker (`[1500 items compressed to 50. hash=abc123]` or `<<ccr:abc123>>`), caches the full original locally with a TTL, and exposes a `headroom_retrieve` tool so the model can pull back the original — or a BM25-filtered slice of it — only when it actually needs the detail. Originals are never silently deleted; retrieval is reversible.

**Why it matters for us:** We hit this exact problem repeatedly — `web_extract` on long pages times out the aux-model summarizer, and large terminal/grep dumps flood context. Our current mitigations are **truncation** (lossy — the bytes are gone) and **aux-model summarization** (lossy + slow + can time out). CCR is strictly better: lossless, retrievable, and the agent decides what slice it needs.

**Mapped onto Hermes (pattern, not the upstream API):**
- **Native equivalent today:** `execute_code` already lets us fetch-then-reduce *before* content enters context — the same shape as CCR's "compress before it reaches the LLM." For a large `web_extract`/`search_files`/terminal result, process it inside `execute_code` (filter, grep, extract the relevant section) and print only the reduced slice. The full result never enters the conversation.
- **For the cache-and-retrieve half:** write the full original to a temp file (`/tmp/` or `~/.hermes/references/.cache/`), surface a one-line marker with the path + a content summary, and read back only the needed section with `read_file(offset, limit)` when required. This is CCR done with native file tools — no proxy, no SPOF, no TTL expiry surprises.
- **Self-hosted Firecrawl escape hatch** (already stood up, port 3002): for pages that time out the cloud summarizer, `/v1/scrape` with `formats:["markdown"]` to a temp file, then `read_file` in sections — full content, no summarizer in the loop. This is the CCR pattern applied to the web stack and is already the documented fallback in `third-party-tool-evaluation`.

**Pitfall (from upstream's own README):** if retrieved originals travel back through the compressor on the next turn, they get re-compressed into a fresh marker → infinite marker→retrieve→marker loop. The native file-cache approach avoids this entirely (a `read_file` result isn't re-compressed). If the proxy is ever installed, the exclusion list (`read_file,headroom_retrieve`) is mandatory.

---

## Net

Both patterns are usable today with zero footprint:
1. **Prefix hygiene** → cache-discount cost savings, just ordering discipline.
2. **Compress-before-context** → `execute_code` reduction + temp-file caching replaces lossy truncation/summarization for large tool outputs.

The upstream tool is a credible flip-to-install if token spend on large tool outputs ever justifies a standing proxy — but the surgical install (Docker proxy + Hermes plugin only, no `headroom learn`, no agent wrap) is the only shape worth considering.
