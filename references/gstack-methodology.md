# gstack methodology patterns
Source: https://github.com/garrytan/gstack (MIT, Garry Tan / YC)  
Cherry-picked: methodology only, no install required.

---

## 1. Office Hours — Six Forcing Questions

Use when evaluating whether to build something. Run one at a time, **stop after each, wait for response**. Smart-skip if earlier answers already cover a later question.

**Stage routing:**
- Pre-product → Q1, Q2, Q3
- Has users → Q2, Q4, Q5
- Has paying customers → Q4, Q5, Q6
- Pure engineering/infra → Q2, Q4 only

---

### Q1: Demand Reality
> "What's the strongest evidence you have that someone actually wants this — not 'is interested,' not 'signed up for a waitlist,' but would be genuinely upset if it disappeared tomorrow?"

Push until you hear: specific behavior, someone paying, someone expanding usage, someone who would scramble if you vanished.

**After first answer, check framing:**
- Are key terms defined? (challenge vague words like "seamless," "AI space")
- What hidden assumptions are being made? Name one and ask if it's verified.
- Real vs. hypothetical? "I think devs would want…" ≠ "Three devs at my last company spent 10h/week on this."

**Core principle:** Interest is not demand. Waitlists, signups, "that's interesting" — none counts. Behavior counts. Money counts. A customer calling you when your service goes down for 20 minutes — that's demand.

---

### Q2: Status Quo
> "What are your users doing right now to solve this problem — even badly? What does that workaround cost them?"

Push until you hear: a specific workflow, hours spent, dollars wasted, tools duct-taped together, people hired to do it manually.

**Red flag:** "Nothing — there's no solution, that's the opportunity." If truly nothing exists and no one does anything, the problem probably isn't painful enough.

**Core principle:** The status quo is your real competitor. Not the other startup — the spreadsheet-and-Slack workaround your user already lives with.

---

### Q3: Desperate Specificity
> "Name the actual human who needs this most. What's their title? What gets them promoted? What gets them fired? What keeps them up at night?"

Push until you hear: a name, a role, a specific consequence they face, ideally something the founder heard directly from that person's mouth.

---

### Q4: Narrowest Wedge
> "What's the smallest possible version of this that someone would pay real money for — this week, not after you build the platform?"

Push until you hear: one feature, one workflow. Something shippable in days, not months, that someone would pay for.

**Core principle:** Narrow beats wide, early. Wedge first. Expand from strength.

---

### Q5: Observation & Surprise
> "Have you actually sat down and watched someone use this without helping them? What did they do that surprised you?"

Push until you hear: a specific surprise. Something the user did that contradicted assumptions. If nothing surprised them, they're either not watching or not paying attention.

---

### Q6: Future-Fit
> "If the world looks meaningfully different in 3 years — and it will — does your product become more essential or less?"

Push until you hear: a specific claim about how the user's world changes and why that change makes the product more valuable. "AI keeps getting better so we keep getting better" doesn't count — that's a rising tide argument every competitor can make.

---

### Response posture
- Calibrated acknowledgment, not praise. Good answer → harder follow-up, don't linger.
- Name common failure patterns directly: "solution in search of a problem," "hypothetical users," "assuming interest equals demand."
- End with one concrete **action**, not a strategy.

**Good push example:**
> Founder: "Everyone I've talked to loves the idea"  
> BAD: "That's encouraging! Who specifically have you talked to?"  
> GOOD: "Loving an idea is free. Has anyone offered to pay? Has anyone asked when it ships? Has anyone gotten angry when your prototype broke? Love is not demand."

---

## 2. CEO/Plan Review — Four Scope Modes

Use when reviewing a feature plan or deciding how ambitious to be.

| Mode | Posture |
|------|---------|
| **SCOPE EXPANSION** | Dream big. Ask "what would make this 10x better for 2x the effort?" Every expansion is user's opt-in decision. |
| **SELECTIVE EXPANSION** | Hold current scope, make it bulletproof. Surface expansion opportunities individually — user cherry-picks each one. |
| **HOLD SCOPE** | Maximum rigor. Scope is accepted. Catch every failure mode, test every edge case, map every error path. Do not silently reduce OR expand. |
| **SCOPE REDUCTION** | Surgical. Find minimum viable version that achieves core outcome. Cut everything else. Be ruthless. |

