---
name: verification-before-completion
description: "Verify before claiming done/fixed/passing."
---

# Verification Before Completion

## Overview

Claiming work is complete without verification is dishonesty, not efficiency.

**Core principle:** Evidence before claims, always.

**Violating the letter of this rule is violating the spirit of this rule.**

## The Iron Law

```
NO COMPLETION CLAIMS WITHOUT FRESH VERIFICATION EVIDENCE
```

If you haven't run the verification command in this message, you cannot claim it passes.

## The Gate Function

```
BEFORE claiming any status or expressing satisfaction:

1. IDENTIFY: What command proves this claim?
2. RUN: Execute the FULL command (fresh, complete)
3. READ: Full output, check exit code, count failures
4. VERIFY: Does output confirm the claim?
   - If NO: State actual status with evidence
   - If YES: State claim WITH evidence
5. ONLY THEN: Make the claim

Skip any step = lying, not verifying
```

## Common Failures

| Claim | Requires | Not Sufficient |
|-------|----------|----------------|
| Tests pass | Test command output: 0 failures | Previous run, "should pass" |
| Linter clean | Linter output: 0 errors | Partial check, extrapolation |
| Build succeeds | Build command: exit 0 | Linter passing, logs look good |
| Bug fixed | Test original symptom: passes | Code changed, assumed fixed |
| Regression test works | Red-green cycle verified | Test passes once |
| Agent completed | VCS diff shows changes | Agent reports "success" |
| Requirements met | Line-by-line checklist | Tests passing |

## Red Flags - STOP

- Using "should", "probably", "seems to"
- Expressing satisfaction before verification ("Great!", "Perfect!", "Done!", etc.)
- About to commit/push/PR without verification
- Trusting agent success reports
- Relying on partial verification
- Thinking "just this once"
- Tired and wanting work over
- **ANY wording implying success without having run verification**

## Rationalization Prevention

| Excuse | Reality |
|--------|---------|
| "Should work now" | RUN the verification |
| "I'm confident" | Confidence ≠ evidence |
| "Just this once" | No exceptions |
| "Linter passed" | Linter ≠ compiler |
| "Agent said success" | Verify independently |
| "I'm tired" | Exhaustion ≠ excuse |
| "Partial check is enough" | Partial proves nothing |
| "Different words so rule doesn't apply" | Spirit over letter |

## Key Patterns

**Tests:**
```
✅ [Run test command] [See: 34/34 pass] "All tests pass"
❌ "Should pass now" / "Looks correct"
```

**Regression tests (TDD Red-Green):**
```
✅ Write → Run (pass) → Revert fix → Run (MUST FAIL) → Restore → Run (pass)
❌ "I've written a regression test" (without red-green verification)
```

**Build:**
```
✅ [Run build] [See: exit 0] "Build passes"
❌ "Linter passed" (linter doesn't check compilation)
```

**Requirements:**
```
✅ Re-read plan → Create checklist → Verify each → Report gaps or completion
❌ "Tests pass, phase complete"
```

**Agent delegation:**
```
✅ Agent reports success → Check VCS diff → Verify changes → Report actual state
❌ Trust agent report
```

## Negative Claims Need Evidence Too (proven 2026-06-08)

The Iron Law is usually framed around SUCCESS claims ("tests pass", "build works"). It applies with EQUAL force to NEGATIVE / absence claims: "X isn't on disk", "the cron is no-opping", "that file is gone", "the skill doesn't exist", "feature Y is broken". A negative claim asserted without a proof command is the same violation, and it's more insidious because absence feels self-evident.

This session the agent twice asserted "the `memory-dedup-audit` skill isn't on disk → the cron is no-opping." Both were FALSE. Root causes — the two classic ways a negative claim goes wrong:

1. **Checked the wrong path.** Looked for `~/.hermes/MEMORY.md`; the real file is `~/.hermes/memories/MEMORY.md`. "Not found" at a guessed path proves nothing.
2. **Used a search whose scope didn't cover the target.** `search_files(target="files", pattern="memory-dedup-audit")` returned 0 because it matches FILENAMES, not DIRECTORY names — the skill lives in a directory of that name with `SKILL.md` inside. A 0-count from a mis-scoped search is not evidence of absence.

