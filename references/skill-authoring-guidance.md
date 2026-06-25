# Skill-Authoring Guidance

> Cherry-picked from [blader/Claudeception](https://github.com/blader/Claudeception) (MIT)
> on 2026-06-03. Two ideas absorbed into Hermes' native `skill_manage` flow — the
> upstream skill/hook itself was NOT installed (it reimplements machinery Hermes
> already has: curator, semantic skill matching, post-task extraction).

## 1. Write retrieval-optimized descriptions

Skill descriptions are what the curator semantic-matches against. Bake **exact
trigger strings** into them so the right skill surfaces when the problem recurs.

- Include **specific symptoms** — exact error messages, not categories.
- Include **context markers** — frameworks, file types, tools, config keys.
- Include **action phrases** — "Use when…", "Fix for…", "Solves…".

Bad  → `Helps with database problems`
Good → `Fix for PrismaClientKnownRequestError: Too many database connections in
        serverless (Vercel/Lambda). Use when connection-count errors appear
        after ~5 concurrent requests.`

The more literal the symptom in the description, the higher the match rate.

## 2. Update-vs-create decision matrix

Before `skill_manage(action='create')`, check whether an existing skill covers
the trigger. Decide with this table:

- **Nothing related** → create new.
- **Same trigger + same fix** → patch existing; bump version (1.0.0 → 1.1.0).
- **Same trigger, different root cause** → create new; add `See also:` cross-links both ways.
- **Partial overlap (same domain, different trigger)** → patch existing; add a "Variant" subsection.
- **Same domain, different problem** → create new; add `See also: [skill-name]` in Notes.
- **Stale or wrong** → mark deprecated in Notes + link replacement; or `skill_manage(action='delete', absorbed_into=…)`.

Versioning convention: **patch** = typos/wording • **minor** = new scenario/variant • **major** = breaking change or deprecation.

## Hermes mapping
- Create → `skill_manage(action='create')`
- Update/variant/version bump → `skill_manage(action='patch')`
- Consolidate/prune → `skill_manage(action='delete', absorbed_into='<umbrella>'|'')`

## Quality gate (unchanged from existing discipline)
Only extract when the knowledge is **reusable**, **non-trivial** (required real
discovery, not a doc lookup), **specific** (exact triggers describable), and
**verified** (actually worked). Not every task produces a skill.

## 3. Self-test gate before committing a skill edit

> Cherry-picked from [garrytan/gbrain](https://github.com/garrytan/gbrain)'s SkillOpt
> pattern (MIT) on 2026-06-04 — the "treat SKILL.md as a validated artifact" idea, lite.
> The full SkillOpt harness (generated benchmarks, A/B adversarial suites) is overkill
> for a single-user system; the *validation gate* is the part worth keeping.

Right now `skill_manage(action='patch')` commits immediately with no check that the
skill still works. Adopt a lightweight gate: any skill whose body contains **executable
steps** (shell commands, scripts, config that can be run) should carry a `## Self-test`
block — a known input plus the expected output or observable result.

Before AND after editing such a skill:
1. Run the `## Self-test` command(s).
2. Confirm the result still matches the expected output.
3. Only commit the edit if the self-test passes post-edit. If it regresses, fix before committing.

This is the verification-before-completion principle applied to the skill library itself:
don't ship a skill edit you haven't exercised. For pure-prose skills (philosophy, conventions,
checklists) a self-test is unnecessary — the gate applies only to skills with runnable steps.

Example `## Self-test` block:
```
## Self-test
Command:  python3 ~/.hermes/scripts/knowledge.py graph-query infrastructure-summary
Expected: prints ≥3 neighbors including manifest-topology and scheduler-recovery-procedure
```