**Completeness principle (Boil the Ocean):** When evaluating approach A (full, ~150 LOC) vs approach B (90%, ~80 LOC) — always prefer A. AI compresses implementation 10-100x, so "ship the shortcut" is legacy thinking. The 70-line delta costs seconds with an agent.

**Hard rule:** User is 100% in control. Every scope change is explicit opt-in, never silent. Once mode is selected, commit to it — do not silently drift.

---

## 3. Review Army — Specialist Personas

The `/review` skill spawns these specialists in sequence, each outputting structured JSON findings:

| Specialist | Scope | Always/Conditional |
|------------|-------|-------------------|
| **Maintainability** | Dead code, unused imports, functions defined but never called | Always-on |
| **Testing** | Missing negative-path tests, untested guard clauses and error paths | Always-on |
| **Security** | Auth/authz patterns, crypto misuse, input validation at trust boundaries, attack surface expansion | SCOPE_AUTH=*** or (SCOPE_BACKEND + diff > 100 lines) |
| **API Contract** | Breaking changes (removed fields, changed types), versioning violations | SCOPE_API=true |
| **Performance** | N+1 queries, ORM loops without eager loading, batching opportunities | SCOPE_BACKEND or SCOPE_FRONTEND |
| **Data Migration** | Reversibility, rollback migrations, zero-downtime requirements | SCOPE_MIGRATIONS=true |
| **Red Team** | Adversarial analysis — finds what all other specialists missed. Think attacker + chaos engineer + hostile QA simultaneously | diff > 200 lines OR security found CRITICAL |

**Finding schema** (each specialist emits JSON lines):
```json
{"severity":"CRITICAL|INFORMATIONAL","confidence":N,"path":"file","line":N,"category":"specialist-name","summary":"...","fix":"...","fingerprint":"path:line:category","specialist":"name"}
```

**Key design decisions:**
- Confidence gate: findings below 7/10 don't surface in critical pass (prevents noise).
- Red team runs **after** other specialists and has access to their findings — its job is finding what they missed.
- Stack-detection gates specialists: Gemfile = ruby, package.json = node, pyproject.toml = python, go.mod = go.
- Adaptive gating: specialist hit-rate stats tracked; low-signal specialists get skipped on future runs.

---

## 4. Investigate — Four-Phase Debugging

**Iron Law: No fixes without root cause.**

Phases:
1. **Investigate** — gather evidence, reproduce, read logs
2. **Analyze** — map what the evidence says vs. what the code says
3. **Hypothesize** — form ranked hypotheses with predicted confirmation tests
4. **Implement** — fix only after root cause is confirmed

Proactively invoke (do NOT debug directly) when: errors, 500s, stack traces, unexpected behavior, "it was working yesterday," troubleshooting why something stopped working.

---

## 5. Slop Scan

Config: `slop-scan.config.json` — runs `bun run slop` or `slop:diff` to detect AI-generated boilerplate/slop in diffs. Compare with `slop:diff` to catch regressions per PR.

The concept: AI inflates code volume with verbose, repetitive patterns. A slop scan measures this separately from LOC and can catch "completed" but low-quality output.

---

## 6. CSO — Security Audit Structure

Two modes:
- **Daily** (zero-noise, 8/10 confidence gate) — fast, high-signal only
- **Comprehensive** (monthly, 2/10 bar) — deep scan, more noise acceptable

Covers in order:
1. Secrets archaeology (hardcoded keys, leaked creds in history)
2. Dependency supply chain (outdated, CVE-flagged, malicious packages)
3. CI/CD pipeline security (secret injection, workflow permissions)
4. LLM/AI security (prompt injection surfaces, trust boundaries)
5. Skill supply chain (if Claude Code skills used)
6. OWASP Top 10
7. STRIDE threat modeling
8. Active verification (not just static analysis)

Trend tracking: results stored across runs so you can see regression/improvement.

---

## 7. Retro — Weekly Engineering Retrospective

Arguments: `/retro`, `/retro 24h`, `/retro 14d`, `/retro compare`, `/retro global`

Analyzes: commit history, work patterns, code quality metrics. Team-aware: per-person praise and growth areas. Midnight-aligned windows (always `--since="YYYY-MM-DDT00:00:00"` not relative strings to avoid wall-clock drift).

---

*Last updated: 2026-06-16. Source: garrytan/gstack @c7ae632*
