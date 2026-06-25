# Model Routing — DeepSWE Benchmark Insight

**Source:** DeepSWE leaderboard (datacurve.ai), verified live 2026-06-16
(leaderboard "Updated June 11, 2026"). Surfaced via r/hermesagent post
by sugumaran95 ("model-task-router" skill, PR #43534) — but the post's
table was cherry-picked (omitted Claude entirely). Numbers below are
read directly from the live leaderboard, NOT the post.

## Why DeepSWE matters
Contamination-free coding benchmark: tasks written from scratch (not
adapted from real PRs), 5.5x more code than SWE-bench Pro, 91 repos /
5 languages, hand-written behavioral verifiers. All models run on the
same mini-swe-agent harness. It separates models that look identical
(~55-60%) on saturated benchmarks like SWE-bench Pro.

## Live numbers (Pass@1, avg cost per task)

| Model | DeepSWE | Avg cost | Note |
|---|---|---|---|
| gpt-5.5 [xhigh] | 70% | $6.61 | leader |
| **claude-opus-4.8 [max]** | **58%** | $12.58 | our complex model |
| gpt-5.4 [xhigh] | 56% | $4.38 | efficiency champ |
| claude-opus-4.7 | 54% | $18.19 | |
| **claude-sonnet-4.6 [high]** | **32%** | $5.52 | OUR PRIMARY |
| gemini-3.5-flash | 28% | $7.42 | |
| claude-opus-4.6 | 28% | $5.39 | |
| gpt-5.4-mini | 24% | $2.08 | |
| kimi-k2.6 (1T MoE) | 24% | $3.16 | "frontier" giant, weak here |
| minimax-m3 | 20% | $5.57 | |
| qwen3.7-max (cloud) | 18% | $2.12 | strongest CLOUD qwen |
| glm-5.1 | 18% | $7.46 | |
| **deepseek-v4-pro** | **8%** | $4.22 | OUR FALLBACK/EXECUTOR |
| gemini-3-flash | 5% | — | |

## Load-bearing takeaways for our stack

1. **The split is real: orchestration ≠ coding.** A model can be a
   strong tool-orchestrator (DeepSeek V4-Pro: Terminal-Bench 67.9%) and
   collapse on real code-gen (8% DeepSWE). NEVER assume a cheap model
   that's good at orchestration is also good at writing code.

2. **Route hard coding to Opus 4.8, not Sonnet.** Sonnet 4.6 is only
   32% on real from-scratch coding; Opus 4.8 is 58%. The rule is
   "Opus 4.8 for hard coding," "Sonnet for orchestration/reasoning,"
   not "Claude for coding."

3. **Do NOT route code-generation to local Qwen on the Studio.** The
   strongest CLOUD Qwen (qwen3.7-max) is only 18%. A local 35B (Qwen3.6
   / Qwen3-32B) will be worse. Studio = executor/orchestration/bulk/
   privacy/vision ONLY. Code-gen stays on Claude (Opus 4.8 for hard).

4. **No local box replaces Opus for coding.** Even kimi-k2.6 (1T MoE,
   the "Claude-competitive" class) is 24%. The capability gap on real
   engineering is architectural, not a quant/hardware problem.

## Studio Phase-2 validation — add this
Original plan measured tok/s + tool-call-loop reliability. ADD: **real
coding success rate** on a few from-scratch tasks. Confirm whether
local Qwen is a code-collapse risk (presumed yes per #3) before
allowing ANY code-gen routing to it. Executor/orchestration routing is
safe to enable after loop-check; code-gen routing is presumed-unsafe.

## Claude headless OAuth / Agent SDK billing risk (verified 2026-06-16)

Anthropic announced May 14 it would move `claude -p` / Agent SDK usage
OUT of Max subscription pools into a separate credit (June 15). This
would have broken the "headless Claude Code runs on your sub" pattern.

**June 15 update: PAUSED.** Anthropic shelved it — confirmed in Help
Center. Nothing changes today; `claude -p` still draws from Max pool.

BUT: paused ≠ cancelled. Anthropic is "reworking the plan." The 15–30×
subsidy that drove the change is still real. They will return to this.

**Implication for our stack:** Do NOT design Studio routing to depend
on headless `claude -p` being free forever. Route heavy programmatic/
cron/batch work to local Studio (zero Anthropic dependency). Use Claude
subscription for interactive + hard coding — exactly the plan. The
bypass is a bonus, not a load-bearing pillar.

Source: https://www.digitalapplied.com/blog/anthropic-claude-credit-overhaul-june-15-2026

## On the model-task-router skill itself
Concept is sound (auto-classify task -> dispatch by type), but the
shipped skill routes to GPT-5.4/5.5 — wrong provider stack for us
(Claude primary + DeepSeek + local Qwen). Did NOT install. Cherry-pick
the insight, not the code. If we build our own router, the dispatch
table is: orchestration->Sonnet/local Qwen, hard coding->Opus 4.8,
bulk/grep/probe->local Qwen executor, vision->local Qwen base.
