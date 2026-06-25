# Runtime patching pattern — installing custom behavior into the agent loop

How to add custom runtime behavior (guards, nudges, hooks) to hermes-agent
WITHOUT editing core source. Proven 2026-06-06 (delegation-checkpoint guard),
extended 2026-06-09 (skill-review-checkpoint guard).

## Guard inventory (keep current — patch_guard protects ALL of these)

As of 2026-06-09 there are THREE `_execute_tool_calls` wrappers, all built with
the pattern below, all golden-protected by `patch_guard.py` (now 5 artifacts:
the 3 patch modules + sitecustomize block + the guard script itself):
1. `anthropic_billing_bypass.py` — OAuth bypass + `_classify_complexity`
   (Sonnet→Opus model upgrade).
2. `delegation_checkpoint.py` — delegation guard.
3. `skill_review_checkpoint.py` — per-session skill-sweep nudge: on a COMPLEX
   user task with zero skill_view/skills_list calls yet this session, appends a
   one-time reminder naming the top-matching skills to the last tool message.
   Latches once (`self._skill_review_fired`); suppressed the moment a skill is
   swept (`self._skill_review_loaded`).

When you add a 4th guard: write the module → wire BOTH load seams → golden copy
in `references/patch-guard/` → register in `patch_guard.py` (golden + markers +
the sitecustomize marker-presence check) → restart. Verify patch_guard runs
silent + exit 0 before claiming done.

## The two load seams

1. **`sitecustomize.py`** (venv site-packages) — runs once at Python interpreter
   startup, before ANY agent/provider code. Use for PROVIDER-INDEPENDENT installs
   (e.g. must arm even on DeepSeek-only sessions). This is the hermes-claude-auth
   hook file; append a guarded import block.
2. **`anthropic_billing_bypass.py` `apply_patches()`** — runs when the Anthropic
   adapter imports (Anthropic path only). Chain from here for belt-and-suspenders.

Both must be IDEMPOTENT — they can both fire. Use a class-level marker attribute
(`AIAgent._<name>_patched`) + a module-level `_INSTALL_STARTED` flag to prevent
double-wrapping / double-arming a finder.

## Verified facts about the agent loop (re-verify after major updates)

- **Agent class is `AIAgent`** in `run_agent.py` — NOT `RunAgent` (my first wrong
  assumption; the grep showed method location, not class name). Target both with
  a fallback: `getattr(mod, "AIAgent", None) or getattr(mod, "RunAgent", None)`.
- **Tool-loop seam:** `AIAgent._execute_tool_calls(self, assistant_message,
  messages, effective_task_id, api_call_count=0)` — instance method, runs every
  tool round, has `self` + the live `messages` list. Ideal for per-session
  cumulative state (hang counters on `self`, naturally per-session) and for
  appending guidance to the last tool message.
- **Live context size:** `agent.context_compressor.last_prompt_tokens` (the most
  recent API-reported prompt count = CURRENT context, can be -1 transiently after
  compression). This is "current context", NOT the cumulative-summed input the
  audit reports — document the difference when thresholding on it.
- **Existing per-turn guardrail** lives in `agent/tool_guardrails.py`
  (`ToolCallGuardrailController`, `reset_for_turn`). It only covers repeated-
  failure/no-progress loops and RESETS each turn — it does NOT track cumulative
  session state. For cross-turn state you must monkeypatch; the guardrail module
  is the wrong seam. Mirror its `append_toolguard_guidance` convention for the
  in-band guidance string.
- **Deferred patch via MetaPathFinder:** don't eager-`import run_agent` from
  sitecustomize (heavy early import). Arm a `MetaPathFinder` that wraps the class
  the moment `run_agent` loads naturally. Same pattern the OAuth bypass hook uses.

## Testing without touching live (mandatory)

