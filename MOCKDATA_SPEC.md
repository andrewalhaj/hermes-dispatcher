# Task: Kill the LAST mock data in the Dispatcher Dashboard Overview panel + sidebar

You are working in `/root/hermes-dispatcher` on branch `feat/live-backend-wiring` (already
checked out). The dashboard is a Vite+React+TS app in `app/` with a FastAPI backend
(`server.py` + `routes/*.py`) serving on :8787. Honest-data rule: **every visible tile shows
REAL data or it is REMOVED. No fabricated metrics. No fake agent names.**

Real data already verified live:
- `/api/overview` returns `{kanban_summary, active_agents, system:{cpu_pct,mem_pct,disk_pct}, recent_activity, sparkline[24]}`.
- `/api/agents` returns a list of real profiles with `{name, role, model, color, status, today, completed, total, success, lastActive}`. Real profiles are `coder, coder-b..coder-l, executor, ha-bot, swarm-worker-*, swarm-synthesizer, swarm-verifier`. NOT `rvc-runner/atlas-etl/npc-builder/ops-bot/w-okada-01` — those are FAKE fixtures to delete.
- kanban DB at `/root/.hermes/kanban.db`. Tables: `tasks(assignee,status,completed_at,...)`, `task_runs(profile,started_at,ended_at,outcome,...)`. Real total task count ~53. There is NO `sqlite3` CLI; use Python `sqlite3` opened read-only `file:...?mode=ro`.

This host is a Mac **mini** with NO GPU telemetry. Do not invent GPU/VRAM/"Mac Studio".

## Part A — Backend: extend `routes/overview.py` `/api/overview`

Add these fields to the returned dict (keep all existing fields intact):

1. `total_tasks`: `SELECT COUNT(*) FROM tasks` (int).

2. `agent_breakdown`: top agents by task count. Query
   `SELECT assignee, COUNT(*) FROM tasks WHERE assignee IS NOT NULL GROUP BY assignee ORDER BY COUNT(*) DESC`.
   Return a list of up to 6 `{name, count}` (collapse the remaining tail into a single
   `{name: "other", count: <sum>}` row if there are more than 6 assignees, so the donut total
   equals the real task total). Do NOT assign colors in the backend — the frontend palette handles color.

3. `agent_activity`: real per-agent hourly heatmap for the last 24h. For the same top (up to 5)
   agents by total task count, compute 24 hourly buckets of `task_runs` started in each hour:
   `SELECT COUNT(*) FROM task_runs WHERE profile=? AND started_at >= ? AND started_at < ?` for
   each of the last 24 hourly windows (now-23h .. now, matching the existing sparkline bucketing).
   Return `[{name, hours:[c0..c23]}, ...]`. If a profile has zero runs across all 24 buckets it
   may still be included (all-zero row is fine — frontend renders it dim).

4. `agent_memory`: real resident memory per running agent process. Walk processes with psutil
   (`psutil.process_iter(['pid','cmdline','memory_info'])`). Identify Hermes agent processes by
   cmdline containing `hermes` (e.g. `hermes_cli.main`, ` hermes -p <profile>`, `--profile <name>`,
   `gateway run`). For each, derive a short label: the `-p <profile>` / `--profile <profile>` value
   if present, else `gateway` for the gateway process, else the script basename. Sum RSS per label.
   Return a list of `{name, rss_mb:int}` sorted by rss_mb desc, capped at 6. Wrap the whole psutil
   walk in try/except returning `[]` on failure — never crash the endpoint. (Empty list is OK; the
   frontend hides the tile when empty.)

Keep the existing top-level try/except behavior: on DB failure the new fields default to
`total_tasks:0, agent_breakdown:[], agent_activity:[], agent_memory:[]` (agent_memory comes from
psutil not the DB, so compute it outside the DB try/except).

## Part B — Frontend Overview

### `app/src/data/overview.ts`
- DELETE the hardcoded `AGENTS` fixture array (rvc-runner/atlas-etl/etc).
- Add a palette constant (reuse colors like `#2dd4bf, #5aa2f0, #9b8cff, #4ade80, #f0a85a, #f06a9b`).
- `buildOverview` must derive `breakdown`, `ringSegs`, `ringTotal`, `heatRows`, and the KPI/stat
  "Tasks Run" values from NEW opts fields passed in: `agentBreakdown: {name,count}[]`,
  `agentActivity: {name,hours:number[]}[]`, `totalTasks: number`. Assign palette color by index.
  - `ringTotal` and the "Tasks Run" KPI/stat value = `totalTasks` (real), formatted with the
    existing `fmt`. If `agentBreakdown` is empty, render an empty ring (no segments) and `ringTotal`
    still = totalTasks.
  - `heatRows` cells come from `agentActivity[i].hours` normalized to 0..4 levels per row using each
    row's own max (reuse the existing alpha-level + color approach). Remove the synthetic
    `Math.sin/Math.cos` fallback entirely — if `agentActivity` is empty, `heatRows` is `[]`.
- Remove now-dead fields/fixtures. Fix the other stat tiles that show invented constants:
  "Tenants" value `'3'` and "Memory Items" `'5.0k'` and "Day Streak" `'7'` are fake — for any stat
  you cannot source from real data passed via opts, REMOVE that stat tile rather than ship a fake
  number. Keep "Tasks Run" (real total) and "Active Sessions" (real active_agents). Drop "Tenants",
  "Memory Items", and the "Day Streak" KPI unless you can wire them to real data cheaply (you can't —
  drop them).

