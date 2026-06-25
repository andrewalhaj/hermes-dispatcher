---
name: token-optimization
description: "Cut Hermes token spend: DB queries, prompt bloat."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [token-optimization, cost, delegation, routing, profiles, auditing]
    related_skills: [subagent-driven-development, hermes-agent]
---

# Token Optimization

Reduce per-session and per-turn token spend without degrading output quality. Covers auditing, model routing, delegate-first tool access, lean profiles, and static knowledge files.

## When to Load

Load when:
- User asks to audit token spend, cut costs, or "stop tokenmaxxing"
- User asks to configure model routing or switch providers
- Setting up delegation discipline or lean executor profiles
- User wants per-toolset token overhead analysis
- Creating cron-based self-audit jobs

## Core Principles

1. **Audit first, cut second.** Query the session DB to find WHERE tokens went before proposing cuts.
2. **Profile-based, reversible changes.** Every change should be undoable with a single command. No destructive edits.
3. **Delegate everything heavy.** >50 lines of tool output → subagent. Browser, MCP, heavy file ops → delegate.
4. **Cheap model for background work.** Cron jobs, kanban workers, delegated subagents → DeepSeek V4 Pro (or cheapest capable model).
5. **Static knowledge over re-discovery.** CONTEXT.md files and Obsidian/wiki reads replace terminal/file exploration.

## Step-by-Step Workflow

### 1. Self-Audit (no changes yet)

Query the session database for the last 14 days:

```python
import sqlite3, json

db = sqlite3.connect("/root/.hermes/state.db")
db.row_factory = sqlite3.Row

sessions = db.execute("""
    SELECT id, title, model, started_at, message_count,
           tool_call_count, input_tokens, output_tokens,
           estimated_cost_usd
    FROM sessions
    ORDER BY started_at DESC
    LIMIT 50
""").fetchall()
```

For each session, count tool patterns from the messages table:
```sql
SELECT id, role, tool_calls, tool_name
FROM messages
WHERE session_id = ?
ORDER BY id
```

Flag violations:
- **>100K input tokens + ZERO delegate_task** → context saturated with direct work
- **High OUTPUT tokens (>200K) + ZERO delegate_task** → orchestrator grinding implementation in-process (see "Output tokens are the real cost driver" below). This is the single most expensive pattern and input-token thresholds MISS it.
- **>8 web_search + ZERO delegation** → should batch-delegate research
- **>15 terminal calls** → iterative build without delegation
- **Browser tool used without delegation** → heavy schema overhead in orchestrator

**⚠️ Cost-attribution pitfall #1 — output tokens, not input, are usually the cost driver.** With a healthy cache (Hermes routinely hits 99%+ cache-read ratio), input is nearly free per turn — the spend is in OUTPUT the orchestrator generates. Real example: two sessions with only 1,691 and 695 INPUT tokens cost $107.68 and $42.97 because they generated 984K and 433K OUTPUT tokens (in-process builds: 46–76 terminal calls + inline `patch`/`write_file`, zero delegation). An audit keyed on `input_tokens > N` would flag NEITHER. Always sort by `output_tokens` and by `estimated_cost_usd`, not just input. Sonnet output is ~5× input price, so a self-built file is the $100 mistake.

**⚠️ Cost-attribution pitfall #2 — check `source` before blaming a cron.** A session titled like a cron job ("Daily X Report") may actually be `source='telegram'` — i.e. the user ran that task interactively on the orchestrator (Sonnet), NOT the scheduled cron firing on its cheap model. Before concluding "cron is leaking expensive model," query `source` and confirm. In one audit the $23 "Daily Delegation Audit" session was interactive; the real 09:00 cron had been running on DeepSeek at ~$0.15/run the whole time. Crons (even a busy fleet of ~18) typically total a few dollars over two weeks; interactive Sonnet sessions are usually 85–90% of spend. Route your attention accordingly — delegation discipline beats cron model-tuning by orders of magnitude.

The full audit query is in `references/session-audit-query.md`.

### 2. Model Routing

**Current architecture (post-Manifest):** Hermes routes directly to providers via `config.yaml`. No middleware router. Routing policy is set in `config.yaml` by specifying `model.provider` and `model.default`.

