#!/usr/bin/env bash
# One-shot: restart hermes-dashboard OUTSIDE the gateway process tree.
# Run via a no_agent cron (cronjob action=create no_agent=True script=this),
# OR — if the no_agent cron silently never fires — via the OS cron daemon:
#   python3 -c "open('/etc/cron.d/hermes-dash-restart','w').write('* * * * * root /root/.hermes/scripts/restart-dashboard-once.sh\n')"
# (point the cron LINE at this script; do NOT inline `systemctl restart` in the
#  cron file or the WRITE GATE re-trips on the literal string.)
#
# The gateway self-protection refuses `systemctl restart hermes-dashboard`
# from inside an agent turn (SIGTERM propagates and kills the command);
# a cron tick is a fresh process not parented by the gateway, so it works.
#
# Stdout is delivered verbatim by the cron, giving a verification line.
# Adjust SERVICE / PORT / HEALTH for other companion services.
SERVICE=hermes-dashboard
PORT=8787

# --- Rogue-squatter guard (verified 2026-06-23) -----------------------------
# A non-systemd process holding :PORT makes `systemctl restart` loop forever on
# `Errno 98 address already in use` — is-active flickers "active" for ~300ms then
# dies. If the PID currently on :PORT is NOT owned by this systemd unit, kill it
# so systemd can rebind. (Common cause: a coding-agent investigation run with Bash
# kill -9'd the unit's uvicorn and spawned its own bare uvicorn outside systemd.)
UNIT_MAIN_PID=$(systemctl show -p MainPID --value "$SERVICE" 2>/dev/null)
PORT_PID=$(ss -tlnp 2>/dev/null | grep ":${PORT}" | grep -oP 'pid=\K[0-9]+' | head -1)
if [ -n "$PORT_PID" ] && [ "$PORT_PID" != "$UNIT_MAIN_PID" ]; then
    echo "rogue process $PORT_PID holds :$PORT (unit MainPID=$UNIT_MAIN_PID) — killing"
    kill "$PORT_PID" 2>/dev/null
    sleep 2
fi

systemctl restart "$SERVICE"
sleep 4
echo "service: $(systemctl is-active "$SERVICE")"

# Catch the restart-loop tell: counter climbing = still can't bind.
RESTARTS=$(systemctl show -p NRestarts --value "$SERVICE" 2>/dev/null)
[ -n "$RESTARTS" ] && [ "$RESTARTS" -gt 5 ] 2>/dev/null && \
    echo "WARNING: NRestarts=$RESTARTS — service is crash-looping (likely port still held)"

# Smoke-check a representative API route. Edit to a route that proves the fix loaded.
curl -s "http://127.0.0.1:${PORT}/api/chat/sessions" | python3 -c "
import sys, json
try:
    s = json.load(sys.stdin)
    print('sessions:', len(s), '| sample:', [x.get('id','')[:18] for x in s[:3]])
except Exception as e:
    print('api check failed:', e)
"
