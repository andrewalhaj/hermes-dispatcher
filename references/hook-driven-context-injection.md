# Hook-Driven Context Injection

> Cherry-picked from [danielmiessler/Personal_AI_Infrastructure](https://github.com/danielmiessler/Personal_AI_Infrastructure) (MIT) on 2026-06-05.
> The *concept* was mapped onto Hermes' cron + skill `load_when` system — the upstream
> artifact itself was NOT installed (37 Bun/TypeScript hooks targeting Claude Code's
> event system; no Hermes equivalent).

## The pattern

PAI's 37 hooks intercept agent lifecycle events (prompt submission, tool completion,
file change, satisfaction rating, session cleanup) and inject context automatically.
The agent doesn't need to remember to load context — the system fires it at the
right moment. This is the architectural insight: **context injection should be
event-driven, not agent-driven.**

## Hermes mapping

Hermes doesn't have hooks, but two existing mechanisms approximate the pattern:

- **Cron jobs** → scheduled context injection (e.g., morning audit, heartbeat checks).
  These fire on time, not on events — coarse but reliable.
- **Skill `load_when` triggers** → context injection on specific conditions ("user asks
  to troubleshoot X"). These fire on intent, not on lifecycle events — narrower scope
  but already built-in.

What Hermes CAN'T currently do (and what makes PAI's hooks novel):
- Intercept on tool completion ("PostToolUse" → inject cost estimate)
- Intercept on prompt submission ("PreToolUse" → inject relevant memory)
- Intercept on file change ("FileChanged" → validate config)

## When this matters

- **Prompt-submission hooks** could inject MEMORY.md updates without the agent manually
  calling `memory()`
- **Tool-completion hooks** could flag token burn mid-turn ("that web_extract was 15K
  tokens — delegate next time")
- **File-change hooks** could auto-validate config YAML before the agent tries to use it

## Caveats / dependencies

- Hermes has no hook API — this is an aspirational pattern map, not a working feature
- Cron jobs fire on schedule, not on events — can't replicate mid-turn interception
- `load_when` triggers require the user to say specific phrases — no pre-submission
  or post-tool triggers exist
- If Hermes adds a hook system in the future, PAI's 37-hook library is the reference
  implementation to study, not install