```bash
# Main provider (Claude via OAuth proxy, no API key needed)
hermes config set model.provider anthropic
hermes config set model.base_url http://localhost:9999/v1
hermes config set model.api_key sk-pro-key   # fake key — proxy ignores it
hermes config set model.default claude-sonnet-4-20250514

# Delegation stays on DeepSeek direct (cheapest capable model for background work)
hermes config set delegation.model deepseek-v4-pro
hermes config set delegation.provider deepseek
hermes config set delegation.base_url https://api.deepseek.com/v1
hermes config set delegation.api_key_env DEEPSEEK_API_KEY
```

**Routing decision heuristics:**
- Orchestrator / interactive sessions → main provider (Anthropic/Claude)
- Cron jobs, kanban workers, delegated subagents → DeepSeek direct (cheap, fast)
- Vision tasks → main provider (Claude handles vision natively; avoid routing vision to text-only endpoints)

**Pitfall — DeepSeek can't handle vision payloads.** If the main provider is a text-only model and a vision request falls back to DeepSeek, it returns `unknown variant 'image_url'`. Always confirm the active provider handles the `image_url` content type before routing vision requests through it.

### 3. Delegate-First Tool Access

Disable the heaviest toolsets on the orchestrator profile. Each disabled toolset saves ~800-1000 tokens/turn in schema overhead.

```bash
# Disable heaviest toolsets (takes effect next session)
hermes tools disable browser       # 13 tools, heaviest
hermes tools disable computer_use  # macOS-only — dead weight on Linux, zero use
hermes tools disable vision        # if not needed inline
hermes tools disable image_gen     # if not needed inline
```

Replace with SOUL.md instructions telling the agent to delegate:

```markdown
# Token Discipline — Delegate-First Rules
1. >50 LOC or tool output → delegate to subagent
2. Never carry raw details — verify summaries, not internals
3. Batch research: 3+ lookups → parallel delegate_task
4. session_search before re-discovery
5. Browser work → delegate_task(toolsets=['browser'])
6. Heavy MCP → executor profile or delegation
7. File ops: search_files/read_file/patch, not ls/cat/sed
```

**Important:** Tool changes take effect on next session (`/reset`). Current session retains loaded tools. Disabled toolsets remain available to delegated subagents.

### 4. Cheap Executor Profile

Create a lean profile for background work (cron jobs, kanban workers, delegated implementation):

```bash
hermes profile create executor --clone-from default

# Pin to cheap model directly (no Manifest overhead)
hermes --profile executor config set model.default deepseek-v4-pro
hermes --profile executor config set model.provider deepseek
hermes --profile executor config set model.base_url https://api.deepseek.com/v1
hermes --profile executor config set model.api_key_env DEEPSEEK_API_KEY

# Disable heavy toolsets
hermes --profile executor tools disable browser
hermes --profile executor tools disable vision
hermes --profile executor tools disable image_gen
hermes --profile executor tools disable tts
hermes --profile executor tools disable messaging
hermes --profile executor tools disable homeassistant
hermes --profile executor tools disable computer_use
```

Write a minimal SOUL.md:

```markdown
You are a background executor — a leaf worker that runs cheaply on DeepSeek V4 Pro
with minimal tools. Do the work, return the result, do not chat. Be concise.
Prefer built-in tools over MCP where possible.
```

### 5. Daily Self-Audit Cron

Set up a cron job that scans for violation patterns daily:

```python
cronjob(
    action="create",
    name="Daily Delegation Audit",
    schedule="0 9 * * *",
    profile="executor",              # cheap model, minimal tools
    model={"model": "deepseek-v4-pro", "provider": "deepseek"},
    enabled_toolsets=["terminal", "file", "session_search"],
    skills=["hermes-agent"],
    prompt="""SELF-AUDIT: Scan session DB for last 24 hours. Flag:
1. >100K input tokens + zero delegate_task
2. >8 web_search + zero delegation
3. >15 terminal calls without delegation
Write violations to /root/.hermes/pending-fixes.md.
Append summary to /root/.hermes/audit-log.md.
DO NOT modify config or session files."""
)
```

### 5b. Cron Fleet Model-Tiering

When auditing a cron fleet for cost, the inventory matters more than instinct. Use `cronjob(action='list')` and classify each job:

**`no_agent: true` script jobs cost ~ZERO regardless of model.** A job with `no_agent: true` runs a `.py`/`.sh` script with NO LLM loop — the `model` field is a no-op. Setting a model on backup.sh / watchdog / export jobs changes nothing about cost or behavior. Do NOT waste effort (or a gated edit) "fixing" their model. In one fleet, 9 of 18 jobs were `no_agent` script jobs; only the remaining ~9 LLM jobs were worth tiering.

