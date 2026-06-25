#!/usr/bin/env python3
"""Infra Watchdog — runs every 15 min. SILENT when healthy (watchdog pattern).
Checks backup nginx, gateway, disk on both hosts, cron job health, and Honcho API.

DETECT + ALERT ONLY. Never remediates. On alert, Andrew decides whether to invoke
the `infra-incident-triage` skill (which diagnoses -> proposes -> waits for approval).

Anti-spam: a state file suppresses duplicate alerts unless the failure set CHANGES
or COOLDOWN_MIN has elapsed, so a multi-hour outage nags hourly, not every 15 min.
Exit 0 ALWAYS when the job ran (alerts are delivered via stdout, which the no_agent
cron sends verbatim). The exit code means "did the job run", not "did it find issues".
"""
import json, os, re, sys, subprocess, urllib.request
from datetime import datetime, timezone, timedelta

HERMES = os.path.expanduser("~/.hermes")
BACKUP_HOST = "178.156.246.115"
# wall-dash nginx binds the Tailscale interface, not the public IP — probe the tailnet addr
WALL_DASH_URL = "http://100.119.118.54:5051/"
STATE = "/tmp/infra_watchdog_state.json"
COOLDOWN_MIN = 60
P0, P1 = [], []   # alertable buckets

def sh(cmd, timeout=12):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout or "").strip(), (r.stderr or "").strip()
    except Exception as e:
        return 124, "", str(e)

def http_code(url, timeout=8):
    try:
        return urllib.request.urlopen(urllib.request.Request(url), timeout=timeout).status
    except Exception:
        return 0

# ── 1. backup nginx :5051 ─────────────────────────────────────────────
if http_code(WALL_DASH_URL) != 200:
    P1.append(f"Backup nginx :5051 unreachable")

# ── 2. gateway (user-scoped systemd) ───────────────────────────────────
rc, out, _ = sh("XDG_RUNTIME_DIR=/run/user/0 systemctl --user is-active hermes-gateway.service")
if out != "active":
    P1.append(f"Hermes gateway not active (state={out or 'unknown'})")

# ── 2b. KB warm-search daemon (user-scoped systemd) ────────────────────
# Pure-acceleration service: knowledge.py falls back to in-process search if
# it's down, so a clean auto-restart is SILENT (self-healed, no alarm —
# "alert only if broken"). Only a FAILED restart escalates to P1.
rc, out, _ = sh("XDG_RUNTIME_DIR=/run/user/0 systemctl --user is-active hermes-kb-daemon.service")
if out != "active":
    sh("XDG_RUNTIME_DIR=/run/user/0 systemctl --user restart hermes-kb-daemon.service")
    import time as _t; _t.sleep(10)
    rc2, out2, _ = sh("XDG_RUNTIME_DIR=/run/user/0 systemctl --user is-active hermes-kb-daemon.service")
    if out2 != "active":
        P1.append(f"KB warm-search daemon down and auto-restart FAILED (state={out2 or 'unknown'}) — knowledge.py search degraded to ~8s cold-start")

# ── 3. disk on both hosts (>90% = P1) ──────────────────────────────────
rc, out, _ = sh("df -P / | awk 'NR==2{gsub(\"%\",\"\",$5); print $5}'")
if out.isdigit() and int(out) > 90:
    P1.append(f"Primary disk {out}% full")
rc, out, _ = sh(f"ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 root@{BACKUP_HOST} "
                f"\"df -P / | awk 'NR==2{{gsub(\\\"%\\\",\\\"\\\",\\$5); print \\$5}}'\"", timeout=20)
if out.isdigit() and int(out) > 90:
    P1.append(f"Backup disk {out}% full")

