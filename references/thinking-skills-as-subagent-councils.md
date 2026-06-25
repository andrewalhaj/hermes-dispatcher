# Thinking Skills as Subagent Councils

> Cherry-picked from [danielmiessler/Personal_AI_Infrastructure](https://github.com/danielmiessler/Personal_AI_Infrastructure) (MIT) on 2026-06-05.
> The *pattern* extends the existing council approach (from karpathy/llm-council,
> `references/council-pattern-via-delegation.md`) with new reasoning modes. The
> upstream artifact itself was NOT installed (total overlap with `delegate_task`).

## The pattern

PAI ships a library of "thinking skills" — structured reasoning approaches integrated
into its Algorithm loop:

- **Council** — multiple perspectives debate, synthesize consensus
- **Red Team** — adversarial review, find weaknesses
- **First Principles** — break down to fundamentals, rebuild
- **Systems Thinking** — map interconnections, feedback loops, second-order effects
- **Iterative Depth** — progressively deeper analysis across rounds
- **Aperture Oscillation** — alternate between broad (big picture) and narrow (detail)
- **Root Cause Analysis** — 5 Whys, causal chains

Each is a thinking protocol the agent applies before acting — not a skill that produces
output, but a method that shapes HOW it thinks about a problem.

## Hermes mapping

`delegate_task(tasks=[...])` with parallel subagents, each instructed to use a specific
thinking mode:

```
task_1 = "Analyze <problem> using FIRST PRINCIPLES: break to fundamentals, rebuild"
task_2 = "Analyze <problem> as RED TEAM: find every weakness, failure mode, edge case"
task_3 = "Analyze <problem> using SYSTEMS THINKING: map all interconnections"
→ Orchestrator synthesizes the three perspectives into a final analysis
```

This extends the existing council pattern (`references/council-pattern-via-delegation.md`)
with named reasoning modes beyond "anonymize and debate."

## Reasoning mode prompts (extracted, usable directly)

- **First Principles:** "What are the irreducible truths? Strip assumptions. Build up from
  fundamentals. If we knew nothing about how this is 'supposed' to work, how would we
  construct it?"
- **Red Team:** "Your goal is to make this fail. Find every weakness, edge case, failure
  mode, assumption that could break. Be adversarial. No defense — pure attack."
- **Systems Thinking:** "Map every component, every connection, every feedback loop.
  What are the second-order effects? What changes ripple where? Draw the causal graph."
- **Iterative Depth:** "Round 1: surface analysis. Round 2: one layer deeper. Round 3:
  deepest structural insight. Report what each round revealed that the previous missed."
- **Aperture Oscillation:** "First pass: 30,000-foot view — what's the big picture?
  Second pass: zoom to one critical detail — what's the precise mechanism? Third pass:
  how does that detail reshape the big picture?"
- **Root Cause:** "Ask 'why' five times. Each answer becomes the next question. Stop
  at the structural cause, not the proximate one. Distinguish root cause from symptom."

## When to use

- ✅ Architecture decisions with multiple valid approaches
- ✅ Security-sensitive changes (Red Team before implementation)
- ✅ Complex system changes (Systems Thinking to map ripple effects)
- ✅ Deep bugs that resist surface fixes (Root Cause + Iterative Depth)
- ❌ Simple, single-answer tasks — a council of 3 debating "what's 2+2" burns tokens
  for nothing
- ❌ Time-sensitive operations where parallel subagent latency is unacceptable

## Caveats / dependencies

- **Delegation transport must work.** As of 2026-06-03, `delegate_task` subagents
  bypass Manifest and route through a direct provider. Verify the transport with a
  1-subagent probe before relying on council patterns.
- 3-subagent council = 3× token cost. Gate this on complex/reasoning-tier tasks only.
- Anonymize subagent output before synthesis — prevents anchoring on the first result