**`model: None` (or `provider: None`) crons inherit the DEFAULT model** — i.e. the expensive orchestrator model (Sonnet), not a cheap one. These are the real leak: a `model: None` LLM cron silently bills Sonnet on every run. Pin them explicitly.

**Tiering rule that worked:** all LLM crons → cheapest capable (`deepseek-v4-flash`); memory/offload/dedup/knowledge-capture crons → next tier up (`deepseek-v4-pro`) since they do reasoning over durable state. Apply via the API, not hand-edited JSON:
```python
cronjob(action='update', job_id='<id>', model={'model': 'deepseek-v4-flash', 'provider': 'deepseek'})
```
**Valid DeepSeek IDs are `deepseek-v4-flash` and `deepseek-v4-pro` only** — there is no plain `deepseek-v4`. If a user says "deepseek v4," it resolves to `-pro` (the heavier tier). Confirm available IDs by grepping existing config (`grep -rhoiE "deepseek-v4[a-z-]*" config.yaml profiles/*/config.yaml`) before pinning, so you don't set a model that doesn't exist.

**Verify a model change actually took.** After updating a cron's model, the cron-config field changing is NOT proof it runs on the new model. Trigger one real run (`cronjob(action='run', job_id=...)`) and poll the `sessions` table for the new row — confirm `model` and `billing_provider` match what you set. A profile-level override (e.g. an `executor` profile pinned to DeepSeek) can win over the per-job model, so the only proof is a live run's session record.

### 6. Static Knowledge (CONTEXT.md)

For each active project directory, create CONTEXT.md so the agent stops re-exploring:

```markdown
# /root — System Context
## Active Services
- Manifest (self-hosted model router) — Docker, port 2099
- Hermes Agent — installed at /usr/local/lib/hermes-agent
## Profiles
- default — main, routes through Manifest
- executor — lean worker, DeepSeek direct, minimal tools
## Key Conventions
- Python: python3 (no pip), PEP 668 enforced
- Delegation: prefer delegate_task over in-process for >50 LOC
```

Where project docs exist (Obsidian vault, wiki), read those instead of re-discovering via terminal calls. Load the `obsidian` skill before reading vault content.

### 7. Skill Pruning

Dead skills burn tokens — each skill's description (~150-200 chars) is injected into the system prompt every turn. Audit and prune regularly.

**Audit:** Run `skills_list()` and categorize by actual usage:
- **Core** — fires in your active domain (HA, infra, Hermes self-management)
- **Situational** — fires rarely but has a clear, important trigger
- **Dead** — target domain you don't work in (e.g., social media banners, mobile app screens, presentation design)

**⚠️ How enable/disable ACTUALLY works — there is NO `hermes skills enable/disable` verb.** `hermes skills <action>` only accepts: browse, search, install, inspect, list, check, update, audit, uninstall, reset, opt-out, opt-in, repair-official, publish, snapshot, tap, config. Calling `hermes skills enable X` returns `invalid choice`. The enabled/disabled status shown by `hermes skills list` is **per-platform** and lives in `config.yaml` under `skills.platform_disabled.<platform>` — a YAML block list of skill names, one per platform (telegram, slack, discord, signal, whatsapp, …). A skill shown "disabled" is merely excluded on the CURRENT platform; it may be active on others and is always available to delegated subagents.

- **To enable a skill** (e.g. on Telegram, or everywhere): remove its `- name` line from the relevant platform list(s) in `config.yaml`. This is a GATED config.yaml edit — back up first. Surgical line-removal is safe because the names appear ONLY as list items inside that block; confirm with `grep -cE "^[[:space:]]*- name$" config.yaml` (count == number of platforms). Validate YAML and re-run `hermes skills list` to confirm the status flipped — the change is live immediately, no restart.
- **To disable a skill on a platform:** add its `- name` under that platform's list. Same gated edit + backup.
- **`opt-out`/`opt-in`** are unrelated — they toggle the `.no-bundled-skills` marker controlling whether bundled skills re-seed on `hermes update`, NOT per-skill activation.

**Deleting a skill from disk** (different from disabling — removes it entirely): `skill_manage(action='delete', name='skill-name')`. Only for skills you authored; bundled/hub skills are protected.

