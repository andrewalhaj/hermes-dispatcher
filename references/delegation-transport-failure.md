# Delegation Transport Failure — Subagents Bypass Manifest LB (401)

> A Reflexion-style failure record (see `reflexion-pattern.md`). This failure has
> surfaced across MULTIPLE sessions with identical signature — that recurrence is
> exactly why this file exists. Read this BEFORE re-diagnosing; go straight to the fix.

## Status
**OPEN / UNRESOLVED as of 2026-06-03.** The fix has been identified but NOT applied
(blocked on the gated `config.yaml` edit, which requires Andrew's explicit approval).

## Symptom (verbatim from probe)
A minimal 1-subagent `delegate_task` probe returns:

```
status: failed
model:  deepseek-v4-pro        # <-- routed direct to DeepSeek, NOT the Manifest LB
api_calls: 1
exit_reason: max_iterations
tokens: {input: 0, output: 0}  # died before any real work
tool_trace: []                 # never executed a single tool
error: 401 - Authentication Fails, Your api key: ****_gAA is invalid
```

Tell-tale signs it's THIS failure (not something new):
- `model` is `deepseek-v4-pro` directly, not via `custom:manifest-vision`.
- `401 ..._gAA is invalid` — stale/invalid DeepSeek key.
- 0 input/output tokens + empty `tool_trace` — death at the first auth handshake.

## Root cause
The `delegation` block routes subagent traffic **directly to DeepSeek with an invalid
key**, instead of through the Manifest load balancer (`custom:manifest-vision`,
`http://178.156.246.115:8080/v1`). Because delegation does NOT inherit the main
conversation's provider, the main thread works fine while every subagent spawn 401s.
The main loop routes through Manifest correctly; delegation is the one path that doesn't.

## Fix (proposed — requires approval before applying)
Repoint the delegation/subagent provider in `~/.hermes/config.yaml` from the direct-
DeepSeek block to `custom:manifest-vision` (the same custom provider the main loop uses),
so delegation inherits Manifest routing, tiering, and the Opus→DeepSeek fallback chain.

- **Risk:** low — same endpoint already serving live main-thread traffic successfully.
  No regression possible: the current state already 401s on every spawn.
- **Constraint:** Hermes cannot write `config.yaml` directly (security gate). Either
  Andrew pastes the current `delegation:` block (key redacted) for an exact corrected
  block, or authorizes the gated edit via the split-token workaround. Snapshot before.
- **Rollback:** revert the single provider block to its prior value (capture before-state first).

## Verification (run after fix)
Re-run the same minimal probe. SUCCESS criteria:
- `status: completed` (not failed),
- `model` reflects the Manifest LB path (not bare `deepseek-v4-pro` via the bad key),
- non-zero tokens + a populated `tool_trace`,
- the subagent echoes a `PROBE_OK <timestamp>` line from `echo "PROBE_OK $(date -u +%H:%M:%S)"`.

Until this probe passes, the council pattern and any multi-subagent delegation are
unusable — they all ride this transport.
