# GBrain Cherry-Pick — Concepts for Hermes Memory Architecture

> Cherry-picked from [garrytan/gbrain](https://github.com/garrytan/gbrain) (MIT, 21k★) on 2026-06-04.
> Lifecycle framework from [aristoapp/awesome-second-brain](https://github.com/aristoapp/awesome-second-brain) (Apache-2.0).
> **Upstream NOT installed.** GBrain is Bun/TypeScript + Postgres+pgvector — incompatible with the Hermes Python stack. These are *concepts* absorbed into our roadmap, not code.

GBrain is Garry Tan's production agent brain: 147k pages, 25k people, 5k companies, 66+ cron jobs, used 16+ hrs/day. It's the most mature single-user agent-brain in the wild. Four concepts are worth adopting; the rest is either already in our roadmap or vendor-locked.

---

## What we already have (no action)

GBrain's hybrid search (vector + BM25 + RRF) and post-retrieval scoring are **already documented** in `retrieval-pipeline-techniques.md` as the knowledge.py v3.0 roadmap. GBrain confirms the approach at scale — it's not new to us. Our `knowledge.py` v2.0 already does contextual chunking with Haiku situating prefixes (the Anthropic contextual-retrieval pattern), which GBrain does NOT appear to do. We're ahead on chunk contextualization.

---

## Cherry-pick 1: Knowledge graph from wikilinks (zero LLM cost)

**The concept.** GBrain extracts *typed edges* from markdown frontmatter and wikilinks — no embedding, no LLM call. Multi-hop traversal (`gbrain graph-query`) then walks those edges. Reported **+31.4 P@5** over vector-only retrieval.

**Why it fits Hermes.** Our `llm-wiki` skill already produces wikilinked Markdown with YAML frontmatter. The links exist; we just don't index them as a graph. A graph layer would let "what connects Manifest to the scheduler outage?" traverse relationships that cosine similarity misses entirely.

**Adoption path (no new infra).**
- Parse `[[wikilink]]` and frontmatter `related:`/`tags:` fields from the wiki + references dirs.
- Build an adjacency list in SQLite (we already have it) — `(source_page, edge_type, target_page)`.
- Add a `graph_neighbors(page, hops=2)` helper to `knowledge.py`.
- Fuse graph-adjacent pages into search results as a confirmatory boost, same pattern as the planned BM25 fusion.
- **Cost: zero LLM calls, zero new dependencies, one SQLite table.**

---

## Cherry-pick 2: Synthesis with explicit gap analysis

**The concept.** `gbrain think` returns retrieval-backed prose *plus* a "what the brain doesn't know" section — it names the gaps in its own knowledge rather than confabulating over them.

**Why it fits Hermes.** This is the anti-fabrication principle (already in SOUL.md) made into a retrieval output format. When I synthesize from the knowledge store, I should explicitly flag what wasn't found, not paper over it.

**Adoption path.** Skill-level, not code. Add to the `knowledge-store` skill: after a synthesis query, emit a "Gaps" line listing query terms with zero or weak hits. Reinforces "I don't claim what I couldn't see."

---

## Cherry-pick 3: Skills as evaluable artifacts (SkillOpt pattern, lite)

**The concept.** GBrain's SkillOpt treats `SKILL.md` as a trainable parameter: edit primitives → validation gates → held-out evaluation → A/B adversarial suites before a skill change is committed. Skills self-improve against benchmarks.

**Why it fits Hermes — partially.** Full SkillOpt is overkill for a single-user system. But the *safety pattern* is valuable: right now `skill_manage(action='patch')` commits immediately with no validation gate. A lightweight version: before committing a skill edit, run the skill's stated "verification steps" against a known case and confirm it still passes.

**Adoption path (lite).** Document-only for now. Add a "validation gate" convention to `skill-authoring-guidance.md`: every skill with executable steps should carry a `## Self-test` block (a known input + expected output) that can be run before and after an edit. No automated harness yet — just the convention and a manual check.

---

## Cherry-pick 4: Durable subagents (Minion pattern) — note, don't build

**The concept.** GBrain's Minion fleet persists subagent job state in Postgres: crash-safe, budget-tracked, rate-leased, AIMD adaptive concurrency, error classification, self-fix for prompt/tool errors. Jobs survive process death.

**The Hermes gap.** Our `delegate_task` subagents run *synchronously inside the parent turn*. If the parent is interrupted (user sends a new message, /stop), children are cancelled and their work is discarded. We have no durable subagent primitive.

**Why NOT to build it now.** This is a large architectural change. We already have two partial mitigations:
- `cronjob` with `context_from` chaining — durable, scheduled, survives restarts.
- `terminal(background=True, notify_on_complete=True)` — durable for shell work.

**Adoption path.** None immediately. Logged as a known limitation. If durable multi-step delegation becomes a recurring need, the right Hermes-native answer is cron-job chaining, not a Postgres Minion fleet. Revisit only if the cron pattern proves insufficient.

---

## Framework borrowed: the Second-Brain Lifecycle

From awesome-second-brain — a clean evaluation lens for any memory decision:

| Stage | Question | Hermes status |
|---|---|---|
| **Collect** | How does context enter? | Sessions (auto), llm-wiki (manual), knowledge.py store (manual), Honcho (auto-observed) |
| **Organize** | Raw context → structured knowledge? | Partial — chunked + contextualized in Supabase; **no graph** |
| **Evolve** | Does memory improve & shed stale data? | Partial — morning-audit + memory-discipline skills; KB dedup cron; manual |
| **Use** | Right context surfaces on demand? | session_search (FTS5), knowledge.py (vector), MEMORY.md (always-on) |
| **Govern** | Inspect, correct, delete, scope, trust? | Strong — all Markdown/SQLite, fully inspectable, per-profile scoped |

**Weakest stage: Organize** (no graph layer) — which is exactly what cherry-pick 1 addresses.

---

## Summary verdict

| Concept | Verdict | Cost |
|---|---|---|
| Hybrid search (vector+BM25+RRF) | Already roadmapped | — |
| Contextual chunking | Already ahead of GBrain | — |
| **Knowledge graph from wikilinks** | **Adopt** — highest value | Zero LLM, 1 SQLite table |
| **Synthesis gap analysis** | **Adopt** — skill convention | Zero |
| **SkillOpt self-test gate** | **Adopt lite** — doc convention | Zero |
| Durable subagents (Minion) | Note only — use cron chaining | Deferred |
| ZeroEntropy embeddings | Skip — vendor lock | — |
| Team-brain sharing | Skip — single user | — |
| MCP server (serve mode) | Skip — different problem | — |