**Disk-vs-table name mismatch.** The directory name can differ from the skill's declared `name:` in frontmatter — e.g. dir `creative/creative-ideation/` holds the skill named `ideation`. When `read_file` on a guessed path 404s, search by frontmatter name: `search_files(pattern='SKILL.md', target='files', path='~/.hermes/skills')` then grep the `name:` field, don't assume dir == name.

**Reviewing disabled skills (can't skill_view them).** `skill_view` refuses disabled skills (`Skill 'X' is disabled`). Read the SKILL.md directly from disk instead to inspect for stale data before enabling.

**Typical candidates for disabling/deletion:**
- Skills targeting domains outside your workflow (frontend niche skills when you only build HA dashboards)
- Skills that overlap with a more specific equivalent (e.g., `home-assistant-dashboard` vs `ha-fusion-custom-build`)
- Skills redundant with built-in tools (e.g., `defuddle` vs built-in `web_extract`)

**Enable-vs-prune is a two-way street.** Re-enabling a genuinely relevant disabled skill (e.g. `subagent-driven-development` when leaning into delegation) is correct even though it adds ~150 tok/turn — relevance beats raw token count. But before enabling an integration skill, verify its prerequisite credential is set (e.g. `LINEAR_API_KEY`): an unconfigured skill that can't function is pure prompt-weight cost. Leave it disabled and note the one-step path (set key → remove from `platform_disabled`) for when it's actually adopted.

**Note on token savings:** Each disabled/deleted skill removes its description from the system prompt. 8 dead skills ≈ 1,200-1,400 chars (~300 tokens) saved per turn. Combined with toolset disabling, these compound.

### 8. Honcho Card Hygiene

Honcho peer cards are injected into the system prompt every turn and accumulate facts over time. After major infrastructure changes (Manifest decommission, provider migration, profile reconfiguration), the card often contains **stale behavioral instructions** that contradict current architecture.

**Audit pattern:** Run `honcho_profile` on the `user` peer and scan `INSTRUCTION:` and `ATTRIBUTE:` entries for stale routing rules, deprecated service references, or model preferences that no longer match the live system.

**Concrete example (2026-06-06):** After decommissioning Manifest, the Honcho card still contained:
- `INSTRUCTION: Route simple/standard requests to DeepSeek V4 Pro.` (stale — user manually switches providers, no auto-routing)
- `INSTRUCTION: Route complex/reasoning requests to Claude Opus 4.8 via local OAuth proxy.` (stale — direct Anthropic API via hermes-claude-auth bypass, no proxy)

Both were removed and replaced with a single accurate `ATTRIBUTE:` describing the actual architecture.

**Pitfall — Honcho identity drift.** When a user switches providers or decommissions a service, the INSTRUCTION entries in the peer card remain and can contradict the agent's actual behavior. The agent sees "route X to Y" but the user manually switches to Z — creating conflicting signals. After any major infra change, audit the Honcho card BEFORE troubleshooting — stale behavioral instructions are the #1 source of "why is the agent still acting like <old architecture>?" questions.

### 10. Always-Inject vs. Retrieval: which `.md` files can offload (asymmetric-risk framework)

When the user asks "can we move USER.md / MEMORY.md / the other `.md` files to retrieval (Honcho) instead of injecting them every turn, to save tokens?" — the answer is **per-entry, not per-file**, and the decision is governed by an **asymmetric-risk** rule, not by token count.

**The deciding question for any entry:** does this content need to shape *every* response, or only responses where it's *contextually relevant*?
- Always-relevant (tone, identity, safety rules, pitfall warnings, behavioral corrections) → **must stay injected**. Retrieval is semantic-similarity based; it surfaces a fact only when the current turn *looks like* the context it was written for. An always-on rule ("be concise", "heavyweight fix over workaround") often won't be retrieved on turns that don't contain its trigger words — so it silently stops firing.
- Contextually-relevant lookups (hardware specs, file paths, `knowledge.py search "X"` pointer entries) → **safe to offload** to Honcho / the knowledge store. These are only needed when the task touches them, which is exactly what retrieval is good at.

**File-by-file verdict:**

| File | Offload to retrieval? | Why |
|------|----------------------|-----|
| USER.md | Partial | Hardware/path facts → offload. **Behavioral corrections + tone/style entries → keep injected** (always-relevant, not contextual). |
| MEMORY.md | Partial | The `knowledge.py search "..."` pointer entries can be dropped entirely (just search). **Pitfall/warning entries must stay hot** — they must be present *before* you act, not retrieved *after* the turn reveals you're about to make the mistake. |
| SOUL.md | ❌ Never | Identity/character. Retrieval-dependent personality = inconsistent personality. |
| AGENTS.md | ❌ Never | Safety-critical (write gate, routing, autonomy boundary). Missing it on one turn is a serious failure. Trim it for verbosity instead — but it stays injected. |

**Why asymmetric risk forbids going all-the-way to retrieval-only:** token savings are *linear* (a fixed ~N tokens/turn per offloaded entry), but a missed behavioral correction or a missed pitfall warning is a *non-linear* cost — it causes a repeat mistake whose recovery (rework, lost trust, a destructive action) dwarfs the savings. Plus retrieval-only adds three failure modes injection doesn't have: (1) propagation lag — a new fact isn't hot next turn, it must be concluded + dialectic-processed + retrieved; (2) Honcho-unreachable = flying blind with zero user context; (3) always-on entries (tone) are *never* contextually triggered so they're chronically under-retrieved.

**The recommended move is the hybrid trim, not wholesale drop:** line-by-line classify each file — keep behavioral corrections / pitfall warnings / high-frequency workflow conventions injected; offload hardware specs / path lookups / lookup pointers to Honcho or the knowledge store. Typical result: 60–70% reduction in injection size with near-zero behavioral risk.

**Pitfall — a webhook does NOT save tokens.** When a user pairs "offload to retrieval" with "should we set up a Honcho webhook?", separate the two: a webhook is an async *delivery/reactivity* mechanism (push a notification when Honcho updates a conclusion). It changes *when you're told something changed*, not *what gets injected per turn*. It cannot replace any always-inject content for token efficiency. The token win is the config change (drop an entry from injection, lean on Honcho's existing per-turn retrieval) — no webhook required.

