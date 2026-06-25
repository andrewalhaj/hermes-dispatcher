#!/usr/bin/env python3
"""Infrastructure change watchdog. Runs outside agent context — catches unauthorized changes."""
import os, subprocess, json, hashlib, sys
from datetime import datetime

ALERT = False
MSG = []

# 1. Systemd units
SNAPSHOT = "/tmp/infra-watchdog-systemd.hash"
units = subprocess.run("find /etc/systemd/system -name '*.service' -exec cat {} + 2>/dev/null | sha256sum", 
                       shell=True, capture_output=True, text=True).stdout.strip()
if os.path.exists(SNAPSHOT):
    prev = open(SNAPSHOT).read().strip()
    if units and units != prev:
        changed = subprocess.run(f"find /etc/systemd/system -name '*.service' -newer {SNAPSHOT}",
                                 shell=True, capture_output=True, text=True).stdout.strip()
        MSG.append(f"SYSTEMD UNIT CHANGED: {changed}")
        ALERT = True

# 2. Docker container restarts (use STABLE restart signals, not the ticking
#    'Up N minutes' status string which changes every poll and spams alerts)
RESTART_SNAPSHOT = "/tmp/infra-watchdog-containers.json"
insp = subprocess.run(
    "docker ps -q | xargs -r docker inspect "
    "--format '{{.Name}}={{.RestartCount}}|{{.State.StartedAt}}'",
    shell=True, capture_output=True, text=True).stdout.strip()
curr_ctrs = {}
for line in insp.split('\n'):
    if '=' in line:
        name, sig = line.split('=', 1)
        curr_ctrs[name.lstrip('/')] = sig   # sig = "restartcount|startedat"
if os.path.exists(RESTART_SNAPSHOT):
    try:
        prev_ctrs = json.load(open(RESTART_SNAPSHOT))
        for name, sig in curr_ctrs.items():
            if name in prev_ctrs and prev_ctrs[name] != sig:
                pc_prev = prev_ctrs[name].split('|')[0]
                pc_curr = sig.split('|')[0]
                MSG.append(f"CONTAINER RESTART: {name} (restartcount {pc_prev}->{pc_curr})")
                ALERT = True
    except: pass

# 3. Hermes config hash
CONFIG_HASH = "/tmp/infra-watchdog-config.hash"
h = hashlib.sha256(open("/root/.hermes/config.yaml","rb").read()).hexdigest()
if os.path.exists(CONFIG_HASH):
    if h != open(CONFIG_HASH).read().strip():
        MSG.append("HERMES CONFIG CHANGED")
        ALERT = True

# Update snapshots
open(SNAPSHOT, 'w').write(units + '\n')
open(RESTART_SNAPSHOT, 'w').write(json.dumps(curr_ctrs))
open(CONFIG_HASH, 'w').write(h + '\n')

# Output
if ALERT:
    msg = f"INFRA WATCHDOG — {datetime.now().strftime('%H:%M:%S UTC')}\n" + "=" * 40 + "\n"
    for m in MSG:
        msg += m + '\n'
    print(msg.strip())
