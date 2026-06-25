# Worker "artifact-write" bug — RESOLVED (2026-06-08, Hermes v0.16.0)

## TL;DR (the resolution)
This was **never a worker bug**. It was a **verifier design mismatch**. Workers were posting
real analysis to the **Kanban blackboard** (structured `kanban_comment` + `kanban_complete`
summary/metadata) — exactly as the native `KANBAN_GUIDANCE` protocol intends. The verifier
SOUL had been written to check the **filesystem** for deliverable files, found none (because
analysis work produces no files), and blocked every run as "fabricated." The workers were
fine the whole time; the gate was looking in the wrong place.

**Fix: gate on blackboard SUBSTANCE, not the filesystem.** After the fix, swarm run #3
passed cleanly end-to-end (verifier `{"gate":"pass"}` → synthesizer fired → done).

## The two-layer rule (the durable lesson)
For **research / analysis** swarms, the deliverable IS the blackboard handoff. Do NOT demand
files on disk. Only **code/document-generation** tasks should produce files — and then the
verifier should check the path the worker actually cites.

This is dictated by the native protocol: `KANBAN_GUIDANCE` (hardcoded in
`agent/prompt_builder.py`, auto-injected into every worker) step 5 says complete via
`kanban_complete(summary=, metadata=)` "naming concrete artifacts" — the *handoff* is the
surface, not the filesystem. `HERMES_KANBAN_WORKSPACE` IS set in worker env
(`hermes_cli/kanban_db.py` sets `env["HERMES_KANBAN_WORKSPACE"]`), but writing a file there
is OPTIONAL and only relevant when the task genuinely yields an artifact.

## The original misdiagnosis (why it took 3 runs)
The first verifier SOUL imported a **coding-worktree mental model** (deliverables = files on
disk) into a **research swarm** (deliverables = blackboard handoffs). Runs 1–2 blocked on
"missing files"; the independent filesystem checks (`find` → 0 hits, empty scratch dirs, no
`write_file` in worker session dump) were all TRUE — they just measured the wrong thing. The
trap was reading "no file on disk" as "fabricated" when it actually meant "analysis handed
off via comment, as designed."

## The fix applied (all SOUL + AGENTS.md, both auto-injected layers)
- **`swarm-verifier` SOUL** rewritten: read `kanban_show` on root + each worker; judge the
  SUBSTANCE of comments/metadata adversarially; pass with metadata `{"gate":"pass"}` when
  complete; only require a file when the TASK explicitly demanded one. Removed all
  "check the filesystem" language.
- **`swarm-worker-a/b/c` SOUL** rewritten: "deliverable surface is the blackboard, not the
  filesystem; put real substance in `kanban_comment`; only `write_file` if the task demands a
  concrete artifact; never name a file/path/line-count/source you didn't actually produce;
  block honestly if you can't complete."
- **Worker + synthesizer `AGENTS.md`** rewritten to match (the OLD AGENTS.md still said
  "verifier checks your output against the filesystem… write your deliverable to a real file"
  — a SECOND copy of the same wrong contract that contradicted the corrected SOULs). Verifier
  excluded from the shared AGENTS.md (keeps its distinct skeptical-gate SOUL).
- Verified: zero "against the filesystem" / "write your deliverable to a real file" strings
  remain in any swarm profile's SOUL or AGENTS.md; blackboard model consistent across both
  layers and all profiles.

## PITFALL — fix BOTH instruction layers
SOUL.md and AGENTS.md BOTH auto-inject into a worker. Fixing only the SOUL leaves a
contradictory AGENTS.md in play (this exact trap happened — the grep that surfaced the stale
AGENTS.md is what caught it). When changing a worker's deliverable contract, grep every
profile's SOUL **and** AGENTS.md for the old language and update both.

## Clean run #3 evidence (the fix verified)
- Goal: caching-strategy comparison (same as the run-2 that blocked).
- Workers (flash): 41–59s each, parallel. Verifier (Opus): ~1m → **PASS**. Synthesizer
  (deepseek-pro): ~2m → done. **Total ~4 min, all 5 cards `done`.**
- Verifier verdict (real): *"Gate PASS. All three worker handoffs verified against the
  goal: each covers cache-aside, write-through…"* — substance-based, not a rubber-stamp.

## If you ever DO need files-on-disk (code-gen swarms)
Make a verifier VARIANT that checks the path the worker cites (and have workers actually
`write_file` + read-back). Keep it separate from the analysis verifier — don't make the
analysis gate demand files. The current `swarm-verifier` is tuned for analysis/research.
