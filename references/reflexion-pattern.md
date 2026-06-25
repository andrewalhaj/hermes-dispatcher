# Reflexion Pattern — Learn From Failure, Don't Repeat It

> Cherry-picked from [noahshinn/reflexion](https://github.com/noahshinn/reflexion) (MIT,
> NeurIPS 2023, arXiv:2303.11366) on 2026-06-03. The *mechanism* was absorbed; the
> upstream repo (GPT-4 research notebooks) was NOT installed — nothing to plug in.

## The mechanism
Reflexion = "verbal reinforcement learning." When an agent attempt fails, it writes a
specific verbal reflection on *why* it failed, persists it, and injects it into the next
attempt's context. The reflection — not a weight update — is the learning signal.

Loop: **attempt → fail (judged by a real signal) → write specific reflection →
persist → inject on retry → don't repeat the mistake.**

## The one rule this adds to existing practice
Hermes already writes post-mortems (`references/` files ARE a Reflexion memory buffer).
What Reflexion formalizes:

> **A non-trivial failure must produce a persisted, specific reflection BEFORE the
> next attempt — or the retry repeats the failure.**

The failure signal must be real, not self-judged: failed tests, a non-zero exit, an
error code, a blocked change, a probe that returned the wrong thing. (Self-graded
"I think that went poorly" is the weak case — anchor on external signal.)

## What a reflection must contain
Vague reflection ("that didn't work, try harder") is the failure mode — same trap as
vague self-critique. A useful reflection is concrete and reusable:
- **Symptom** — exact error string / observed wrong behavior, verbatim.
- **Root cause** — the actual mechanism, not the surface error.
- **Fix** — the specific change that resolves it.
- **Verification** — how to confirm the fix worked (the test to re-run).

## When to apply
- ✅ A task/phase failed and will plausibly be retried (infra phase, migration step,
  probe, blocked config change, recurring transport error).
- ✅ Same failure has surfaced across >1 session — STRONG trigger; that means no
  reflection was persisted last time and each session re-diagnoses from scratch.
- ❌ Trivial one-off typos, or successes (those become skills, not reflections).

## Hermes mapping
- Persist reflection → a `references/<failure>.md` file (durable, injected into future
  context), or a skill if it generalizes into a reusable procedure.
- Cross-link: a **skill** is a reflection on a *solved* problem (see
  `skill-authoring-guidance.md`); a **failure record** is a reflection on an *open or
  recurring* one. Same discipline, different lifecycle stage.

## Relationship to the other patterns
- Self-refine = depth (iterate one line against a checkable signal).
- Council = breadth (parallel independent opinions, then synthesize).
- Reflexion = time (carry the lesson from a failed attempt into the next attempt).
They compose: reflect after a failed council; self-refine the synthesis; persist the
reflection so the next session starts ahead.
