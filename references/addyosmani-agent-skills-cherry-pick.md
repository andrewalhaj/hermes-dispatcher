# Cherry-Pick: addyosmani/agent-skills
**Source:** https://github.com/addyosmani/agent-skills — MIT, 54.1k★, Addy Osmani (Google Chrome eng lead), actively maintained, CI-validated skill structure. Pushed 2026-06-11.
**Verdict:** Cherry-pick. ~9/26 skills overlap existing Hermes stack. Hooks/commands/.gemini/agents are CC/Gemini-native, won't fire in Hermes. Upstream installer NOT used.
**Note on descriptions:** If any nugget below is promoted to a full skill, front-load the key discriminator in the first **60 chars** of `description:` (skills_list truncates there).

---

## Nugget 1: Doubt-Driven Development — Adversarial Fresh-Context Review

**Pattern:** Before any *non-trivial* decision stands (irreversible, crosses module boundary, asserts correctness the compiler can't verify), spawn a fresh-context reviewer whose job is to **disprove**, not approve.

Non-trivial = at least one of: branching logic change, module/service boundary, unverifiable property (thread safety, ordering, idempotence), irreversible blast radius.

**Hermes mapping:**
```python
delegate_task(
    goal="You are a skeptical reviewer. Read the attached implementation and try to find flaws, edge cases, or wrong assumptions. Do NOT approve it — try to disprove it. Return: 1) problems found, 2) verdict: ship/block/revise.",
    context="<artifact + non-trivial decision criteria>"
)
```
Not `/review` (verdict on finished artifact). This is **in-flight** while course-correction is cheap.

**Do NOT use for:** renaming, formatting, following unambiguous instructions, one-line obvious fixes, or when user asks for speed over verification. Doubting every keystroke ships nothing.

---

## Nugget 2: Spec-Driven — Surface Assumptions Before Writing a Line

**Pattern:** Before any spec content, emit an explicit assumptions block and demand correction:
```
ASSUMPTIONS I'M MAKING:
1. This is a web app (not native mobile)
2. Auth uses session cookies (not JWT)
→ Correct me now or I'll proceed with these.
```
Then gate: SPECIFY → PLAN → TASKS → IMPLEMENT. Each phase requires human review before advancing.

**Hermes mapping:** Bake the assumption-surface step into the `writing-plans` / `plan` skill workflow. The `plan` skill doesn't have this — it's the gap. When a task could go multiple architectural directions, emit the block before proposing a plan.

---

## Nugget 3: Source-Driven — Detect Stack → Fetch Docs → Cite

**Pattern:** Before writing framework-specific code, never implement from training memory. Steps:
1. Read dependency file (package.json, pyproject.toml, go.mod) → state exact versions found
2. Fetch the *specific* docs page for the feature (not homepage, not full docs)
3. Implement following the documented patterns
4. Cite sources inline

**Hermes mapping:** Aligns with `factual-discipline` skill. Apply specifically when writing framework boilerplate, routing, auth, or data-fetching patterns. The version-detect step is the key addition — state "React 19.1.0 detected → fetching docs" before writing components.

---

## Nugget 4: Incremental — Vertical Slices, Not Horizontal Layers

**Pattern:** Ship thin end-to-end slices (DB + API + UI in one slice) rather than "all models first, all routes second, all UI last." Each slice must leave the system in a working, testable state. Commit after each.

**Variants:**
- **Vertical (preferred):** Complete user-facing action per slice
- **Contract-first:** Define API interface → backend implements → frontend mocks → integrate
- **Risk-first:** Tackle the riskiest unknown as Slice 0

**Hermes mapping:** Feeds directly into `subagent-driven-development` task decomposition. When writing a plan, structure tasks as vertical slices, not horizontal layers. The "risk-first slice" maps onto the "spike first" pattern in `writing-plans`.

---

## Nugget 5: Context Hierarchy for Agent Setup

**Pattern:** Structure what the agent sees, ordered by persistence:
```
1. Rules files (CLAUDE.md / AGENTS.md) — always loaded, project-wide
2. Spec / architecture docs          — per feature/session
3. Relevant source files             — per task
4. Error output / test results       — per iteration
5. Conversation history              — accumulates, compacts
```
Agent output quality degrades when wrong-tier context dominates (e.g. loading too many source files when the agent just needs the spec).

**Hermes mapping:** Validates Hermes's existing AGENTS.md + skill `load_when` discipline. Actionable: when subagent output quality drops, diagnose which tier is missing vs. flooding context. When authoring a handoff package, follow the hierarchy — spec first, source files second, never dump raw conversation.

---

## Nugget 6: API Design — Hyrum's Law + Design for Deprecation at Design Time

**Pattern:** Every observable API behavior — including undocumented quirks, error text, ordering, timing — becomes a de facto contract once users depend on it (Hyrum's Law). Corollary: **plan removal at design time**, not when you want to sunset.

Practical rule: before shipping an endpoint, ask "how would we remove this?" If the answer is "we can't," rethink the shape.

**Hermes mapping:** Apply to Mealio API evolution. Before adding any new endpoint or field to the Mealio API, write the deprecation path first. Pairs with `deprecation-and-migration` nugget below.

---

## Nugget 7: Security — STRIDE Threat Model (5 min) Before Coding

**Pattern:** Before building any feature that touches user input, auth, or external services:
1. Map trust boundaries (HTTP, form fields, file uploads, webhooks, **LLM output** counts)
2. Name the assets (credentials, PII, payment, admin actions)
3. Run STRIDE quickly per boundary: Spoofing / Tampering / Repudiation / Information disclosure / DoS / Elevation

Key addition: **LLM output is a trust boundary** — prompt injection is an attack surface. Treat model-generated content that touches any I/O path as untrusted input.

**Hermes mapping:** `security-and-hardening` skill would be the natural home. Immediately applicable to Mealio (recipe import from URLs = external untrusted input, webhook handlers).

---

## Nugget 8: Observability — Define "Working" Before Instrumenting

**Pattern:** Before adding any telemetry, write 2–4 questions an on-call engineer will ask about this feature. Telemetry without a question is noise.
```
FEATURE: checkout payment retry
QUESTIONS ON-CALL WILL ASK:
1. What fraction of payments succeed on first attempt vs retry?
2. When a payment fails permanently, why?
```
Then instrument to answer exactly those questions.

**Hermes mapping:** Applies to Mealio production instrumentation. Before adding logs/metrics to a feature, write the on-call question list first — prevents dashboard clutter.

---

## Nugget 9: Deprecation — Code Is a Liability; Migration ≠ Announcement

**Pattern:** Code's value is the functionality it provides, not the code itself. Deprecation requires **active migration**, not just announcement — users depend on undocumented behaviors and can't "just switch." Two rules:
- Plan deprecation at design time: when building X, write "how do we remove X?"
- Mirror period: run old + new in parallel, route traffic incrementally, kill old only when traffic to it is zero

**Hermes mapping:** Relevant for Mealio feature evolution (old recipe import paths, legacy endpoints). When sunsetting any Mealio behavior, default to a mirror period rather than a flag day cutover.

---

## Nugget 10: ADRs — Document the Why, Not the What

**Pattern:** Architecture Decision Records at `docs/decisions/ADR-NNN-<slug>.md`. Template:
```markdown
# ADR-001: <Decision title>
## Status: Accepted | Superseded by ADR-XXX | Deprecated
## Date: YYYY-MM-DD
## Context: <constraints, requirements, problem>
## Decision: <what was decided>
## Alternatives considered: <what was rejected and why>
## Consequences: <trade-offs accepted>
```

**Hermes mapping:** Mealio `/root/projects/mealio/app/docs/decisions/` would be the natural home. Any non-obvious Mealio architectural decision (SQLite vs Postgres, CF Tunnel vs direct, Mealie import approach) deserves an ADR. Also applicable to Hermes infra decisions — record "why we run the gateway as systemd --user" etc.

---

*Upstream artifact NOT installed. Removal of cherry-pick note: `rm ~/.hermes/references/addyosmani-agent-skills-cherry-pick.md`.*
