# Evaluating a NATIVE feature pitched by a third-party tutorial

A distinct sub-case of tool evaluation: the user shares a blog/Reddit/marketing post that
hypes a capability — but the capability is **already native to Hermes**, and what the post is
actually selling is an *operating model* on top of it. Don't evaluate "should I install this";
evaluate "is the pitched operating model the right fit, or do I adopt the primitive and reject
the model?"

## Tell-tale signs you're in this case

- The post links to a third-party "verified setup / CI proof" site (traffic funnel), not the
  vendor's own docs. Treat those links as marketing; the vendor docs are source of truth.
- The post says things like "two commands differ from what the docs implied" — a tell that
  their command set may not match the real CLI. **Verify every command against the live
  install** (`<tool> <subcmd> --help`), not the post.
- The underlying thing turns out to be a built-in (`hermes kanban`, a native flag, an existing
  subsystem) — so there's nothing to "install," only a usage pattern to accept or reject.

## The move: separate the PRIMITIVE from the PITCHED MODEL

1. **Verify the primitive is real and what its actual surface is.** Run `--help` on the live
   binary, list real subcommands/flags, check current board/state read-only. The post usually
   *undersells* the surface (showed 3 workflows; the CLI had 35 subcommands).
2. **Name the pitched operating model explicitly** and test it against THIS setup's hard
   constraints — not generic best practice. The constraints that decided the Kanban case:
   - **RAM ceiling.** Each worker is a full OS process (~400MB). Probe `free -h` *and swap*.
     An 8GB box with ~200MB free + Docker + HA stack cannot run a 6-process swarm (workers +
     verifier + synthesizer ≈ 2.4GB transient) without OOM/swap. Safe ceiling was 2–3 workers.
   - **No-silent-triggers rule.** The pitched model ran an *always-on in-gateway dispatcher*
     firing on a 60s tick with no human in the loop — the exact autonomy posture this user
     rejects. That alone disqualifies the upstream operating model regardless of RAM.
3. **Map the primitive against what already exists** (the Overlap lens). Kanban vs
   `delegate_task`: delegation is in-turn + ephemeral (children die on turn interruption);
   Kanban is durable + cross-session + cross-profile. The *gap* delegation can't fill is the
   only reason to adopt at all — state that gap precisely.
4. **Propose a FITTED alternative, not the upstream default.** Outcome of the Kanban case:
   adopt the durable on-disk board as a **task ledger**, but make the **agent the only
   dispatcher** via the bounded one-shot `hermes kanban dispatch --max 2 --dry-run` path —
   never the always-on tick. Keep `delegate_task` for in-turn parallel bursts and cron for
   timed idempotent jobs. The new tool earns its place ONLY for durable multi-track work that
   must survive turn-interruption; it's dead weight everywhere else.

## Verdict shape for this sub-case

Lead with: "This is a native feature, not a third-party install — the question is the operating
model." Then: primitive (real, verified surface) → pitched model (named, tested against RAM +
autonomy constraints) → fitted alternative (bounded, agent-dispatched) → where it's worth it vs
not. Log the row in `references/evaluated-tools-log.md` with verdict **Adopt-primitive /
reject-pitched-model**.
