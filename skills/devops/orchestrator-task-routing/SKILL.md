---
name: orchestrator-task-routing
description: "Route tasks: right worker, load-balance, dispatch."
tags: [kanban, orchestration, routing, workers]
---

# Orchestrator Task Routing

## Trigger
Any time Andrew asks you to complete a task. Every repo, every domain.

## Workflow

1. **Classify domain** — what kind of work is this?
2. **Check availability** — `kanban_list(status='running')` before assigning.
3. **Pick the right worker** (domain first, then load-balance):

| Domain | Workers |
|---|---|
| Source code (any language, CSS, bugs, builds) | `coder` → `coder-b` (only two profiles exist on disk) |
| Home Assistant / home automation / wall-dash | `ha-bot` |
| Orchestration / board ops / routing | `default` |

4. **Draft the card:**
   - Title: specific, actionable
   - Body: goal, scope, constraints, acceptance criteria
   - Reference files: save to `~/.hermes/references/<topic>/` before creating the card
   - Default: `complete directly` — no review-required block unless Andrew asks
   - Tenant: associated repo name (e.g. `hermes-dispatcher`)

5. **Dispatch immediately** — create with no `initial_status` (defaults to `ready`).
   Only use `initial_status=blocked` when Andrew says hold/draft/batch.

6. **Monitor silently** — let the worker run, don't report mid-task.

7. **Verify on completion:**
   - Read the handoff comment (changed files, commit, build status)
   - Check live at the real endpoint — build success ≠ working in browser
   - Confirm committed & pushed to repo
   - Complete the card as orchestrator

8. **Report past-tense** — what shipped, commit hash, what to look at.
   Only escalate genuine decisions.

## Load-balancing rules
- Never stack 2 cards on one worker when another is free.
- Check `kanban_list(status='running')` — the running worker is busy.
- Fan out parallel independent tasks to different workers simultaneously.
- **HARD RULE — alternate at creation time, in the SAME turn:** when you create
  2+ independent cards in one turn, assign them to DIFFERENT workers as you write
  them (card A → `coder`, card B → `coder-b`). Do NOT write both to `coder` and
  plan to "rebalance later" — the dispatcher claims `ready` cards almost instantly,
  so by your next turn they're both locked to `coder` and can't be reassigned.
  The default-everything-to-`coder` habit is the #1 routing failure here; it has
  required an explicit "you're only dispatching to Coder" correction. Catch it at
  the `kanban_create` call, not after.
- If you already over-stacked and the cards are still `ready` (rare — usually too
  late), reassign with `hermes kanban reassign <task_id> coder-b`. Once `running`,
  it's locked; let it finish.
- ONLY `coder` and `coder-b` exist as profiles on disk. `coder-c`/`coder-d`/etc.
  are GHOST assignees — a card assigned to them sits `ready` forever, never claimed.
  Verify with `hermes kanban assignees` (look for "ON DISK = yes") or
  `ls ~/.hermes/profiles/` BEFORE assigning. If you assigned a ghost, recover with
  `hermes kanban reassign <task_id> coder-b`.

## Inline vs. card decision
Not every request is board-shaped. Tiny, single-file, low-risk edits Andrew asks
for in rapid back-and-forth (recolor an orb, remove an animation, tweak one CSS
value, swap a palette) are faster done INLINE: patch → `npm run build --prefix app`
→ commit → push. Reserve cards for multi-file features, new components, or anything
needing real reasoning. A string of "now change X / now remove Y" follow-ups during
active iteration = inline each one; spinning up a worker per tweak adds a ~2-min
latency tax per change for no quality gain. (Coding-delegation gate still applies to
substantial source work — this is the small-tweak carve-out, not a license to inline
features.)

## Pitfalls
- Don't default to `coder` for every task — check domain first.
- Don't create card `blocked` unless explicitly asked to hold.
- Don't add review-required acceptance criteria unless Andrew asks.
- Don't report on a task until the worker completes it.
- Headless Chromium screenshots over Tailscale come back dark/blank —
  verify JS bundle grep + build status instead; note screenshot caveat in report.
- The dispatcher promotes `ready` cards almost instantly. After `kanban_create`
  (ready), the card is often already `running` before you can act on it — an
  `kanban_unblock` will 404 with "not blocked or unknown". That's expected, not an
  error; just `kanban_list(status='running')` to confirm it was claimed.
- Workers self-block with `review-required` ONLY when the card spec told them to.
  With the complete-directly default, drop that instruction so they finish cleanly.
- A worker hitting a gated command (`systemctl restart`) correctly self-blocks
  WRITE-GATE. The dashboard restart is gateway-self-protected — Andrew runs it
  himself; provide the one-liner, don't schedule a cron.
- Inline-editing a repo while workers run on it: the working tree may carry the
  workers' uncommitted/untracked files. `git add` ONLY your specific file(s) by
  path — never `git add .` — or you'll sweep peer WIP into your commit. (`patch`
  also warns "modified by sibling subagent" — re-read before writing.)
- **A worker can push a build-broken commit.** "Completed, build passes" in the
  handoff is a self-report, not proof — workers have pushed TS that fails `tsc`
  (e.g. referenced `isHidden`/`MachineSelector` it never defined). ALWAYS run
  `npm --prefix app run build` yourself after pulling worker commits and BEFORE
  merging. If it fails, route a tight fix-card (the missing symbols, exact line
  numbers from the tsc output) to the OTHER worker — don't fix substantial source
  inline, and don't merge a red branch.
- **Merging a long-lived feature branch into a diverged base:** a squash-merge via
  the GitHub API will 405 "merge conflicts" even when only 1–2 files actually
  conflict. Rebasing a 40+ commit branch onto the base often explodes (every commit
  whose content is already upstream re-conflicts). Cleaner path: local
  `git merge origin/<base> --no-edit`, resolve the handful of real conflicts
  (`git checkout --ours <file>` when the feature branch holds the correct newer
  version — verify with a `diff` of both sides first), rebuild, push, THEN merge the
  PR via the API. If squash still 405s post-resolve, fall back to `merge_method=merge`.