### `app/src/components/panels/Overview.tsx`
- Pass the new live fields into `buildOverview` (read `live.total_tasks`, `live.agent_breakdown`,
  `live.agent_activity` from the overview hook — extend the hook below).
- Agent Breakdown donut + legend: render from real breakdown. The info-drawer "Busiest" stat should
  read the real busiest agent name.
- Heatmap: render `ov.heatRows`. If `heatRows` is empty, hide the entire heatmap card (don't render
  an empty box). Remove the hardcoded "Peak hour: 14:00" stat in the info drawer (compute from data
  or drop the stat).
- **System Monitor**: remove the Mac Studio/Mac Mini machine switcher entirely (single host).
  Replace the `useSystemMonitor` hook so metrics come from REAL `/api/overview` `system` values
  (cpu_pct, mem_pct, disk_pct) accumulated into rolling buffers on each 10s poll. Show CPU%, Memory%,
  Disk% only. DROP GPU, VRAM, and Network rows (no telemetry source). Relabel the box header host as
  the real hostname (use `os` hostname via a tiny backend field if easy, else just "Local host" — do
  NOT say "Mac Studio").
- **Per-Agent Memory**: render from real `live.agent_memory` (`{name, rss_mb}`). If the list is empty,
  hide the Per-Agent Memory subsection. Remove the fake CHAT_AGENTS-based memory rows.
- **System Memory** sparkline: drive from the real mem_pct buffer (relabel to "Memory %" or keep "GB"
  only if you actually compute GB from psutil — simpler: show mem% to stay honest).
- **Agent Swarm** canvas: keep as ambient decoration, but in its info drawer REMOVE the fake
  `Agents: 5` and `Mode: Emergent`-as-stat — or set Agents to the real running count. Keep the canvas
  itself (decorative is allowed).

### `app/src/components/overview/useSystemMonitor.ts`
Rewrite to consume real system metrics. Simplest correct design: accept the latest
`{cpu_pct, mem_pct, disk_pct}` (from the overview hook / a fetch) and maintain short rolling buffers
(length ~14) updated each poll, producing sparkline paths for CPU/Memory/Disk only. Remove studio/mini
machines, GPU, VRAM, Network, and the random `seed`/`advance` synthetic generators. Per-agent memory
should come from the overview `agent_memory` field, not synthetic CHAT_AGENTS data.

### `app/src/components/overview/useOverviewData.ts`
Extend `OverviewApiData` + `EMPTY` to include `total_tasks:number`, `agent_breakdown:{name:string,count:number}[]`,
`agent_activity:{name:string,hours:number[]}[]`, `agent_memory:{name:string,rss_mb:number}[]`. Default
all to empty/0.

## Part C — Sidebar Agents quick-list (`app/src/components/Shell.tsx` + `app/src/data/agents.ts`)
- The left-rail "Agents" list currently uses `agentRows()` built from the FAKE `CHAT_AGENTS`
  fixture. Replace it with a live fetch of `/api/agents`, showing the top 5 real profiles by recent
  activity (sort by `today` desc then `total` desc), mapping status -> badge:
  `busy`->`RUN` (accent), `online`->`LIVE` (green), else `IDLE` (grey). Use each agent's real `color`
  and `name`. If the fetch fails, render nothing (no fake fallback). Implement as a small hook
  (e.g. `useAgentRows` in `app/src/data/fleet.ts` or inline in Shell) — `/api/agents` already exists
  and `fleet.ts` already fetches it.
- It's fine to keep `CHAT_AGENTS` if the Chat panel still needs it, but the sidebar must NOT use fake
  names. If `CHAT_AGENTS` is only used by the sidebar, you may remove the fake worker entries.

## Part D — Build, restart, verify, commit
1. `cd app && npm run build` must be GREEN (tsc + vite). Fix all type errors.
2. Restart live server:
   `kill $(lsof -ti :8787) 2>/dev/null; cd /root/hermes-dispatcher && HERMES_HOME=/root/.hermes nohup .venv/bin/uvicorn server:app --host 0.0.0.0 --port 8787 >/tmp/uvicorn.log 2>&1 &`
   then `sleep 3`.
3. Verify with curl: `curl -s localhost:8787/api/overview | python3 -m json.tool` — confirm
   `total_tasks`, `agent_breakdown` (real profile names, no rvc-runner/atlas-etl), `agent_activity`,
   `agent_memory` all present and real. `curl -s localhost:8787/api/agents | head -c 500`.
4. Grep the built/source to confirm no fixtures remain:
   `grep -rn "rvc-runner\|atlas-etl\|npc-builder\|ops-bot\|w-okada-01\|Mac Studio" app/src` must
   return nothing (CHAT_AGENTS removed or sanitized).
5. Commit to the SAME branch (do NOT create a new branch, do NOT touch master, do NOT merge):
   `git add -A && git commit -m "feat(overview): wire Overview panel + sidebar to real data, remove last mock fixtures"`
   then `git push`. 
6. Print the commit SHA (`git rev-parse HEAD`) at the very end of your output prefixed with
   `COMMIT_SHA=`.

Report concisely what you changed per file and the final commit SHA.
