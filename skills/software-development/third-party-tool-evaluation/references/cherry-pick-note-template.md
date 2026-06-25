# Cherry-Pick Note Template

Copy this shape when documenting a cherry-pick. Goal: capture the durable nugget
with zero footprint, mapped onto Hermes tooling. Keep it concise — value-focused,
not a mirror of upstream docs. House under the governing umbrella's `references/`
or in `~/.hermes/references/<topic>.md` for cross-cutting patterns.

```markdown
# <Pattern Name>

> Cherry-picked from [<owner>/<repo>](<url>) (<license>) on <YYYY-MM-DD>.
> The *pattern* was absorbed into Hermes' native <tool/flow> — the upstream
> artifact itself was NOT installed (<one-line why: overlap / unmaintained /
> env-incompat / footprint>).

## The pattern
<2-4 sentences: what the technique is and why it helps.>

## Hermes mapping
- <upstream step> → <Hermes tool, e.g. delegate_task / skill_manage / curator>
- ...
- Stays inside Manifest cost tiering (if relevant), unlike <upstream's bypass>.

## When to use (gate)
- ✅ <high-value cases>
- ❌ <cases where it's wasteful — single call / verification pass instead>

## Caveats / dependencies
<Any Hermes capability this rides on that must be verified before relying on it.>
```

## Worked examples from the wild (2026-06-03 session)
- `~/.hermes/references/skill-authoring-guidance.md` — from Claudeception:
  retrieval-optimized descriptions + update-vs-create decision matrix.
- `~/.hermes/references/council-pattern-via-delegation.md` — from karpathy/llm-council:
  parallel-subagent council, anonymize-then-synthesize, cost gate.
