---
name: hermes-host-migration
description: "Migrate a Hermes install to a new host: rsync flow"
version: 1.0.0
platforms: [linux]
metadata:
  hermes:
    tags: [hermes, migration, rsync, ssh, systemd, cutover, gateway]
    related_skills: [hermes-maintenance, hermes-core-update-with-bypass, t2-mac-linux-install]
    created_by: agent
load_when:
  - "moving Hermes to a new server/host/machine"
  - "setting up a second Hermes box from an existing one"
  - "gateway cutover between hosts"
  - "post-migration cron failures or SSH key trust problems"
---

# Hermes Host Migration (proven 2026-06-12: hil-1 → andrew-Macmini)

Full migration of a live Hermes install (gateway + profiles + crons + OAuth bypass)
to a new Linux host. ~2.4GB, ~5 min cutover downtime. Every pitfall below cost a
real round-trip.

## Pre-flight decisions

1. **Same user on both hosts — non-negotiable.** Audit first:
   `grep -rc "/root/" ~/.hermes/patches/ ~/.hermes/scripts/` — this session: 62 files
   with hardcoded `/root/` paths. If source runs as root, run target as root.
   Enabling root SSH on a default-Ubuntu target: add the key to
   `/root/.ssh/authorized_keys` via the sudo user; stock `PermitRootLogin
   prohibit-password` is already sufficient for key auth.
2. **Prune dead profiles before transfer** (`pre-update-*`, `stable-*`, swarm
   workers) — can halve the rsync.
3. **Map every service unit**: `find ~/.config/systemd /etc/systemd -name "hermes*"`.
   Default + per-profile gateways each need their unit moved.

## The sequence

