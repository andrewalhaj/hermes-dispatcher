# Companion service serves WRONG / ZERO data — port-squat + poisoned HERMES_HOME

A deployed dashboard (or any companion service) returns 200 with **empty or wrong
data** — Insights all zeros, Memory Galaxy shows 1 node instead of ~27, kanban
counts blank — even though the code, YAML, and logs all look clean. Server-side
green is a false positive for data-layer death. This recipe root-causes it at the
process/env layer, where the real bug lives.

## Root cause class (verified 2026-06-22, hermes-dispatcher :8787)

A **rogue background process squatted the port** with a leaked profile env. A
worker profile (e.g. `coder-b`) had manually launched a bg `uvicorn` and leaked
`HERMES_HOME=/root/.hermes/profiles/coder-b` into it. That process grabbed `:8787`
**before** the real systemd unit could bind, so the live API read every data route
from the WRONG tree:

| Route reads | poisoned path (live, WRONG) | real path |
|---|---|---|
| `kanban.db` | `/profiles/coder-b/kanban.db` → doesn't exist → all-zero Insights | `/root/.hermes/kanban.db` (real tasks) |
| `memories/*.md` | empty dir → 0 galaxy nodes | MEMORY.md + USER.md |
| `references/` | 1 file → the lone `ref-0` node | 72 files |

The single galaxy node the API returned (`write-gate-audit.log`) was *literally the
only file* in the poisoned profile's references dir — that's the dead-to-rights tell.

A frequent **second, overlapping** cause: the squatting process started before a
later code edit, so it also runs **stale code** (Python imports once; post-startup
edits to route files never load). One restart fixes both at once.

## Diagnosis recipe (read-only — no gate)

```bash
# 1. WHO actually serves the port (not what systemd THINKS) — MainPID can be 0
#    while a bg process answers 200s.
PID=$(ss -tlnp 2>/dev/null | grep ':<port>' | grep -oP 'pid=\K[0-9]+' | head -1)
echo "serving PID = $PID"
tr '\0' ' ' < /proc/$PID/cmdline; echo                 # exact argv
stat -c '%y' /proc/$PID                                  # start time
tr '\0' '\n' < /proc/$PID/environ | grep -i HERMES_HOME  # THE smoking gun
ls -l /proc/$PID/cwd

# 2. compare process start time against route-file mtimes → stale code?
stat -c '%y' <repo>/<edited_route>.py

# 3. prove the data-path consequence: what the poisoned tree actually holds
ls /root/.hermes/profiles/<bad-profile>/references/ | wc -l   # tiny → confirms
ls /root/.hermes/references/ | wc -l                          # real count
```

If live `HERMES_HOME` ≠ `/root/.hermes`, or process-start predates a route edit,
you've found it. Don't theorize past this — the env var IS the proof.

## The fix — just kill the squatter (one gated command)

Counter-intuitive but verified: you usually do **NOT** need to hand-relaunch
anything. These services are real systemd units (`systemctl status <name>` →
`enabled`, auto-restart). The rogue process was just **squatting the port** the unit
wanted. Free the port and systemd's own unit rebinds instantly with the CORRECT env
baked into its unit file:

```bash
kill <squatter-pid>          # SIGTERM, not -9
sleep 2
ss -tlnp | grep ':<port>'    # a NEW pid (parent = PID 1) should already be bound
tr '\0' '\n' < /proc/<newpid>/environ | grep -i HERMES_HOME   # now /root/.hermes
systemctl status <name> --no-pager | head -8                  # active, Main PID = newpid
```

## Verify LIVE through the public tunnel (server-side 200 is not enough)

```bash
curl -s https://<public-host>/api/insights | python3 -c "import sys,json;d=json.load(sys.stdin);print(d.get('tasks_today'), d.get('by_status'))"
curl -s https://<public-host>/api/memory/galaxy | python3 -c "import sys,json;d=json.load(sys.stdin);n=d.get('nodes',d if isinstance(d,list) else []);print('nodes:',len(n))"
systemctl is-enabled <name>   # survives reboot
```

## Hardening — stop the recurrence

Hard-pin `HERMES_HOME` in the launch wrapper so a leaked worker env can NEVER
repoint the data routes again. Have the systemd unit's `ExecStart` call a wrapper
that `export`s it explicitly rather than inheriting:

```bash
#!/usr/bin/env bash
export HERMES_HOME=/root/.hermes      # pin, do not inherit
cd <repo> || exit 1
exec ./.venv/bin/uvicorn server:app --host 0.0.0.0 --port <port> --log-level warning
```

## Pitfalls / corrections

- **`MainPID=0` + working curls = a bg process is squatting, not systemd serving.**
  Trust `ss -tlnp` + `/proc/<pid>/environ`, never `systemctl`'s view of the PID.
- **MYTH (disproven 2026-06-22): "cloudflared drops when uvicorn restarts."** Not
  true for this setup — cloudflared is a SEPARATE daemon with its own token; killing
  uvicorn leaves the tunnel up. Don't avoid `systemctl`/`kill` out of this fear.
- **Don't hand-relaunch a bg uvicorn as the fix** — that just recreates the
  squatter. Kill it and let systemd rebind. Hand-relaunch only if there genuinely is
  no systemd unit (check `systemctl status` first).
- **`scripts/knowledge.py`, not `knowledge.py`.** The cold-store query tool lives at
  `/root/.hermes/scripts/knowledge.py`; the bare path 404s.
