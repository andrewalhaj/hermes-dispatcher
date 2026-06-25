# Quick Reference — Key Files and Commands

## Critical file paths

```
Live standalone:      /root/projects/hermes-webui-new/standalone.html
Server:               /root/projects/hermes-webui-new/server.py
Environment:          /root/projects/hermes-webui-new/.env
Service unit:         /etc/systemd/system/hermes-webui.service
Backups (auto):       /root/projects/hermes-webui-new/standalone.html.bak-*
Feature port plan:    /root/.hermes/references/webui-feature-port-plan.md
Hermes home:          /root/.hermes/
Agent venv python:    /usr/local/lib/hermes-agent/venv/bin/python
```

## Server routes (what the backend exposes)

```
GET  /                         → serves standalone.html with injected __RD_* globals
POST /api/auth/login           → password auth → sets hermes_session cookie
POST /api/auth/logout
GET  /api/auth/status

GET  /api/kanban/board         → full board data (columns + tasks)
PATCH /api/kanban/tasks/{id}   → update task status/fields
POST /api/kanban/tasks         → create task
POST /api/kanban/tasks/{id}/comment
PATCH /api/kanban/tasks/{id}/desc
POST /api/kanban/dispatch      → trigger dispatcher on a task
GET  /api/kanban/events/stream → SSE, live board updates (fingerprints kanban.db ~2s)

GET  /api/memory               → MEMORY.md + USER.md + SOUL.md + AGENTS.md
GET  /api/insights             → stats from state.db + kanban.db
GET  /api/skills               → skill list (name + description)
GET  /api/logs                 → log file tail
GET  /api/galaxy               → 3D memory nodes (622 nodes, 7 tiers, TTL 30s)
GET  /api/swarm                → agent topology (profiles + running state, TTL 15s)
GET  /api/chat                 → chat seed (agents list + last messages)
POST /api/chat/send            → send message (fake SSE, subprocess -Q)
GET  /api/sessions             → session list from state.db
GET  /api/settings             → settings.json
POST /api/settings             → save settings.json
```

## State.db schema (hermes agent sessions)

```sql
-- /root/.hermes/state.db
sessions:  id, title, model, message_count, started_at, ended_at, source, archived
messages:  id, session_id, role, content, active, created_at
```

## Kanban.db schema

```sql
-- /root/.hermes/kanban.db
tasks:        id, title, body, status, priority, assignee, tenant, branch_name, skills, created_at
task_runs:    id, task_id, profile, status, outcome, started_at, summary
task_events:  id, task_id, kind, payload, created_at
task_comments:id, task_id, author, body, created_at
task_links:   parent_id, child_id
```

## Quick health checks

```bash
# Is service up?
systemctl status hermes-webui --no-pager | head -5

# Auth + galaxy test
PW=$(grep HERMES_WEBUI_PASSWORD /root/projects/hermes-webui-new/.env | cut -d= -f2)
curl -s -X POST http://127.0.0.1:8787/api/auth/login \
  -H 'Content-Type: application/json' -d "{\"password\":\"$PW\"}" \
  -c /tmp/hw.txt | python3 -c "import sys,json; print(json.load(sys.stdin))"
curl -sb /tmp/hw.txt http://127.0.0.1:8787/api/galaxy | \
  python3 -c "import sys,json; d=json.load(sys.stdin); print('nodes:', len(d['mem']))"

# JS syntax check after any server.py patch
cd /root/projects/hermes-webui-new
HERMES_HOME=/root/.hermes /usr/local/lib/hermes-agent/venv/bin/python - << 'EOF'
import re, json, base64, gzip, sys
sys.path.insert(0, '.')
import server
raw = open('standalone.html').read()
patched = server._patch_standalone(raw)
scripts = re.findall(r'<script[^>]*>(.*?)</script>', patched, re.DOTALL)
manifest = json.loads(scripts[1])
for k, v in manifest.items():
    if 'javascript' in v.get('mime','') and v.get('compressed'):
        js = gzip.decompress(base64.b64decode(v['data']+'==')).decode('utf-8','replace')
        open('/tmp/_check.js','w').write(js); break
EOF
node --check /tmp/_check.js && echo "✓ JS OK"
```

## Agents on this system

```
Profiles:  default, ha-bot, executor, swarm-worker-a through swarm-worker-p, swarm-verifier
Gateway:   Telegram + Discord (default profile)
HA bot:    HAJarvis profile → separate gateway service
Executor:  executor profile
Swarm:     16 workers (a-p) pointing at Mac Studio llama.cpp (qwen2.5-32b)
```

## Chromium CDP (for screenshots)

```bash
# Start (background)
chromium --headless=new --no-sandbox --disable-gpu \
  --window-size=1400,900 --remote-debugging-port=9223 \
  --remote-allow-origins=* "about:blank" &
sleep 3

# Get WS URL
curl -s http://127.0.0.1:9223/json/list | \
  python3 -c "import sys,json; print(json.load(sys.stdin)[0]['webSocketDebuggerUrl'])"
```

Then use the CDP script in `05-editing-workflow.md`.
