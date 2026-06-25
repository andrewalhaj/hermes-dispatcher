# Skill Architecture Patterns

> Cherry-picked from [testdino-hq/playwright-skill](https://github.com/testdino-hq/playwright-skill) (MIT) on 2026-06-03.
> The *skill structure patterns* were absorbed into Hermes' skill authoring conventions — the upstream artifact itself was NOT installed (600KB of Playwright testing guides from a commercial consultancy; domain-specific content, generic .md format, zero executable code).

## The patterns

Three structural conventions observed in a well-organized 70+ guide skill pack. The content is domain-specific (Playwright E2E testing), but the architecture patterns are domain-agnostic and directly applicable to any large Hermes skill.

## Hermes mapping

### 1. Hierarchical routing with progressive disclosure

Instead of one monolithic SKILL.md (like our 500+ line `manifest-router`), use a dispatch-table root that routes to sub-skills, which route to individual reference files:

```
SKILL.md (root) — "what to load for which task"
  ├── core/SKILL.md — "when doing X"
  │     ├── topic-a.md — "when doing X.a"
  │     └── topic-b.md — "when doing X.b"
  ├── advanced/SKILL.md — "when doing Y"
  └── migration/SKILL.md — "when migrating from Z"
```

**Hermes implementation:** Large skills (>300 lines) should split into a root SKILL.md (dispatch table + golden rules) and `references/*.md` files loaded on demand. The root SKILL.md's load_when triggers are broader; reference files are loaded by name when the agent needs depth. This is already supported by `skill_view(name, file_path='references/...')` — we just don't use it structurally.

**Before (monolithic):** `skill_view('manifest-router')` → 500+ lines every time.
**After (tiered):** `skill_view('manifest-router')` → 80-line dispatch table. `skill_view('manifest-router', file_path='references/routing-api-auth.md')` → only when auth is the actual topic.

### 2. "Golden Rules" preamble

Every sub-skill opens with a numbered list of immutable principles — pattern-matchable at the top of context, before detailed guides. Example from the upstream:

```
## Golden Rules
1. Use `getByRole()` over CSS/XPath — resilient to markup changes
2. Never `page.waitForTimeout()` — use `expect(locator).toBeVisible()`
...
10. Mock external services only — never mock your own app
```

**Hermes implementation:** Every skill's SKILL.md should have a "Golden Rules" or "Invariants" section immediately after the frontmatter — 3-8 lines that the agent can internalize before diving into reference depth. These are NOT procedural steps (those go below); they're design constraints that apply to ALL workflows in the skill's domain.

**Example for `manifest-router`:**
```
## Invariants
1. Complexity thresholds are hardcoded — tier→model assignment is the ONLY lever.
2. Trust NO stored routing claim — query the live DB before stating how a tier routes.
3. Delegation bypasses Manifest entirely on v0.15.1 — use execute_code, not delegate_task.
```

### 3. "When to use / when to avoid" gates

Every pattern/guide has explicit activation gates — not just "here's how to use X" but "use X when: ... avoid X when: ...". This prevents cargo-culting a pattern into the wrong context.

```markdown
### Role-Based Locators (Default Choice)
- **Use**: Always. They mirror assistive technology and survive UI refactors.
- **Avoid**: Elements with no ARIA role and you can't add one.
```

**Hermes implementation:** Every procedural section in a skill should answer two questions inline: "When does this apply?" and "When should you reach for something else?" This is especially critical for skills with multiple approaches (e.g., `manifest-router` has API-key auth, OAuth subscription, session-cookie, and direct-DB paths — each needs explicit gates).

**Example for `manifest-router` references/routing-api-auth.md:**
```
## Session-cookie auth (for dashboard REST API)
- **Use**: Configuring tiers, providers, fallbacks programmatically.
- **Avoid**: The proxy chat completions endpoint — use the mnfst_ Bearer key instead.
```

## When to apply (gate)

- **Hierarchical routing (#1):** When a skill exceeds ~300 lines or has clearly separable sub-domains. Don't split prematurely — a 150-line skill is fine monolithic.
- **Golden rules (#2):** Every skill, regardless of size. Even a 40-line skill benefits from 3 constraints up front.
- **Use/avoid gates (#3):** Any skill with multiple approaches to the same goal, or any pattern that can be misapplied.

## Caveats / dependencies

- Hierarchical routing depends on `skill_view(name, file_path=...)` working correctly (it does — verified).
- Golden rules must be genuinely invariant, not aspirational. "Always use getByRole()" is invariant. "Prefer async patterns" is aspirational and doesn't belong here.
- Use/avoid gates require the author to know the failure modes. A gate that says "Use: always" is worthless — if there's no "avoid" case, drop the gate and state the rule directly.