## Pitfalls

- **Delegation rules need a COUNTABLE trigger, not a vibe.** SOUL.md language like "I spin up subagents when work is heavy" does not fire in practice — "heavy" has no threshold, so the orchestrator grinds 46 terminal calls and never stops. Make the delegation rule enforceable like the WRITE GATE: e.g. "Before the 4th terminal/patch/write call in a single implementation task, STOP and delegate execution to a subagent; the orchestrator plans + verifies the diff, it does not author large file contents inline." Both observed $100/$43 blowout sessions crossed 4 terminal calls in their first turns and never tripped a rule. A measurable threshold is enforceable; "when heavy" is not.
- **Stale provider key in a profile config = latent landmine, often masked.** After a provider migration (e.g. Manifest decommission), a profile's `model.api_key` may still hold a dead key (e.g. `mnfst_…`) while runtime silently succeeds because `api_key_env` (e.g. `DEEPSEEK_API_KEY` from the profile `.env`) wins precedence. It works UNTIL key-precedence shifts, then every job on that profile 401s silently. Fix: set `model.api_key: ''` and rely solely on `api_key_env`. Verify by triggering one real run and confirming `billing_provider` + token flow in the session DB (not just that the config parses). `cronjob(action='run', job_id=...)` then poll `sessions` for the new row.
- **Browser tools disabled breaks browser-only workflows.** The SOUL.md delegation instruction must be present so the agent knows to delegate. Test with a trivial browser task after disabling.
- **Delegation model must have API key.** Set `delegation.api_key_env` to reference the env var (DEEPSEEK_API_KEY), not hardcode the key in config.yaml.
- **Tool changes need /reset.** Disabled toolsets only take effect on next session. Current session retains all tools loaded at startup.
- **Don't disable delegation toolset.** The orchestrator needs delegate_task to offload work. Disabling it traps everything in-process.
- **Executor profile needs its own .env.** Profiles don't inherit .env from default. Either copy it or ensure the required env vars are set globally.
- **Secret redaction blocks API key access.** Hermes's `security.redact_secrets` redacts keys from ALL tool output (terminal, read_file, execute_code). Workaround: write key to temp file via terminal, then hex-dump with `xxd /tmp/key.txt` and decode the hex bytes manually. Clean up temp files after.
- **Ghost skills — listed but undeletable.** `skills_list()` may surface skills that have no filesystem file and cannot be deleted via `skill_manage(action='delete')`. These are likely bundled or plugin-sourced. When pruning, verify each skill exists on disk with `search_files(pattern='skill-name', target='files', path='/root/.hermes/skills')` before attempting deletion. If `skill_manage` delete fails with "not found in active profile," skip it — the skill is a ghost and its description is not actually in your system prompt.