1. **Install Hermes fresh on target** — installer lives at
   `https://hermes-agent.nousresearch.com/install.sh` (the raw.githubusercontent URL
   404s). Download-then-run; piping with args breaks (`| bash -- --skip-setup` →
   "No such file or directory"):
   ```bash
   curl -fsSL https://hermes-agent.nousresearch.com/install.sh -o /tmp/hi.sh && bash /tmp/hi.sh --skip-setup
   ```
   Fresh install gives the right venv/Python (source may be 3.11 while target OS
   ships 3.12 — the installer handles it; don't reuse target system python).
2. **Backup the fresh config** (`config.yaml.fresh-install.bak`) before rsync overwrites it.
3. **rsync HERMES_HOME**:
   ```bash
   rsync -avz --exclude='hermes-agent/' --exclude='__pycache__' --exclude='*.pyc' \
     --exclude='audio_cache/' --exclude='logs/' ~/.hermes/ root@TARGET:/root/.hermes/
   ```
   Don't be alarmed by a tiny "sent" figure — rsync deltas against the fresh
   install; verify with `du -sh` + spot-check skills/ on the target instead.
4. **Sync auth artifacts**: `~/hermes-claude-auth/`, `~/.claude/` (OAuth creds),
   systemd units → `/root/.config/systemd/user/`.
5. **Re-hook the OAuth bypass on the target — TWO traps:**
   - `install.sh` hangs over non-interactive SSH (its final `systemctl --user
     restart` blocks with no user session bus). Run its steps manually instead:
     copy `anthropic_billing_bypass.py` to `~/.hermes/patches/`, append
     `sitecustomize_hook.py` to the venv's `sitecustomize.py` if the marker is absent.
   - **PITFALL 1 fires on fresh hosts too**: install.sh's bypass file is VANILLA
     (no complexity classifier). After any install.sh contact, check
     `grep -c _classify_complexity ~/.hermes/patches/anthropic_billing_bypass.py`
     (want 2) and restore from `~/.hermes/references/patch-guard/anthropic_billing_bypass.golden.py`
     on BOTH hosts if 0 — the copy step can clobber the source-side file's sync too.
6. **Cutover**: enable+start gateways on target → verify live → stop/disable on
   source. Source stays intact as rollback until you disable it.
7. **Post-cutover sweep** (the part people skip):
   - **Out-of-repo venv packages did NOT migrate (PROVEN 2026-06-12).** rsync moves
     `~/.hermes/` but extra deps live in the venv's site-packages — the knowledge
     store (`scripts/knowledge.py`) died on the new host with `No module named
     'lancedb'`, then `'lance'`, then `'pandas'`, one missing module per attempt.
     Enumerate pins on the SOURCE first:
     ```bash
     /usr/local/lib/hermes-agent/venv/bin/python3 -m pip show lancedb pylance pandas pyarrow numpy sentence-transformers | grep -E "^Name|^Version"
     ```
     then install the full set on the target in ONE shot. Note `pylance` is a
     separate package providing the `lance` module — lancedb alone is not enough.
   - **The uv-built venv has NO pip** — `venv/bin/pip` doesn't exist and
     `python3 -m pip install` fails. Use:
     ```bash
     uv pip install --python /usr/local/lib/hermes-agent/venv/bin/python3 lancedb==X pylance==X pandas==X pyarrow==X sentence-transformers==X
     ```
     (`-m pip show` still works for read-only queries; only install is missing.)
   - Make the package set survive `hermes update` venv rebuilds: patch_guard now\n     carries `_heal_knowledge_db_packages` (sentinel-import lancedb → uv reinstall\n     the pinned set; added 2026-06-12). When adding NEW venv-dependent tooling,\n     extend that REQUIRED list AND re-sync `patch_guard.golden.py` (both-files\n     rule) — verify `md5sum` of live vs golden match after.
   - Verify: `python3 scripts/knowledge.py status` (fact count) + one real\n     semantic search returning scored hits.\n   - The knowledge-store set is NOT the whole list — tool deps also vanish:\n     `playwright`, `faster-whisper`, `firecrawl-py` were missing too (found only\n     when probed later). Diff the FULL `pip list` source-vs-target, not just the\n     modules that already crashed.
   - `hermes cron list` — read EVERY job's last-run status.
   - **Stale errors look like fresh failures.** Check the last-run TIMESTAMP
     against the migration time; pre-migration errors need no fix. Force a tick to
     prove health: `hermes cron run <job_id>`, wait, re-list, want `ok`.
   - **Cross-host SSH trust breaks silently**: any cron that scp/ssh's to peer
     hosts (kanban export → ash-1, etc.) fails until the target's key is on those
     peers. Propagate via a hop through a host that still has access:
     `ssh root@TRUSTED 'ssh root@PEER "echo KEY >> /root/.ssh/authorized_keys"'`.

## Full-host audit (MANDATORY — user-corrected 2026-06-12)

Sweeping only `~/.hermes/` is NOT a complete migration; it earned an explicit
correction ("look at every corner of hil-1"). Hermes-adjacent data lives all
over the home dir. After the sweep above, diff the ENTIRE source home dir and
classify every item as migrate / stays / obsolete:

```bash
ssh SOURCE 'ls /root/' > /tmp/src.txt; ls /root/ > /tmp/dst.txt
diff /tmp/src.txt /tmp/dst.txt | grep '^<'
diff <(ssh SOURCE 'ls ~/.hermes/scripts/') <(ls ~/.hermes/scripts/) | grep '^<'
diff <(ssh SOURCE 'ls ~/.hermes/references/') <(ls ~/.hermes/references/) | grep '^<'
```

Known out-of-HERMES_HOME items that MUST migrate (this host):
- `/root/AGENTS.md` + `/root/CONTEXT.md` (project-context injection)
- `~/Documents/Obsidian Vault/` (honcho-bridge output target — a fresh-install
  stub dir on the target MASKS the missing vault: bridge "succeeds" writing
  into an empty shell; compare SIZE and .md COUNT, not existence)
- project dirs referenced in MEMORY (`/root/projects/...`), user tooling dirs
- after vault sync, re-index: `knowledge.py index-vault` (fact count should jump)

Classify-don't-copy: `.bak-*` files (historical, leave), old snapshots/tarballs
(obsolete, leave), running Docker apps + their CF tunnel `.cloudflared/` token
(STAY with the workload — Mealio stayed on hil-1), host-specific dev artifacts
(stay). State the stays-behind list to the user explicitly so "everything
migrated" has defined scope.

## Pitfalls

- **Verify the LIVE pubkey before handing it to anyone.** `cat ~/.ssh/id_ed25519.pub`
  at the moment of use — a key quoted earlier in a long session may no longer match
  (this session the active keypair differed from the one shared hours earlier;
  auth failed until re-read). Debug key rejections with
  `ssh -v ... 2>&1 | grep Offering` and compare fingerprints.
- **Gateway restarts sever your own session mid-migration** and produce confusing
  half-state. Before claiming cutover happened (or didn't), prove which host you're
  on: `hostname` via terminal, and check gateway PID start times. Never infer
  cutover status from logs alone — this session produced a wrong "already migrated"
  claim that needed walking back.
- A botched `sudo tee` to a remote authorized_keys can lock you out of the
  non-root user too — keep one out-of-band access path (user at the console) until
  target SSH is proven stable.
- Self-heal/patch-guard crons migrate with HERMES_HOME and keep working since
  paths are identical (same-user rule) — but they protect the GOLDEN versions, so
  step 5's golden restore is what makes the next 05:00 heal correct.

## Verification checklist (all must pass before declaring done)

```bash
ssh root@TARGET 'hostname; hermes --version'         # right box, right version
hermes cron list                                      # every job ok or explainably stale
grep -c _classify_complexity ~/.hermes/patches/anthropic_billing_bypass.py   # 2
# live turn through the gateway (message actually answered from target)
# peer-host SSH: each cross-host cron force-run returns ok
```

## Final-audit gates (PROVEN 2026-06-12 — each found a real defect)

Run these AFTER the basic checklist; presence-checks lie, behavior-checks don't:

- **PITFALL 6 lands on fresh hosts too**: copied gateway units had no
  `EnvironmentFile=` → both gateways ran with ZERO API keys in env (delegation
  401s silently). Diagnose: `tr '\0' '\n' < /proc/$(systemctl --user show -p
  MainPID --value hermes-gateway.service)/environ | grep -cE '^(DEEPSEEK|ANTHROPIC|XAI)'`
  → 0 = broken. Fix: `EnvironmentFile=-/root/.hermes/.env` under `[Service]` in
  BOTH units, daemon-reload. Restart ha-bot immediately and re-grep (want ≥1);
  restart the DEFAULT gateway last or user-triggered — it kills the live chat.
- **`hermes config check` per profile** — fresh installer may carry a newer
  config version than the rsync'd configs (28→29 here). Backup each
  config.yaml, then `hermes config migrate` + `hermes --profile <p> config
  migrate` (satellites never auto-migrate). The migration can also REORDER
  config lists (approval danger-list) — a 15-line diff vs source that's pure
  reordering is benign; compare entry COUNTS not line positions.
- **Compare core patches by MARKER COUNT, not md5.** Fresh install sits on a
  different upstream base than the source, so md5 of `gateway/run.py` etc.
  ALWAYS differs. The real check: `grep -c _bfull gateway/run.py` (want 8 / 1
  for `_bfull_retrieve(message_text)`), honcho drift marker, delegate_tool
  fallback string, sitecustomize markers (want 4) — equal counts on both hosts.
- **B-full behavioral proof**: import the engine exactly as `gateway/run.py`
  does (`importlib.util.spec_from_file_location("knowledge_bfull",
  "/root/.hermes/scripts/knowledge.py")`) and run a `search()` — scored hits
  returned = per-turn RAG functional. Journal-grepping for "bfull" proves
  nothing; it logs silently.
- **`hermes` CLI as a non-root user: `bad interpreter: Permission denied`** (PROVEN
  2026-06-12). The uv-built venv's `python` symlink resolves through
  `/root/.local/share/uv/python/cpython-*/bin/python3.11` — `/root` is 0700, so
  any other user dies at path traversal. Do NOT copy the binary out to
  `/usr/local/bin` (orphaned interpreter loses its prefix tree → "Could not find
  platform independent libraries"). Correct fix: `chmod 711 /root` (traversal
  without listing), keep the symlink. Non-root runs then print harmless
  `sitecustomize install failed (no-op)` warnings for the checkpoint hooks —
  cosmetic; `hermes --version` output below them is the success signal.
- **Skill enable/disable parity: trust `hermes skills list`, nothing else.**
  Footer gives ground truth (`88 enabled, 51 disabled` this migration). The
  system-prompt `available_skills` block is a truncated summary (showed 28) and
  grepping frontmatter for `enabled:` false-positives on references/ files and
  body text. Compare the footer counts source-vs-target.
- `loginctl show-user root | grep Linger` → `Linger=yes` or gateways die on logout.
- Source-host leftovers: system crontab entries (`@reboot ...`) pointing at
  dead `/tmp` scripts are ignorable; live Docker/redis/cloudflared belong to the
  workloads that stayed — don't migrate, don't kill.
