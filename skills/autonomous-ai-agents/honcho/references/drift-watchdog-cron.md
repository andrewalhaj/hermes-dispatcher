# Honcho Drift-Correction Watchdog — recipe + verified pitfalls

A durable pattern for grinding down representation-layer drift on a long-lived peer.
Built and verified 2026-06-08 for Andrew's `default` profile. Pairs with the
"Drift-Watchdog Pattern" subsection in SKILL.md.

## Why it exists

Editing the peer card (`honcho_profile card=[...]`) fixes the authoritative layer
instantly, but the **dialectic re-derives** the same false facts from the raw
observation log on its next cadence cycle. The injected `memory-context` block
therefore stays dirty for turns/sessions after a clean card write. A daily cron
keeps planting premise-negating conclusions so the representation converges and
stays converged, without the user having to re-correct every session.

## Components

### 1. The blocklist file (single source of truth)

`~/.hermes/references/honcho-confabulation-blocklist.md` — three sections:

- **Blocked terms** — table of `term | reality`. Each "reality" is the exact
  ground-truth sentence the cron will plant as an `honcho_conclude` when that term
  reappears as an asserted fact.
- **Ground-truth to re-assert** — standalone true statements.
- **Known-TRUE — do NOT flag** — the allowlist. Real things that *resemble*
  confabulations and must never be negated. This is the LanceDB guard: LanceDB IS
  installed/active; `claude-opus-4-8`, `deepseek-v4-flash`, `deepseek-v4-pro` are
  real configured models. Without this section a pattern-match watchdog will
  scrub live config.

Keep blocked-vs-true precise. Example of a fix this session: the entry
`"Opus 4.8 preferred" | no such preference/model` was WRONG — `claude-opus-4-8`
is a real model; only a *user preference* for it is false. Reworded to flag
`Andrew "prefers Opus 4.8" (as a user preference)` and added the bare model name
to Known-TRUE.

### 2. The cron job

- Schedule: daily (e.g. `30 6 * * *`), `deliver: local`, repeat forever.
- Silent-by-default: clean run emits exactly `CLEAN — no drift detected`, saved
  locally, nothing sent. Drift run alerts the Cron channel (`-1003947663220`).
- Toolset: leave broad enough that `honcho_*` + `file` + `send_message` all load.
  (`honcho_*` tools are NOT guaranteed in a restricted cron run — if absent, the
  job must fall back to the SDK; see `direct-sdk-card-access.md`.)

### Cron prompt skeleton (derive terms from the FILE, do not hardcode)

```
STEP 1 — Read /root/.hermes/references/honcho-confabulation-blocklist.md.
  Parse the "Blocked terms" table for scan terms AND the
  "Known-TRUE — do NOT flag" section for the allowlist.
STEP 2 — Read the live card: honcho_profile(peer="user")  (and peer="ai").
STEP 3 — Discriminate the READ first:
  - If the card came back populated → proceed to scan.
  - If it came back empty/None UNEXPECTEDLY (you have a known-populated baseline)
    → DO NOT report CLEAN. Alert: "⚠️ drift cron could not read curated card —
      manual check needed." Stop.
STEP 4 — Scan populated card for any Blocked term that is NOT in Known-TRUE,
  asserted as a fact about the peer. A term inside a negation ("Sanja is NOT
  real") is the fix working, not drift — skip it.
STEP 5 — Decision:
  - No blocked term → respond exactly: CLEAN — no drift detected.
  - Drift → (a) honcho_conclude each matching reality statement;
            (b) re-assert clean card via honcho_profile(card=[...]),
                preserving genuine facts, stripping false ones;
            (c) send_message to the Cron channel listing terms corrected.
```

## The two silent-failure pitfalls (both hit this session)

### Empty ≠ clean (false NEGATIVE)
A fresh-context run read the curated card as `None` and concluded
"empty card asserts no facts → CLEAN" — while a direct `honcho_profile(peer="user")`
in the live session returned 22 real facts. The cron's isolated session resolved
the peer/observer differently and got an empty read. A watchdog that passes
because it saw *nothing* is blind to real drift. Fix: the prompt must treat an
unexpected empty/None read as an ERROR-and-alert, not a CLEAN result. Anchor on a
known-populated baseline so "empty" is recognized as anomalous.

#### ROOT CAUSE + the real fix: pin the explicit peer ID (do NOT use `peer="user"`)
The "different peer/observer resolution" above has a concrete, verified cause and a
permanent fix — found 2026-06-08 by enumerating the workspace via the SDK:

- The `peer="user"` **alias** resolves contextually. In an interactive `default`-profile
  session it binds to the real operator peer; in an isolated cron run (fresh session,
  running as OS user `root`) it binds to a peer literally named **`root`**, which has an
  empty card and 0 conclusions. Same alias, two different peers → the empty read.
- Enumerate the truth instead of trusting the alias. The workspace is **not** `default`
  (the SDK's default workspace_id) — list workspaces and peers with the key from
  `~/.hermes/.env`:
  ```bash
  set -a; source /root/.hermes/.env; set +a
  python3 - <<'PY'
  import os; from honcho import Honcho
  key=os.environ["HONCHO_API_KEY"]
  for w in Honcho(api_key=key).workspaces():
      wid=getattr(w,'id',w); hw=Honcho(api_key=key,workspace_id=wid)
      for p in hw.peers():
          pid=getattr(p,'id',p)
          try: n=len(hw.peer(pid).get_card() or [])
          except Exception: n='?'
          print(wid, pid, n)
  PY
  ```
  This session's result: workspace=`hermes`; operator peer=`8878729385` (the Telegram ID,
  ~22-26 facts); AI peer=`hermes` (22 facts); `root` peer=empty. (SDK API:
  `h.workspaces()`, `h.peers()`, `h.peer(id).get_card()` — NOT `get_peers()`; needs
  `api_key=` explicitly even when env is set.)
- **The fix: pin the explicit operator peer ID in the cron prompt** — replace every
  `peer="user"` with `peer="8878729385"` (the actual ID for that workspace). Pinning
  bypasses alias resolution so the cron reads the SAME card the live session sees,
  regardless of which OS user the run executes as. Verified: after pinning, the cron read
  the full 22-fact card and returned a true CLEAN; before pinning it hit empty `root` and
  fired the fail-loud alert. Keep the fail-loud check too — it's the safety net that
  *caught* this bug instead of silently passing.

### Hardcoded scan list (false POSITIVE)
The original prompt embedded its own copy of the term list including `LanceDB` and
bare `"Opus 4.8"`. After both moved to Known-TRUE in the blocklist FILE, the
prompt's embedded copy was stale and would flag real config as drift. Two sources
of truth always diverge. Fix: derive scan terms from the file at runtime; never
duplicate the list into the prompt.

## Verification

- After creating, run once on-demand (`cronjob run <id>`) and read the output
  file under `~/.hermes/cron/output/<id>/`. Confirm it returns `CLEAN` on a clean
  card AND does not false-positive on negation statements already present.
- Re-run after any blocklist edit to confirm Known-TRUE terms are not flagged.
- Cross-check the cron's card read against a direct `honcho_profile` in your live
  session — if they disagree (cron sees empty, you see populated), the read-path
  discriminator above is doing real work.

## Rollback

`cronjob remove <id>` + delete the blocklist file. Read-mostly job; only writes to
Honcho (never infra), so rollback is clean.
