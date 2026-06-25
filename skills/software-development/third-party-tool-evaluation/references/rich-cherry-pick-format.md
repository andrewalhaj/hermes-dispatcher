# Rich Cherry-Pick Note Format (for multi-concept repos)

> Use this format when a reviewed repo has 3+ distinct concepts worth extracting,
> each with different verdicts. Simpler repos (1-2 nuggets) can use the basic
> template in `cherry-pick-note-template.md`.

Living example: `~/.hermes/references/gbrain-cherry-pick.md` (GBrain, 2026-06-04).

## Structure

### Header block
```markdown
# <Repo Name> Cherry-Pick — Concepts for Hermes

> Cherry-picked from [<owner>/<repo>](<url>) (<license>, ★stars) on <YYYY-MM-DD>.
> **Upstream NOT installed.** <One-line why: incompatible stack / overlap / footprint>.
> These are *concepts* absorbed into our roadmap, not code.
```

### "What we already have" section
For repos that overlap with existing Hermes capabilities (like GBrain's hybrid search
overlapping with our retrieval-pipeline-techniques.md), explicitly call out what's
already covered. This prevents double-implementing and gives Andrew confidence that
you're not chasing things we already built.

### Concept-by-concept breakdown
Each concept gets its own section with a clear verdict:

```markdown
## Cherry-pick N: <Concept Name>

**The concept.** <2-3 sentences: what it is, how it works upstream, proof of value
(metrics, benchmarks, scale evidence).>

**Why it fits Hermes.** <How this maps onto our existing stack, not the upstream's.>

**Adoption path.** <Concrete steps: which files change, which deps are needed,
cost estimate (zero LLM / ~50 lines / new pip install).>
```

### Summary verdict table
Close with a table summarizing every concept and its disposition:

```markdown
| Concept | Verdict | Cost |
|---|---|---|
| <name> | **Adopt** — <why> | <Zero / ~50 lines / deferred> |
| <name> | **Adopt lite** — <doc convention only> | Zero |
| <name> | Note only — <why deferred> | Deferred |
| <name> | Skip — <vendor lock / wrong problem / overlap> | — |
```

### Lifecycle lens (optional)
If the repo introduces a useful evaluation framework (like awesome-second-brain's
Collect→Organize→Evolve→Use→Govern), integrate it inline — score our own system
against it to identify the weakest stage.

## When to use this format vs. the basic template

- **Rich format** (this doc): 3+ concepts, mixed verdicts, scaling evidence,
  evaluation frameworks — repos like GBrain, awesome-second-brain.
- **Basic template** (`cherry-pick-note-template.md`): 1-2 nuggets, single-verdict
  repos — things like claudeception (skill descriptions + decision matrix).

## Verification

After writing the cherry-pick note:
1. Append a row to `~/.hermes/references/evaluated-tools-log.md` with verdict,
   repo link, date, and pointer to the note.
2. If the note references any system path or capability off-handedly, verify
   that path/capability actually exists before shipping the note.