Before any "missing / broken / gone / no-op" claim, run the command that would prove it PRESENT and confirm that command itself is correctly targeted:
- File/dir existence: `ls -la <exact path>` and `find <root> -name <pattern>` (not a filename-only search-tool call). For skills, `skill_view(name)` is the authoritative existence check — it resolves the real skill dir.
- "Cron is no-opping": read the job's last output file (`~/.hermes/cron/output/<id>/`) and `last_status` — don't infer from a presumed-missing dependency.
- "Schema/code is broken": actually run it against the live data once.

**Absence of evidence ≠ evidence of absence — until you've run the RIGHT command at the RIGHT path.** When a prior turn's offhand claim is the thing under test, verify it into the ground before repeating it; correct the record explicitly when it was wrong, rather than building the next action on the bad premise.

## Presence ≠ Correctness: Functional Probes, Not Existence Checks (proven 2026-06-16)

The subtlest completion-claim failure is verifying that a thing **exists/responds** and reporting it as **working**. They are not the same, and a green existence check on a broken subsystem is a false positive you'll carry forward.

Proven live this session: a full system audit reported a CodeGraph MCP server "green" because the binary launched and the gateway config listed it. A later FUNCTIONAL probe (`hermes mcp test codegraph` parsing `Tools discovered: N`) showed it connected in 122ms but served **0 tools** — wired but useless. The existence check passed; the functional check failed. Same pattern recurs everywhere:

| Weak proxy (presence) | Strong probe (correctness) |
|-----------------------|----------------------------|
| Process is `active` / port is open | A real request returns the expected response |
| MCP server "connects" | `mcp test` reports tools discovered > 0 |
| Retrieval store has N rows | A canned query returns the KNOWN-right hit above the score floor |
| Index/cache exists | Its recorded commit matches the current source HEAD (not stale) |
| Config lists the integration | The integration actually serves/answers when called |
| Golden file is present | Golden content matches the live file byte-for-byte |

**Rule:** for each subsystem, define a probe that proves it *does its job*, not that it *is installed*. Row counts, "connected", "active", and "file present" are existence checks — escalate to a functional one before calling it healthy.

### The third state: UNVERIFIABLE (never silently PASS)

Binary PASS/FAIL hides the most dangerous case: a probe that *couldn't run* (capability absent, timeout, path not discoverable). Defaulting that to PASS is the silent-green trap. Use three states:
- **PASS** — functional probe ran and confirmed working.
- **FAIL** — functional probe ran and showed broken.
- **UNVERIFIABLE** — probe could not run; surfaced LOUDLY, never folded into PASS.

A green audit then means "every listed check was *verified working*," not "nothing errored." When you build a recurring audit, drive its scope from a canonical inventory file (a written subsystem list), not from memory — an unlisted subsystem is an invisible one, and you won't flag the absence of a check you didn't know to write. (Reusable harness shape lives in `scripts/health-audit-harness.py`.)

### Don't ship a wrong root cause as the "verified" finding

When a probe fails, the *cause* is itself a claim that needs verification before it lands in a golden/reference file. This session's first hypothesis for the 0-tools result was "cwd-sensitive bug"; a few more probes proved it was actually a **cold-daemon transient** (0 on first call post-restart, self-heals to N once the daemon warms). A wrong root cause written into a reference doc is worse than no note — it misdirects every future reader. Verify the diagnosis, not just the symptom, before recording it.

## The Deployed Artifact ≠ The Merged Source (proven 2026-06-23)

A whole class of "implementation failed" reports trace to a stale BUILD, not broken code. When a self-hosted app serves a **prebuilt bundle** (SPA `dist/`, compiled assets, a baked container image) and that build output is **gitignored / not part of the merge**, then `git merge` + a clean local `tsc/vite build` are BOTH green while the live site keeps serving the OLD artifact. Every layer reports success; the user sees no change and calls it a failure.

This session: ruixen-mono-chat Chat redesign was committed, merged in the PR, and `vite build` passed — yet the dashboard at :8787 rendered the old design across several rounds. Root cause: `app/dist/` is gitignored, the static server serves it directly, and **no step rebuilt `dist/` on the host after merge**. Workers pushed source; nobody regenerated the artifact the server actually serves.

**The verification chain for "deployed and live" has FOUR links, not two — check all four:**

| Link | Weak (skipped this session) | Strong probe |
|------|------------------------------|--------------|
| 1. Source merged | `git log` shows the commit | (necessary, not sufficient) |
| 2. Build succeeds | `tsc/vite build` exit 0 | (necessary, not sufficient) |
| 3. **Host artifact regenerated** | *assumed* | `rm -rf <dist>` then rebuild ON THE HOST; the server serves THIS dir |
| 4. **Live server serves the new build** | *assumed* | `curl -s <url> \| grep -o 'index-[hash].js'` matches the just-built hash; grep a **string literal** (emoji, placeholder text — survives minification) inside the served bundle to confirm the new code is in it |

