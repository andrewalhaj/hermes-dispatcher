# WebUI Claude-Design Port — Session State (2026-06-18)

## Goal
Make the live Hermes WebUI match the "Claude Design" handoff EXACTLY, panel-by-panel,
with the Memory Galaxy wired to the REAL memory system. Two prior sessions shipped only
the mission-control SKIN (palette/fonts/starfield) — the user's complaints ("Overview tab
is broken, Memory Galaxy looks terrible, EXACTLY like the design") were PANEL-LEVEL gaps.

## Root cause of prior failures
Skin ≠ panels. The design is a panel-level rebuild. Live app had:
- Overview trapped in the 320px SIDEBAR (cramped/clipped), MISSING donut + heatmap.
- Memory Galaxy: weak 3-tier engine (MEMORY/USER/SOUL), flat dots, sidebar-sized.
- Agents panel: DID NOT EXIST.

## What was built (all in STAGING /root/projects/hermes-webui-staging/static/)
1. **Memory Galaxy** — replaced engine (panels.js ~6166+). 6 tiers wired to REAL data:
   Notes→MEMORY.md, User Profile→USER.md, Agent Soul→SOUL.md, Project Context→AGENTS.md,
   Knowledge→/api/skills, Conversations→/api/sessions. Full-width #mainGalaxy in <main>
   (was sidebar). Nebula + depth-sort + neighbour links + persistent labels + inspect card
   + background starfield. CDP-verified: 70 mem, 6 tiers, pixel density matches design ref.
2. **Overview** — full-width #mainOverview (moved out of sidebar). Added AGENT BREAKDOWN
   donut (real /api/insights models) + 24h ACTIVITY HEATMAP (real activity_by_hour).
   fmt() handles k/M/B. CDP-verified: all 4 sections, full-width.
3. **Agents** — NEW full-width #mainAgents panel + rail nav btn + tab_agents i18n (13 locales).
   Success-ring cards + 5-card summary strip, fed by real model usage (/api/insights +
   /api/gateway/status). CDP-verified 9.2/10.

## Wiring changes
- switchPanel: added 'overview','agents' to showing- list; galaxy-on teardown on leave;
  loadAgents() call. CSS: #mainOverview/#mainAgents visibility + chat-default :not() chain
  extended (CRITICAL — must include :not(.showing-overview):not(.showing-agents) or chat bleeds).
  Sidebar hidden via :has() for overview/agents (full-bleed dashboards).

## Verification harness (still running)
- chromium headless CDP :9222, design-serve :8799, staging static :8788.
- Drivers in /tmp/: verify_galaxy.py, verify_overview.py, verify_agents.py, verify_panel.py.
- Screenshots: /tmp/staging_{galaxy2,overview,agents}.png.

## Cutover (GATED — awaiting greenlight)
Staging static/index.html keeps __WEBUI_VERSION__ placeholders (17), zero ?v=staging — clean.
Diff vs live: index.html +22/-12, panels.js +360/-152, style.css +109/-13, i18n.js +13/-0.
boot.js/ui.js identical. Plan: backup live static → rsync staging static/{index.html,panels.js,
style.css,i18n.js} → live → systemctl restart hermes-webui (BLIPS LIVE CHAT ~5s) → hard-refresh.
mission-control is ALREADY the default skin (api/config.py line 6890).

## DO NOT REDO without grepping live first
After restart, verify: grep -c '_GALAXY_TIERS\|ov-donut\|loadAgents' live panels.js.