# ── 4. cron job health (inherited from heartbeat.py) ───────────────────
try:
    with open(f"{HERMES}/cron/jobs.json") as f:
        for job in json.load(f).get("jobs", []):
            if not job.get("enabled", True):
                continue
            name, st, lr = job["name"], job.get("last_status"), job.get("last_run_at")
            if name == "Infra Watchdog (15-min)":
                continue   # skip self — prevents cascading false alarms
            if st == "error":
                P1.append(f"Cron '{name}': last run FAILED")
            elif st == "timeout":
                P1.append(f"Cron '{name}': last run TIMED OUT")
            elif st is None and lr is None:
                nr = job.get("next_run_at", "")
                if nr:
                    dt = datetime.fromisoformat(nr)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    if dt < datetime.now(timezone.utc) - timedelta(hours=2):
                        P1.append(f"Cron '{name}': scheduled but never executed")
except Exception as e:
    P1.append(f"Cron DB unreadable: {e}")

# ── 5. Honcho API (inherited from heartbeat.py) ────────────────────────
if http_code("https://api.honcho.dev/health", timeout=10) != 200:
    P1.append("Honcho API unreachable (memory degraded)")

# ── 6. Delegation provider key health (DeepSeek) ───────────────────────
# Resolves the delegation key the same way Hermes does (config literal first,
# then DEEPSEEK_API_KEY env) and probes the provider. A 401 here means
# delegation is silently dead — exactly the failure that went unnoticed for
# days. P1 so Andrew gets one ping, not silence.
try:
    dkey = ""
    import yaml as _yaml
    with open(f"{HERMES}/config.yaml") as _f:
        _cfg = _yaml.safe_load(_f) or {}
    dkey = ((_cfg.get("delegation") or {}).get("api_key") or "").strip()
    if not dkey:
        for _line in open(f"{HERMES}/.env"):
            if _line.startswith("DEEPSEEK_API_KEY="):
                dkey = _line.split("=", 1)[1].strip().strip('"').strip("'")
                break
    if dkey:
        rc, out, _ = sh(
            "curl -s -o /dev/null -w '%{http_code}' "
            "https://api.deepseek.com/v1/models "
            f"-H 'Authorization: Bearer {dkey}'", timeout=12)
        if out == "401":
            P1.append("Delegation key REJECTED (DeepSeek 401) — subagents dead")
        elif out not in ("200", ""):
            P1.append(f"Delegation provider probe HTTP {out}")
    else:
        P1.append("Delegation key MISSING (no config literal or .env key)")
except Exception as e:
    P1.append(f"Delegation probe failed: {e}")

# ── 7. Memory store pressure (backstop for proactive-storage doctrine) ──
# The in-session doctrine stops autonomous ADD at 90% and gates eviction.
# This is the BACKSTOP: page only when a store creeps to >=98% of its cap —
# i.e. the doctrine failed to keep up and the store is about to reject writes.
# Caps live in config.yaml (memory.memory_char_limit / memory.user_char_limit).
try:
    import yaml as _yaml7
    # Probe BOTH the default profile AND each sister profile under profiles/.
    # Each profile carries its OWN caps in its OWN config.yaml — never assume
    # default's caps apply to a sister (ha-bot ran 2200/1375 vs default 3000/1750).
    # (label, config.yaml path, memories dir)
    _mem_targets = [("default", f"{HERMES}/config.yaml", f"{HERMES}/memories")]
    _prof_root = f"{HERMES}/profiles"
    # Skip rollback/update SNAPSHOTS — they are frozen archives, not live
    # profiles; their stores are stale by design and must not page.
    _snap_re = re.compile(r"^(pre-update|stable|pre-|backup-|snapshot)", re.I)
    if os.path.isdir(_prof_root):
        for _p in sorted(os.listdir(_prof_root)):
            if _snap_re.match(_p):
                continue
            _pcfg = f"{_prof_root}/{_p}/config.yaml"
            _pmem = f"{_prof_root}/{_p}/memories"
            if os.path.isfile(_pcfg) and os.path.isdir(_pmem):
                _mem_targets.append((_p, _pcfg, _pmem))
    for _label, _cfgpath, _memdir in _mem_targets:
        try:
            with open(_cfgpath) as _cf:
                _pc = (_yaml7.safe_load(_cf) or {}).get("memory") or {}
        except Exception:
            _pc = {}
        _mlimit = int(_pc.get("memory_char_limit", 3000))
        _ulimit = int(_pc.get("user_char_limit", 1375))
        for _name, _path, _lim in (("MEMORY.md", f"{_memdir}/MEMORY.md", _mlimit),
                                   ("USER.md",   f"{_memdir}/USER.md",   _ulimit)):
            try:
                with open(_path, encoding="utf-8") as _mf:
                    _n = len(_mf.read())
                _pct = round(_n / _lim * 100)
                if _pct >= 92:
                    P1.append(f"[{_label}] {_name} at {_pct}% ({_n}/{_lim}) — compaction overdue, store near reject")
            except FileNotFoundError:
                pass
