#!/usr/bin/env bash
# One-shot: restart hermes-dashboard outside the gateway process tree
# Runs via no_agent cron so it's not a child of the gateway.
systemctl restart hermes-dashboard
sleep 4
systemctl is-active hermes-dashboard
curl -s http://127.0.0.1:8787/api/chat/sessions | python3 -c "
import sys,json
s=json.load(sys.stdin)
if s:
    for r in s[:3]: print(r['id'][:20], r.get('title','')[:45])
else:
    print('(no telegram sessions)')
"