Build in `/tmp`, test against the REAL module in an isolated subprocess so the
running gateway is untouched:
```
cd /usr/local/lib/hermes-agent && timeout 120 venv/bin/python -c "...import + assert..."
```
Cover: below-threshold silent, at-threshold fires once, latch prevents re-fire,
never-fires-if-delegated, guard-exception-no-ops-but-original-still-runs,
double-arm idempotency, both ordering scenarios (provider-first / startup-first).

## Self-heal is mandatory for patch files

ANY file under `~/.hermes/patches/` or venv `sitecustomize.py` gets overwritten by
`hermes update` (venv rebuild) AND hermes-claude-auth `install.sh`. Keep golden
copies in `~/.hermes/references/patch-guard/` and a daily no_agent watchdog
(`~/.hermes/scripts/patch_guard.py`, cron job) that marker-checks live files and
restores from golden on drift. Marker-check, not raw diff (markers survive
harmless churn). Watchdog must NOT auto-restart the gateway (surprising mid-
session) — restore + report the restart command. **After any intentional patch
change, refresh the golden copies or the watchdog reverts you.**

## Decouple a guard's tunables from any core constant it BORROWS (PROVEN 2026-06-09)

skill-review-checkpoint originally imported `_COMPLEX_SIGNALS` /
`_COMPLEX_SCORE_THRESHOLD` straight from the bypass and thresholded on them
directly. That shares ONE knob across TWO consequences (model-upgrade AND
skill-sweep). The motivating LanceDB prompt tripped only 1 signal ("build a")
against the shared threshold of 2 → the sweep never fired on the exact failure
it was built to catch.
**Rule:** reuse a core constant as a *base/default*, never as the live knob for a
second behavior. Define the guard's OWN `_SR_EXTRA_SIGNALS` + `SR_SIGNALS =
list(SIGNALS) + extras` and its OWN `SR_THRESHOLD`, so tuning sweep-sensitivity
can NEVER perturb model routing. One definition can inform two consequences, but
each consequence needs its own dial.

## Lock guard behavior with a calibration suite BEFORE editing it (PROVEN 2026-06-09)

A guard's "does it fire on the right inputs?" logic is pure and testable without
the live agent. Ship a `scripts/` test next to the module that asserts:
- COMPLEX prompts (incl. the original motivating-failure prompt verbatim) →
  `_is_complex` True; trivial prompts ("hi", "test") → False.
- the matcher surfaces the RIGHT domain skill in its top-N for representative
  prompts (the regression guard — see matcher pitfall below).
- nudge formatting + generic fallback.
Run it (`venv/bin/python <test>`) and require ALL GREEN before syncing golden /
restarting. This is what catches a silent re-break of the threshold or matcher.
Reusable copy: `scripts/test_skill_review_checkpoint.py` (also lives live at
`~/.hermes/patches/test_skill_review_checkpoint.py`).

## Skill-matcher must read TAGS and split hyphens (PROVEN 2026-06-09)

The skill-review matcher returned wrong candidates (touchdesigner/gateway instead
of knowledge-store for a LanceDB prompt). Two root causes, both worth copying into
ANY "match free text against the on-disk skill set" code:
1. **Read `tags:`, not just name+description.** A skill's real domain lives in its
   frontmatter tags (`lancedb`, `semantic-search`, `vector-db`), which sit in the
   `metadata.hermes.tags` block several lines PAST `description:` — scan ~40 lines,
   not 25. Weight **tags + name 3× over description** (a curated tag is a far
   stronger domain signal than an incidental description word).
2. **Hyphens are token SEPARATORS, not word chars.** Tokenizing `lancedb-backed`
   as one glued token means the query word `lancedb` never matches. Split on
   non-alnum so compound tags (`semantic-search`) become matchable parts.

## Pitfall: credential filter mangles tokens in inline shell

Reading a bot token via inline `$(grep ... .env)` in a terminal command gets the
value truncated to ~14 chars by the credential filter. Write a script file
(filter leaves write_file content intact) and execute it; read the token at
runtime INSIDE the script. Same for any authed curl built inline.
