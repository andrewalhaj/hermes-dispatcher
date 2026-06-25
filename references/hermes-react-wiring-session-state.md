# Hermes-React WebUI Wiring — Session State (2026-06-18)

## Task
Wire `hermes-react/` (Vite+React+TS+Tailwind v4) to the REAL backend WITHOUT changing visual design.
Source: `/root/.hermes/webui/attachments/8ee93b9446a6/Hermes WebUI Design (1)/hermes-react`
Live backend: http://127.0.0.1:8787 (hermes-webui.service). Auth: POST /api/auth/login {password} → hermes_session cookie. Password in service env HERMES_WEBUI_PASSWORD.

## Files to edit (preserve types.ts shapes)
- `src/lib/mockData.ts` → real API calls (TASKS, AGENTS, MEMORIES, LOGS)
- `src/lib/store.tsx` → real actions (moveTask, runDispatcher) + SSE
- panels read directly: Logs.tsx(LOGS), MemoryGalaxy.tsx(MEMORIES), Insights.tsx(inline mock), Skills.tsx(inline mock)
- via useHermes(): Sidebar, Agents, Settings, Kanban, Overview, Chat

## CONFIRMED API CONTRACTS (probed live)
- **GET /api/kanban/board** → {columns:[{name,tasks[]}], tenants[], assignees[], latest_event_id, changed}
  task: {id,title,body,assignee,status,priority,created_by,created_at,started_at,completed_at,tenant,branch_name,result,skills(null|csv),link_counts:{parents,children},comment_count,goal_mode,...}
  columns: triage,todo,ready,running,blocked,done
- **GET /api/kanban/tasks/{id}** → {task,comments:[{author,body,created_at}],events:[{kind,payload,created_at}],runs:[{id,profile,status,...}],links:{parents[],children[]},read_only}
  (events use `kind` not `type`; comments use `body`+`created_at`)
- **POST /api/kanban/tasks/{id}** or /bulk → status change. Running ONLY via dispatch (claim_task). Bridge rejects raw running write w/ 400.
- **POST /api/kanban/dispatch** → runDispatcher target
- **GET /api/kanban/events/stream** → SSE live updates (diff by latest_event_id cursor)
- **GET /api/memory** → {memory,user,soul,project_context, *_mtime, external_notes_enabled} (4 text blobs)
- **GET /api/sessions** → {sessions:[{title,model,message_count,updated_at,...}]} (Conversations tier)
- **GET /api/skills** → {skills:[...]} (Knowledge tier)
- **GET /api/insights?period=30** → {total_sessions,total_messages,total_tokens,total_cost,total_input_tokens,total_output_tokens,models:[{model,sessions,...}],daily_tokens[],activity_by_day[{day,sessions}],activity_by_hour[{hour,sessions}],period_days}
- **GET /api/logs** → {file,tail,lines:[str],truncated,total_bytes,mtime,hint} (lines are RAW strings, parse to LogEntry)
- **GET /api/settings** → flat dict: theme,skin,language,bot_name,default_model,default_workspace,api_redact_enabled,check_for_updates,notifications_enabled,session_endless_scroll,... POST to save.
- **GET /api/models** → {active_provider,default_model,configured_model_badges,groups,aliases}
- **GET /api/health/agent** → {alive,details:{gateway_state,active_agents,platform_count},...}

## GALAXY pos projection (PROVEN — port from static/panels.js:6314-6395)
6 tiers: notes←memory, profile←user, soul←soul(split by heading), context←project_context, facts←skills, convos←sessions.
Tier centers + seeded gas() jitter → pos[3]. importance from len+keywords, recall from char variety, ageDays from mtime.
React TIER_META centers differ slightly (theme.ts) — use theme.ts centers, keep the jitter algo.

## Build status
- [ ] npm install (check version issues)
- [ ] wire mockData.ts (async loaders)
- [ ] wire store.tsx (actions + SSE)
- [ ] panels: Logs, MemoryGalaxy, Insights, Skills, Settings, Agents
- [ ] production checklist: a11y, loading/error, auth, i18n
- [ ] DON'T add colors — all via --ac + index.css tokens

## DELEGATION LESSON (2026-06-18)
Delegated 4 panel rewrites to Mac Studio (qwen2.5-32b) — DISASTER. 3 timed out (900s), 1 "completed" with mangled JSX (boxShadow as prop, broken .map). Corrupted Logs/Skills/Settings/Insights. Restored from attachment originals. TSX fidelity authoring MUST stay on the main model (Sonnet) — Studio mangles JSX. Author directly.

## STATUS: WIRING COMPLETE (2026-06-18)
All panels wired to real backend + verified via CDP on live data:
- Overview: 569 sessions, 1 tenant, 28 memory, real status bars ✓
- Kanban: 20 real cards, P8 priorities, dispatcher contract ✓
- Galaxy: 86 memories, 6 tiers, ErrorBoundary for WebGL ✓ (headless has no GPU; works w/ real browser)
- Insights: 569 sessions/13.7k msgs/112.1M tokens/$667 ✓
- Agents/Logs/Skills/Settings: real data ✓
Build: npm run build exit 0. tsc -b exit 0. No color drift (only theme.ts palette + #1c1404 accent-text).
New files: src/lib/api.ts, src/lib/useAsync.ts, src/components/Login.tsx, src/components/ErrorBoundary.tsx
Auth gate in App.tsx (Login on 401). CSRF via __HERMES_CONFIG__ in index.html.
Working dir: /root/projects/hermes-react. Dev: vite proxy /api → :8787.

## Deploy target
TBD — likely separate port or replace static/. Confirm with user before any cutover (WRITE GATE).
