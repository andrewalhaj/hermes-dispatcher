# Swarm Introspection Doctrine

How to author kanban-swarm dispatches that audit/introspect the **default profile's own**
state (cron, references, config, state.db) without false "missing" results.

**Status:** verified 2026-06-08 (first real swarm run). The swarm is mechanically proven —
autonomous dispatch works, and the Opus verifier independently re-checks ground truth and
correctly BLOCKS bad handoffs (it caught 2 of 3 workers falsely reporting "0 cron jobs /
file missing" and refused to pass garbage to the synthesizer).

## The gotcha (root cause)

The filesystem is **SHARED**, not isolated — every profile lives under `/root/.hermes/`,
and a worker can read `/root/.hermes/...` absolute paths fine (worker-A did, correctly).

But each swarm worker profile has its **OWN** profile dir with:
- an **empty `cron/jobs.json`** (no jobs) — so `hermes cron list` from a worker returns "0 jobs"
- **no `references/` dir** — so relative/profile-scoped lookups of reference files miss
- its **own `state.db`** (this isolation is INTENTIONAL — prevents SQLite contention between
  parallel workers; do NOT break it)

So a worker that introspects via **profile-scoped `hermes` subcommands** or **relative paths**
reads its own empty profile and reports the default profile's real artifacts as "missing."
That's a false negative ("empty ≠ missing"), not real drift.

## The fix — dispatch DOCTRINE (not a config/profile change)

When a swarm task must inspect default-profile state, the **task prompt** must:

1. **Give absolute paths** to every default-profile artifact, e.g.
   `/root/.hermes/cron/jobs.json`, `/root/.hermes/references/<file>.md`,
   `/root/.hermes/config.yaml`, `/root/.hermes/memories/MEMORY.md`.
2. **Forbid profile-scoped introspection commands** — explicitly: "read files/DBs directly
   (cat/read/python sqlite3 on the absolute path); do NOT use `hermes cron`, `hermes profile`,
   or any profile-scoped `hermes` subcommand to introspect the default profile — they resolve
   to YOUR empty worker profile, not default's."
3. For DB reads, point at the absolute db path and use the Python `sqlite3` module
   (the `sqlite3` CLI binary is not installed on this host).

This is purely how the goal/worker cards are authored. Zero infra change, zero risk.

## What NOT to do

**Do NOT "align worker cwd/profile" to the default profile.** It looks like the obvious fix
but it points workers at default's `state.db` / kanban store, breaking the per-profile
`state.db` isolation that is the entire reason the swarm pod has separate profiles. That trades
a cosmetic audit bug for a real parallel-write/concurrency regression. The doctrine above
achieves correct introspection while preserving isolation.

## When the swarm is the right tool at all

Parallel, decomposable, independent read/analysis work (audit N independent files, research N
topics). NOT sequential dependency chains (probe→diagnose→gate→apply→verify) — those stay with
the orchestrator directly, which also keeps the stronger Sonnet-4.6/Opus reasoning in the loop.
