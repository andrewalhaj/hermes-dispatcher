# Hermes WebUI — Claude Design Handoff
*Self-contained spec for a design agent with zero prior context.*

## What this is

The Hermes WebUI is a **full-screen dark dashboard** served at `hermes.andrewskingdom.com` (port 8787). It is a **DC/bundler standalone HTML file** — a self-contained React-like component runtime where all JS is gzip+base64 encoded inside the HTML. There is no separate build step for the design. The served file is `/root/projects/hermes-webui-new/standalone.html`.

**Your job:** Edit the visual design — layout, colors, typography, spacing, component styling — while keeping the data wiring and functional logic intact.

## Read this in order

1. `00-README.md` — this file (start here)
2. `01-architecture.md` — how the file is structured, how to safely edit it
3. `02-design-system.md` — color tokens, typography, spacing, component patterns
4. `03-panels.md` — each panel's layout, elements, and current state
5. `04-feature-gaps.md` — panels/features planned but not yet built
6. `05-editing-workflow.md` — exact safe workflow for making changes

## Golden Rules (never break these)

1. **Read before writing.** Always read the section you're about to change. The standalone is a compiled bundle; blind writes corrupt it.
2. **`node --check` before restart.** After any JS patch, extract the component script and run `node --check`. A bad patch white-screens the UI with no error in logs.
3. **Backup first.** `cp standalone.html standalone.html.bak-$(date +%s)` before touching anything.
4. **Gate restarts.** `systemctl restart hermes-webui` is a write-gate action. Present what changed and wait for explicit "proceed" from Andrew.
5. **Verify in browser, not just curl.** A 200 response doesn't mean the UI rendered. Use the CDP screenshot workflow in `05-editing-workflow.md`.
6. **No layout changes without greenlight.** Color and typography tweaks are low-risk. Structural DOM changes (moving panels, rebuilding nav) need explicit approval.
7. **Don't invent data.** The UI is wired to real backends. Never substitute hardcoded mock values for real API data.

## System summary

- **Live URL:** https://hermes.andrewskingdom.com (Cloudflare tunnel → port 8787)
- **Served file:** `/root/projects/hermes-webui-new/standalone.html` (759KB)
- **Server:** `/root/projects/hermes-webui-new/server.py` (FastAPI + uvicorn, 3186 lines)
- **Service:** `hermes-webui.service` → `WorkingDirectory=/root/projects/hermes-webui-new`
- **Auth:** Password-protected. Password in `/root/projects/hermes-webui-new/.env` as `HERMES_WEBUI_PASSWORD`
- **Chromium:** `/snap/bin/chromium` — use for CDP screenshots (see `05-editing-workflow.md`)
