#!/bin/bash
set -e
exec 1> /root/.hermes/cron/output/restart_dashboard_$(date +%s).log 2>&1
echo "[$(date)] systemctl daemon-reload"
systemctl daemon-reload
echo "[$(date)] systemctl restart hermes-dashboard"
systemctl restart hermes-dashboard
sleep 3
echo "[$(date)] status: $(systemctl is-active hermes-dashboard)"
curl -s -m 5 -o /dev/null -w "[$(date)] health: HTTP %{http_code}\n" http://localhost:8787/api/health
echo "[$(date)] done"