Pitfalls that wasted turns here:
- **Grepping minified bundles for identifier names returns false negatives.** Production minify renames `reactionPicker` → `a`, so `grep reactionPicker dist/*.js` finds nothing even when the feature shipped. Grep **string literals** instead (emoji `👍`, placeholder copy, aria-labels) — those survive minification and prove the code is present.
- **A static FastAPI/uvicorn server does NOT need a restart to serve new `dist/` files** — it reads them off disk per request. So "I restarted the service" is not the fix and not the proof; rebuilding the dir is. (Restart matters only for backend `.py` changes.)
- **Browser caches `index.html`**, which pins a stale JS hash. After confirming the server serves the new hash, the user still needs a hard-refresh (Cmd+Shift+R) to bust their local cache. "Server is correct" and "your screen is correct" are two separate claims.

**Rule:** when the deliverable is a built/deployed artifact, "merged + builds" is link 1–2 of 4. Prove link 3 (host rebuilt the served dir) and link 4 (live URL serves the new hash, new string literal present) before claiming the change is live — and tell the user to hard-refresh. If the build output is gitignored, a host rebuild step is MANDATORY after every merge, not optional.

### Link 5: the bundle is fresh AND correct, but the BEHAVIOR still fails (proven 2026-06-24)

Even with all four links green — source merged, build clean, host `dist/` rebuilt, live server serving the new hash — a specific *interaction* can still be broken. This is the deepest false-positive: the worker's handoff said "Escape-to-close added (useEffect keydown listener)", lint was clean, build passed, the new bundle was live — and pressing Escape in the browser did nothing. The code was textually correct; it just didn't fire at runtime.

Two complementary probes caught it where reading the diff did not:

1. **Grep the BUILT bundle for the feature's string literal, not just the source.** The fix lived in `TileInfoDrawer.tsx` as `if (e.key === 'Escape') closeInfo()`. Grepping the minified bundle for `"Escape"` returned exactly ONE occurrence — and it belonged to a *different* component (chat search). The drawer's handler was effectively absent from the shipped code. A source diff can't show you this; only grepping the artifact can. (String literals like `"Escape"`, `"ArrowDown"`, aria-labels survive minification — see Link 4.)
2. **Pixel/DOM functional probe of the actual interaction.** Open the component, perform the gesture (`browser_press_key('Escape')`), then assert the state changed (drawer node gone / fixed-overlay count dropped). "The handler is in the code" is an existence check; "the drawer closed when I pressed Escape" is the functional probe. Only the latter proves the behavior.

**Root cause worth remembering (React):** a `useEffect` that registers a `window.addEventListener` *inside a component that conditionally returns `null`* (`if (!state) return null` right after the effect) is fragile — the listener may never attach on the null→non-null transition the way you expect. The robust fix is to move the global listener up to the always-mounted provider/parent (which never unmounts) and have its handler call the stable setter. So: when a keyboard/global-event handler "is in the source but doesn't fire," suspect a conditionally-rendered host component, and relocate the listener to something always mounted. (Captured here as a verification lesson — the *probe* that exposes it is the durable part: grep-the-bundle + functional-gesture, not trust-the-diff.)

**Rule:** "worker reports the handler was added" + "lint/build pass" + "bundle is live" still does NOT prove an interaction works. For any event handler / keyboard shortcut / click-to-close behavior, the completion proof is: (a) the feature's string literal appears in the *served* bundle in the *right* component's vicinity, and (b) a live gesture produces the expected state change.

## Why This Matters

From 24 failure memories:
- your human partner said "I don't believe you" - trust broken
- Undefined functions shipped - would crash
- Missing requirements shipped - incomplete features
- Time wasted on false completion → redirect → rework
- Violates: "Honesty is a core value. If you lie, you'll be replaced."

## When To Apply

**ALWAYS before:**
- ANY variation of success/completion claims
- ANY expression of satisfaction
- ANY positive statement about work state
- Committing, PR creation, task completion
- Moving to next task
- Delegating to agents

**Rule applies to:**
- Exact phrases
- Paraphrases and synonyms
- Implications of success
- ANY communication suggesting completion/correctness

## The Bottom Line

**No shortcuts for verification.**

Run the command. Read the output. THEN claim the result.

This is non-negotiable.
