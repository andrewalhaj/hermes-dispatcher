---
name: office-hours-forcing-questions
description: "Pressure-test a product idea: 6 forcing questions."
version: 1.0.0
author: Hermes Agent (adapted from garrytan/gstack, MIT)
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [product, evaluation, brainstorming, scoping, decision, yc]
    related_skills: [brainstorming, plan, writing-plans]
---

# Office Hours — Six Forcing Questions

Pressure-test whether something is worth building **before** writing code. Adapted
from YC's office-hours method (garrytan/gstack). The questions separate real
demand from wishful thinking and force a narrow, shippable wedge.

## When to Use

- User describes a new product, feature, or project idea ("I want to build X")
- User asks "is this worth building", "should I build this", "help me think through this"
- Before `plan` / `writing-plans` on any net-new feature
- Any time scope feels vague or demand feels assumed

**Do NOT answer the build question directly.** Run the questions first — the
interrogation IS the value.

## How to Run

- Ask **one question at a time. STOP after each. Wait for the response** before the next.
- **Smart-skip:** if an earlier answer already covers a later question, skip it.
- Push each answer until it's specific. Vague answers are the failure signal.

### Stage routing (pick the relevant subset)

| Stage | Ask |
|-------|-----|
| Pre-product (just an idea) | Q1, Q2, Q3 |
| Has users | Q2, Q4, Q5 |
| Has paying customers | Q4, Q5, Q6 |
| Pure engineering / infra | Q2, Q4 only |

**Internal/intrapreneur projects:** reframe Q4 as "smallest demo that gets your
sponsor to greenlight?" and Q6 as "does this survive a reorg, or die when your
champion leaves?"

---

## Q1 — Demand Reality

> "What's the strongest evidence you have that someone actually wants this — not
> 'is interested,' not 'signed up for a waitlist,' but would be genuinely upset
> if it disappeared tomorrow?"

**Push until you hear:** specific behavior. Someone paying. Someone expanding
usage. Someone who'd scramble if you vanished.

**After the first answer, check framing before continuing:**
1. **Language precision** — are key terms defined? Challenge vague words ("seamless," "AI space," "better platform"): "What do you mean by [term], so I could measure it?"
2. **Hidden assumptions** — name one thing the framing takes for granted and ask if it's verified.
3. **Real vs. hypothetical** — "I think devs would want…" is hypothetical. "Three devs at my last company spent 10h/week on this" is real.

If framing is imprecise, **reframe constructively** (don't dissolve the question):
"Let me restate what I think you're building: [reframe]. Does that capture it?"

**Core principle:** *Interest is not demand.* Waitlists, signups, "that's
interesting" — none counts. Behavior counts. Money counts. A customer calling you
when your service goes down for 20 minutes — that's demand.

---

## Q2 — Status Quo

> "What are your users doing right now to solve this problem — even badly? What
> does that workaround cost them?"

**Push until you hear:** a specific workflow. Hours spent. Dollars wasted. Tools
duct-taped together. People hired to do it manually.

**Red flag:** "Nothing — there's no solution, that's the opportunity." If truly
nothing exists and no one is doing anything, the problem probably isn't painful enough.

**Core principle:** *The status quo is your real competitor.* Not the other
startup — the spreadsheet-and-Slack workaround your user already lives with.

---

## Q3 — Desperate Specificity

> "Name the actual human who needs this most. What's their title? What gets them
> promoted? What gets them fired? What keeps them up at night?"

**Push until you hear:** a name. A role. A specific consequence they face if the
problem isn't solved — ideally something heard directly from that person's mouth.

---

## Q4 — Narrowest Wedge

> "What's the smallest possible version of this that someone would pay real money
> for — this week, not after you build the platform?"

**Push until you hear:** one feature, one workflow. Something shippable in days,
not months, that someone would pay for.

**Core principle:** *Narrow beats wide, early.* Wedge first. Expand from strength.

---

## Q5 — Observation & Surprise

> "Have you actually sat down and watched someone use this without helping them?
> What did they do that surprised you?"

**Push until you hear:** a specific surprise. Something the user did that
contradicted assumptions. If nothing surprised them, they're not watching closely.

---

## Q6 — Future-Fit

> "If the world looks meaningfully different in 3 years — and it will — does your
> product become more essential or less?"

**Push until you hear:** a specific claim about how the user's world changes and
why that makes the product *more* valuable. "AI keeps getting better so we keep
getting better" doesn't count — that's a rising-tide argument every competitor can make.

---

## Response Posture

- **Calibrated acknowledgment, not praise.** Good answer → name what was good in one line, then a *harder* follow-up. Don't linger.
- **Name failure patterns directly:** "solution in search of a problem," "hypothetical users," "assuming interest equals demand," "waiting to launch until it's perfect."
- **End with one concrete action**, not a strategy. Every session produces one thing to do next.

**Example of a good push:**
> Founder: "Everyone I've talked to loves the idea"
> ❌ "That's encouraging! Who specifically have you talked to?"
> ✅ "Loving an idea is free. Has anyone offered to pay? Has anyone asked when it ships? Has anyone gotten angry when your prototype broke? Love is not demand."

## Escape Hatch

If the user says "just do it" / "skip the questions":
> "I hear you. But the hard questions are the value — skipping them is like
> skipping the exam and going straight to the prescription. Two more, then we move."

Then ask the 2 most critical remaining questions for their stage and proceed.

## Output

After the questions, produce a short verdict:
- **Demand evidence:** real / thin / hypothetical
- **The wedge:** the one shippable thing (or "not found yet")
- **The human:** named target user (or "undefined")
- **Recommendation:** build the wedge / sharpen first / don't build yet — and the one next action.

Then hand off to `plan` or `writing-plans` if it's a go.

## Pitfalls

- Asking all 6 regardless of stage → wastes time. Use the routing table.
- Accepting the first vague answer → the push is the whole point.
- Answering the build question yourself before running the questions → defeats the skill.
- Praising instead of escalating → rewards a good answer with a harder one, not applause.
