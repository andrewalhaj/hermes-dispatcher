# Third-party kanban tool teardown — BloopAI/vibe-kanban (June 2026)

Worked example of the review-before-install discipline applied to an external multi-agent
kanban tool. Reusable as a template for evaluating the next one.

## VERDICT (first, before details): do NOT install

Two independent reasons, either sufficient:

1. **It's sunsetting.** README top banner: "Vibe Kanban is sunsetting" + a shutdown
   announcement link; last commit ~2 months stale (v0.1.44, Apr 2026). Never base core
   orchestration infrastructure on a tool the maintainers are actively winding down. This
   alone closes it.

2. **Wrong shape for a headless chat-driven VPS, even if it were healthy.**
   - It is a **local web UI** (Rust backend + React frontend, `npx vibe-kanban`, binds
     `127.0.0.1`) that wraps *external* coding-agent CLIs — Claude Code, Codex, Gemini CLI,
     Copilot, Cursor, OpenCode, etc.
   - Its job: plan issues on a visual board → spawn each agent into a **git workspace**
     (branch + terminal + dev server) → **review diffs with inline comments** in the UI →
     open PRs and merge. It is a human-in-the-loop GUI for supervising coding agents on a
     git repo, single-machine, browser-centric.
   - You operate over Telegram on a headless server — a `127.0.0.1` browser UI is the
     opposite of that access pattern. And its domain (git diff/PR review) is narrower than
     general multi-agent work (research→verify→synthesize, ops, fleet).

## Other findings (security / overlap / footprint)

- **Architecturally redundant.** Hermes Kanban already provides a durable board, named
  workers, dispatcher, and dependency graph natively. vibe-kanban would duplicate that with
  a heavier Rust+Node+pnpm stack compiled from source.
- **Telemetry.** Ships PostHog analytics with build-time keys (`POSTHOG_API_KEY` /
  `POSTHOG_API_ENDPOINT`). Disablable but a posture you'd have to actively neutralize —
  counter to minimal-footprint / scrub-tracking habits.

## The one idea worth cherry-picking (don't install — borrow)

Its **diff-review-with-inline-comments gate** — a structured review checkpoint before work
merges — is a good pattern. It maps exactly onto:
- the **`swarm-verifier`** profile's skeptical, check-don't-build posture, and
- Kanban's native `comment` / `block` / `unblock` verbs (human-in-the-loop is first-class).

So: workers produce → verifier reviews and can `block` with comments → nothing synthesizes
until it signs off. Capture as an attributed `~/.hermes/references/` note; never adopt the
upstream tool.

## Reusable evaluation checklist for the next tool

1. Is it maintained? (last commit, release cadence, any sunset/EOL notice) — kill if dead.
2. Access pattern fit? (GUI vs CLI vs API; localhost vs remote; does it suit a headless
   chat-driven box?)
3. Domain fit? (does it solve the actual class of work, or a narrower adjacent one?)
4. Redundant with a native Hermes feature? (Kanban, delegate_task, cron already cover it?)
5. Footprint & telemetry? (deps, compile burden, analytics, network calls).
6. Cherry-pick verdict: is there a single idea to borrow as a reference note instead of
   installing the whole thing?