### 9. Subdirectory-Hint Re-injection (AGENTS.md / CLAUDE.md leak)

**Symptom:** The full text of `AGENTS.md` (or `CLAUDE.md`/`.cursorrules`) appears appended to nearly EVERY terminal/read_file tool result as `[Subdirectory context discovered: <path>]`. On a heavy session this silently duplicates 1,000+ tokens per tool call (e.g. a 1,126-token AGENTS.md × 46 terminal calls ≈ 52K tokens of pure waste), and those copies accumulate in context and re-send every subsequent turn until compaction. It is NOT in the cached prompt prefix, so it costs full input price every time.

**Root cause (the off-by-one-directory):** `agent/subdirectory_hints.py` runs a `SubdirectoryHintTracker` that lazily loads context files from directories the agent navigates INTO, appending them to the tool result. It pre-marks its `working_dir` as already-loaded (so the CWD's own AGENTS.md is NOT re-injected — that one is already in the system prompt via `prompt_builder.py` at startup). The tracker's `working_dir` comes from `os.getenv("TERMINAL_CWD") or None`, falling back to `os.getcwd()`. If the gateway's effective CWD is a PARENT of where `AGENTS.md` actually lives (e.g. gateway CWD = `/root` but the file is `/root/.hermes/AGENTS.md`), then `/root/.hermes` is treated as a fresh subdirectory and its AGENTS.md gets re-discovered on every command that touches that path. The file ends up injected TWICE: once in the cached prompt (correct) and again per-tool-call (waste).

**Diagnosis:**
```bash
LIB=/usr/local/lib/hermes-agent
grep -rn "Subdirectory context discovered" $LIB --include="*.py"   # agent/subdirectory_hints.py
grep -rn "SubdirectoryHintTracker(" $LIB/agent/agent_init.py        # working_dir source
# live gateway CWD (what the tracker falls back to):
PID=$(systemctl --user show hermes-gateway -p MainPID --value); ls -l /proc/$PID/cwd
# is the AGENTS.md dir a SUBDIR of that CWD? -> that's the leak
```

**Fix (gated — config.yaml):** Point `terminal.cwd` at the absolute directory where AGENTS.md lives, so the gateway `chdir`s there at startup and the tracker pre-marks it as loaded:
```yaml
terminal:
  cwd: /root/.hermes    # was '.' — relative '.' did NOT bridge a clean absolute TERMINAL_CWD
```
This makes `os.getcwd()` (and the tracker's `working_dir`) equal the AGENTS.md directory → it's pre-marked loaded → never re-injected as a subdirectory hint. AGENTS.md still loads once at startup (cached at ~99.6%), so ZERO context is lost. Needs a gateway restart (CWD/`TERMINAL_CWD` read at startup) — use the detached out-of-cgroup restart from `hermes-maintenance`.

**Verify against runtime behaviour, not the env var:** After restart, `TERMINAL_CWD` may STILL be absent from the process env — the fix can work purely via `os.getcwd()` (confirm with `ls -l /proc/<PID>/cwd → /root/.hermes`). The real proof is behavioural: run any command that touches the AGENTS.md directory and confirm NO `[Subdirectory context discovered: ...]` block follows the output. Do not trust the env value; trust the absence of the injected block.

**Alternative (mitigation, not a cure):** Shrink AGENTS.md itself (it often duplicates SOUL.md + a verbose WRITE GATE). Caps the per-injection cost but leaves the redundancy. The `terminal.cwd` fix kills the root cause and is preferred.

**Pitfall — relative-path resolution shift.** Changing `terminal.cwd` changes where RELATIVE paths in terminal commands resolve. If your workflow uses absolute paths / explicit `cd`, impact is near-zero, but flag it. Real project subdirectories with their own AGENTS.md still get discovered correctly — only the home-config double-injection is removed.

## References

- `references/session-audit-query.md` — Full SQL query for session token audit
- `references/fable-5-pricing-and-routing.md` — Claude Fable 5 pricing, safety-fallback rerouting, and the cron `model: None` inheritance leak (verified launch-day 2026-06-09)