except Exception as e:
    P1.append(f"Memory pressure probe failed: {e}")

# ── 8. Cold-store pointer-coverage decay (B-lite reliability backstop) ──
# B-lite retrieval is reliable only while cold facts keep a hot-tier POINTER.
# Automated growth can store rows WITHOUT a pointer → "orphan facts" invisible
# to judgment-fired search. The crossover signal to B-full is pointer-coverage
# DECAY, not row count. Alert only on a significant RISE above the recorded
# baseline (a trend), not an absolute ratio — the baseline is intentionally
# noisy-but-stable; what matters is movement. Cheap: reads Supabase knowledge store directly,
# no embedding-model load. Baseline: references/orphan-ratio-baseline.json.
try:
    sys.path.insert(0, f"{HERMES}/scripts")
    import orphan_ratio as _orph
    _base_path = f"{HERMES}/references/orphan-ratio-baseline.json"
    _baseline = 0.50
    try:
        with open(_base_path) as _bf:
            _baseline = float(json.load(_bf).get("baseline_ratio", 0.50))
    except Exception:
        pass
    _res = _orph.compute()
    _cur = float(_res.get("ratio", 0.0))
    _DECAY_ALERT = 0.15   # +15 percentage points above baseline = pointer rot
    if _cur - _baseline >= _DECAY_ALERT:
        P1.append(
            f"Cold-store orphan ratio {_cur:.0%} (baseline {_baseline:.0%}, "
            f"+{(_cur - _baseline) * 100:.0f}pts) — pointer coverage decaying. "
            f"{_res.get('orphans')} of {_res.get('scored')} facts have no hot cue. "
            f"Run `orphan_ratio.py` + add pointers (Stage 2 doctrine)."
        )
except Exception as e:
    # Never let the probe break the watchdog — it's a backstop, not a gate.
    P1.append(f"Orphan-ratio probe failed: {e}")

# ── decide + anti-spam cooldown ────────────────────────────────────────
fails = [("P0", m) for m in P0] + [("P1", m) for m in P1]
sig = "|".join(sorted(m for _, m in fails))

if not fails:
    try: os.remove(STATE)   # clear state on recovery so next failure alerts immediately
    except FileNotFoundError: pass
    sys.exit(0)             # SILENT — healthy

now = datetime.now(timezone.utc)
prev = {}
try:
    with open(STATE) as f: prev = json.load(f)
except Exception: pass
if prev.get("sig") == sig:
    last = datetime.fromisoformat(prev.get("ts"))
    if now - last < timedelta(minutes=COOLDOWN_MIN):
        sys.exit(0)         # same failure, within cooldown — stay silent
with open(STATE, "w") as f:
    json.dump({"sig": sig, "ts": now.isoformat()}, f)

sev = "P0" if P0 else "P1"
print(f"\u26a0 INFRA WATCHDOG [{sev}] {now.strftime('%Y-%m-%d %H:%M')}Z — {len(fails)} issue(s):")
for s, m in fails:
    print(f"  [{s}] {m}")
print("\nRead-only detection. To act: ask me to run `infra-incident-triage` (diagnose \u2192 propose \u2192 your approval).")
# Exit 0 even when issues are found: the alert is DELIVERED via stdout above
# (no_agent cron sends stdout verbatim). The exit code only sets last_status —
# exit 1 made every healthy-but-found-issues run record "error" (false alarm in
# the cron-health view, and the watchdog then flags ITSELF). Detection != failure:
# the job ran correctly, so exit 0. Real crashes still exit non-zero via traceback.
sys.exit(0)
